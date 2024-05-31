from AI.chatgpt import build_messages


def test_build_messages():
    messages = build_messages("system", "aaa", "bbb")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "system"
    assert messages[0]["content"] == "aaa"
    assert messages[1]["content"] == "bbb"
