import json, unittest

from AI.chatgpt import build_messages, ChatGPTAPI, get_quests_system_prompt, get_events_system_prompt, QUESTS_PROMPT
from pilgram.classes import Zone

SETTINGS = json.load(open('settings.json'))


class TestChatGPT(unittest.TestCase):
    ZONE: Zone = Zone(1, "Test zone", 1, "forest at the edge of the city")
    api_wrapper = ChatGPTAPI(SETTINGS["ChatGPT token"], "gpt-3.5-turbo")

    def test_build_messages(self):
        messages = build_messages("system", "aaa", "bbb")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "system")
        self.assertEqual(messages[0]["content"], "aaa")
        self.assertEqual(messages[1]["content"], "bbb")
        messages = build_messages("system", "a", "b") + build_messages("user", "c", "d")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "system")
        self.assertEqual(messages[0]["content"], "a")
        self.assertEqual(messages[1]["content"], "b")
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[3]["role"], "user")
        self.assertEqual(messages[2]["content"], "c")
        self.assertEqual(messages[3]["content"], "d")

    def test_get_system_prompts(self):
        print(get_quests_system_prompt(self.ZONE))
        print(get_events_system_prompt(self.ZONE))

    def test_generate_quests(self):
        messages = get_quests_system_prompt(self.ZONE) + build_messages("user", QUESTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        print(generated_text)

    def _test_chatgpt_api(self):
        response = self.api_wrapper.create_completion(
            build_messages("system", "your name is HAL") + build_messages("user", "Hi, what's your name?")
        )
        print(response)
