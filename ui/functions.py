import re
from typing import Tuple, Union, Callable, Any


class ArgumentValidationError(Exception):
    pass


class InterpreterFunctionWrapper:  # mayber import as IFP, this name is a tad too long
    """ wrapper around interpreter functions that automatically checks argument validity & optimizes itself"""

    def __init__(
            self,
            number_of_args: int,
            regexes: Union[Tuple[Union[re.Pattern, None], ...], None],
            function: Callable[..., str],
    ):
        self.number_of_args = number_of_args
        self.regexes = regexes
        self.function = function
        if number_of_args == 0:
            self.__call__ = self.__call_no_args
        elif regexes is None:
            self.__call__ = self.__call_with_args_no_check
        else:
            self.__call__ = self.__call_with_args_and_check

    def __call_with_args_and_check(self, *args) -> str:
        args = args[:self.number_of_args]  # clamp the args to the defined value
        for index, arg in enumerate(args):
            if self.regexes[index]:
                result = re.match(self.regexes[index], arg)
                if not result:
                    raise ArgumentValidationError(f"Invalid argument {index}: '{arg}'")
        return self.function(*args)

    def __call_with_args_no_check(self, *args) -> str:
        args = args[:self.number_of_args]
        return self.function(*args)

    def __call_no_args(self, *args) -> str:
        return self.function()
