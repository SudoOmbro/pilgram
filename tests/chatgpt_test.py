import json, unittest

from AI.chatgpt import build_messages, ChatGPTAPI, get_quests_system_prompt, get_events_system_prompt, QUESTS_PROMPT, \
    EVENTS_PROMPT, ChatGPTGenerator
from pilgram.classes import Zone

SETTINGS = json.load(open('settings.json'))


def _read_file(filename: str) -> str:
    with open(filename, 'r') as f:
        return f.read()


class TestChatGPT(unittest.TestCase):
    ZONE: Zone = Zone(1, "Test zone", 1, "forest at the edge of the city")
    api_wrapper = ChatGPTAPI(SETTINGS["ChatGPT token"], "gpt-3.5-turbo")
    generator: ChatGPTGenerator = ChatGPTGenerator(api_wrapper)

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

    def test_generate_events(self):
        messages = get_events_system_prompt(self.ZONE) + build_messages("user", EVENTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        print(generated_text)

    def test_build_quests_from_generated_text(self):
        text = _read_file("mock_quests_response.txt")
        quests = self.generator._get_quests_from_generated_text(text, self.ZONE, 5)
        for quest, num in zip(quests, range(5, 10)):
            self.assertEqual(quest.number, num)
            print(f"{quest}\nnum: {quest.number}, success: '{quest.success_text}', failure: '{quest.failure_text}'\n")

    def test_build_events_from_generated_text(self):
        text = _read_file("mock_events_response.txt")
        events = self.generator._get_events_from_generated_text(text, self.ZONE)
        for event in events:
            print(event)

    def _test_chatgpt_api(self):
        response = self.api_wrapper.create_completion(
            build_messages("system", "your name is HAL") + build_messages("user", "Hi, what's your name?")
        )
        print(response)
