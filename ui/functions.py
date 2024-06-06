from functools import cache
from typing import Tuple, Dict, Union, Callable, Any

from orm.db import PilgramORMDatabase
from pilgram.classes import Player
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta, PLAYER_NAME_REGEX, PLAYER_ERROR
from ui.utils import UserContext, InterpreterFunctionWrapper as IFW, RegexWithErrorMessage as RWE


DB: PilgramDatabase = PilgramORMDatabase.instance()


def placeholder(context: UserContext) -> str:
    """ temporary placeholder function """
    return "hello world"


def echo(context: UserContext, text) -> str:
    try:
        username = context.get("username")
    except KeyError:
        username = "player"
    return f"{username} says: '{text}'"


def check_self(context: UserContext) -> str:
    try:
        ch = DB.get_player_data(context.get("id"))
        return str(ch)
    except KeyError:
        return "You haven't made a character yet!"


def check_player(context: UserContext, player_name: str) -> str:
    try:
        player = DB.get_player_data(DB.get_player_id_from_name(player_name))
        return str(player)
    except KeyError:
        return f"A player with name {player_name} does not exist"


def start_character_creation(context: UserContext) -> str:
    try:
        player = DB.get_player_data(context.get("id"))
        return f"You already have a character! Their name is {player.name} and they are very sad now :("
    except KeyError:
        context.start_process("character creation")
        return "Ok, let's start by naming your character. Send me a name"


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


CC_STEPS: Tuple[str, ...] = (
    "name",
    "description"
)


def character_creation_process(context: UserContext, user_input: str) -> str:
    context.set(CC_STEPS[context.get_process_step()], user_input)
    if context.get_process_step() == len(CC_STEPS):
        # finish character creation
        context.end_process()
        player = Player.create_default(
            context.get("id"), context.get("name"), context.get("description")
        )
        world_name = ContentMeta.get("world.name")
        DB.add_player(player)
        return f"Your character has been created! Welcome to the world of {world_name}!"
    context.progress_process()
    return f"Ok now send me you character's {CC_STEPS[context.get_process_step()]}"


COMMANDS: Dict[str, Any] = {
    "check": {
        "board": IFW(None, placeholder, "Shows the quest board"),
        "guild": IFW(None, placeholder, "Shows your own guild"),
        "self": IFW(None, check_self, "Shows your own stats"),
        "player": IFW([RWE("player name", PLAYER_NAME_REGEX, PLAYER_ERROR)], check_player, "Shows player stats")
    },
    "create": {
        "character": IFW(None, start_character_creation, "Create your character"),
        "guild": IFW(None, placeholder, "create your own Guild")
    },
    "upgrade": {
        "gear": IFW(None, placeholder, "Upgrade your gear"),
        "guild": IFW(None, placeholder, "Upgrade your guild"),
        "home": IFW(None, placeholder, "Upgrade your home"),
    },
    "embark": IFW([RWE("zone number", r"[\d]+", "Zone number must be a positive integer number")], placeholder, "Starts a quest in specified zone"),
    "kick": IFW([RWE("player name", PLAYER_NAME_REGEX, PLAYER_ERROR)], placeholder, "Kicks specified player from your guild"),
    "help": IFW(None, help_function, "Shows and describes all commands"),
    "echo": IFW([RWE("text", None, None)], echo, "repeats 'text'")
}

PROCESSES: Dict[str, Tuple[Callable, ...]] = {
    "character creation": (
        character_creation_process,
        character_creation_process
    ),
    "guild creation": (

    )
}
