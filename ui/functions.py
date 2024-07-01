import logging
import re
from copy import copy
from datetime import datetime, timedelta
from typing import Tuple, Dict, Union, Callable, Type, List

from minigames.generics import PilgramMinigame, MINIGAMES
from minigames.games import AAA
from orm.db import PilgramORMDatabase
from pilgram.classes import Player, Guild, Zone, SpellError, QTE_CACHE, TOWN_ZONE, Cult
from pilgram.generics import PilgramDatabase, AlreadyExists
from pilgram.globals import ContentMeta, PLAYER_NAME_REGEX, GUILD_NAME_REGEX, POSITIVE_INTEGER_REGEX, DESCRIPTION_REGEX, \
    MINIGAME_NAME_REGEX, YES_NO_REGEX, SPELL_NAME_REGEX
from pilgram.spells import SPELLS
from pilgram.utils import read_text_file
from pilgram.strings import Strings, MONEY
from ui.utils import UserContext, InterpreterFunctionWrapper as IFW, RegexWithErrorMessage as RWE


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

BBB = AAA
MODIFY_COST = ContentMeta.get("modify_cost")
MAX_TAX = ContentMeta.get("guilds.max_tax")


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def check_board(context: UserContext) -> str:
    zones = db().get_all_zones()
    return Strings.check_board + "\n".join(f"Zone {x.zone_id} - *{x.zone_name}* (lv. {x.level})" for x in zones) + "\n\n" + Strings.embark_underleveled


def check_current_quest(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        try:
            ac = db().get_player_adventure_container(player)
            if ac.quest is None:
                return Strings.not_on_a_quest
            return str(ac)
        except KeyError as e:
            return f"Fatal error: {e}"
    except KeyError:
        return Strings.no_character_yet


def check_zone(context: UserContext, zone_id_str: int) -> str:
    try:
        zone_id = int(zone_id_str)
        if zone_id == 0:
            return str(TOWN_ZONE)
        zone = db().get_zone(int(zone_id))
        return str(zone)
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="zone")


def return_string(context: UserContext, string: str = "") -> str:
    return string


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


def check_artifact(context: UserContext, artifact_id_str: str) -> str:
    try:
        artifact_id = int(artifact_id_str)
        artifact = db().get_artifact(artifact_id)
        return str(artifact)
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="Artifact")


def check_guild(context: UserContext, guild_name: str) -> str:
    try:
        guild = db().get_guild(db().get_guild_id_from_name(guild_name))
        return str(guild)
    except KeyError:
        return Strings.named_object_not_exist.format(obj="guild", name=guild_name)


def check_prices(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        result: str = f"*Gear upgrade*: {player.get_gear_upgrade_required_money()} {MONEY}\n*Home upgrade*: {player.get_home_upgrade_required_money()} {MONEY}"
        if player.guild:
            result += f"\n*Guild upgrade*: {player.guild.get_upgrade_required_money()} {MONEY}"
        result += f"\n\n*Create guild*: {ContentMeta.get('guilds.creation_cost')} {MONEY}\n*Modify*: {MODIFY_COST} {MONEY}"
        result += f"\n\n*You have*: {player.money} {MONEY}"
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
        return Strings.here_are_your_mates.format(num=len(members)) + Guild.print_members(members)
    except KeyError:
        return Strings.no_character_yet


def check_guild_members(context: UserContext, guild_name: str) -> str:
    try:
        guild = db().get_guild(db().get_guild_id_from_name(guild_name))
        if guild is None:
            return Strings.named_object_not_exist.format(obj="guild", name=guild_name)
        members = db().get_guild_members_data(guild)
        return Strings.show_guild_members.format(name=guild.name,num=len(members)) + Guild.print_members(members)
    except KeyError:
        return Strings.no_character_yet


def start_character_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        return Strings.character_already_created.format(name=player.name)
    except KeyError:
        context.start_process("character creation")
        context.set("operation", "create")
        log.info(f"User {context.get('id')} is creating a character")
        return context.get_process_prompt(USER_PROCESSES)


def process_get_character_name(context: UserContext, user_input) -> str:
    if not re.match(PLAYER_NAME_REGEX, user_input):
        return Strings.player_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_character_cult(context: UserContext, user_input) -> str:
    if not re.match(POSITIVE_INTEGER_REGEX, user_input):
        return Strings.positive_integer_error
    cult_id = int(user_input)
    if cult_id >= len(Cult.LIST):
        return Strings.cult_does_not_exist.format(start=0, end=len(Cult.LIST)-1)
    context.set("cult", cult_id)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_character_description(context: UserContext, user_input) -> str:
    if not re.match(DESCRIPTION_REGEX, user_input):
        return Strings.description_validation_error
    try:
        if context.get("operation") == "edit":
            player = db().get_player_data(context.get("id"))
            # make a copy of the original player (to avoid cases in which we set a name that isn't valid in the object
            player_copy = copy(player)
            player_copy.name = context.get("name")
            player_copy.cult = Cult.LIST[context.get("cult")]
            player_copy.description = user_input
            player_copy.money -= MODIFY_COST
            db().update_player_data(player_copy)
            # if the name is valid then actually update the object
            player.name = player_copy.name
            player.description = player_copy.description
            player.money = player_copy.money
            player.cult = player_copy.cult
            context.end_process()
            return Strings.obj_modified.format(obj="character")
        else:
            player = Player.create_default(
                context.get("id"), context.get("name"), user_input
            )
            player.cult = Cult.LIST[context.get("cult")]
            db().add_player(player)
            context.end_process()
            log.info(f"User {context.get('id')} created character {player.name}")
            return Strings.welcome_to_the_world
    except AlreadyExists:
        context.end_process()
        return Strings.name_object_already_exists.format(obj="character", name=context.get("name"))


def start_guild_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if db().get_owned_guild(player):
            return Strings.guild_already_created
        creation_cost = ContentMeta.get("guilds.creation_cost")
        if player.money < creation_cost:
            return Strings.not_enough_money.format(amount=creation_cost - player.money)
        log.info(f"Player '{player.name}' is creating a guild")
        context.start_process("guild creation")
        context.set("operation", "create")
        return context.get_process_prompt(USER_PROCESSES)
    except KeyError:
        return Strings.no_character_yet


def process_get_guild_name(context: UserContext, user_input) -> str:
    if not re.match(GUILD_NAME_REGEX, user_input):
        return Strings.guild_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_guild_tax(context: UserContext, user_input) -> str:
    if not re.match(POSITIVE_INTEGER_REGEX, user_input):
        return Strings.positive_integer_error
    tax = int(user_input)
    if tax > MAX_TAX:
        return Strings.invalid_tax
    context.set("tax", tax)
    context.progress_process()
    return context.get_process_prompt(USER_PROCESSES)


def process_get_guild_description(context: UserContext, user_input) -> str:
    if not re.match(DESCRIPTION_REGEX, user_input):
        return Strings.description_validation_error
    player = db().get_player_data(context.get("id"))
    try:
        if context.get("operation") == "edit":
            guild = db().get_owned_guild(player)
            # make a copy of the original guild (to avoid cases in which we set a name that isn't valid in the object
            guild_copy = copy(guild)
            guild_copy.name = context.get("name")
            guild_copy.tax = context.get("tax")
            guild_copy.description = user_input
            db().update_guild(guild_copy)
            # if the name is valid then actually update the object
            guild.name = guild_copy.name
            guild.description = guild_copy.description
            guild.tax = guild_copy.tax
            player.money -= MODIFY_COST
            db().update_player_data(player)
            context.end_process()
            return Strings.obj_modified.format(obj="guild")
        else:
            guild = Guild.create_default(player, context.get("name"), user_input)
            guild.tax = context.get("tax")
            db().add_guild(guild)
            guild = db().get_owned_guild(player)
            player.guild = guild
            player.money -= ContentMeta.get("guilds.creation_cost")
            db().update_player_data(player)
            context.end_process()
            log.info(f"Player '{player.name}' {context.get("operation")}d guild '{guild.name}'")
            return Strings.guild_creation_success.format(name=guild.name)
    except AlreadyExists:
        context.end_process()
        return Strings.name_object_already_exists.format(obj="guild", name=context.get("name"))


def upgrade(context: UserContext, obj: str = "gear") -> str:
    try:
        player = db().get_player_data(context.get("id"))
        price: int = {
            "gear": player.get_gear_upgrade_required_money,
            "home": player.get_home_upgrade_required_money,
        }.get(obj)()
        if player.money < price:
            return Strings.not_enough_money.format(amount=price-player.money)
        func = {
            "gear": player.upgrade_gear,
            "home": player.upgrade_home
        }.get(obj)
        db().update_player_data(player)
        context.start_process("upgrade confirm")
        context.set("price", price)
        context.set("obj", obj)
        context.set("func", func)
        return Strings.upgrade_object_confirmation.format(obj=obj, price=price)
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
            return Strings.not_enough_money.format(amount=price-player.money)
        context.start_process("upgrade confirm")
        context.set("price", price)
        context.set("obj", "guild")
        context.set("func", guild.upgrade)
        return Strings.upgrade_object_confirmation.format(obj="guild", price=price)
    except KeyError:
        return Strings.no_character_yet


def process_upgrade_confirm(context: UserContext, user_input: str) -> str:
    processed_user_input = user_input[0].lower()
    if not re.match(YES_NO_REGEX, processed_user_input):
        return Strings.yes_no_error
    player = db().get_player_data(context.get("id"))
    context.end_process()
    if processed_user_input == "n":
        return Strings.upgrade_cancelled
    obj = context.get("obj")
    price = context.get("price")
    func = context.get("func")
    func()
    db().update_player_data(player)
    if obj == "guild":
        guild = db().get_owned_guild(player)
        db().update_guild(guild)
    return Strings.upgrade_successful.format(obj=obj, paid=price)


def modify_player(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        # check if the player has enough money
        if db().is_player_on_a_quest(player):
            return Strings.cannot_modify_on_quest
        if player.money < MODIFY_COST:
            return Strings.not_enough_money.format(amount=MODIFY_COST-player.money)
        context.start_process("character creation")
        context.set("operation", "edit")
        return f"name: `{player.name}`\n\ndescr: `{player.description}`\n\n" + context.get_process_prompt(USER_PROCESSES)
    except KeyError:
        return Strings.no_character_yet


def modify_guild(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        guild = db().get_owned_guild(player)
        # check if the player doesn't already have a guild of his own & has enough money
        if not guild:
            return Strings.guild_not_owned
        if player.money < MODIFY_COST:
            return Strings.not_enough_money.format(amount=MODIFY_COST-player.money)
        # set the attribute
        context.start_process("guild creation")
        context.set("operation", "edit")
        return f"name: `{guild.name}`\n\ndescr: `{guild.description}`\n\ntax: `{guild.tax}`\n\n" + context.get_process_prompt(USER_PROCESSES)
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


def __start_quest_in_zone(player: Player, zone: Zone) -> str:
    quest = db().get_next_quest(zone, player)
    adventure_container = db().get_player_adventure_container(player)
    adventure_container.quest = quest
    adventure_container.finish_time = datetime.now() + quest.get_duration(player)
    db().update_quest_progress(adventure_container)
    return Strings.quest_embark.format(quest=str(quest))


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
        return Strings.obj_does_not_exist.format(obj="zone")
    if player.level < zone.level:
        context.start_process("embark confirm")
        context.set("zone", zone)
        return Strings.embark_underleveled_confirm.format(zone=zone.zone_name, lv=zone.level)
    return __start_quest_in_zone(player, zone)


def process_embark_confirm(context: UserContext, user_input: str) -> str:
    processed_user_input = user_input[0].lower()
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    if not re.match(YES_NO_REGEX, processed_user_input):
        return Strings.yes_no_error
    context.end_process()
    if processed_user_input == "n":
        return Strings.embark_underleveled_cancel
    return __start_quest_in_zone(player, context.get("zone"))


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


def cast_spell(context: UserContext, spell_name: str, *extra_args) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if spell_name not in SPELLS:
            return Strings.named_object_not_exist.format(obj="Spell", name=spell_name)
        spell = SPELLS[spell_name]
        if not spell.can_cast(player):
            return Strings.not_enough_power
        if not spell.check_args(extra_args):
            return Strings.not_enough_args.format(num=spell.required_args)
        try:
            result = spell.cast(player, extra_args)
            db().update_player_data(player)
            return result
        except SpellError as e:
            return e.message
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
        recipient.add_money(amount)
        db().update_player_data(recipient)
        player.money -= amount
        db().update_player_data(player)
        # use context to communicate to the external interface that a notification should be sent to the recipient
        context.set_event("donation", {"amount": amount, "donor": player, "recipient": recipient})
        log.info(f"player '{player.name}' donated {amount} to '{recipient_name}'")
        return Strings.donation_successful.format(amm=amount_str, rec=recipient_name)
    except KeyError:
        return Strings.no_character_yet


def rank_guilds(context: UserContext) -> str:
    result = Strings.rank_guilds + "\n"
    guilds = db().rank_top_guilds()
    for guild, position in zip(guilds, range(len(guilds))):
        result += f"{position + 1}. {guild[0]} | {guild[1]}\n"
    return result


def rank_players(context: UserContext) -> str:
    result = Strings.rank_players + "\n"
    players = db().rank_top_players()
    for player, position in zip(players, range(len(players))):
        result += f"{position + 1}. {player[0]} | {player[1]}\n"
    return result


def rank_tourney(context: UserContext) -> str:
    result = Strings.rank_tourney + "\n"
    guilds = db().get_top_n_guilds_by_score(10)
    for guild, position in zip(guilds, range(len(guilds))):
        result += f"{position + 1}. {guild.name} | {guild.tourney_score}\n"
    return result


def send_message_to_player(context: UserContext, player_name: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.name == player_name:
            return Strings.no_self_message
        target = db().get_player_from_name(player_name)
        if not target:
            return Strings.named_object_not_exist.format(obj="Player", name=player_name)
        context.set("targets", [target.player_id])
        context.set("text", f"{{name}} sent you a message:\n\n")
        context.start_process("message")
        return Strings.write_your_message
    except KeyError:
        return Strings.no_character_yet


def send_message_to_owned_guild(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        owned_guild = db().get_owned_guild(player)
        if not owned_guild:
            return Strings.no_guild_yet
        members: List[Tuple[int, str, int]] = db().get_guild_members_data(owned_guild)
        context.set("targets", [member[0] for member in members])
        context.set("text", f"{{name}} sent a message to the guild ({owned_guild.name}):\n\n")
        context.start_process("message")
        return Strings.write_your_message
    except KeyError:
        return Strings.no_character_yet


def send_message_process(context: UserContext, message: str):
    player = db().get_player_data(context.get("id"))
    context.set_event("message", {"sender": player, "targets": context.get("targets"), "text": context.get("text") + message})
    context.end_process()
    return Strings.message_sent


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
            return "Fatal error: adventure container not found. THIS SHOULD NOT HAPPEN. EVER."
    except KeyError:
        return Strings.no_character_yet


def assemble_artifact(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.artifact_pieces < 10:
            return Strings.not_enough_pieces.format(amount=10 - player.artifact_pieces)
        try:
            artifact = db().get_unclaimed_artifact()
            player.artifact_pieces -= 10
            player.artifacts.append(artifact)
            db().update_artifact(artifact, player)
            db().update_player_data(player)
            return Strings.craft_successful.format(name=artifact.name)
        except KeyError:
            return "ERROR: no artifacts available! Try again in a few hours!"
    except KeyError:
        return Strings.no_character_yet


def __list_minigames() -> str:
    return "Available minigames:\n\n" + "\n".join(f"`{x}`" for x in MINIGAMES.keys()) + "\n\nWrite '`play [minigame]`' to play a minigame"


def __list_cults() -> str:
    return Strings.list_cults + "\n\n".join(str(x) for x in Cult.LIST)


def __list_spells() -> str:
    return "Grimoire:\n\n" + "\n\n".join(f"`{key}` | min power: {spell.required_power}\n_{spell.description}_" for key, spell in SPELLS.items())


def do_quick_time_event(context: UserContext, option_chosen_str: str) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        qte = QTE_CACHE.get(player.player_id)
        if not qte:
            return Strings.no_qte_active
        option_chosen = int(option_chosen_str) - 1
        if option_chosen >= len(qte.options):
            return Strings.invalid_option
        func, string = qte.resolve(option_chosen)
        if func:
            func(player)
            player.renown += 5
            if player.guild:
                guild = db().get_guild(player.guild.guild_id)
                guild.tourney_score += 5
                db().update_guild(guild)
            db().update_player_data(player)
        del QTE_CACHE[player.player_id]
        return string
    except KeyError:
        return Strings.no_character_yet


def start_minigame(context: UserContext, minigame_name: str) -> str:
    try:
        minigame: Union[Type[PilgramMinigame], None] = MINIGAMES.get(minigame_name, None)
        if not minigame:
            return Strings.named_object_not_exist.format(obj="minigame", name=minigame_name) + f"\n\n{__list_minigames()}"
        if minigame.has_played_too_recently(context.get("id")):
            return Strings.minigame_played_too_recently.format(seconds=minigame.COOLDOWN)
        player = db().get_player_data(context.get("id"))
        can_play, error = minigame.can_play(player)
        if not can_play:
            return minigame.INTRO_TEXT + "\n\n" + error
        minigame_instance = minigame(player)
        context.set("minigame instance", minigame_instance)
        context.start_process("minigame")
        if not minigame_instance.has_started:  # skip setup if it is not needed
            return minigame.INTRO_TEXT + "\n\n" + minigame_instance.setup_text()
        return minigame.INTRO_TEXT + "\n\n" + minigame_instance.turn_text()
    except KeyError:
        return Strings.no_character_yet


def minigame_process(context: UserContext, user_input: str) -> str:
    minigame: PilgramMinigame = context.get("minigame instance")
    if not minigame.has_started:
        message = minigame.setup_game(user_input)
        if minigame.has_started:
            return message + f"\n\n{minigame.turn_text()}"
        return message
    message = minigame.play_turn(user_input)
    if minigame.has_ended:
        context.end_process()
        player: Player = minigame.player
        xp, money = minigame.get_rewards()
        if minigame.won:
            player.add_xp(xp),
            player.add_money(money)
            player.renown += minigame.RENOWN
            db().update_player_data(minigame.player)
            if (minigame.RENOWN != 0) and player.guild:
                guild = db().get_guild(player.guild.guild_id)
                guild.tourney_score += minigame.RENOWN
                db().update_guild(guild)
            return message + f"\n\nYou gain {xp} xp & {money} {MONEY}." + ("" if minigame.RENOWN == 0 else f"\nYou gain {minigame.RENOWN} renown.")
        player.add_xp(xp)
        db().update_player_data(minigame.player)
        return message + f"\n\n{Strings.xp_gain.format(xp=xp)}"
    return message


def explain_minigame(context: UserContext, user_input: str) -> str:
    minigame = MINIGAMES.get(user_input, None)
    if not minigame:
        return Strings.named_object_not_exist.format(obj="minigame", name=user_input) + f"\n\n{__list_minigames()}"
    return minigame.EXPLANATION


USER_COMMANDS: Dict[str, Union[str, IFW, dict]] = {
    "check": {
        "board": IFW(None, check_board, "Shows the quest board."),
        "quest": IFW(None, check_current_quest, "Shows the current quest name, objective & duration if you are on a quest."),
        "zone": IFW([RWE("zone number", POSITIVE_INTEGER_REGEX, Strings.obj_number_error.format(obj="Zone number"))], check_zone, "Shows a description of a Zone."),
        "guild": IFW([RWE("guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], check_guild, "Shows the guild with the given name."),
        "self": IFW(None, check_self, "Shows your own stats."),
        "player": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], check_player, "Shows player stats."),
        "artifact": IFW([RWE("Artifact number", POSITIVE_INTEGER_REGEX, Strings.obj_number_error.format(obj="Artifact number"))], check_artifact, "Shows a description of an Artifact."),
        "prices": IFW(None, check_prices, "Shows all the prices."),
        "my": {
            "guild": IFW(None, check_my_guild, "Shows your own guild."),
        },
        "mates": IFW(None, check_guild_mates, "Shows your guild mates"),
        "members": IFW([RWE("Guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], check_guild_members, "Shows the members of the given guild")
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
    "edit": {
        "character": IFW(None, modify_player, "Modify your character (for a price).",),
        "guild": IFW(None, modify_guild, f"Modify your guild (for a price).",)
    },
    "join": IFW([RWE("guild name", GUILD_NAME_REGEX, Strings.guild_name_validation_error)], join_guild, "Join guild with the given name."),
    "embark": IFW([RWE("zone number", POSITIVE_INTEGER_REGEX, Strings.obj_number_error.format(obj="Zone number"))], embark_on_quest, "Starts quest in specified zone."),
    "kick": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], kick, "Kicks player from your own guild."),
    "donate": IFW([RWE("recipient", PLAYER_NAME_REGEX, Strings.player_name_validation_error), RWE("amount", POSITIVE_INTEGER_REGEX, Strings.invalid_money_amount)], donate, f"donates 'amount' of {MONEY} to player 'recipient'."),
    "cast": IFW([RWE("spell name", SPELL_NAME_REGEX, Strings.spell_name_validation_error)], cast_spell, "Cast a spell.", optional_args=1),
    "grimoire": IFW(None, return_string, "Shows & describes all spells", default_args={"string": __list_spells()}),
    "rank": {
        "guilds": IFW(None, rank_guilds, "Shows the top 20 guilds, ranked based on their prestige."),
        "players": IFW(None, rank_players, "Shows the top 20 players, ranked based on their renown."),
        "tourney": IFW(None, rank_tourney, "Shows the top 10 guilds competing in the tourney. Only the top 3 will win."),
    },
    "message": {
        "player": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], send_message_to_player, "Send message to a single player."),
        "guild": IFW(None, send_message_to_owned_guild, "Send message to every member of your owned guild.")
    },
    "assemble": {
        "artifact": IFW(None, assemble_artifact, "Assemble an artifact using 10 artifact pieces")
    },
    "qte": IFW([RWE("Option number", POSITIVE_INTEGER_REGEX, "QTE options must be positive integers")], do_quick_time_event, "Do a quick time event"),
    "retire": IFW(None, set_last_update, f"Take a 1 year vacation (pauses the game for 1 year) (cost: 100 {MONEY})", default_args={"delta": timedelta(days=365), "msg": Strings.you_retired, "cost": 100}),
    "back": {
        "to": {
            "work": IFW(None, set_last_update, "Come back from your vacation", default_args={"delta": None, "msg": Strings.you_came_back})
        }
    },
    "minigames": IFW(None, return_string, "Shows all the minigames", default_args={"string": __list_minigames()}),
    "cults": IFW(None, return_string, "Shows all cults", default_args={"string": __list_cults()}),
    "play": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], start_minigame, "Play the specified minigame."),
    "explain": {
        "minigame": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], explain_minigame, "Explains how the specified minigame works."),
        "mechanics": {
            "1": IFW(None, return_string, "Explains the mechanics of the game (page 1)", default_args={"string": read_text_file("mechanics.txt").split("\n\n----\n\n")[0]}),
            "2": IFW(None, return_string, "Explains the mechanics of the game (page 2)", default_args={"string": read_text_file("mechanics.txt").split("\n\n----\n\n")[1]})
        }
    }
}

USER_PROCESSES: Dict[str, Tuple[Tuple[str, Callable], ...]] = {
    "character creation": (
        (Strings.character_creation_get_name, process_get_character_name),
        (Strings.choose_cult + "\n" + __list_cults(), process_get_character_cult),
        (Strings.character_creation_get_description, process_get_character_description)
    ),
    "guild creation": (
        (Strings.guild_creation_get_name, process_get_guild_name),
        (Strings.insert_tax, process_get_guild_tax),
        (Strings.guild_creation_get_description, process_get_guild_description)
    ),
    "embark confirm": (
        ("confirm", process_embark_confirm),
    ),
    "minigame": (
        ("minigame turn", minigame_process),
    ),
    "message": (
        (Strings.write_your_message, send_message_process),
    ),
    "upgrade confirm": (
        ("confirm", process_upgrade_confirm),
    )
}
