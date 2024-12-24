import re
from collections.abc import Callable
from typing import Any

from pilgram.classes import Player
from pilgram.generics import PilgramDatabase
from pilgram.globals import POSITIVE_INTEGER_REGEX, PLAYER_NAME_REGEX, GUILD_NAME_REGEX, YES_NO_REGEX
from pilgram.strings import Strings
from pilgram.utils import PathDict


class CommandError(Exception):
    pass


class ArgumentValidationError(CommandError):

    def __init__(self, argument: str, argument_name: str, index: int, error_message: str) -> None:
        if error_message:
            msg = f"'{argument}' is not a valid value for argument '{argument_name}' ({index}): {error_message}"
        else:
            msg = f"'{argument}' is not a valid value for argument '{argument_name}' ({index})"
        super().__init__(msg)


class TooFewArgumentsError(CommandError):

    def __init__(self, command: str, required: int, passed: int) -> None:
        self.required = required
        self.passed = passed
        super().__init__(f"command {command} requires {required} arguments, but {passed} were given")


class YesNoError(CommandError):

    def __init__(self) -> None:
        super().__init__(Strings.yes_no_error)


class CommandParsingResult:
    """ Contains the result of the parsing of a command, which includes the function to be executed & the args. """

    def __init__(self, function: Callable, args: list[str] | None):
        self.function = function
        self.args = args

    def execute(self, context: "UserContext") -> str:
        if self.args:
            return self.function(context, *self.args)
        return self.function(context)


class UserContext:
    """
        A wrapper around a dictionary that supports getting/settings variables through path strings.
        Also helps with managing sequential processes like character or guild creation.
        The first argument of all ui functions must be the context.
    """

    def __init__(self, dictionary: dict | None = None):
        self.__dictionary: PathDict = PathDict(dictionary) if dictionary else PathDict()
        self.__process: str | None = None  # controls whether the user is in a sequential process
        self.__process_step: int = 0

    def get(self, path: str, separator: str = ".") -> Any:
        return self.__dictionary.path_get(path, separator=separator)

    def set(self, path: str, value: Any, separator: str = "."):
        self.__dictionary.path_set(path, value, separator=separator)

    def is_in_a_process(self):
        return self.__process is not None

    def get_process_name(self) -> str:
        return self.__process

    def get_process_step(self) -> int:
        return self.__process_step

    def start_process(self, process_name: str):
        self.__process = process_name
        self.__process_step = 0

    def progress_process(self):
        self.__process_step += 1

    def end_process(self):
        self.__process = None

    def set_event(self, event_type: str, event_data: dict):
        """ set event data """
        self.set("event", event_data)
        self.set("event.type", event_type)

    def get_event_data(self) -> dict | None:
        """ get data contained in 'event' if an event has happened"""
        try:
            return self.get("event")
        except KeyError:
            return None

    def get_process_prompt(self, processes_container: dict[str, tuple[tuple[str, Callable], ...]]):
        return processes_container[self.get_process_name()][self.get_process_step()][0]

    def __str__(self):
        return str(self.__dictionary)


class RegexWithErrorMessage:
    """ convenience class that stores the regex to check + the error message to give the user if the regex isn't met """

    def __init__(self, arg_name: str, regex: str | None, error_message: str | None):
        self.argument_name = arg_name
        self.regex = regex
        self.error_message = error_message

    def check(self, string_to_check: str) -> bool:
        return re.match(self.regex, string_to_check) is not None


def integer_arg(arg_name: str) -> RegexWithErrorMessage:
    return RegexWithErrorMessage(arg_name, POSITIVE_INTEGER_REGEX, Strings.obj_number_error.format(obj=arg_name))


def player_arg(arg_name: str) -> RegexWithErrorMessage:
    return RegexWithErrorMessage(arg_name, PLAYER_NAME_REGEX, Strings.player_name_validation_error)


def guild_arg(arg_name: str) -> RegexWithErrorMessage:
    return RegexWithErrorMessage(arg_name, GUILD_NAME_REGEX, Strings.guild_name_validation_error)


class InterpreterFunctionWrapper:  # maybe import as IFW, this name is a tad too long
    """ wrapper around interpreter functions that automatically checks argument validity & optimizes itself"""

    def __init__(
            self,
            args: list[RegexWithErrorMessage] | None,
            function: Callable[..., str],
            description: str,
            default_args: dict[str, Any] | None = None,
            optional_args: list[RegexWithErrorMessage] | None = None
    ):
        self.number_of_args = (len(args)) if args else 0
        self.required_args_container: tuple[RegexWithErrorMessage, ...] = tuple(args) if args else tuple()
        self.optional_args_container: tuple[RegexWithErrorMessage, ...] = tuple(optional_args) if optional_args else tuple()
        self.function = function
        self.description = description
        self.default_args = default_args
        if not default_args:
            if (self.number_of_args == 0) and (not self.optional_args_container):
                self.run = self.__call_no_args
            elif self.__are_all_arg_regexes_none():
                self.run = self.__call_with_args_no_check
            else:
                self.run = self.__call_with_args_and_check
        else:
            if (self.number_of_args == 0) and (not self.optional_args_container):
                self.run = self.__call_no_args_da
            elif self.__are_all_arg_regexes_none():
                self.run = self.__call_with_args_no_check_da
            else:
                self.run = self.__call_with_args_and_check_da

    def __are_all_arg_regexes_none(self) -> bool:
        if not self.required_args_container:
            return True
        for arg in self.required_args_container:
            if arg.regex is not None:
                return False
        return True

    def generate_help_args_string(self) -> str:
        result: str = ""
        for arg in self.required_args_container:
            result += f"\\[{arg.argument_name}] "
        for arg in self.optional_args_container:
            result += f"({arg.argument_name}) "
        return result

    def __get_args(self, *args) -> tuple[tuple[str, ...], tuple[str, ...]]:
        required_args = args[:self.number_of_args]
        optional_args = args[self.number_of_args:]
        return required_args, optional_args

    @staticmethod
    def __check_args(container: tuple[RegexWithErrorMessage, ...], *args):
        for (index, arg), arg_container in zip(enumerate(*args), container, strict=False):
            if arg_container.regex and (not arg_container.check(arg)):
                raise ArgumentValidationError(arg, arg_container.argument_name, index, arg_container.error_message)

    def __check_required_args(self, args):
        self.__check_args(self.required_args_container, args)

    def __check_optional_args(self, args):
        self.__check_args(self.optional_args_container, args)

    def __call_with_args_and_check_da(self, context: UserContext, *args) -> str:
        """ call with args and check args validity + use default args """
        command_args, optional_args = self.__get_args(*args)
        self.__check_required_args(command_args)
        self.__check_optional_args(command_args)
        return self.function(context, *args, **self.default_args)

    def __call_with_args_no_check_da(self, context: UserContext, *args) -> str:
        """ call with args and DO NOT check args validity + use default args """
        return self.function(context, *args, **self.default_args)

    def __call_no_args_da(self, context: UserContext, *args) -> str:
        """ call no args, use default args """
        return self.function(context, **self.default_args)

    def __call_with_args_and_check(self, context: UserContext, *args) -> str:
        """ call with args and check args validity """
        command_args, optional_args = self.__get_args(*args)
        self.__check_required_args(command_args)
        self.__check_optional_args(command_args)
        return self.function(context, *args)

    def __call_with_args_no_check(self, context: UserContext, *args) -> str:
        """ call with args and DO NOT check args validity """
        return self.function(context, *args)

    def __call_no_args(self, context: UserContext, *args) -> str:
        """ call no args """
        return self.function(context)

    def __call__(self, context: UserContext, *args) -> str:
        return self.run(context, *args)


def reconstruct_delimited_arguments(separated_strings: list[str], delimiter: str = "\"") -> list[str]:
    """ restores spaces in arguments delimited by delimiter """
    result: list[str] = []
    built_string = ""
    building: bool = False
    for string in separated_strings:
        if not building:
            if string.startswith(delimiter):
                building = True
                built_string += f"{string[1:]} "
                continue
            result.append(string)
        else:
            if string.endswith(delimiter):
                building = False
                built_string += string[:-1]
                result.append(built_string)
                built_string = ""
                continue
            built_string += f"{string} "
    return result


def get_yes_or_no(user_input: str) -> bool:
    """
    returns True if the input was yes, else returns False

    :raises YesNoError
    """
    processed_user_input = user_input[0].lower()
    if not re.match(YES_NO_REGEX, processed_user_input):
        raise YesNoError()
    return processed_user_input == "y"


def get_player(db: Callable[[], PilgramDatabase], context: UserContext) -> Player:
    """
    retrieve & return the player character

    :raises CommandError
    """
    try:
        return db().get_player_data(context.get("id"))
    except KeyError:
        raise CommandError(Strings.no_character_yet)
