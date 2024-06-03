from typing import Dict, Any, List, Callable, Union

from ui.functions import InterpreterFunctionWrapper as IFP


def placeholder_function():
    """ temporary placeholder function """
    return "hello world"


def __depth_first_search(dictionary: Dict[str, Union[dict, IFP]], depth: int = 0) -> str:
    result_string: str = ""
    for key, value in dictionary.items():
        result_string += "> " * depth + f"`{key}`"
        if isinstance(value, dict):
            result_string += "\n" + __depth_first_search(value, depth + 1)
        else:
            result_string += f" -- _{value.description}_\n"
    return result_string


def help_function() -> str:
    """ basically do a depth first search on the COMMANDS dictionary and print what you find """
    return __depth_first_search(COMMANDS, 0)


COMMANDS: Dict[str, Any] = {
    "check": {
        "board": IFP(0, None, placeholder_function, "aaa"),
        "guild": IFP(0, None, placeholder_function, "aaa"),
        "self": IFP(0, None, placeholder_function, "aaa")
    },
    "embark": IFP(0, None, placeholder_function, "aaa"),
    "help": IFP(0, None, help_function, "shows and describes all commands")
}


def error_function(command: str, suggestion: str) -> str:
    return f"command '{command}' invalid, did you mean '{suggestion}'? Type 'help' for a list of commands."


def parse_command(command: str) -> (Callable, List[str]):
    """ parses the given command and returns a ParsingResult object."""
    split_command: List[str] = command.split()
    parser = COMMANDS
    indentation_levels: int = 0
    for command_token in split_command:
        ctlw = command_token.lower()  # ctlw = command token lower
        if ctlw in parser:
            if isinstance(parser[ctlw], IFP):
                return parser[ctlw], split_command[indentation_levels:]
            parser = parser[ctlw]
            indentation_levels += 1
        else:
            return error_function, [command, list(parser.keys())[0]]
