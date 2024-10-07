import logging
import random
import re
from collections.abc import Callable
from copy import copy
from datetime import datetime, timedelta
from functools import cache
from random import choice

from minigames.games import AAA
from minigames.generics import MINIGAMES, PilgramMinigame
from orm.db import PilgramORMDatabase
from pilgram.classes import (
    QTE_CACHE,
    TOWN_ZONE,
    Auction,
    Vocation,
    Guild,
    Player,
    SpellError,
    Zone,
)
from pilgram.combat_classes import CombatContainer
from pilgram.equipment import Equipment, EquipmentType
from pilgram.flags import ForcedCombat, HexedFlag, CursedFlag, AlloyGlitchFlag3, AlloyGlitchFlag1, AlloyGlitchFlag2, \
    LuckFlag1, LuckFlag2, StrengthBuff, OccultBuff, FireBuff, IceBuff, AcidBuff, ElectricBuff, MightBuff3, MightBuff2, \
    MightBuff1, SwiftBuff3, SwiftBuff2, SwiftBuff1, QuestCanceled, Explore
from pilgram.generics import AlreadyExists, PilgramDatabase
from pilgram.globals import (
    DESCRIPTION_REGEX,
    GUILD_NAME_REGEX,
    MINIGAME_NAME_REGEX,
    PLAYER_NAME_REGEX,
    POSITIVE_INTEGER_REGEX,
    SPELL_NAME_REGEX,
    ContentMeta,
)
from pilgram.spells import SPELLS
from pilgram.strings import MONEY, Strings, rewards_string
from pilgram.utils import read_text_file, read_update_interval
from ui.utils import InterpreterFunctionWrapper as IFW, integer_arg, player_arg, guild_arg, get_yes_or_no, get_player
from ui.utils import RegexWithErrorMessage as RWE
from ui.utils import UserContext

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

BBB = AAA
MODIFY_COST: int = ContentMeta.get("modify_cost")
MAX_TAX: int = ContentMeta.get("guilds.max_tax")
REQUIRED_PIECES: int = ContentMeta.get("artifacts.required_pieces")
SWITCH_DELAY: timedelta = read_update_interval(ContentMeta.get("guilds.switch_delay"))
REROLL_MULT: int = ContentMeta.get("crafting.reroll_mult")


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def check_board(context: UserContext) -> str:
    player = get_player(db, context)
    anomaly = db().get_current_anomaly()
    zones = db().get_all_zones()
    text = Strings.check_board
    for zone in zones:
        text += f"*Zone {zone.zone_id} - {zone.zone_name}* (lv. {zone.level})\n"
        player_progress = player.progress.get_zone_progress(zone)
        if player_progress != 0:
            text += f"> progress: {player_progress}\n"
    return text + "\n\n" + Strings.embark_underleveled + f"\n\n*Player*:\nlv. {player.level}, gear lv: {player.gear_level}\n\n{anomaly}"


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


def check_enemy(context: UserContext, zone_id_str: int) -> str:
    try:
        enemy_id = int(zone_id_str)
        enemy = db().get_enemy_meta(enemy_id)
        return str(enemy)
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="enemy")


def return_string(context: UserContext, string: str = "") -> str:
    return string


def __get_player_from_name(player_name: str) -> tuple[str | None, Player | None]:
    player_ids: list[int] = db().get_player_ids_from_name_case_insensitive(player_name)
    if len(player_ids) == 0:
        return Strings.named_object_not_exist.format(obj="player", name=player_name), None
    players = [db().get_player_data(player_id) for player_id in player_ids]
    if len(players) == 1:
        return None, players[0]
    player = None
    for p in players:
        if p.name == player_name:
            player = p
    if player is None:
        return Strings.multiple_matches_found.format(obj="player") + "\n\n" + "\n".join(x.name for x in players), None
    return None, player


def __get_guild_from_name(guild_name: str) -> tuple[str | None, Guild | None]:
    guild_ids: list[int] = db().get_guild_ids_from_name_case_insensitive(guild_name)
    if len(guild_ids) == 0:
        return Strings.named_object_not_exist.format(obj="guild", name=guild_name), None
    guilds = [db().get_guild(guild_id) for guild_id in guild_ids]
    if len(guilds) == 1:
        return None, guilds[0]
    guild = None
    for g in guilds:
        if g.name == guild_name:
            guild = g
    if guild is None:
        return Strings.multiple_matches_found.format(obj="guild") + "\n\n" + "\n".join(x.name for x in guilds), None
    return None, guild


def check_player(context: UserContext, *args) -> str:
    if len(args) > 0:
        try:
            message, player = __get_player_from_name(args[0])
            if message:
                return message
            return str(player)
        except KeyError:
            return Strings.named_object_not_exist.format(obj="player", name=args[0])
    else:
        player = get_player(db, context)
        return str(player)


def check_artifact(context: UserContext, artifact_id_str: str) -> str:
    try:
        artifact_id = int(artifact_id_str)
        artifact = db().get_artifact(artifact_id)
        return str(artifact)
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="Artifact")


def check_guild(context: UserContext, *args) -> str:
    if len(args) > 0:
        try:
            message, guild = __get_guild_from_name(args[0])
            if message:
                return message
            return str(guild)
        except KeyError:
            return Strings.named_object_not_exist.format(obj="guild", name=args[0])
    else:
        player = get_player(db, context)
        if player.guild:
            return str(player.guild)
        else:
            return Strings.not_in_a_guild


def check_prices(context: UserContext) -> str:
    player = get_player(db, context)
    result: str = f"*Gear upgrade*: {player.get_gear_upgrade_required_money()} {MONEY}\n*Home upgrade*: {player.get_home_upgrade_required_money()} {MONEY}"
    if player.guild:
        result += f"\n*Guild upgrade*: {player.guild.get_upgrade_required_money()} {MONEY}"
    result += f"\n\n*Create guild*: {ContentMeta.get('guilds.creation_cost')} {MONEY}\n*Modify*: {MODIFY_COST} {MONEY}"
    result += f"\n\n*You have*: {player.money} {MONEY}"
    return result


def check_guild_members(context: UserContext, *args) -> str:
    if len(args) > 0:
        message, guild = __get_guild_from_name(args[0])
        if message:
            return message
        if guild is None:
            return Strings.named_object_not_exist.format(obj="guild", name=args[0])
        members = db().get_guild_members_data(guild)
        members.sort(key=lambda entry: entry[2], reverse=True)
        return Strings.show_guild_members.format(name=guild.name, num=len(members)) + Guild.print_members(members)
    else:
        player = get_player(db, context)
        if not player.guild:
            return Strings.not_in_a_guild
        members = db().get_guild_members_data(player.guild)
        members.sort(key=lambda entry: entry[2], reverse=True)
        return Strings.here_are_your_mates.format(num=len(members)) + Guild.print_members(members)


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


def process_get_character_description(context: UserContext, user_input) -> str:
    if not re.match(DESCRIPTION_REGEX, user_input):
        return Strings.description_validation_error
    try:
        if context.get("operation") == "edit":
            player = db().get_player_data(context.get("id"))
            # make a copy of the original player (to avoid cases in which we set a name that isn't valid in the object
            player_copy = copy(player)
            player_copy.name = context.get("name")
            player_copy.description = user_input
            player_copy.money -= MODIFY_COST
            db().update_player_data(player_copy)
            # if the name is valid then actually update the object
            player.name = player_copy.name
            player.description = player_copy.description
            player.money = player_copy.money
            context.end_process()
            return Strings.obj_modified.format(obj="character")
        else:
            player = Player.create_default(
                context.get("id"), context.get("name"), user_input
            )
            starting_weapon = Equipment.generate(1, EquipmentType.get(0), 0)
            db().add_player(player)
            item_id = db().add_item(starting_weapon, player)
            starting_weapon.equipment_id = item_id
            player.equip_item(starting_weapon)
            db().update_player_data(player)
            context.end_process()
            log.info(f"User {context.get('id')} created character {player.name}")
            return Strings.welcome_to_the_world
    except AlreadyExists:
        context.end_process()
        return Strings.name_object_already_exists.format(obj="character", name=context.get("name"))


def start_guild_creation(context: UserContext) -> str:
    player = get_player(db, context)
    if db().get_owned_guild(player):
        return Strings.guild_already_created
    creation_cost = ContentMeta.get("guilds.creation_cost")
    if player.money < creation_cost:
        return Strings.not_enough_money.format(amount=creation_cost - player.money)
    log.info(f"Player '{player.name}' is creating a guild")
    context.start_process("guild creation")
    context.set("operation", "create")
    return context.get_process_prompt(USER_PROCESSES)


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
    player = get_player(db, context)
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
    player = get_player(db, context)
    can_upgrade: bool = {
        "gear": player.can_upgrade_gear,
        "home": player.can_upgrade_home
    }.get(obj)()
    if not can_upgrade:
        return Strings.obj_reached_max_level.format(obj=obj)
    price: int = {
        "gear": player.get_gear_upgrade_required_money,
        "home": player.get_home_upgrade_required_money,
    }.get(obj)()
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
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


def upgrade_guild(context: UserContext) -> str:
    player = get_player(db, context)
    guild = db().get_owned_guild(player)
    if not guild:
        return Strings.no_guild_yet
    if guild.can_upgrade():
        return Strings.obj_reached_max_level.format(obj="guild")
    price = guild.get_upgrade_required_money()
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
    context.start_process("upgrade confirm")
    context.set("price", price)
    context.set("obj", "guild")
    context.set("func", guild.upgrade)
    return Strings.upgrade_object_confirmation.format(obj="guild", price=price)


def process_upgrade_confirm(context: UserContext, user_input: str) -> str:
    yes = get_yes_or_no(user_input)
    player = db().get_player_data(context.get("id"))
    context.end_process()
    if not yes:
        return Strings.upgrade_cancelled
    obj = context.get("obj")
    price = context.get("price")
    func = context.get("func")
    func()
    player.money -= price
    db().update_player_data(player)
    if obj == "guild":
        guild = db().get_owned_guild(player)
        db().update_guild(guild)
    return Strings.upgrade_successful.format(obj=obj, paid=price)


def modify_player(context: UserContext) -> str:
    player = get_player(db, context)
    # check if the player has enough money
    if db().is_player_on_a_quest(player):
        return Strings.cannot_modify_on_quest
    if player.money < MODIFY_COST:
        return Strings.not_enough_money.format(amount=MODIFY_COST - player.money)
    context.start_process("character editing")
    context.set("operation", "edit")
    return f"name: `{player.name}`\n\ndescr: `{player.description}`\n\n" + context.get_process_prompt(USER_PROCESSES)


def modify_guild(context: UserContext) -> str:
    player = get_player(db, context)
    guild = db().get_owned_guild(player)
    # check if the player doesn't already have a guild of his own & has enough money
    if not guild:
        return Strings.guild_not_owned
    if player.money < MODIFY_COST:
        return Strings.not_enough_money.format(amount=MODIFY_COST - player.money)
    # set the attribute
    context.start_process("guild creation")
    context.set("operation", "edit")
    return f"name: `{guild.name}`\n\ndescr: `{guild.description}`\n\ntax: `{guild.tax}`\n\n" + context.get_process_prompt(USER_PROCESSES)


def join_guild(context: UserContext, guild_name: str) -> str:
    player = get_player(db, context)
    message, guild = __get_guild_from_name(guild_name)
    if message:
        return message
    if not guild:
        return Strings.named_object_not_exist.format(obj="guild", name=guild_name)
    time_since_last_switch = datetime.now() - player.last_guild_switch
    if time_since_last_switch < SWITCH_DELAY:
        return Strings.switched_too_recently.format(hours=(SWITCH_DELAY.total_seconds() - time_since_last_switch.total_seconds()) // 3600)
    members: int = db().get_guild_members_number(guild)
    if not guild.can_add_member(members):
        return Strings.guild_is_full
    player.guild = guild
    player.last_guild_switch = datetime.now()
    db().update_player_data(player)
    db().create_and_add_notification(
        guild.founder,
        Strings.player_joined_your_guild.format(
            player=player.print_username(), guild=guild.name
        )
    )
    return Strings.guild_join_success.format(guild=guild_name)


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
    yes = get_yes_or_no(user_input)
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if yes:
        return __start_quest_in_zone(player, context.get("zone"))
    return Strings.embark_underleveled_cancel


def kick(context: UserContext, player_name: str) -> str:
    player = get_player(db, context)
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
    db().create_and_add_notification(target, Strings.you_have_been_kicked.format(guild=guild.name))
    return Strings.player_kicked_successfully.format(name=player_name, guild=guild.name)


def cast_spell(context: UserContext, spell_name: str, *extra_args) -> str:
    player = get_player(db, context)
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


def donate(context: UserContext, recipient_name: str, amount_str: str) -> str:
    player = get_player(db, context)
    amount: int = int(amount_str)
    if amount <= 0:
        return Strings.invalid_money_amount
    if player.money < amount:
        return Strings.not_enough_money
    message, recipient = __get_player_from_name(recipient_name)
    if message:
        return message
    if not recipient:
        return Strings.named_object_not_exist.format(obj="Player", name=recipient_name)
    # update money for recipient
    recipient.money += amount
    db().update_player_data(recipient)
    # update money for donor
    player.money -= amount
    db().update_player_data(player)
    # notify
    db().create_and_add_notification(
        recipient,
        Strings.donation_received.format(
            donor=player.print_username(), amm=amount
        ),
    )
    log.info(f"player '{player.name}' donated {amount} to '{recipient_name}'")
    return Strings.donation_successful.format(amm=amount_str, rec=recipient_name)


def rank_guilds(context: UserContext) -> str:
    result = Strings.rank_guilds + "\n"
    guilds = db().rank_top_guilds()
    for guild, position in zip(guilds, range(len(guilds)), strict=False):
        result += f"{position + 1}. {guild[0]} | {guild[1]}\n"
    return result


def rank_players(context: UserContext) -> str:
    result = Strings.rank_players + "\n"
    players = db().rank_top_players()
    for player, position in zip(players, range(len(players)), strict=False):
        result += f"{position + 1}. {player[0]} | {player[1]}\n"
    return result


def rank_tourney(context: UserContext) -> str:
    result = Strings.rank_tourney + "\n"
    guilds = db().get_top_n_guilds_by_score(10)
    for guild, position in zip(guilds, range(len(guilds)), strict=False):
        result += f"{position + 1}. {guild.name} | {guild.tourney_score}\n"
    days_left = db().get_tourney().get_days_left()
    if days_left > 1:
        result += "\n" + Strings.tourney_ends_in_x_days.format(x=days_left)
    elif days_left == 1:
        result += "\n" + Strings.tourney_ends_tomorrow
    else:
        result += "\n" + Strings.tourney_ends_today
    return result


def send_message_to_player(context: UserContext, player_name: str) -> str:
    player = get_player(db, context)
    if player.name == player_name:
        return Strings.no_self_message
    message, target = __get_player_from_name(player_name)
    if message:
        return message
    context.set("targets", [target.player_id])
    context.set("text", "{name} sent you a message:\n\n")
    context.start_process("message")
    return Strings.write_your_message


def send_message_to_owned_guild(context: UserContext) -> str:
    player = get_player(db, context)
    owned_guild = db().get_owned_guild(player)
    if not owned_guild:
        return Strings.no_guild_yet
    members: list[tuple[int, str, int]] = db().get_guild_members_data(owned_guild)
    context.set("targets", [member[0] for member in members])
    context.set("text", f"{player.name} sent a message to the guild ({owned_guild.name}):\n\n")
    context.start_process("message")
    return Strings.write_your_message


def send_message_process(context: UserContext, message: str):
    for target in context.get("targets"):
        db().create_and_add_notification(
            Player.create_default(target, str(target), ""),
            context.get("text") + message
        )
    context.end_process()
    return Strings.message_sent


def set_last_update(context: UserContext, delta: timedelta | None = None, msg: str = "default", cost: int | None = None) -> str:
    player = get_player(db, context)
    if cost and player.money < cost:
        return Strings.not_enough_money.format(amount=cost - player.money)
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


def assemble_artifact(context: UserContext) -> str:
    player = get_player(db, context)
    if len(player.artifacts) >= player.get_max_number_of_artifacts():
        return Strings.max_number_of_artifacts_reached.format(num=len(player.artifacts))
    if player.artifact_pieces < REQUIRED_PIECES:
        return Strings.not_enough_pieces.format(amount=REQUIRED_PIECES - player.artifact_pieces)
    try:
        artifact = db().get_unclaimed_artifact()
        player.artifact_pieces -= REQUIRED_PIECES
        player.artifacts.append(artifact)
        db().update_artifact(artifact, player)
        db().update_player_data(player)
        return Strings.craft_successful.format(name=artifact.name)
    except KeyError:
        return "ERROR: no artifacts available! Try again in a few hours!"


def __list_minigames() -> str:
    return "Available minigames:\n\n" + "\n".join(f"`{x}`" for x in MINIGAMES.keys()) + "\n\nWrite '`play [minigame]`' to play a minigame"


def __list_spells() -> str:
    return "Grimoire:\n\n" + "\n\n".join(f"`{key}` | min power: {spell.required_power}\n_{spell.description}_" for key, spell in SPELLS.items())


def list_vocations(context: UserContext) -> str:
    player = get_player(db, context)
    string: str = "Here are all your vocations:\n\n"
    for vocation in Vocation.LIST[1:]:
        if vocation.level == player.vocations_progress.get(vocation.vocation_id, 1):
            string += f"{"✅ " if vocation in player.vocation.original_vocations else ""}{vocation}\n"
    return string


def do_quick_time_event(context: UserContext, option_chosen_str: str) -> str:
    player = get_player(db, context)
    qte = QTE_CACHE.get(player.player_id)
    if not qte:
        return Strings.no_qte_active
    option_chosen = int(option_chosen_str) - 1
    if option_chosen >= len(qte.options):
        return Strings.invalid_option
    func, string, success = qte.resolve(option_chosen)
    if func:
        results = func(player)
        for result in results:
            if isinstance(result, Equipment):
                items = db().get_player_items(player.player_id)
                item = result
                item_id = db().add_item(item, player)
                item.equipment_id = item_id
                items.append(item)
    if success:
        player.renown += 5
        if player.guild:
            guild = db().get_guild(player.guild.guild_id)
            guild.tourney_score += 5
            db().update_guild(guild)
        db().update_player_data(player)
    del QTE_CACHE[player.player_id]
    return string


def start_minigame(context: UserContext, minigame_name: str) -> str:
    minigame: type[PilgramMinigame] | None = MINIGAMES.get(minigame_name, None)
    if not minigame:
        return Strings.named_object_not_exist.format(obj="minigame", name=minigame_name) + f"\n\n{__list_minigames()}"
    if minigame.has_played_too_recently(context.get("id")):
        return Strings.minigame_played_too_recently.format(seconds=minigame.COOLDOWN)
    player = get_player(db, context)
    can_play, error = minigame.can_play(player)
    if not can_play:
        return minigame.INTRO_TEXT + "\n\n" + error
    minigame_instance = minigame(player)
    context.set("minigame instance", minigame_instance)
    context.start_process("minigame")
    if not minigame_instance.has_started:  # skip setup if it is not needed
        return minigame.INTRO_TEXT + "\n\n" + minigame_instance.setup_text()
    return minigame.INTRO_TEXT + "\n\n" + minigame_instance.turn_text()


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
        xp, money = minigame.get_rewards_apply_bonuses()
        if minigame.won:
            money_am = player.add_money(money)
            if xp > 0:
                xp_am = player.add_xp(xp)
                message += f"\n\nYou gain {xp_am} xp & {money_am} {MONEY}."
            else:
                items = db().get_player_items(player.player_id)
                item = Equipment.generate(player.level, EquipmentType.get_random(), random.choice((0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 3)))
                message += f"\n\nYou gain {money_am} {MONEY} & find *{item.name}*."
                if len(items) >= player.get_inventory_size():
                    message += " You leave the item there since you don't have space in your inventory."
                else:
                    item_id = db().add_item(item, player)
                    item.equipment_id = item_id
                    items.append(item)
            player.renown += minigame.RENOWN
            db().update_player_data(minigame.player)
            if (minigame.RENOWN != 0) and player.guild:
                guild = db().get_guild(player.guild.guild_id)
                guild.tourney_score += minigame.RENOWN
                db().update_guild(guild)
            return message + ("" if minigame.RENOWN == 0 else f"\n\nYou gain {minigame.RENOWN} renown.")
        if xp < 0:
            xp = 1
        xp_am = player.add_xp(xp)
        db().update_player_data(minigame.player)
        return message + f"\n\n{Strings.xp_gain.format(xp=xp_am)}"
    return message


def explain_minigame(context: UserContext, user_input: str) -> str:
    minigame = MINIGAMES.get(user_input, None)
    if not minigame:
        return Strings.named_object_not_exist.format(obj="minigame", name=user_input) + f"\n\n{__list_minigames()}"
    return minigame.EXPLANATION


@cache
def __get_mechanics(page_id: int):
    pages = read_text_file("mechanics.txt").split("\n\n----\n\n")
    print(len(pages))
    if (page_id == 0) or (page_id > len(pages)):
        return Strings.invalid_page.format(pl=len(pages))
    text = pages[page_id - 1] + (f"\n\nUse command `man {page_id + 1}` to continue reading" if page_id != len(pages) else "")
    return text


def manual(context: UserContext, page_str: str) -> str:
    page_id = int(page_str)
    return __get_mechanics(page_id)


def switch_stance(context: UserContext, stance: str) -> str:
    player = get_player(db, context)
    stance_byte = stance[0].lower()
    if stance_byte not in Strings.stances:
        return Strings.invalid_stance + "\n".join([f"*{stance}*: _{descr}_" for stance, descr in list(Strings.stances.values())])
    player.stance = stance_byte
    db().update_player_data(player)
    return Strings.stance_switch + Strings.stances[stance_byte][0]


def bestiary(context: UserContext, zone_id_str: str):
    try:
        zone_id = int(zone_id_str)
        if zone_id == 0:
            return Strings.no_monsters_in_town
        zone = db().get_zone(int(zone_id))
        enemies = db().get_all_zone_enemies(zone)
        if len(enemies) == 0:
            return Strings.no_enemies_yet.format(zone=zone.zone_name)
        return Strings.bestiary_string.format(zone=zone.zone_name) + "\n\n" + "\n".join([f"{x.meta_id} - {x.name}" for x in enemies])
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="zone")


def __get_items(player: Player) -> list[Equipment]:
    items = db().get_player_items(player.player_id)
    items.sort(key=lambda item: (item.equipment_type.slot, item.get_rarity(), item.level))
    return items


def inventory(context: UserContext) -> str:
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    return f"Items ({len(items)}/{player.get_inventory_size()}):\n\n{'\n'.join([f'{i + 1} - {Strings.get_item_icon(x.equipment_type.slot)}{' ✅' if player.is_item_equipped(x) else ''}| *{x.name}*' for i, x in enumerate(items)])}"


def __item_id_is_valid(item_id: int, items: list[Equipment]) -> bool:
    return (item_id > 0) and (item_id <= len(items))


def check_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    return str(items[item_pos - 1])


def equip_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if db().get_auction_from_item(item):
        return Strings.cannot_equip_auctioned_item
    player.equip_item(item)
    db().update_player_data(player)
    return Strings.item_equipped.format(item=item.name, slot=Strings.slots[item.equipment_type.slot])


def unequip_all_items(context: UserContext) -> str:
    player = get_player(db, context)
    player.equipped_items = {}
    db().update_player_data(player)
    return Strings.unequip_all


def reroll_item(context: UserContext, item_pos_str: str) -> str:
    player = get_player(db, context)
    items = __get_items(player)
    item_pos = int(item_pos_str)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    price = int(item.get_value() * REROLL_MULT * player.vocation.reroll_cost_multiplier)
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
    context.set("item pos", item_pos)
    context.start_process("reroll confirm")
    return Strings.item_reroll_confirm.format(item=item.name, price=price)


def process_reroll_confirm(context: UserContext, user_input: str) -> str:
    yes = get_yes_or_no(user_input)
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if yes:
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        price = int(item.get_value() * REROLL_MULT * player.vocation.reroll_cost_multiplier)
        old_name = item.name
        item.reroll(player.vocation.reroll_stats_bonus, player.vocation.perk_rarity_bonus)
        if player.is_item_equipped(item):
            player.equip_item(item)
        player.money -= price
        text = ""
        if player.vocation.xp_on_reroll > 0:
            xp_am = player.add_xp(player.vocation.xp_on_reroll * item.level)
            text = rewards_string(xp_am, 0, 0)
        db().update_player_data(player)
        db().update_item(item, player)
        return Strings.item_rerolled.format(amount=price, old_name=old_name) + "\n\n" + str(item) + text
    return Strings.action_canceled.format(action="Reroll")


def enchant_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    if player.artifact_pieces < 1:
        return Strings.no_items_yet
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if item.get_rarity() >= 4:
        return Strings.max_enchants_reached
    if db().get_auction_from_item(item):
        return Strings.cannot_enchant_auctioned_item
    context.set("item pos", item_pos)
    context.start_process("enchant confirm")
    return Strings.item_enchant_confirm.format(item=item.name)


def process_enchant_confirm(context: UserContext, user_input: str) -> str:
    yes = get_yes_or_no(user_input)
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if yes:
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        item.enchant()
        player.artifact_pieces -= 1
        if player.is_item_equipped(item):
            player.equip_item(item)
        db().update_player_data(player)
        db().update_item(item, player)
        return Strings.item_enchanted + "\n\n" + str(item)
    return Strings.action_canceled.format(action="Enchant")


def sell_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if player.is_item_equipped(item):
        return Strings.cannot_sell_equipped_item
    if db().get_auction_from_item(item):
        return Strings.cannot_sell_auctioned_item
    context.set("item pos", item_pos)
    context.start_process("sell confirm")
    return Strings.item_sell_confirm.format(item=item.name)


def process_sell_confirm(context: UserContext, user_input: str) -> str:
    yes = get_yes_or_no(user_input)
    player = get_player(db, context)
    context.end_process()
    if yes:
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        if player.is_item_equipped(item):
            return Strings.cannot_sell_equipped_item
        if db().get_auction_from_item(item):
            return Strings.cannot_sell_auctioned_item
        mult = 1 if player.guild_level() < 6 else 2
        money = int(item.get_value() * mult)
        player.add_money(money)
        items.pop(item_pos - 1)
        db().update_player_data(player)
        try:
            db().delete_item(item)
        except KeyError as e:
            return f"Error: {e}"
        return Strings.item_sold.format(item=item.name, money=money)
    return Strings.action_canceled.format(action="Sell")


def show_market(context: UserContext) -> str:
    items = db().get_market_items()
    text = "Here are today's market items:\n\n" + "\n".join(f"{i + 1}. " + str(x) for i, x in enumerate(items))
    return text


def __get_item_type_value(item_type: EquipmentType, player: Player):
    return (item_type.value + player.level) * 25


def show_smithy(context: UserContext) -> str:
    player = get_player(db, context)
    item_types = db().get_smithy_items()
    return "Here what the smithy can craft for you today:\n\n" + "\n".join(f"{i + 1}. {Strings.get_item_icon(x.slot)}| {x.name} (lv. {player.level}) - {__get_item_type_value(x, player)} {MONEY}" for i, x in enumerate(item_types))


def market_buy(context: UserContext, item_pos_str: str) -> str:
    player = get_player(db, context)
    if db().is_player_on_a_quest(player) and (not player.vocation.can_buy_on_a_quest):
        return Strings.cannot_shop_on_a_quest
    item_pos = int(item_pos_str)
    if item_pos > 10:
        return "Invalid item (max item: 10)"
    if len(player.satchel) >= player.get_max_satchel_items():
        return "Satchel already full!"
    item = db().get_market_items()[item_pos - 1]
    item_cost = int(item.value * (1 if player.guild_level() < 8 else 0.5))
    if player.money < item.value:
        return Strings.not_enough_money.format(amount=item_cost - player.money)
    player.satchel.append(item)
    player.money -= item_cost
    db().update_player_data(player)
    return Strings.item_bought.format(item=item.name, money=item_cost)


def smithy_craft(context: UserContext, item_pos_str: str) -> str:
    player = get_player(db, context)
    if db().is_player_on_a_quest(player) and (not player.vocation.can_craft_on_a_quest):
        return Strings.cannot_shop_on_a_quest
    item_pos = int(item_pos_str)
    if item_pos > 10:
        return "Invalid item (max item: 10)"
    items = db().get_player_items(player.player_id)
    if len(items) >= player.get_inventory_size():
        return "Inventory already full!"
    item_type = db().get_smithy_items()[item_pos - 1]
    price = int(__get_item_type_value(item_type, player) * (1 if player.guild_level() < 9 else 0.5))
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
    rarity: int = choice((0, 0, 0, 0, 1)) if player.guild_level() < 7 else 1
    item = Equipment.generate(player.level, item_type, rarity)
    item_id = db().add_item(item, player)
    item.equipment_id = item_id
    items.append(item)
    player.money -= price
    db().update_player_data(player)
    return Strings.item_bought.format(item=item.name, money=price)


def use_consumable(context: UserContext, item_pos_str: str) -> str:
    player = get_player(db, context)
    item_pos = int(item_pos_str)
    text, used = player.use_consumable(item_pos)
    if used:
        db().update_player_data(player)
    return text


def force_combat(context: UserContext) -> str:
    player = get_player(db, context)
    if Explore.is_set(player.flags):
        return Strings.already_exploring
    player.set_flag(ForcedCombat)
    db().update_player_data(player)
    return Strings.force_combat


def force_qte(context: UserContext) -> str:
    player = get_player(db, context)
    if ForcedCombat.is_set(player.flags):
        return Strings.already_hunting
    player.set_flag(Explore)
    db().update_player_data(player)
    return Strings.explore_text


def check_auctions(context: UserContext) -> str:
    try:
        auctions = db().get_auctions()
        if not auctions:
            return Strings.no_auctions_yet
        return "Here are all auctions:\n\n" + "\n\n".join(str(x) for x in auctions)
    except KeyError:
        return Strings.no_auctions_yet


def check_my_auctions(context: UserContext) -> str:
    player = get_player(db, context)
    auctions = db().get_player_auctions(player)
    if not auctions:
        return Strings.no_auctions_yet
    return "Here are all your auctions:\n\n" + "\n".join(str(x) for x in auctions)


def create_auction(context: UserContext, item_pos_str: str, starting_bid_str: str) -> str:
    player = get_player(db, context)
    items = __get_items(player)
    item_pos = int(item_pos_str)
    if item_pos > len(items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if player.is_item_equipped(item):
        return Strings.cannot_sell_equipped_item
    starting_bid = int(starting_bid_str)
    if db().get_auction_from_item(item):
        return Strings.auction_already_exists
    auction = Auction.create_default(player, item, starting_bid)
    db().add_auction(auction)
    return Strings.auction_created.format(item=item.name)


def bid_on_auction(context: UserContext, auction_id_str: str, bid_str: str) -> str:
    player = get_player(db, context)
    auction_id = int(auction_id_str)
    bid = int(bid_str)
    if player.money < bid:
        return Strings.not_enough_money.format(amount=bid - player.money)
    try:
        auction = db().get_auction_from_id(auction_id)
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="Auction")
    if auction.auctioneer == player:
        return Strings.cant_bid_on_own_auction
    if auction.is_expired():
        return Strings.auction_is_expired
    if not auction.place_bid(player, bid):
        return Strings.bid_too_low + str(auction.best_bid + 1)
    db().update_auction(auction)
    return Strings.bid_placed.format(amount=bid, item=auction.item.name)


def check_auction(context: UserContext, auction_id_str: str) -> str:
    try:
        auction_id = int(auction_id_str)
        auction = db().get_auction_from_id(auction_id)
        return auction.verbose_string()
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="Auction")


def send_gift_to_player(context: UserContext, player_name: str, item_pos_str: str) -> str:
    # get player
    player = get_player(db, context)
    # get recipient
    message, recipient = __get_player_from_name(player_name)
    if message:
        return message
    if recipient.name == player.name:
        return Strings.no_self_gift
    # get specified item
    items = __get_items(player)
    item_pos = int(item_pos_str)
    if item_pos > len(items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if player.is_item_equipped(item):
        return Strings.cannot_gift_equipped_item
    # check if there is enough space
    recipient_items = db().get_player_items(recipient.player_id)
    if len(recipient_items) >= recipient.get_inventory_size():
        return f"{recipient.name} does not have enough space for your item!"
    # transfer item
    db().update_item(item, recipient)
    recipient_items.append(item)
    items.pop(item_pos - 1)
    # notify
    db().create_and_add_notification(
        recipient,
        f"{player.name} gifted you a *{item.name}*!"
    )
    return f"successfully gifted *{item.name}* to {recipient.name}."


def duel_invite(context: UserContext, player_name: str) -> str:
    # get player
    player = get_player(db, context)
    # get target
    message, target = __get_player_from_name(player_name)
    if message:
        return message
    if target.name == player.name:
        return Strings.no_self_duel
    db().add_duel_invite(player, target)
    log.info(f"{player.name} sent a duel invite to {target.name}")
    return Strings.duel_invite_sent.format(name=target.name)


def duel_accept(context: UserContext, player_name: str) -> str:
    # get player
    player = get_player(db, context)
    # get challenger
    message, challenger = __get_player_from_name(player_name)
    if message:
        return message
    # check if the duel invite exists
    if not db().duel_invite_exists(challenger, player):
        return Strings.not_invited_to_duel.format(name=challenger.name)
    # check that both player are in town
    player_ac = db().get_player_adventure_container(player)
    challenger_ac = db().get_player_adventure_container(challenger)
    if player_ac.quest is not None:
        return Strings.you_must_be_in_town
    if challenger_ac.quest is not None:
        return Strings.opponent_must_be_in_town
    # do combat
    players = [player, challenger]
    db().delete_duel_invite(challenger, player)
    combat = CombatContainer(players, helpers={player: None, challenger: None})
    combat_log = combat.fight()
    log.info(f"{player.name} & {challenger.name} dueled.")
    # give xp to both players, money to the winner + restore health
    for p in players:
        p.add_xp(100)
        if not p.is_dead():
            p.add_money(100)
        p.hp_percent = 1.0
        db().update_player_data(p)
    # notify participants
    text = "Duel!\n\n" + combat_log
    db().create_and_add_notification(challenger, text, "Duel log")
    return text


def duel_reject(context: UserContext, player_name: str) -> str:
    # get player
    player = get_player(db, context)
    # get challenger
    message, challenger = __get_player_from_name(player_name)
    if message:
        return message
    # check if the duel invite exists
    if not db().duel_invite_exists(challenger, player):
        return Strings.not_invited_to_duel.format(name=challenger.name)
    # reject & notify
    db().delete_duel_invite(challenger, player)
    db().create_and_add_notification(
        challenger,
        Strings.duel_invite_reject_notification.format(player.name),
        "Duel log"
    )
    return Strings.duel_invite_reject.format(name=challenger.name)


def __get_player_stats_string(player: Player) -> str:
    # add base stats
    string = f"*{player.name}'s stats*\n\nTotal Base Damage:\n_{player.get_base_attack_damage()}_\n\nTotal Base Resist:\n_{player.get_base_attack_resistance()}_\n\nTotal Weight: {player.get_delay()} Kg"
    # add temporary buffs / de-buffs
    if CursedFlag.is_set(player.flags):
        string += "\n\nCursed: -2 to quest rolls."
    elif HexedFlag.is_set(player.flags):
        string += "\n\nHexed: -1 to quest rolls."
    if AlloyGlitchFlag3.is_set(player.flags):
        string += "\n\nAlloy Glitch (3): x3.375 BA multiplier"
    elif AlloyGlitchFlag2.is_set(player.flags):
        string += "\n\nAlloy Glitch (2): x2.25 BA multiplier"
    elif AlloyGlitchFlag1.is_set(player.flags):
        string += "\n\nAlloy Glitch (1): x1.5 BA multiplier"
    if LuckFlag2.is_set(player.flags):
        string += "\n\nBlessed (2): +2 to quest rolls."
    elif LuckFlag1.is_set(player.flags):
        string += "\n\nBlessed (1): +1 to quest rolls."
    if StrengthBuff.is_set(player.flags):
        string += "\n\nStrength buff: slash, blunt & pierce damage x1.5"
    if OccultBuff.is_set(player.flags):
        string += "\n\nOccult buff: occult damage x2"
    if FireBuff.is_set(player.flags):
        string += "\n\nFire buff: fire damage x2"
    if IceBuff.is_set(player.flags):
        string += "\n\nIce buff: ice damage x2"
    if AcidBuff.is_set(player.flags):
        string += "\n\nAcid buff: acid damage x2"
    if ElectricBuff.is_set(player.flags):
        string += "\n\nElectric buff: electric damage x2"
    if MightBuff3.is_set(player.flags):
        string += "\n\nMight buff (3): all damage x2.5"
    elif MightBuff2.is_set(player.flags):
        string += "\n\nMight buff (2): all damage x2"
    elif MightBuff1.is_set(player.flags):
        string += "\n\nMight buff (1): all damage x1.5"
    if SwiftBuff3.is_set(player.flags):
        string += "\n\nSwift buff (3): weight -45 kg"
    elif SwiftBuff2.is_set(player.flags):
        string += "\n\nSwift buff (2): weight -30 kg"
    elif SwiftBuff1.is_set(player.flags):
        string += "\n\nSwift buff (1): weight -15 kg"
    # add perks (if the player has any)
    perks = player.get_modifiers()
    perks.sort(key=lambda perk: (perk.RARITY, perk.NAME, perk.strength))
    if not perks:
        return string
    return string + f"\n\n*Perks*:\n\n{'\n\n'.join(str(x) for x in perks)}"


def check_player_stats(context: UserContext, *args) -> str:
    if len(args) > 0:
        try:
            message, player = __get_player_from_name(args[0])
            if message:
                return message
            return __get_player_stats_string(player)
        except KeyError:
            return Strings.named_object_not_exist.format(obj="player", name=args[0])
    else:
        player = get_player(db, context)
        return __get_player_stats_string(player)


def change_vocation(context: UserContext, vocation_id1_str: str, *args):
    try:
        # get player
        player = get_player(db, context)
        # validate if player can change vocation
        if player.level < 5:
            return "You haven't unlocked vocations yet!"
        if db().is_player_on_a_quest(player):
            return Strings.cannot_change_vocation_on_quest
        time_since_last_switch = datetime.now() - player.last_guild_switch
        if time_since_last_switch < SWITCH_DELAY:
            return Strings.switched_too_recently.format(hours=(SWITCH_DELAY.total_seconds() - time_since_last_switch.total_seconds()) // 3600)
        # convert strings to ints
        if len(args) > 0:
            vocation_id2_str = args[0]
        else:
            vocation_id2_str = 1
        vocation_ids = [int(vocation_id1_str), int(vocation_id2_str)]
        if vocation_ids[0] == vocation_ids[1]:
            return "You can't use 2 of the same vocation!"
        # equip vocations
        vocations = [Vocation.get_correct_vocation_tier(vid, player) for vid in vocation_ids[:(player.get_vocation_limit())]]
        player.equip_vocations(vocations)
        player.last_guild_switch = datetime.now()
        db().update_player_data(player)
        return f"Activated vocations: {" & ".join([x.name for x in vocations])}"
    except ValueError as e:
        return str(e)


def upgrade_vocation(context: UserContext, vocation_id_str: str):
    try:
        player = get_player(db, context)
        # get basic inputs
        vocation_id: int = int(vocation_id_str)
        vocation = Vocation.get_correct_vocation_tier(vocation_id, player)
        # do checks
        if vocation.level == Vocation.MAX_LEVEL:
            return f"Vocation '{vocation.name}' is already at max level ({Vocation.MAX_LEVEL})."
        price = vocation.get_upgrade_cost()
        if price > player.money:
            return Strings.not_enough_money.format(amount=price-player.money)
        # actually upgrade the vocation
        player.upgrade_vocation(vocation_id)
        # re-equip vocations
        vocations = player.vocation.original_vocations
        new_vocations: list[Vocation] = []
        for v in vocations:
            new_vocations.append(Vocation.get_correct_vocation_tier(v.vocation_id, player))
        player.equip_vocations(new_vocations)
        # pay & save player data
        player.money -= price
        db().update_player_data(player)
        return f"Upgraded vocation *{vocation.name}* to *{vocation.get_next_rank().get_rank_string()}*"
    except ValueError as e:
        return str(e)


def cancel_quest(context: UserContext):
    player = get_player(db, context)
    ac = db().get_player_adventure_container(player)
    if not ac.is_on_a_quest():
        return Strings.not_on_a_quest
    player.set_flag(QuestCanceled)
    db().update_player_data(player)
    return Strings.quest_canceled


USER_COMMANDS: dict[str, str | IFW | dict] = {
    "check": {
        "player": IFW(None, check_player, "Shows player stats.", optional_args=[player_arg("Player name")]),
        "board": IFW(None, check_board, "Shows the quest board."),
        "quest": IFW(None, check_current_quest, "Shows the current quest name, objective & duration."),
        "zone": IFW([integer_arg("Zone number")], check_zone, "Describes a Zone."),
        "enemy": IFW([integer_arg("Zone number")], check_enemy, "Describes an Enemy."),
        "guild": IFW(None, check_guild, "Shows guild (your guild by default).", optional_args=[guild_arg("Guild")]),
        "stats": IFW(None, check_player_stats, "Shows player perks.", optional_args=[player_arg("Player name")]),
        "artifact": IFW([integer_arg("Artifact number")], check_artifact, "Describes an Artifact."),
        "prices": IFW(None, check_prices, "Shows all the prices."),
        "my": {
            "auctions": IFW(None, check_my_auctions, "Shows your auctions."),
        },
        "auctions": IFW(None, check_auctions, "Shows all auctions."),
        "auction": IFW([integer_arg("Auction")], check_auction, "Show a specific auction."),
        "members": IFW(None, check_guild_members, "Shows the members of the given guild", optional_args=[guild_arg("Guild")]),
        "item": IFW([integer_arg("Item")], check_item, "Shows the specified item stats"),
        "market": IFW(None, show_market, "Shows the daily consumables you can buy."),
        "smithy": IFW(None, show_smithy, "Shows the daily equipment you can buy."),
    },
    "cancel": {
        "quest": IFW(None, cancel_quest, "Cancels the current quest.")
    },
    "create": {
        "character": IFW(None, start_character_creation, "Create your character."),
        "guild": IFW(None, start_guild_creation, f"Create your own Guild (cost: {ContentMeta.get('guilds.creation_cost')} {MONEY})."),
        "auction": IFW([integer_arg("item"), integer_arg("Starting bid")], create_auction, "auctions the selected item."),
    },
    "bid": IFW([integer_arg("Auction id"), integer_arg("Bid")], bid_on_auction, "bid on the selected auction."),
    "upgrade": {
        "gear": IFW(None, upgrade, "Upgrade your gear.", default_args={"obj": "gear"}),
        "home": IFW(None, upgrade, "Upgrade your home.", default_args={"obj": "home"}),
        "guild": IFW(None, upgrade_guild, "Upgrade your guild."),
        "vocation": IFW([integer_arg("Vocation id")], upgrade_vocation, "Upgrade your vocations.")
    },
    "edit": {
        "character": IFW(None, modify_player, "Modify your character (for a price).",),
        "guild": IFW(None, modify_guild, "Modify your guild (for a price).",),
    },
    "select": {
        "vocations": IFW([integer_arg("Vocation id")], change_vocation, "Select your vocations", optional_args=[integer_arg("Vocation id")])
    },
    "join": IFW([guild_arg("Guild")], join_guild, "Join guild with the given name."),
    "embark": IFW([integer_arg("Zone number")], embark_on_quest, "Starts quest in specified zone."),
    "kick": IFW([player_arg("player")], kick, "Kicks player from your own guild."),
    "donate": IFW([player_arg("recipient"), integer_arg("Amount")], donate, f"donates 'amount' of {MONEY} to player 'recipient'."),
    "gift": IFW([player_arg("recipient"), integer_arg("Item")], send_gift_to_player, f"gifts an item to a player."),
    "cast": IFW([RWE("spell name", SPELL_NAME_REGEX, Strings.spell_name_validation_error)], cast_spell, "Cast a spell.", optional_args=[RWE("spell args", None, None)]),
    "grimoire": IFW(None, return_string, "Shows & describes all spells", default_args={"string": __list_spells()}),
    "rank": {
        "guilds": IFW(None, rank_guilds, "Shows the top 20 guilds, ranked based on their prestige."),
        "players": IFW(None, rank_players, "Shows the top 20 players, ranked based on their renown."),
        "tourney": IFW(None, rank_tourney, "Shows the top 10 guilds competing in the tourney. Only the top 3 will win."),
    },
    "message": {
        "player": IFW([player_arg("player name")], send_message_to_player, "Send message to a single player."),
        "guild": IFW(None, send_message_to_owned_guild, "Send message to every member of your owned guild.")
    },
    "duel": {
        "invite": IFW([player_arg("player name")], duel_invite, "Send duel invite to a player."),
        "accept": IFW([player_arg("player name")], duel_accept, "Accept a duel invite."),
        "reject": IFW([player_arg("player name")], duel_reject, "Reject a duel invite.")
    },
    "assemble": {
        "artifact": IFW(None, assemble_artifact, f"Assemble an artifact using {REQUIRED_PIECES} artifact pieces")
    },
    "inventory": IFW(None, inventory, "Shows all your items"),
    "equip": IFW([integer_arg("Item")], equip_item, "Equip an item from your inventory"),
    "unequip": IFW(None, unequip_all_items, "Unequip all items"),
    "sell": IFW([integer_arg("Item")], sell_item, "Sell an item from your inventory."),
    "buy": IFW([integer_arg("Item")], market_buy, "Buy something from the market."),
    "craft": IFW([integer_arg("Item")], smithy_craft, "Craft something at the smithy."),
    "reroll": IFW([integer_arg("Item")], reroll_item, "Reroll an item from your inventory"),
    "enchant": IFW([integer_arg("Item")], enchant_item, "Add a perk to an item from your inventory"),
    "consume": IFW([integer_arg("Item")], use_consumable, "Use an item in your satchel"),
    "stance": IFW([RWE("stance", None, None)], switch_stance, "Switches you stance to the given stance"),
    "qte": IFW([integer_arg("Option")], do_quick_time_event, "Do a quick time event"),
    "retire": IFW(None, set_last_update, f"Take a 1 year vacation (pauses the game for 1 year) (cost: 100 {MONEY})", default_args={"delta": timedelta(days=365), "msg": Strings.you_retired, "cost": 100}),
    "back": {
        "to": {
            "work": IFW(None, set_last_update, "Come back from your vacation", default_args={"delta": None, "msg": Strings.you_came_back})
        }
    },
    "minigames": IFW(None, return_string, "Shows all the minigames", default_args={"string": __list_minigames()}),
    "vocations": IFW(None, list_vocations, "Shows all vocations"),
    "hunt": IFW(None, force_combat, "Hunt for a strong enemy"),
    "explore": IFW(None, force_qte, "Force a QTE"),
    "play": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], start_minigame, "Play the specified minigame."),
    "explain": {
        "minigame": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], explain_minigame, "Explains how the specified minigame works."),
    },
    "bestiary": IFW([integer_arg("Zone number")], bestiary, "shows all enemies that can be found in the given zone."),
    "man": IFW([integer_arg("Page")], manual, "Shows the specified manual page.")
}

USER_PROCESSES: dict[str, tuple[tuple[str, Callable], ...]] = {
    "character creation": (
        (Strings.character_creation_get_name, process_get_character_name),
        (Strings.character_creation_get_description, process_get_character_description)
    ),
    "character editing": (
        (Strings.character_creation_get_name, process_get_character_name),
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
    ),
    "reroll confirm": (
        ("confirm", process_reroll_confirm),
    ),
    "enchant confirm": (
        ("confirm", process_enchant_confirm),
    ),
    "sell confirm": (
        ("confirm", process_sell_confirm),
    ),
}
