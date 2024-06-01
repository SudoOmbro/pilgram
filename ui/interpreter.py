from typing import Dict, Any, List, Callable

from ui.functions import InterpreterFunctionWrapper as IFP


def placeholder_function():
    """ temporary placeholder function """
    return "hello world"


def help_function() -> str:
    """ basically do a depth first search on the COMMANDS dictionary and print what you find """
    # TODO
    return "aaa"


COMMANDS: Dict[str, Any] = {
    "check": {
        "board": IFP(0, None, placeholder_function),
        "guild": IFP(0, None, placeholder_function),
        "self": IFP(0, None, placeholder_function)
    },
    "embark": IFP(0, None, placeholder_function),
    "help": IFP(0, None, help_function)
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
