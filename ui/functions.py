import re
from datetime import datetime, timedelta
from typing import Tuple, Dict, Union, Callable

from orm.db import PilgramORMDatabase
from pilgram.classes import Player, AdventureContainer, Guild, TOWN_ZONE
from pilgram.generics import PilgramDatabase, AlreadyExists
from pilgram.globals import ContentMeta, PLAYER_NAME_REGEX, GUILD_NAME_REGEX, POSITIVE_INTEGER_REGEX, DESCRIPTION_REGEX
from ui.strings import Strings, MONEY
from ui.utils import UserContext, InterpreterFunctionWrapper as IFW, RegexWithErrorMessage as RWE


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def check_board(context: UserContext) -> str:
    zones = db().get_all_zones()
    return Strings.check_board + "\n".join(f"Zone {x.zone_id} - *{x.zone_name}* (lv. {x.level})" for x in zones)


def check_current_quest(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        try:
            quest = db().get_player_current_quest(player)
            if quest is None:
                return Strings.not_on_a_quest
            return str(quest)
        except KeyError as e:
            return f"Fatal error: {e}"
    except KeyError:
        return Strings.no_character_yet


def check_zone(context: UserContext, zone_id_str: int) -> str:
    try:
        zone = db().get_zone(int(zone_id_str))
        return str(zone)
    except KeyError:
        return Strings.zone_does_not_exist


def check_town(context: UserContext) -> str:
    return str(TOWN_ZONE)


def check_self(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        return str(player)
    except KeyError:
        return Strings.no_character_yet


def check_player(context: UserContext, player_name: str) -> str:
    try:
        player = db().get_player_data(db().get_player_id_from_name(player_name))
        return str(player)
    except KeyError:
        return Strings.named_object_not_exist.format(obj="player", name=player_name)


def check_guild(context: UserContext, guild_name: str) -> str:
    try:
        guild = db().get_guild(db().get_guild_id_from_name(guild_name))
        return str(guild)
    except KeyError:
        return Strings.named_object_not_exist.format(obj="guild", name=guild_name)


def check_prices(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        result: str = f"Gear upgrade: {player.get_gear_upgrade_required_money()} {MONEY}\nHome upgrade: {player.get_home_upgrade_required_money()} {MONEY}"
        if player.guild:
            result += f"\nGuild upgrade: {player.guild.get_upgrade_required_money()} {MONEY}"
        result += f"\n\nCreate guild: {ContentMeta.get('guilds.creation_cost')} {MONEY}\nModify: {ContentMeta.get('modify_cost')} {MONEY}"
        return result
    except KeyError:
        return Strings.no_character_yet


def check_my_guild(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.guild:
            return str(player.guild)
        else:
            return Strings.not_in_a_guild
    except KeyError:
        return Strings.no_character_yet


def check_guild_mates(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if not player.guild:
            return Strings.not_in_a_guild
        members = db().get_guild_members_data(player.guild)
        return Strings.here_are_your_mates.format(num=len(members)) + "\n".join(f"{name} | {level}" for name, level in members)
    except KeyError:
        return Strings.no_character_yet


def start_character_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        return Strings.character_already_created.format(name=player.name)
    except KeyError:
        context.start_process("character creation")
        return context.get_process_prompt(USER_PROCESSES)


def process_get_character_name(context: UserContext, user_input) -> str:
    if not re.match(PLAYER_NAME_REGEX, user_input):
        return Strings.player_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_character_description(context: UserContext, user_input) -> str:
    if not re.match(DESCRIPTION_REGEX, user_input):
        return Strings.description_validation_error
    player = Player.create_default(
        context.get("id"), context.get("name"), user_input
    )
    try:
        db().add_player(player)
        context.end_process()
        return Strings.welcome_to_the_world
    except AlreadyExists:
        context.end_process()
        return Strings.name_object_already_exists.format(obj="character", name=player.name)


def start_guild_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if db().get_owned_guild(player):
            return Strings.guild_already_created
        creation_cost = ContentMeta.get("guilds.creation_cost")
        if player.money < creation_cost:
            return Strings.not_enough_money.format(amount=creation_cost - player.money)
        context.start_process("guild creation")
        return context.get_process_prompt(USER_PROCESSES)
    except KeyError:
        return Strings.no_character_yet


def process_get_guild_name(context: UserContext, user_input) -> str:
    if not re.match(GUILD_NAME_REGEX, user_input):
        return Strings.guild_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_guild_description(context: UserContext, user_input) -> str:
    if not re.match(DESCRIPTION_REGEX, user_input):
        return Strings.description_validation_error
    player = db().get_player_data(context.get("id"))
    guild = Guild.create_default(player, context.get("name"), user_input)
    db().add_guild(guild)
    guild = db().get_owned_guild(player)
    player.guild = guild
    player.money -= ContentMeta.get("guilds.creation_cost")
    try:
        db().update_player_data(player)
        context.end_process()
        return Strings.guild_creation_success.format(name=guild.name)
    except AlreadyExists:
        context.end_process()
        return Strings.name_object_already_exists.format(obj="guild", name=player.name)


def upgrade(context: UserContext, obj: str = "gear") -> str:
    try:
        player = db().get_player_data(context.get("id"))
        price: int = {
            "gear": player.get_gear_upgrade_required_money,
            "home": player.get_home_upgrade_required_money,
        }.get(obj)()
        if player.money < price:
            return Strings.not_enough_money.format(amount=price-player.money)
        {
            "gear": player.upgrade_gear,
            "home": player.upgrade_home
        }.get(obj)()
        db().update_player_data(player)
        return Strings.upgrade_successful.format(obj=obj, paid=price)
    except KeyError:
        return Strings.no_character_yet


def upgrade_guild(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        guild = db().get_owned_guild(player)
        if not guild:
            return Strings.no_guild_yet
        if guild.level == ContentMeta.get("guilds.max_level"):
            return Strings.guild_already_maxed
        price = guild.get_upgrade_required_money()
        if player.money < price:
            return Strings.not_enough_money
        guild.upgrade()
        db().update_guild(guild)
        db().update_player_data(player)
        return Strings.upgrade_successful.format(obj="guild", paid=price)
    except KeyError:
        return Strings.no_character_yet


def modify_player(context: UserContext, user_input: str, target: str = "name") -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.money < ContentMeta.get("modify_cost"):
            return Strings.not_enough_money
        player.__dict__[target] = user_input
        player.money -= ContentMeta.get("modify_cost")
        db().update_player_data(player)
        return Strings.obj_attr_modified.format(obj="character", attr=target)
    except KeyError:
        return Strings.no_character_yet


def modify_guild(context: UserContext, user_input: str, target: str = "name") -> str:
    try:
        player = db().get_player_data(context.get("id"))
        guild = db().get_owned_guild(player)
        if not guild:
            return Strings.guild_not_owned
        if player.money < ContentMeta.get("modify_cost"):
            return Strings.not_enough_money
        guild.__dict__[target] = user_input
        db().update_guild(guild)
        player.money -= ContentMeta.get("modify_cost")
        db().update_player_data(player)
        return Strings.obj_attr_modified.format(obj="guild", attr=target)
    except KeyError:
        return Strings.no_character_yet


def join_guild(context: UserContext, guild_name: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        guild = db().get_guild_from_name(guild_name)
        if not guild:
            return Strings.named_object_not_exist.format(obj="guild", name=guild_name)
        members: int = db().get_guild_members_number(guild)
        if not guild.can_add_member(members):
            return Strings.guild_is_full
        player.guild = guild
        db().update_player_data(player)
        context.set_event("guild joined", {"player": player, "guild": guild})
        return Strings.guild_join_success.format(guild=guild_name)
    except KeyError:
        return Strings.no_character_yet


def embark_on_quest(context: UserContext, zone_id_str: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
    except KeyError:
        return Strings.no_character_yet
    if db().is_player_on_a_quest(player):
        return Strings.already_on_a_quest
    try:
        zone = db().get_zone(int(zone_id_str))
    except KeyError:
        return Strings.zone_does_not_exist
    if player.level < zone.level:
        return Strings.level_too_low.format(lv=zone.level)
    quest = db().get_next_quest(zone, player)
    adventure_container = AdventureContainer(player, quest, datetime.now() + quest.get_duration())
    db().update_quest_progress(adventure_container)
    return Strings.quest_embark.format(name=quest.name, descr=quest.description)


def kick(context: UserContext, player_name: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        guild = db().get_owned_guild(player)
        if not guild:
            return Strings.guild_not_owned
        target = db().get_player_from_name(player_name)
        if not target:
            return Strings.named_object_not_exist.format(obj="Player", name=player_name)
        if target.guild != guild:
            return Strings.player_not_in_own_guild.format(name=player_name)
        target.guild = None
        db().update_player_data(target)
        context.set_event("player kicked", {"player": target, "guild": guild})
        return Strings.player_kicked_successfully.format(name=player_name, guild=guild.name)
    except KeyError:
        return Strings.no_character_yet


def donate(context: UserContext, recipient_name: str, amount_str: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        amount: int = int(amount_str)
        if amount <= 0:
            return Strings.invalid_money_amount
        if player.money < amount:
            return Strings.not_enough_money
        recipient = db().get_player_from_name(recipient_name)
        if not recipient:
            return Strings.named_object_not_exist.format(obj="Player", name=recipient_name)
        # update money for both player and save data to the database
        recipient.money += amount
        db().update_player_data(recipient)
        player.money -= amount
        db().update_player_data(player)
        # use context to communicate to the external interface that a notification should be sent to the recipient
        context.set_event("donation", {"amount": amount, "donor": player, "recipient": recipient})
        return Strings.donation_successful.format(amm=amount_str, rec=recipient_name)
    except KeyError:
        return Strings.no_character_yet


def rank_guilds(context: UserContext) -> str:
    result = "Here are the top guilds (guild | prestige):\n\n"
    guilds = db().rank_top_guilds()
    for guild in guilds:
        result += f"{guild[0]} | {guild[1]}\n"
    return result


def set_last_update(context: UserContext, delta: Union[timedelta, None] = None, msg: str = "default", cost: Union[int, None] = None) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if cost and player.money < cost:
            return Strings.not_enough_money.format(amount=cost-player.money)
        try:
            adventure_container = db().get_player_adventure_container(player)
            db().update_quest_progress(adventure_container, last_update=(datetime.now() + timedelta(days=365)) if delta else datetime.now())
            if cost:
                player.money -= cost
                db().update_player_data(player)
                return msg + "\n\n" + Strings.you_paid.format(paid=cost)
            return msg
        except KeyError:
            return "Fatal error: adventure container not found"
    except KeyError:
        return Strings.no_character_yet


USER_COMMANDS: Dict[str, Union[str, IFW, dict]] = {
    "check": {
        "board": IFW(None, check_board, "Shows the quest board."),
        "quest": IFW(None, check_current_quest, "Shows the current quest name & objective (if you are on a quest)."),
        "town": IFW(None, check_town, f"Shows a description of {ContentMeta.get('world.city.name')}."),
        "zone": IFW([RWE("zone number", POSITIVE_INTEGER_REGEX, Strings.zone_number_error)], check_zone, "Shows a description of the given zone."),
        "guild": IFW([RWE("guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], check_guild, "Shows the guild with the given name."),
        "self": IFW(None, check_self, "Shows your own stats."),
        "player": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], check_player, "Shows player stats."),
        "prices": IFW(None, check_prices, "Shows all the prices."),
        "my": {
            "guild": IFW(None, check_my_guild, "Shows your own guild.")
        },
        "mates": IFW(None, check_guild_mates, "Shows your guild mates")
    },
    "create": {
        "character": IFW(None, start_character_creation, "Create your character."),
        "guild": IFW(None, start_guild_creation, f"Create your own Guild (cost: {ContentMeta.get('guilds.creation_cost')} {MONEY}).")
    },
    "upgrade": {
        "gear": IFW(None, upgrade, "Upgrade your gear.", default_args={"obj": "gear"}),
        "home": IFW(None, upgrade, "Upgrade your home.", default_args={"obj": "home"}),
        "guild": IFW(None, upgrade_guild, "Upgrade your guild.")
    },
    "modify": {
        "character": {
            "name": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], modify_player, f"Modify your character's name for a price ({ContentMeta.get('modify_cost')} {MONEY}).", default_args={"target": "name"}),
            "description": IFW([RWE("player description", DESCRIPTION_REGEX, Strings.description_validation_error)], modify_player, f"Modify your character's description for a price ({ContentMeta.get('modify_cost')} {MONEY}).", default_args={"target": "description"})
        },
        "guild": {
            "name": IFW([RWE("guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], modify_guild, f"Modify your guild's name for a price ({ContentMeta.get('modify_cost')} {MONEY}).", default_args={"target": "name"}),
            "description": IFW([RWE("guild description", DESCRIPTION_REGEX, Strings.description_validation_error)], modify_guild, f"Modify your guild's description for a price ({ContentMeta.get('modify_cost')} {MONEY}).", default_args={"target": "description"})
        }
    },
    "join": IFW([RWE("guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], join_guild, "Join the guild with the given name."),
    "embark": IFW([RWE("zone number", POSITIVE_INTEGER_REGEX, Strings.zone_number_error)], embark_on_quest, "Starts a quest in specified zone."),
    "kick": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], kick, "Kicks specified player from your own guild."),
    "donate": IFW([RWE("recipient", PLAYER_NAME_REGEX, Strings.player_name_validation_error), RWE("amount", POSITIVE_INTEGER_REGEX, Strings.invalid_money_amount)], donate, "donates the specified amount of money to the recipient."),
    "rank": {
        "guilds": IFW(None, rank_guilds, "Shows the top 20 guilds, ranked based on their prestige.")
    },
    "retire": IFW(None, set_last_update, f"Take a 1 year vacation (pauses the game for 1 year) (cost: 100 {MONEY})", default_args={"delta": timedelta(days=365), "msg": Strings.you_retired, "cost": 100}),
    "back": {
        "to": {
            "work": IFW(None, set_last_update, "Come back from your vacation", default_args={"delta": None, "msg": Strings.you_came_back})
        }
    }
}

USER_PROCESSES: Dict[str, Tuple[Tuple[str, Callable], ...]] = {
    "character creation": (
        (Strings.character_creation_get_name, process_get_character_name),
        (Strings.character_creation_get_description, process_get_character_description)
    ),
    "guild creation": (
        (Strings.guild_creation_get_name, process_get_guild_name),
        (Strings.guild_creation_get_description, process_get_guild_description)
    )
}
