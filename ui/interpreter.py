from functools import cache
from typing import Dict, Any, List, Union, Callable, Tuple

from pilgram.globals import PLAYER_NAME_REGEX, PLAYER_ERROR
from ui.utils import InterpreterFunctionWrapper as IFW, CommandParsingResult as CPS, UserContext, \
    reconstruct_delimited_arguments, TooFewArgumentsError, ArgumentValidationError, \
    RegexWithErrorMessage as RWE
from ui.functions import placeholder, echo, start_character_creation, character_creation_process, check_self, \
    check_player


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


def command_not_found_error_function(context: UserContext, command: str, suggestion: str) -> str:
    return f"command '{command}' invalid, did you mean '{suggestion}'? Type 'help' for a list of commands."


# TODO? move COMMANDS & PROCESSES to functions
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


def parse_command(command: str) -> CPS:
    """ parses the given command and returns a CommandParsingResult object."""
    split_command: List[str] = reconstruct_delimited_arguments(command.split())
    parser = COMMANDS
    indentation_levels: int = 0
    full_command: str = ""
    for command_token in split_command:
        ctlw = command_token.lower()  # ctlw = command token lower
        if ctlw in parser:
            if isinstance(parser[ctlw], IFW):
                ifw: IFW = parser[ctlw]
                args: List[str] = split_command[indentation_levels+1:]
                if ifw.number_of_args > len(args):
                    raise TooFewArgumentsError(full_command + command_token, ifw.number_of_args, len(args))
                return CPS(ifw, args)
            full_command = f"{full_command} {command_token}"
            parser = parser[ctlw]
            indentation_levels += 1
        else:
            return CPS(command_not_found_error_function, [command, list(parser.keys())[0]])


def context_aware_execute(user: UserContext, user_input: str) -> str:
    """ parses and elaborates the given user input and returns the output. """
    if user.is_in_a_process():
        return PROCESSES[user.get_process_name()][user.get_process_step()](user_input)
    try:
        parsing_result = parse_command(user_input)
        return parsing_result.execute(user)
    except ArgumentValidationError as e:
        return str(e)
