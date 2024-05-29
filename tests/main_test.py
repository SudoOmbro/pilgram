import inspect
import sys

from tests.chatgpt import *
from tests.ormdb import *


if __name__ == "__main__":
    all_functions = inspect.getmembers(sys.modules[__name__], inspect.isfunction)
    for key, value in all_functions:
        if str(key).startswith("test_"):
            value()
            print(f"{key} passed")
