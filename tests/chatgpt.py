import json

from AI.chatgpt import build_messages, ChatGPTAPI


SETTINGS = json.load(open('settings.json'))


def test_build_messages():
    messages = build_messages("system", "aaa", "bbb")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "system"
    assert messages[0]["content"] == "aaa"
    assert messages[1]["content"] == "bbb"
    messages = build_messages("system", "a", "b") + build_messages("user", "c", "d")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "system"
    assert messages[0]["content"] == "a"
    assert messages[1]["content"] == "b"
    assert messages[2]["role"] == "user"
    assert messages[3]["role"] == "user"
    assert messages[2]["content"] == "c"
    assert messages[3]["content"] == "d"


def __test_chatgpt_api():
    api = ChatGPTAPI(SETTINGS["ChatGPT token"], "gpt-3.5-turbo")
    response = api.create_completion(
        build_messages("system", "your name is HAL") + build_messages("user", "Hi, what's your name?")
    )
    print(response)
