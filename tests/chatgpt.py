import inspect
import sys

from AI.chatgpt import build_messages


def test_build_messages():
    messages = build_messages("system", "aaa", "bbb")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "system"
    assert messages[0]["content"] == "aaa"
    assert messages[1]["content"] == "bbb"


if __name__ == "__main__":
    all_functions = inspect.getmembers(sys.modules[__name__], inspect.isfunction)
    for key, value in all_functions:
        if str(key).startswith("test_"):
            value()
            print(f"{key} passed")
