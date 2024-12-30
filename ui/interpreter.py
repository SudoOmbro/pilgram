import logging
import traceback
from collections.abc import Callable
from functools import cache

from ui.utils import (
    TooFewArgumentsError,
    UserContext,
    reconstruct_delimited_arguments,
    CommandError,
)
from ui.utils import CommandParsingResult as CPS
from ui.utils import InterpreterFunctionWrapper as IFW


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def command_not_found_error_function(context: UserContext, command: str, suggestion: str) -> str:
    return f"command '{command}' invalid, did you mean '`{suggestion}`'? Type '`help`' for a list of commands."


def _help_dfs(dictionary: dict[str, dict | IFW], previous_command: str, formatting: str) -> str:
    result_string: str = ""
    for key, value in dictionary.items():
        command = f"{previous_command}{key} "
        if isinstance(value, dict):
            result_string += _help_dfs(value, command, formatting)
        else:
            result_string += formatting.format(c=command, a=value.generate_help_args_string(), d=value.description)
    return result_string


def populate_sc_commands_list(commands_list: list[tuple[str, int, str]], commands_dict: dict[str, dict | IFW], string: str):
    """ populate a list with all the commands written in snake case + their number of arguments"""
    for key, value in commands_dict.items():
        if isinstance(value, dict):
            populate_sc_commands_list(commands_list, value, string + f"{key}_")
        elif isinstance(value, IFW):
            commands_list.append((string + key, value.number_of_args, value.description))


class CLIInterpreter:
    """ generic CLI interpreter that can be used with any commands list """

    def __init__(
            self,
            commands_dict: dict[str, str | IFW],
            processes: dict[str, tuple[tuple[str, Callable], ...]],
            help_formatting: str | None = None,
            aliases: dict[str, str] = None
    ):
        self.commands_dict = commands_dict
        self.processes = processes
        # automatically add the help command
        if help_formatting is None:
            self.commands_dict["help"] = IFW(None, self.help_function, "Shows and describes all commands")
        else:
            self.commands_dict["help"] = IFW(
                None,
                self.help_function,
                "Shows and describes all commands",
                default_args={"formatting": help_formatting}
            )
        self.commands_list: list[tuple[str, int, str]] = []
        populate_sc_commands_list(self.commands_list, self.commands_dict, "")
        # init aliases
        if aliases is None:
            self.aliases = {}
        else:
            self.aliases = aliases

    @cache
    def __help(self, formatting: str) -> str:
        """  does the dfs & caches the result for later use, slightly speeds up execution """
        return "here's a list of all commands:\n\n" + _help_dfs(self.commands_dict, "", formatting)

    def help_function(self, context: UserContext, formatting: str = "{c}{a}- {d}\n") -> str:
        """ basically do a depth first search on the COMMANDS dictionary and print what you find """
        return f"hey {context.get('username')}, {self.__help(formatting)}"

    def parse_command(self, command: str) -> CPS:
        """ parses the given command and returns a CommandParsingResult object."""
        split_command: list[str] = reconstruct_delimited_arguments(command.split())
        parser = self.commands_dict
        indentation_levels: int = 0
        full_command: str = ""
        for command_token in split_command:
            ctlw = command_token.lower()  # ctlw = command token lower
            if ctlw in parser:
                if isinstance(parser[ctlw], IFW):
                    ifw: IFW = parser[ctlw]
                    args: list[str] = split_command[indentation_levels + 1:]
                    if ifw.number_of_args > len(args):
                        raise TooFewArgumentsError(full_command + command_token, ifw.number_of_args, len(args))
                    return CPS(ifw, args)
                full_command = f"{full_command}{command_token} "
                parser = parser[ctlw]
                indentation_levels += 1
        return CPS(command_not_found_error_function, [command, f"{full_command}{list(parser.keys())[0]}"])

    def context_aware_execute(self, user: UserContext, user_input: str) -> str:
        """ parses and elaborates the given user input and returns the output. """
        if user_input.lower() in self.aliases:
            user_input = self.aliases[user_input.lower()]
        try:
            if user.is_in_a_process():
                return self.processes[user.get_process_name()][user.get_process_step()][1](user, user_input)
            parsing_result = self.parse_command(user_input)
            return parsing_result.execute(user)
        except CommandError as e:
            return str(e)
        except TypeError as e:
            log.error(e)
            # raise(e)  # enable if there is some weird error that returns the below expression
            return "Too many arguments given! Check help for instructions."
