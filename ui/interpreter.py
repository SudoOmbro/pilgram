from typing import Dict, Any, List, Union, Callable, Tuple

from ui.utils import InterpreterFunctionWrapper as IFW, CommandParsingResult as CPS, UserContext, \
    reconstruct_delimited_arguments, TooFewArgumentsError
from ui.functions import placeholder, echo, start_character_creation, character_creation_process


def __generate_help_args_string(ifw: IFW) -> str:
    result: str = " "
    for i in range(ifw.number_of_args):
        result += f"[arg{i}] "
    return result


def __help_dfs(dictionary: Dict[str, Union[dict, IFW]], depth: int = 0) -> str:
    result_string: str = ""
    for key, value in dictionary.items():
        result_string += "> " * depth + f"`{key}`"
        if isinstance(value, dict):
            result_string += "\n" + __help_dfs(value, depth + 1)
        else:
            result_string += f"{__generate_help_args_string(value)}-- {value.description}\n"
    return result_string


def help_function() -> str:
    """ basically do a depth first search on the COMMANDS dictionary and print what you find """
    return __help_dfs(COMMANDS, 0)


def command_not_found_error_function(context: UserContext, command: str, suggestion: str) -> str:
    return f"command '{command}' invalid, did you mean '{suggestion}'? Type 'help' for a list of commands."


COMMANDS: Dict[str, Any] = {
    "check": {
        "board": IFW(0, None, placeholder, "Shows the quest board"),
        "guild": IFW(0, None, placeholder, "Shows your own guild"),
        "self": IFW(0, None, placeholder, "Shows your own stats"),
        "player": IFW(1, (r"\S+",), placeholder, "Shows player arg0 stats")
    },
    "create": {
        "character": IFW(0, None, start_character_creation, "Create your character"),
        "guild": IFW(0, None, placeholder, "create your own Guild")
    },
    "upgrade": {
        "gear": IFW(0, None, placeholder, "Upgrade your gear"),
        "guild": IFW(0, None, placeholder, "Upgrade your guild"),
        "home": IFW(0, None, placeholder, "Upgrade your home"),
    },
    "embark": IFW(1, (r"",), placeholder, "Starts quest in zone arg0"),
    "kick": IFW(1, (r"\S+",), placeholder, "Kicks player arg0 from your guild"),
    "help": IFW(0, None, help_function, "Shows and describes all commands"),
    "echo": IFW(1, (r"\S+",), echo, "repeats arg0")
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
    parsing_result = parse_command(user_input)
    return parsing_result.execute(user)
