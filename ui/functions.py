import re
from datetime import datetime, timedelta
from functools import cache
from typing import Tuple, Dict, Union, Callable, Any

from orm.db import PilgramORMDatabase
from pilgram.classes import Player, AdventureContainer, Guild
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta, PLAYER_NAME_REGEX, GUILD_NAME_REGEX, ZONE_ID_REGEX, YES_NO_REGEX
from ui.strings import Strings
from ui.utils import UserContext, InterpreterFunctionWrapper as IFW, RegexWithErrorMessage as RWE


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def placeholder(context: UserContext) -> str:
    """ temporary placeholder function """
    return "hello world"


def echo(context: UserContext, text) -> str:
    try:
        username = context.get("username")
    except KeyError:
        username = "player"
    return f"{username} says: '{text}'"


def check_board(context: UserContext) -> str:
    zones = db().get_all_zones()
    return Strings.check_board + "\n".join(f"Zone {x.zone_id} - *{x.zone_name}* (lv. {x.level})" for x in zones)


def check_zone(context: UserContext, zone_id_str: int) -> str:
    try:
        zone = db().get_zone(int(zone_id_str))
        return str(zone)
    except KeyError:
        return Strings.zone_does_not_exist


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
        guild_id = db().get_guild(db().get_guild_id_from_name(guild_name))
        return str(guild_id)
    except KeyError:
        return Strings.named_object_not_exist.format(obj="guild", name=guild_name)


def check_current_guild(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.guild:
            return str(player.guild)
        else:
            return Strings.not_in_a_guild
    except KeyError:
        return Strings.no_character_yet

def start_character_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        return Strings.character_already_created.format(name=player.name)
    except KeyError:
        context.start_process("character creation")
        return Strings.character_creation_get_name


def process_get_character_name(context: UserContext, user_input) -> str:
    if not re.match(PLAYER_NAME_REGEX, user_input):
        return Strings.player_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return Strings.character_creation_get_description


def process_get_character_description(context: UserContext, user_input) -> str:
    player = Player.create_default(
        context.get("id"), context.get("name"), user_input
    )
    db().add_player(player)
    context.end_process()
    return Strings.welcome_to_the_world


def start_guild_creation(context: UserContext) -> str:
    try:
        player = db().get_player_data(context.get("id"))
        if player.guild and (player.guild.founder == player.player_id):
            return Strings.guild_already_created
        if player.money < ContentMeta.get("guilds.creation_cost"):
            return Strings.not_enough_money
        context.start_process("guild creation")
        return Strings.guild_creation_get_name
    except KeyError:
        return Strings.no_character_yet


def process_get_guild_name(context: UserContext, user_input) -> str:
    if not re.match(GUILD_NAME_REGEX, user_input):
        return Strings.guild_name_validation_error
    context.set("name", user_input)
    context.progress_process()
    return Strings.guild_creation_get_description


def process_get_guild_description(context: UserContext, user_input) -> str:
    player = db().get_player_data(context.get("id"))
    guild = Guild.create_default(player, context.get("name"), user_input)
    db().add_guild(guild)
    context.end_process()
    return Strings.welcome_to_the_world


def start_upgrade_process(context: UserContext, obj: str = "guild") -> str:
    try:
        player = db().get_player_data(context.get("id"))
        price: Union[int, None] = {
            "guild": lambda: player.guild.get_upgrade_required_money() if player.guild else None,
            "gear": lambda: player.get_gear_upgrade_required_money(),
            "home": lambda: player.get_home_upgrade_required_money(),
        }.get(obj)()
        if price is None:
            return Strings.no_guild_yet
        if obj == "guild" and player.guild.level == ContentMeta.get("guilds.max_level"):
            return Strings.guild_already_maxed
        if player.money < price:
            return Strings.not_enough_money
        context.start_process("upgrade")
        upgrade_func: Callable = {
            "guild": lambda: player.guild.upgrade(),
            "gear": lambda: player.upgrade_gear(),
            "home": lambda: player.upgrade_home()
        }.get(obj)
        context.set("func", upgrade_func)
        context.set("obj", obj)
        context.set("price", price)
        return Strings.upgrade_object_confirmation.format(obj=obj, price=price)
    except KeyError:
        return Strings.no_character_yet


def process_verify_upgrade_confirmation(context: UserContext, user_input: str) -> str:
    player = db().get_player_data(context.get("id"))
    if not re.match(YES_NO_REGEX, user_input):
        return Strings.yes_no_error
    if user_input == "no":
        context.end_process()
        return Strings.upgrade_cancelled
    context.get("func")()
    if context.get("obj") == "guild":
        db().update_guild(player.guild)
    db().update_player_data(player)
    context.end_process()
    return Strings.upgrade_successful.format(obj=context.get("obj"), paid=context.get("price"))


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
    zone_progress = player.progress.get_zone_progress(zone)
    quest = db().get_quest_from_number(zone, zone_progress)
    adventure_container = AdventureContainer(player, quest, datetime.now() + timedelta(hours=1))  # TODO adjust quest time
    db().update_quest_progress(adventure_container)
    return Strings.quest_embark.format(name=quest.name, descr=quest.description)


def __help_dfs(dictionary: Dict[str, Union[dict, IFW]], depth: int = 0) -> str:
    result_string: str = ""
    for key, value in dictionary.items():
        result_string += "> " * depth + f"`{key}`"
        if isinstance(value, dict):
            result_string += "\n" + __help_dfs(value, depth + 1)
        else:
            result_string += f"{value.generate_help_args_string()}-- {value.description}\n"
    return result_string


@cache
def help_function() -> str:
    """ basically do a depth first search on the COMMANDS dictionary and print what you find """
    return __help_dfs(COMMANDS, 0)


COMMANDS: Dict[str, Any] = {
    "check": {
        "board": IFW(None, check_board, "Shows the quest board"),
        "zone": IFW([RWE("zone number", ZONE_ID_REGEX, Strings.zone_id_error)], check_board, "Shows the quest board"),
        "guild": IFW([RWE("guild name", PLAYER_NAME_REGEX, Strings.guild_name_validation_error)], check_guild, "Shows the guild with the given name"),
        "self": IFW(None, check_self, "Shows your own stats"),
        "player": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], check_player, "Shows player stats"),
        "my": {
            "guild": IFW(None, check_board, "Shows your own guild"),
        }
    },
    "create": {
        "character": IFW(None, start_character_creation, "Create your character."),
        "guild": IFW(None, start_guild_creation, "Create your own Guild")
    },
    "upgrade": {
        "gear": IFW(None, start_upgrade_process, "Upgrade your gear", default_args={"obj": "gear"}),
        "guild": IFW(None, start_upgrade_process, "Upgrade your guild", default_args={"obj": "guild"}),
        "home": IFW(None, start_upgrade_process, "Upgrade your home", default_args={"obj": "home"}),
    },
    "modify": {
        "character": IFW(None, placeholder, "Modify your character for a price (1500 money)"),
        "guild": IFW(None, placeholder, "Modify your guild for a price (1500 money)")
    },
    "embark": IFW([RWE("zone number", ZONE_ID_REGEX, Strings.zone_id_error)], embark_on_quest, "Starts a quest in specified zone"),
    "kick": IFW([RWE("player name", PLAYER_NAME_REGEX, Strings.player_name_validation_error)], placeholder, "Kicks specified player from your own guild"),
    "help": IFW(None, help_function, "Shows and describes all commands"),
    "echo": IFW([RWE("text", None, None)], echo, "Repeats 'text'")
}

PROCESSES: Dict[str, Tuple[Callable, ...]] = {
    "character creation": (
        process_get_character_name,
        process_get_character_description
    ),
    "guild creation": (
        process_get_guild_name,
        process_get_character_description
    ),
    "upgrade": {
        process_verify_upgrade_confirmation
    }
}
