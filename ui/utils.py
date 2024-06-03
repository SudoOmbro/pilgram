import re
from typing import Union, Tuple, Callable, List, Any, Dict


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

    def __init__(self, dictionary: Union[Dict[str, Any], None] = None):
        if dictionary:
            self.__dictionary = dictionary
        else:
            self.__dictionary = {}
        self.__process: Union[str, None] = None  # controls whether the user is in a sequential process
        self.__process_step: int = 0

    def get(self, path: str, separator: str = ".") -> Any:
        keys = path.split(separator)
        rv = self.__dictionary
        for key in keys:
            if key not in rv:
                raise KeyError(f"Could not find key '{key}' in dictionary: {self.__dictionary}")
            rv = rv[key]
        return rv

    def set(self, path: str, value: Any, separator: str = "."):
        keys = path.split(separator)
        last_key = keys[-1]
        keys = keys[:-1]
        container = self.__dictionary
        for key in keys:
            if key not in container:
                container[key] = {}
            container = container[key]
        container[last_key] = value

    def is_in_a_process(self):
        return self.__process is not None

    def get_process_name(self) -> str:
        return self.__process

    def get_process_step(self) -> int:
        return self.__process_step

    def begin_process(self, process_name: str):
        self.__process = process_name
        self.__process_step = 0

    def update_process(self):
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
            description: str
    ):
        self.number_of_args = number_of_args
        self.regexes = regexes
        self.function = function
        self.description = description
        if number_of_args == 0:
            self.run = self.__call_no_args
        elif regexes is None:
            self.run = self.__call_with_args_no_check
        else:
            assert len(regexes) == number_of_args
            self.run = self.__call_with_args_and_check

    def __call_with_args_and_check(self, context: UserContext, *args) -> str:
        args = args[:self.number_of_args]  # clamp the args to the defined value
        for index, arg in enumerate(args):
            if self.regexes[index]:
                result = re.match(self.regexes[index], arg)
                if not result:
                    raise ArgumentValidationError(f"Invalid argument {index}: '{arg}'", index)
        return self.function(context, *args)

    def __call_with_args_no_check(self, context: UserContext, *args) -> str:
        args = args[:self.number_of_args]
        return self.function(context, *args)

    def __call_no_args(self, context: UserContext, *args) -> str:
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
