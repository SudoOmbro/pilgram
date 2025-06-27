import logging
import math
import random
import re
import json
from collections.abc import Callable
from collections import deque
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
    Progress,
    RAID_DELAY,
    Pet,
)
from pilgram.combat_classes import CombatContainer, Stats
from pilgram.equipment import Equipment, EquipmentType
from pilgram.flags import ForcedCombat, HexedFlag, CursedFlag, AlloyGlitchFlag3, AlloyGlitchFlag1, AlloyGlitchFlag2, \
    LuckFlag1, LuckFlag2, StrengthBuff, OccultBuff, FireBuff, IceBuff, AcidBuff, ElectricBuff, MightBuff3, MightBuff2, \
    MightBuff1, SwiftBuff3, SwiftBuff2, SwiftBuff1, QuestCanceled, Catching, InCrypt, Raiding, DeathwishMode
from pilgram.generics import AlreadyExists, PilgramDatabase
from pilgram.globals import (
    DESCRIPTION_REGEX,
    GUILD_NAME_REGEX,
    MINIGAME_NAME_REGEX,
    PLAYER_NAME_REGEX,
    POSITIVE_INTEGER_REGEX,
    SPELL_NAME_REGEX,
    ContentMeta, Slots,
)
from pilgram.modifiers import Modifier, get_all_modifiers, get_scaled_strength_modifier
from pilgram.spells import SPELLS
from pilgram.strings import MONEY, Strings, rewards_string
from pilgram.utils import read_text_file, read_update_interval, generate_random_eldritch_name, \
    get_nth_triangle_number_inverse, get_nth_triangle_number
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
HUNT_SANITY_COST: int = ContentMeta.get("hunt.sanity_cost")
ASCENSION_COST: int = ContentMeta.get("ascension.cost")
MAX_MARKET_ITEMS: int = ContentMeta.get("market.max_items")
PET_RENAME_COST: int = ContentMeta.get("pet.rename_cost")


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
        player_essences = player.essences.get(zone.zone_id, 0)
        if (player_progress != 0) or (player_essences != 0):
            text += f"> progress: {player_progress}, essence: {player_essences}\n"
    return text + "\n\n" + Strings.embark_underleveled + f"\n\n*Player*:\nlv. {player.level}, gear lv: {player.gear_level}\n\n{anomaly}"


def check_current_quest(context: UserContext) -> str:
    player = get_player(db, context)
    try:
        ac = db().get_player_adventure_container(player)
        if ac.quest is None:
            if InCrypt.is_set(player.flags):
                return Strings.in_crypt
            return Strings.not_on_a_quest
        return str(ac)
    except KeyError as e:
        return f"Fatal error: {e}"


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
            return str(player.guild) + f"\n\n_Bank: {player.guild.bank} {MONEY}_"
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
    player = get_player(db, context)
    context.end_process()
    if not get_yes_or_no(user_input):
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
    player = get_player(db, context)
    if db().is_player_on_a_quest(player):
        return Strings.already_on_a_quest
    if InCrypt.is_set(player.flags):
        return Strings.no_quest_while_in_crypt
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
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if get_yes_or_no(user_input):
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
    if target == player:
        return Strings.cant_kick_yourself
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
    if player.ascension < spell.level:
        return Strings.ascension_too_low
    if not spell.can_cast(player):
        return Strings.not_enough_power
    if not spell.check_args(extra_args):
        return Strings.not_enough_args.format(num=spell.required_args)
    try:
        result = spell.cast(player, extra_args)
        log.info(f"{player.name} casted {spell_name} on {extra_args}")
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


def withdraw(context: UserContext, amount_str: str) -> str:
    player = get_player(db, context)
    amount: int = int(amount_str)
    guild = db().get_owned_guild(player)
    if not guild:
        return Strings.guild_not_owned
    if amount <= 0:
        return Strings.invalid_money_amount
    if guild.bank < amount:
        return Strings.bank_not_enough_money
    # update money
    player.money += amount
    db().update_player_data(player)
    # update bank's money
    guild.bank -= amount
    db().update_guild(guild)
    # create a log
    guild.create_bank_log("withdrawal", player.player_id, amount)
    return Strings.withdrawal_successful.format(amm=amount_str)


def process_transactions(data):
    withdrawals = deque(maxlen=10)
    deposits = deque(maxlen=10)
    transactions = data.strip().split('\n')
    for transaction in transactions:
        try:
            data = json.loads(transaction)
            if data["transaction"] == "withdrawal":
                withdrawals.append(data)
            elif data["transaction"] == "deposit":
                deposits.append(data)
        except json.JSONDecodeError as e:
            return Strings.no_logs # there might actually be something deeper going on
    message = "Last 10 withdrawals:\n"
    for withdrawal in withdrawals:
            withdrawer = db().get_player_data(withdrawal['by']) # if the player withdrawed he must exist
            message += f"{withdrawal['amount']} {MONEY} ➡️ {withdrawer.name}\n"
    message += "\nLast 10 deposits:\n"
    for deposit in deposits:
            depositer = db().get_player_data(deposit['by']) # if the player deposited he must exist
            message += f"{depositer.name} ➡️ {deposit['amount']} {MONEY}\n"
    return message


def check_bank_logs(context: UserContext) -> str:
    player = get_player(db, context)
    guild = player.guild
    if not guild:
        return Strings.not_in_a_guild
    return process_transactions(guild.get_bank_logs_data())


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
    player = get_player(db, context)
    for target in context.get("targets"):
        db().create_and_add_notification(
            Player.create_default(target, str(target), ""),
            context.get("text").format(name=player.name) + message
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
    return "Grimoire:\n\n" + "\n\n".join(f"`{key}` | min power: {spell.required_power}, level: {spell.level} {(" | artifact pieces: " + str(spell.required_artifacts)) if spell.required_artifacts > 0 else ""}\n_{spell.description}_" for key, spell in SPELLS.items())


def list_vocations(context: UserContext) -> str:
    player = get_player(db, context)
    string: str = "Here are all your vocations:\n\n"
    for vocation in Vocation.ALL_ITEMS[1:]:
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


def __get_pets(player: Player) -> list[Pet]:
    pets = db().get_player_pets(player.player_id)
    pets.sort(key=lambda pet: (pet.level, pet.name))
    return pets


def inventory(context: UserContext) -> str:
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    return f"Items ({len(items)}/{player.get_inventory_size()}):\n\n{'\n'.join([f'{i + 1} - {Strings.get_item_icon(x.equipment_type.slot)}{' ✅' if player.is_item_equipped(x) else ''}| *{x.name}* (lv. {x.level})' for i, x in enumerate(items)])}"


def pets_inventory(context: UserContext) -> str:
    player = get_player(db, context)
    pets = __get_pets(player)
    if not pets:
        return Strings.no_pets_yet
    return f"Pets ({len(pets)}/{player.get_pet_inventory_size()}):\n\n{'\n'.join([f'{i+1} - {' ✅' if player.is_pet_equipped(x) else ''}| *{x.name}* (lv. {x.level})' for i, x in enumerate(pets)])}"


def __item_id_is_valid(item_id: int, items: list) -> bool:
    """ checks if given id is > 0 and withing the length of the given list of items """
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


def check_pet(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    items = __get_pets(player)
    if not items:
        return Strings.no_pets_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_pet
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
    if (item.level > player.level) and (item.equipment_type.slot != Slots.RELIC):
        return Strings.cannot_equip_higher_level_item
    player.equip_item(item)
    db().update_player_data(player)
    return Strings.item_equipped.format(item=item.name, slot=Strings.slots[item.equipment_type.slot])


def equip_pet(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    pets = __get_pets(player)
    if not pets:
        return Strings.no_pets_yet
    if not __item_id_is_valid(item_pos, pets):
        return Strings.invalid_pet
    pet = pets[item_pos - 1]
    player.equip_pet(pet)
    db().update_player_data(player)
    return Strings.pet_equipped.format(name=pet.name, race=pet.meta.name)


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
    price = item.get_reroll_price(player)
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
    context.set("item pos", item_pos)
    context.start_process("reroll confirm")
    return Strings.item_reroll_confirm.format(item=item.name, price=price)


def process_reroll_confirm(context: UserContext, user_input: str) -> str:
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if get_yes_or_no(user_input):
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        price = item.get_reroll_price(player)
        old_name = item.name
        item.reroll(player.vocation.reroll_stats_bonus, player.vocation.perk_rarity_bonus)
        if player.is_item_equipped(item):
            player.equip_item(item)
        player.money -= price
        text = ""
        if player.vocation.xp_on_reroll > 0:
            xp_am = player.add_xp(player.vocation.xp_on_reroll * max(item.level - item.rerolls, 1))
            text = rewards_string(xp_am, 0, 0)
        db().update_player_data(player)
        db().update_item(item, player)
        return Strings.item_rerolled.format(amount=price, old_name=old_name) + "\n\n" + str(item) + text
    return Strings.action_canceled.format(action="Reroll")


def enchant_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    if player.ascension == 0:
        return Strings.enchant_ascension_required
    if player.artifact_pieces < 1:
        return Strings.no_items_yet
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    if item.get_rarity() >= item.equipment_type.max_perks:
        return Strings.max_enchants_reached
    if db().get_auction_from_item(item):
        return Strings.cannot_enchant_auctioned_item
    context.set("item pos", item_pos)
    context.start_process("enchant confirm")
    return Strings.item_enchant_confirm.format(item=item.name)


def process_enchant_confirm(context: UserContext, user_input: str) -> str:
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if get_yes_or_no(user_input):
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


def sell_pet(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    pets = __get_pets(player)
    if not pets:
        return Strings.no_pets_yet
    if not __item_id_is_valid(item_pos, pets):
        return Strings.invalid_pet
    pet = pets[item_pos - 1]
    if player.is_pet_equipped(pet):
        return Strings.cannot_sell_equipped_pet
    context.set("item pos", item_pos)
    context.start_process("sellpet confirm")
    return Strings.item_sell_confirm.format(item=pet.name)


def sell_all(context: UserContext) -> str:
    player = db().get_player_data(context.get("id"))
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    context.start_process("sell all confirm")
    return Strings.sell_all_confirm


def process_sell_all_confirm(context: UserContext, user_input: str) -> str:
    context.end_process()
    if not get_yes_or_no(user_input):
        return Strings.action_canceled.format(action="sell all")
    player = db().get_player_data(context.get("id"))
    items = __get_items(player)
    result: str = ""
    total_money_gained: int = 0
    for pos in reversed(range(len(items))):
        item = items[pos - 1]
        if player.is_item_equipped(item) or db().get_auction_from_item(item) or (item.equipment_type.slot == Slots.RELIC):
            continue
        mult = 1 if player.guild_level() < 6 else 2
        money = int(item.get_value() * mult)
        money_am = player.add_money(money)
        total_money_gained += money_am
        items.pop(pos - 1)
        try:
            db().delete_item(item)
        except KeyError as e:
            return f"Error: {e}"
        result += f"Sold *{item.name}* for {money_am} {MONEY}\n"
    db().update_player_data(player)
    return result + f"\nTotal {MONEY} gained: {total_money_gained}"


def process_sell_confirm(context: UserContext, user_input: str) -> str:
    player = get_player(db, context)
    context.end_process()
    if get_yes_or_no(user_input):
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        if player.is_item_equipped(item):
            return Strings.cannot_sell_equipped_item
        if db().get_auction_from_item(item):
            return Strings.cannot_sell_auctioned_item
        mult = 1 if player.guild_level() < 6 else 2
        money = int(item.get_value() * mult)
        money_am = player.add_money(money)
        items.pop(item_pos - 1)
        db().update_player_data(player)
        try:
            db().delete_item(item)
        except KeyError as e:
            return f"Error: {e}"
        return Strings.item_sold.format(item=item.name, money=money_am)
    return Strings.action_canceled.format(action="Sell")


def process_sell_pet_confirm(context: UserContext, user_input: str) -> str:
    player = get_player(db, context)
    context.end_process()
    if get_yes_or_no(user_input):
        pets = __get_pets(player)
        item_pos = context.get("item pos")
        pet = pets[item_pos - 1]
        if player.is_pet_equipped(pet):
            return Strings.cannot_sell_equipped_pet
        mult = 1 if player.guild_level() < 6 else 2
        money = int(pet.get_value() * mult)
        money_am = player.add_money(money)
        pets.pop(item_pos - 1)
        db().update_player_data(player)
        try:
            db().delete_pet(pet)
        except KeyError as e:
            return f"Error: {e}"
        return Strings.item_sold.format(item=pet.name, money=money_am)
    return Strings.action_canceled.format(action="Sell")


def show_market(context: UserContext) -> str:
    items = db().get_market_items()
    text = "Here are today's market items:\n\n" + "\n".join(f"{i + 1}. " + str(x) for i, x in enumerate(items))
    return text


def __get_item_type_value(item_type: EquipmentType, player: Player):
    return item_type.value * player.level * 25


def show_smithy(context: UserContext) -> str:
    player = get_player(db, context)
    item_types = db().get_smithy_items()
    return "Here what the smithy can craft for you today:\n\n" + "\n".join(f"{i + 1}. {Strings.get_item_icon(x.slot)}| {x.name} (lv. {player.level}) - {__get_item_type_value(x, player)} {MONEY}" for i, x in enumerate(item_types))


def market_buy(context: UserContext, item_pos_str: str) -> str:
    player = get_player(db, context)
    if db().is_player_on_a_quest(player) and (not player.vocation.can_buy_on_a_quest):
        return Strings.cannot_shop_on_a_quest
    item_pos = int(item_pos_str)
    if item_pos > MAX_MARKET_ITEMS:
        return f"Invalid item (max item: {MAX_MARKET_ITEMS})"
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
    if item_pos > MAX_MARKET_ITEMS:
        return f"Invalid item (max item: {MAX_MARKET_ITEMS})"
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
    if ForcedCombat.is_set(player.flags):
        return Strings.already_hunting
    player.add_sanity(-HUNT_SANITY_COST - player.vocation.hunt_sanity_loss)
    player.set_flag(ForcedCombat)
    db().update_player_data(player)
    return Strings.force_combat


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
    challenger.team = 1
    db().delete_duel_invite(challenger, player)
    combat = CombatContainer(players, helpers={player: None, challenger: None})
    combat_log = combat.fight()
    challenger.team = 0
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
    string = f"*{player.name}'s stats*\n\n{player.get_stats()}\n\n"
    string += f"Total Base Damage:\n_{player.get_base_attack_damage()}_\n\nTotal Base Resist:\n_{player.get_base_attack_resistance()}_\n\nTotal Weight: {player.get_delay()} Kg"
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
        string += "\n\nBlessed (2): +3 to quest rolls."
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
    if DeathwishMode.is_set(player.flags):
        string += "\n\nDeathwish mode enabled!"
    # add perks (if the player has any)
    perks_string = ""
    for _, item in player.equipped_items.items():
        perks = item.modifiers
        perks.sort(key=lambda perk: (perk.RARITY, perk.NAME, perk.strength))
        if perks:
            perks_string += "\n\n".join(Strings.get_item_icon(item.equipment_type.slot) + " " + str(x) for x in perks)
        perks_string += "\n\n"
    if perks_string:
        return f"{string}\n\n*Perks*:\n\n{perks_string}"
    return string


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


def change_vocation(context: UserContext, vocation_id1_str: str, *args) -> str:
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
        # get default vocation 2 if not passed
        if len(args) > 0:
            vocation_id2_str = args[0]
        else:
            vocation_id2_str = "0"
        # transform strings to integers
        if vocation_id2_str == "0":
            vocation_ids = [int(vocation_id1_str)]
        else:
            vocation_ids = [int(vocation_id1_str), int(vocation_id2_str)]
            # duplication check
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


def upgrade_vocation(context: UserContext, vocation_id_str: str) -> str:
    try:
        player = get_player(db, context)
        # get basic inputs
        vocation_id: int = int(vocation_id_str)
        if vocation_id == 0:
            return "Vocation with id 0 does not exist"
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


def cancel_quest(context: UserContext) -> str:
    player = get_player(db, context)
    ac = db().get_player_adventure_container(player)
    if not ac.is_on_a_quest():
        return Strings.not_on_a_quest
    if ac.quest.is_raid:
        return Strings.cannot_cancel_raid
    player.set_flag(QuestCanceled)
    db().update_player_data(player)
    return Strings.quest_canceled


def sacrifice(context: UserContext) -> str:
    player = get_player(db, context)
    if player.hp_percent < 0.80:
        return "Your HP is too low!"
    if not db().is_player_on_a_quest(player):
        return "You can't sacrifice in town!"
    eldritch_truth = ""
    for _ in range(random.randint(5, 10)):
        eldritch_truth += f"{generate_random_eldritch_name()} "
    player.hp_percent -= 0.75
    player.add_sanity(-25)
    amount: int = int((player.get_max_hp() * 0.2) * player.level)
    amount_am = player.add_xp(amount)
    db().update_player_data(player)
    return f"You stab yourself with your ritual knife. Some eldritch truth is revealed to you:\n\n_{eldritch_truth}_\n\nYou gain {amount_am} XP."


def start_raid(context: UserContext, zone_id_str: str) -> str:
    player = get_player(db, context)
    # do basic checks
    guild = db().get_owned_guild(player)
    if not guild:
        return Strings.raid_guild_required
    if not guild.can_raid():
        return Strings.too_many_raids.format(days=(RAID_DELAY - (datetime.now() - guild.last_raid)).days)
    if db().is_player_on_a_quest(player):
        return Strings.raid_on_quest
    available_members = db().get_avaible_players_for_raid(guild)
    if len(available_members) < 3:
        return Strings.raid_not_enough_players
    # confirm
    context.set("zone", int(zone_id_str))
    context.start_process("raid start")
    return f"The following players are avaiable for a raid:\n\n{"\n".join(x.name for x in available_members)}\n\nDo you confirm?"


def process_start_raid_confirm(context: UserContext, user_input: str) -> str:
    context.end_process()
    if not get_yes_or_no(user_input):
        return Strings.raid_cancel
    player = get_player(db, context)
    guild = db().get_owned_guild(player)
    available_members = db().get_avaible_players_for_raid(guild)
    # get zone & quest
    zone_id: int = context.get("zone")
    quest = db().get_quest(-zone_id)
    finish_time = datetime.now() + timedelta(days=1)
    # actually start the raid
    for member in available_members:
        ac = db().get_player_adventure_container(member)
        member.set_flag(Raiding)
        ac.quest = quest
        ac.finish_time = finish_time
        db().update_player_data(member)
        if member == player:
            db().update_quest_progress(ac)
        else:
            db().update_quest_progress(ac, last_update=finish_time + timedelta(hours=1) + timedelta(minutes=random.randint(-30, 30)))
    log.info(f"Player {player.name} started raid in zone {zone_id}")
    return Strings.raid_started.format(zone=quest.zone.zone_name)


def delete_guild(context: UserContext) -> str:
    player = get_player(db, context)
    guild = db().get_owned_guild(player)
    if not guild:
        return Strings.no_guild_yet
    context.start_process("delete guild")
    return Strings.are_you_sure_action.format(action="disband your Guild")


def process_delete_guild_confirm(context: UserContext, user_input: str) -> str:
    context.end_process()
    if not get_yes_or_no(user_input):
        return Strings.action_canceled.format(action="Guild deletion")
    player = get_player(db, context)
    guild = db().get_owned_guild(player)
    members = db().get_guild_members_data(guild)
    for _, name, _ in members:
        member = db().get_player_from_name(name)
        db().create_and_add_notification(member, f"Your guild ({guild.name}) was deleted!")
        member.guild = None
        db().update_player_data(member)
    db().delete_guild(guild)
    return Strings.guild_deleted


def crypt(context: UserContext) -> str:
    player = get_player(db, context)
    ac = db().get_player_adventure_container(player)
    if ac.is_on_a_quest():
        return Strings.no_crypt_while_questing
    if InCrypt.is_set(player.flags):
        player.unset_flag(InCrypt)
        db().update_player_data(player)
        return Strings.exit_crypt
    player.set_flag(InCrypt)
    db().update_player_data(player)
    return Strings.entered_crypt


def ascension(context: UserContext) -> str:
    player = get_player(db, context)
    if not player.can_ascend():
        return Strings.ascension_level_too_low + f" (lv >= {player.get_ascension_level()})"
    if player.artifact_pieces < ASCENSION_COST:
        return Strings.ascension_not_enough_artifacts
    ac = db().get_player_adventure_container(player)
    if ac.is_on_a_quest():
        return Strings.ascension_on_quest
    context.start_process("ascension")
    return Strings.ascension_confirm


def process_ascension_confirm(context: UserContext, user_input: str) -> str:
    context.end_process()
    if not get_yes_or_no(user_input):
        return Strings.action_canceled.format(action="Guild deletion")
    player = get_player(db, context)
    player.artifact_pieces -= ASCENSION_COST
    # reset & increase ascension level
    player.level = 1
    player.xp = 0
    player.money = 1000
    player.gear_level = 1
    player.ascension += 1
    player.renown = 0
    player.equip_vocations([])
    player.progress = Progress({})
    player.hp_percent = 1.0
    # increase player stats by using essences
    remaining_essences: dict[int, int] = {}
    for zone_id, amount in player.essences.items():
        levels = get_nth_triangle_number_inverse(amount)
        remaining_essences[zone_id] = player.essences[zone_id] - get_nth_triangle_number(levels)
        zone = db().get_zone(zone_id)
        if zone.extra_data.get("essence", None):
            # if the zone the essences came from has defined essence values, then increase the stats defined there
            new_stats = Stats.create_default(base=0)
            for stat, value in zone.extra_data["essence"].items():
                if stat not in new_stats.__dict__:
                    log.error(f"Stat '{stat}' as defined in zone {zone_id} essence dict does not exist")
                    continue
                new_stats = new_stats.add_single_value(stat, int(value * levels))
        else:
            # if the zone the essences came from does not have defined essence values, then add random stats
            new_stats = Stats.generate_random(0, levels)
        player.stats += new_stats
    player.essences = remaining_essences
    # remove all items except for relics
    player.equipped_items = {}
    items = __get_items(player)
    if items:
        for pos in reversed(range(len(items))):
            item = items[pos - 1]
            if item.equipment_type.slot == Slots.RELIC:
                continue
            auction: Auction = db().get_auction_from_item(item)
            if auction:
                db().delete_auction(auction)
            items.pop(pos - 1)
            try:
                db().delete_item(item)
            except KeyError as e:
                return f"Error: {e}"
    db().update_player_data(player)
    return Strings.ascension_success.format(level=player.ascension)


def records(context: UserContext, *args) -> str:
    if len(args) > 0:
        try:
            message, player = __get_player_from_name(args[0])
            if message:
                return message
        except KeyError:
            return Strings.named_object_not_exist.format(obj="player", name=args[0])
    else:
        player = get_player(db, context)
    return f"{player.name}'s records:\n\n*max level*: {player.max_level_reached}\n*max {MONEY}*: {player.max_money_reached}\n*max renown*: {player.max_renown_reached}"


def toggle_deathwish_mode(context: UserContext) -> str:
    player = get_player(db, context)
    ac = db().get_player_adventure_container(player)
    if ac.is_on_a_quest() or InCrypt.is_set(player.flags):
        return Strings.no_deathwish_toggle_on_quest
    if DeathwishMode.is_set(player.flags):
        player.unset_flag(DeathwishMode)
        db().update_player_data(player)
        return Strings.deathwish_disabled
    player.set_flag(DeathwishMode)
    db().update_player_data(player)
    return Strings.deathwish_enabled


def check_notice_board(context: UserContext) -> str:
    notice_board = db().get_message_board()
    if notice_board:
        return "\n\n".join(notice_board)
    return "No messages in the notice board"


def add_message_to_notice_board(context: UserContext, message: str) -> str:
    if len(message) > 240:
        return "Message too long"
    player = get_player(db, context)
    if player.money >= 100:
        player.money -= 100
    else:
        return "100 BA required. Not enough money."
    db().update_notice_board(player, message)
    return f"Your message '{message}' has been added to the notice board."


def temper_item(context: UserContext, item_pos_str: str) -> str:
    item_pos = int(item_pos_str)
    player = get_player(db, context)
    items = __get_items(player)
    if not items:
        return Strings.no_items_yet
    if not __item_id_is_valid(item_pos, items):
        return Strings.invalid_item
    item = items[item_pos - 1]
    price = item.get_reroll_price(player)
    if player.money < price:
        return Strings.not_enough_money.format(amount=price - player.money)
    context.set("item pos", item_pos)
    context.start_process("temper confirm")
    return Strings.item_temper_confirm.format(item=item.name, price=price)


def process_temper_confirm(context: UserContext, user_input: str) -> str:
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    context.end_process()
    if get_yes_or_no(user_input):
        items = __get_items(player)
        item_pos = context.get("item pos")
        item = items[item_pos - 1]
        price = item.get_reroll_price(player)
        item.temper()
        if player.is_item_equipped(item):
            player.equip_item(item)
        player.money -= price
        text = ""
        if player.vocation.xp_on_reroll > 0:
            xp_am = player.add_xp(player.vocation.xp_on_reroll * max(item.level - item.rerolls, 1))
            text = rewards_string(xp_am, 0, 0)
        db().update_player_data(player)
        db().update_item(item, player)
        return Strings.item_tempered.format(amount=price, item=item.name) + text
    return Strings.action_canceled.format(action="Temper")


def catch_pet(context: UserContext) -> str:
    player = get_player(db, context)
    if Catching.is_set(player.flags):
        return Strings.already_catching
    pets = __get_pets(player)
    if len(pets) >= player.get_pet_inventory_size():
        return Strings.max_pets_reached
    player.set_flag(Catching)
    db().update_player_data(player)
    return Strings.pet_catch_start


def rename_pet(context: UserContext, pet_pos_str: str) -> str:
    player = get_player(db, context)
    if player.money < PET_RENAME_COST:
        return Strings.not_enough_money.format(amount=PET_RENAME_COST-player.money)
    pet_pos = int(pet_pos_str)
    pets = __get_pets(player)
    if not __item_id_is_valid(pet_pos, pets):
        return Strings.invalid_pet
    pet = pets[pet_pos - 1]
    context.start_process("rename pet")
    context.set("pet pos", pet_pos - 1)
    return Strings.pet_start_rename.format(name=pet.get_name())


def rename_pet_process(context: UserContext, user_input: str) -> str:
    if not re.match(PLAYER_NAME_REGEX, user_input):
        return Strings.player_name_validation_error
    player = db().get_player_data(context.get("id"))  # player must exist to get to this point
    player.money -= PET_RENAME_COST
    pet_pos = context.get("pet pos")
    pets = __get_pets(player)
    pet = pets[pet_pos]
    old_name = pet.name
    pet.name = user_input
    if player.is_pet_equipped(pet):
        player.pet = pet
    db().update_pet(pet, player)
    db().update_player_data(player)
    context.end_process()
    return Strings.pet_renamed.format(oldname=old_name, newname=user_input, amount=PET_RENAME_COST)


def list_perks(context: UserContext, page_str: str) -> str:
    player = get_player(db, context)
    page = int(page_str) - 1
    pages: int = math.ceil(len(get_all_modifiers()) / 10)
    if page >= pages:
        return "Invalid page"
    starting_id: int = page * 10
    modifiers: list[Modifier] = []
    for i in range(starting_id, starting_id + 10):
        try:
            m: Modifier = get_scaled_strength_modifier(i, player.level)
            modifiers.append(m)
        except:
            break
    return f"Perks ({page + 1}/{pages})\n_Note that the reported numbers are scaled to your level ({player.level})_\n\n" + "\n\n".join(f"{m.ID + 1} - {m}" for m in modifiers)


USER_COMMANDS: dict[str, str | IFW | dict] = {
    "check": {
        "player": IFW(None, check_player, "Shows player stats.", optional_args=[player_arg("Player name")]),
        "records": IFW(None, records, "Shows player records", optional_args=[player_arg("Player name")]),
        "board": IFW(None, check_board, "Shows quest board."),
        "quest": IFW(None, check_current_quest, "Shows current quest name, objective & duration."),
        "zone": IFW([integer_arg("Zone number")], check_zone, "Describes a Zone."),
        "enemy": IFW([integer_arg("Zone number")], check_enemy, "Describes an Enemy."),
        "guild": IFW(None, check_guild, "Shows guild.", optional_args=[guild_arg("Guild")]),
        "stats": IFW(None, check_player_stats, "Shows player perks.", optional_args=[player_arg("Player name")]),
        "artifact": IFW([integer_arg("Artifact number")], check_artifact, "Describes an Artifact."),
        "prices": IFW(None, check_prices, "Shows all the prices."),
        "my": {
            "auctions": IFW(None, check_my_auctions, "Shows your auctions."),
        },
        "auctions": IFW(None, check_auctions, "Shows all auctions."),
        "auction": IFW([integer_arg("Auction")], check_auction, "Show a specific auction."),
        "members": IFW(None, check_guild_members, "Shows the members of the given guild", optional_args=[guild_arg("Guild")]),
        "item": IFW([integer_arg("Item")], check_item, "Shows specified item stats"),
        "pet": IFW([integer_arg("Pet")], check_pet, "Shows specified pet stats"),
        "market": IFW(None, show_market, "Shows daily consumables you can buy."),
        "smithy": IFW(None, show_smithy, "Shows daily items you can buy."),
        "notices": IFW(None, check_notice_board, "Shows notice board.")
    },
    "post": IFW([RWE("message", None, None)], add_message_to_notice_board, "post message on notice board"),
    "sacrifice": IFW(None, sacrifice, "Sacrifice 75% of HP for XP."),
    "ascension": IFW(None, ascension, "Use 10 artifact pieces to ascend"),
    "raid": IFW([integer_arg("Zone number")], start_raid, "Start a raid with your guild members"),
    "crypt": IFW(None, crypt, "Enter the crypt"),
    "deathwish": IFW(None, toggle_deathwish_mode, "Toggle Deathwish mode"),
    "cancel": {
        "quest": IFW(None, cancel_quest, "Cancels current quest.")
    },
    "create": {
        "character": IFW(None, start_character_creation, "Create your character."),
        "guild": IFW(None, start_guild_creation, f"Create your own Guild (cost: {ContentMeta.get('guilds.creation_cost')} {MONEY})."),
        "auction": IFW([integer_arg("item"), integer_arg("Starting bid")], create_auction, "auctions the selected item."),
    },
    "disband": IFW(None, delete_guild, "Disband your guild"),
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
        "vocations": IFW([integer_arg("Vocation id")], change_vocation, "Select your vocations", optional_args=[integer_arg("Vocation id")]),
        "pet": IFW([integer_arg("Pet")], equip_pet, "Select pet from pet inventory"),
    },
    "join": IFW([guild_arg("Guild")], join_guild, "Join guild with the given name."),
    "embark": IFW([integer_arg("Zone number")], embark_on_quest, "Start quest in specified zone."),
    "kick": IFW([player_arg("player")], kick, "Kick player from your own guild."),
    "gift": {
        "ba": IFW([player_arg("recipient"), integer_arg("Amount")], donate, f"donate 'amount' of {MONEY} to player 'recipient'."),
        "item": IFW([player_arg("recipient"), integer_arg("Item")], send_gift_to_player, f"gift item to player.")
    },
    "withdraw": IFW([integer_arg("Amount")], withdraw, "Withdraw from your guild's bank"),
    "logs": IFW(None, check_bank_logs, "Shows last 10 withdrawals & deposits from guild bank"),
    "cast": IFW([RWE("spell name", SPELL_NAME_REGEX, Strings.spell_name_validation_error)], cast_spell, "Cast a spell.", optional_args=[RWE("target", None, None)]),
    "grimoire": IFW(None, return_string, "Shows & describes all spells", default_args={"string": __list_spells()}),
    "rank": {
        "guilds": IFW(None, rank_guilds, "Shows the top 20 guilds, ranked by prestige."),
        "players": IFW(None, rank_players, "Shows the top 20 players, ranked by renown."),
        "tourney": IFW(None, rank_tourney, "Shows the top 10 guilds in the current tourney."),
    },
    "message": {
        "player": IFW([player_arg("player name")], send_message_to_player, "message player."),
        "guild": IFW(None, send_message_to_owned_guild, "message everyone in your owned guild.")
    },
    "duel": {
        "invite": IFW([player_arg("player name")], duel_invite, "Send duel invite to player."),
        "accept": IFW([player_arg("player name")], duel_accept, "Accept duel invite."),
        "reject": IFW([player_arg("player name")], duel_reject, "Reject duel invite.")
    },
    "assemble": {
        "artifact": IFW(None, assemble_artifact, f"Assemble artifact using {REQUIRED_PIECES} artifact pieces")
    },
    "inventory": IFW(None, inventory, "Shows all your items"),
    "pets": IFW(None, pets_inventory, "Shows all your pets"),
    "rename": IFW([integer_arg("Pet")], rename_pet, "Rename a pet"),
    "equip": IFW([integer_arg("Item")], equip_item, "Equip item from inventory"),
    "unequip": IFW(None, unequip_all_items, "Unequip all items"),
    "sell": {
        "item": IFW([integer_arg("Item")], sell_item, "Sell item from inventory."),
        "pet": IFW([integer_arg("Pet")], sell_pet, "Sells a pet.")
    },
    "sellall": IFW(None, sell_all, "Sell all unused items from inventory."),
    "buy": IFW([integer_arg("Item")], market_buy, "Buy something from the market."),
    "craft": IFW([integer_arg("Item")], smithy_craft, "Craft something at the smithy."),
    "reroll": IFW([integer_arg("Item")], reroll_item, "Reroll an item from inventory"),
    "temper": IFW([integer_arg("Item")], temper_item, "Temper an item from inventory"),
    "enchant": IFW([integer_arg("Item")], enchant_item, "Add perk to an item from inventory"),
    "consume": IFW([integer_arg("Item")], use_consumable, "Use an item in your satchel"),
    "stance": IFW([RWE("stance", None, None)], switch_stance, "Switches stance to the given stance"),
    "qte": IFW([integer_arg("Option")], do_quick_time_event, "Do a quick time event"),
    "retire": IFW(None, set_last_update, f"Take a 1 year vacation for 100 BA", default_args={"delta": timedelta(days=365), "msg": Strings.you_retired, "cost": 100}),
    "back": {
        "to": {
            "work": IFW(None, set_last_update, "Come back from vacation", default_args={"delta": None, "msg": Strings.you_came_back})
        }
    },
    "minigames": IFW(None, return_string, "Shows all minigames", default_args={"string": __list_minigames()}),
    "vocations": IFW(None, list_vocations, "Shows all vocations"),
    "hunt": IFW(None, force_combat, "Hunt for a strong enemy"),
    "catch": IFW(None, catch_pet, "Try to catch pet"),
    "play": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], start_minigame, "Play specified minigame."),
    "explain": {
        "minigame": IFW([RWE("minigame name", MINIGAME_NAME_REGEX, Strings.invalid_minigame_name)], explain_minigame, "Explains specified minigame."),
    },
    "bestiary": IFW([integer_arg("Zone number")], bestiary, "shows all enemies that can be found in the given zone."),
    "man": IFW([integer_arg("Page")], manual, "Shows specified manual page."),
    "perks": IFW([integer_arg("Page")], list_perks, "Shows specified perks page.")
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
    "sellpet confirm": (
        ("confirm", process_sell_pet_confirm),
    ),
    "sell all confirm": (
        ("confirm", process_sell_all_confirm),
    ),
    "delete guild": (
        ("confirm", process_delete_guild_confirm),
    ),
    "raid start": (
        ("confirm", process_start_raid_confirm),
    ),
    "ascension": (
        ("confirm", process_ascension_confirm),
    ),
    "temper confirm": (
        ("confirm", process_temper_confirm),
    ),
    "rename pet": (
        ("rename", rename_pet_process),
    )
}

ALIASES: dict[str, str] = {
    "check self": "check player",
    "check mates": "check members",
    "donate": "gift ba"
}
