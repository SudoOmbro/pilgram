import json
import unittest

from AI.chatgpt import (
    ARTIFACTS_PER_BATCH,
    ARTIFACTS_PROMPT,
    ENEMIES_PROMPT,
    EVENTS_PER_BATCH,
    EVENTS_PROMPT,
    MONSTERS_PER_BATCH,
    QUESTS_PROMPT,
    ChatGPTAPI,
    ChatGPTGenerator,
    build_messages,
    get_artifacts_system_prompt,
    get_enemies_system_prompt,
    get_events_system_prompt,
    get_quests_system_prompt,
    get_anomaly_system_prompt,
    ANOMALY_PROMPT,
    ANOMALY_RESPONSE_FORMAT,
)
from AI.utils import (
    filter_string_list_remove_empty,
    filter_strings_list_remove_too_short,
    remove_leading_numbers,
)
from pilgram.classes import Zone
from pilgram.combat_classes import Damage

SETTINGS = json.load(open('settings.json'))


def _read_file(filename: str) -> str:
    with open(filename) as f:
        return f.read()


class TestChatGPT(unittest.TestCase):
    ZONE: Zone = Zone(1, "Test zone", 1, "forest at the edge of the city", Damage.get_empty(), Damage.get_empty(), {})
    api_wrapper = ChatGPTAPI(SETTINGS["ChatGPT token"], "gpt-4o-mini")
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

    def test_generate_artifacts(self):
        messages = get_artifacts_system_prompt() + build_messages("user", ARTIFACTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        print(generated_text)

    def test_generate_enemies(self):
        messages = get_enemies_system_prompt(self.ZONE) + build_messages("user", ENEMIES_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        print(generated_text)

    def test_generate_anomaly(self):
        messages = get_anomaly_system_prompt(self.ZONE) + build_messages("user", ANOMALY_PROMPT)
        generated_output = self.api_wrapper.create_completion(messages, response_format=ANOMALY_RESPONSE_FORMAT)
        print(generated_output)

    def test_build_quests_from_generated_text(self):
        text = _read_file("mock_quests_response.txt")
        quests = self.generator._get_quests_from_generated_text(text, self.ZONE, 5)
        for quest, num in zip(quests, range(5, 10), strict=False):
            self.assertEqual(quest.number, num)
            print(f"{quest}\nnum: {quest.number}, success: '{quest.success_text}', failure: '{quest.failure_text}'\n")

    def test_build_events_from_generated_text(self):
        text = _read_file("mock_events_response.txt")
        events = self.generator._get_events_from_generated_text(text, self.ZONE)
        self.assertEqual(len(events), EVENTS_PER_BATCH)
        for event in events:
            print(event)

    def test_build_artifacts_from_generated_text(self):
        text = _read_file("mock_artifacts_response.txt")
        artifacts = self.generator._get_artifacts_from_generated_text(text)
        self.assertEqual(len(artifacts), ARTIFACTS_PER_BATCH)
        for artifact in artifacts:
            print(artifact)

    def test_build_enemy_metas_from_generated_text(self):
        text = _read_file("mock_enemies_response.txt")
        enemy_metas = self.generator._get_enemies_from_generated_text(text, self.ZONE)
        self.assertEqual(len(enemy_metas), MONSTERS_PER_BATCH)
        for enemy_meta in enemy_metas:
            print(enemy_meta)
            print(enemy_meta.win_text)
            print(enemy_meta.lose_text)

    def test_filter_string_list_remove_empty_strings(self):
        string_list = ["aaa", "bbb", "", "\n", "ccc"]
        result = filter_string_list_remove_empty(string_list)
        self.assertEqual(result, ["aaa", "bbb", "ccc"])

    def test_filter_string_list_remove_too_short(self):
        string_list = ["aaaa", "bbbbb", "ccc", "ccc", "eee"]
        result = filter_strings_list_remove_too_short(string_list, 4)
        self.assertEqual(result, ["aaaa", "bbbbb"])

    def test_remove_leading_numbers(self):
        string = "1.aaa 1"
        result = remove_leading_numbers(string)
        self.assertEqual(result, "aaa 1")
        string = "568.bbb 34 cc"
        result = remove_leading_numbers(string)
        self.assertEqual(result, "bbb 34 cc")
        string = "aaaa bbbb"
        result = remove_leading_numbers(string)
        self.assertEqual(result, string)

    def _test_chatgpt_api(self):
        response = self.api_wrapper.create_completion(
            build_messages("system", "your name is HAL") + build_messages("user", "Hi, what's your name?")
        )
        print(response)
