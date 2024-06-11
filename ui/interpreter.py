from typing import List, Dict, Union, Tuple, Callable

from ui.utils import InterpreterFunctionWrapper as IFW, CommandParsingResult as CPS, UserContext, \
    reconstruct_delimited_arguments, TooFewArgumentsError, ArgumentValidationError


def command_not_found_error_function(context: UserContext, command: str, suggestion: str) -> str:
    return f"command '{command}' invalid, did you mean '`{suggestion}`'? Type '`help`' for a list of commands."


def _help_dfs(dictionary: Dict[str, Union[dict, IFW]], previous_command: str, formatting: str) -> str:
    result_string: str = ""
    for key, value in dictionary.items():
        command = f"{previous_command}{key} "
        if isinstance(value, dict):
            result_string += _help_dfs(value, command, formatting)
        else:
            result_string += formatting.format(c=command, a=value.generate_help_args_string(), d=value.description)
    return result_string


class CLIInterpreter:
    """ generic CLI interpreter that can be used with any commands list """

    def __init__(
            self,
            commands_dict: Dict[str, Union[str, IFW]],
            processes: Dict[str, Tuple[Tuple[str, Callable], ...]],
            help_formatting: Union[str, None] = None
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

    def help_function(self, context: UserContext, formatting: str = "{c}{a}- {d}\n") -> str:
        """ basically do a depth first search on the COMMANDS dictionary and print what you find """
        return f"hey {context.get('username')}, here's a list of all commands:\n\n" + _help_dfs(self.commands_dict, "", formatting)

    def parse_command(self, command: str) -> CPS:
        """ parses the given command and returns a CommandParsingResult object."""
        split_command: List[str] = reconstruct_delimited_arguments(command.split())
        parser = self.commands_dict
        indentation_levels: int = 0
        full_command: str = ""
        for command_token in split_command:
            ctlw = command_token.lower()  # ctlw = command token lower
            if ctlw in parser:
                if isinstance(parser[ctlw], IFW):
                    ifw: IFW = parser[ctlw]
                    args: List[str] = split_command[indentation_levels + 1:]
                    if ifw.number_of_args > len(args):
                        raise TooFewArgumentsError(full_command + command_token, ifw.number_of_args, len(args))
                    return CPS(ifw, args)
                full_command = f"{full_command}{command_token} "
                parser = parser[ctlw]
                indentation_levels += 1
        return CPS(command_not_found_error_function, [command, f"{full_command}{list(parser.keys())[0]}"])

    def context_aware_execute(self, user: UserContext, user_input: str) -> str:
        """ parses and elaborates the given user input and returns the output. """
        if user.is_in_a_process():
            return self.processes[user.get_process_name()][user.get_process_step()][1](user, user_input)
        try:
            parsing_result = self.parse_command(user_input)
            return parsing_result.execute(user)
        except ArgumentValidationError as e:
            return str(e)
        except TooFewArgumentsError as e:
            return str(e)
