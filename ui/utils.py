import re
from typing import Union, Tuple, Callable, List, Any, Dict

from pilgram.utils import PathDict


class ArgumentValidationError(Exception):

    def __init__(self, message: str, index: int) -> None:
        super().__init__(message)
        self.index = index
        super().__init__(message)


class TooFewArgumentsError(Exception):

    def __init__(self, command: str, required: int, passed: int) -> None:
        self.required = required
        self.passed = passed
        super().__init__(f"command {command} requires {required} arguments, but {passed} were given")


class CommandParsingResult:

    def __init__(self, function: Callable, args: Union[List[str], None]):
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

    def __init__(self, dictionary: Union[Dict, None] = None):
        self.__dictionary: PathDict = PathDict(dictionary) if dictionary else PathDict()
        self.__process: Union[str, None] = None  # controls whether the user is in a sequential process
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
        self.__process_step = None


class InterpreterFunctionWrapper:  # maybe import as IFW, this name is a tad too long
    """ wrapper around interpreter functions that automatically checks argument validity & optimizes itself"""

    def __init__(
            self,
            number_of_args: int,
            regexes: Union[Tuple[Union[str, None], ...], None],
            function: Callable[..., str],
            description: str,
            default_args: Union[Dict[str, Any], None] = None,
    ):
        self.number_of_args = number_of_args
        self.regexes = regexes
        self.function = function
        self.description = description
        self.default_args = default_args
        if not default_args:
            if number_of_args == 0:
                self.run = self.__call_no_args
            elif regexes is None:
                self.run = self.__call_with_args_no_check
            else:
                assert len(regexes) == number_of_args
                self.run = self.__call_with_args_and_check
        else:
            if number_of_args == 0:
                self.run = self.__call_no_args_da
            elif regexes is None:
                self.run = self.__call_with_args_no_check_da
            else:
                assert len(regexes) == number_of_args
                self.run = self.__call_with_args_and_check_da

    def __check_args(self, args):
        for index, arg in enumerate(args):
            if self.regexes[index]:
                result = re.match(self.regexes[index], arg)
                if not result:
                    raise ArgumentValidationError(f"Invalid argument {index}: '{arg}'", index)

    def __call_with_args_and_check_da(self, context: UserContext, *args) -> str:
        """ call with args and check args validity + use default args """
        args = args[:self.number_of_args]  # clamp the args to the defined value
        self.__check_args(args)
        return self.function(context, *args, **self.default_args)

    def __call_with_args_no_check_da(self, context: UserContext, *args) -> str:
        """ call with args and DO NOT check args validity + use default args """
        args = args[:self.number_of_args]
        return self.function(context, *args, **self.default_args)

    def __call_no_args_da(self, context: UserContext, *args) -> str:
        """ call no args, use default args """
        return self.function(context, **self.default_args)

    def __call_with_args_and_check(self, context: UserContext, *args) -> str:
        """ call with args and check args validity """
        args = args[:self.number_of_args]  # clamp the args to the defined value
        self.__check_args(args)
        return self.function(context, *args)

    def __call_with_args_no_check(self, context: UserContext, *args) -> str:
        """ call with args and DO NOT check args validity """
        args = args[:self.number_of_args]
        return self.function(context, *args)

    def __call_no_args(self, context: UserContext, *args) -> str:
        """ call no args """
        return self.function(context)

    def __call__(self, context: UserContext, *args) -> str:
        return self.run(context, *args)


def reconstruct_delimited_arguments(separated_strings: List[str], delimiter: str = "\"") -> List[str]:
    """ restores spaces in arguments delimited by delimiter """
    result: List[str] = []
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
