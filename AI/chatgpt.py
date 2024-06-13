import logging
from functools import cache
from typing import Union, List

import requests

from pilgram.classes import Zone, Quest, ZoneEvent
from pilgram.generics import PilgramGenerator
from pilgram.globals import ContentMeta


log = logging.getLogger(__name__)


QUESTS_PER_BATCH: int = 5
EVENTS_PER_BATCH: int = 25

WORLD_PROMPT = f"You write about a dark fantasy world named {ContentMeta.get('world.name')}"
STYLE_PROMPT = "Refer to the protagonist as \"You\"."
QUEST_FORMATTING_PROMPT = "Leave 2 lines between quests"
EVENT_FORMATTING_PROMPT = "Leave 2 lines between events"

ZONE_PROMPT = "The current zone is called \"{name}\", it is a {descr}"
QUESTS_PROMPT = f"Write {QUESTS_PER_BATCH} quests set in the current zone with objective, success and failure descriptions"
EVENTS_PROMPT = f"Write {EVENTS_PER_BATCH} short events set in the current zone"


def build_messages(role: str, *messages: str) -> List[dict]:
    return [{"role": role, "content": x} for x in messages]


def get_quests_system_prompt(zone: Zone) -> List[dict]:
    return build_messages(
        "system",
        WORLD_PROMPT,
        STYLE_PROMPT,
        QUEST_FORMATTING_PROMPT,
        ZONE_PROMPT.format(name=zone.zone_name, descr=zone.zone_description)
    )


def get_events_system_prompt(zone: Zone) -> List[dict]:
    return build_messages(
        "system",
        WORLD_PROMPT,
        STYLE_PROMPT,
        ZONE_PROMPT.format(name=zone.zone_name, descr=zone.zone_description)
    )


class GPTAPIError(Exception):

    def __init__(self, response: requests.Response):
        super().__init__()
        self.status_code = response.status_code
        self.response = response


class ChatGPTAPI:
    """ Wrapper around the ChatGpt API, used by the generator """

    BASE_URL = 'https://api.openai.com'

    def __init__(
            self,
            token: str,
            model: str,
            api_version: int = 1,
            project: Union[str, None] = None,
            organization: Union[str, None] = None
    ):
        self.token = token
        self.model = model
        self.api_version = api_version
        self.project = project if project else "default project"
        self.organization = organization
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if organization:
            self.headers["organization"] = organization
        if project:
            self.headers["project"] = project
        self.last_batch: str = ""

    @cache
    def _build_request_url(self, endpoint: str) -> str:
        return f"{self.BASE_URL}/v{self.api_version}/{endpoint}"

    def create_completion(self, messages: List[dict], temperature: int = 1) -> str:
        response = requests.post(
            self._build_request_url("chat/completions"),
            None,
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            },
            headers=self.headers
        )
        if response.ok:
            json_response = response.json()
            log.info(json_response)
            return json_response["choices"][0]["message"]["content"]
        log.error(f"could not create completion, response: {response.text}")
        raise GPTAPIError(response)

    def create_batch_line(self, messages: List[dict]) -> str:
        # TODO (?) adding batches would half the cost of API calls
        pass


class ChatGPTGenerator(PilgramGenerator):

    def __init__(self, api_wrapper: ChatGPTAPI):
        self.api_wrapper = api_wrapper

    @staticmethod
    def __get_quests_from_generated_text(input_text: str, zone: Zone, starting_number: int) -> List[Quest]:
        result = []
        split_text = input_text.split("\n\n")
        for text in split_text:

            new_quest = Quest.create_default(
                zone,
                starting_number,
                "",
                "",
                "",
                ""
            )
            starting_number += 1
            result.append(new_quest)
        return result

    @staticmethod
    def __get_events_from_generated_text(input_text: str, zone: Zone) -> List[ZoneEvent]:
        result = []
        split_text = input_text.split("\n\n")
        for text in split_text:
            new_event = ZoneEvent.create_default(zone, text)
            result.append(new_event)
        return result

    def generate_quests(self, zone: Zone, quest_numbers: List[int]) -> List[Quest]:
        try:
            messages = get_quests_system_prompt(zone) + build_messages("user", QUESTS_PROMPT)
            generated_text = self.api_wrapper.create_completion(messages)
            starting_number = quest_numbers[zone.zone_id - 1]
            return self.__get_quests_from_generated_text(generated_text, zone, starting_number)
        except GPTAPIError as e:
            log.error(f"could not generate quests, error: {e}")
            return []

    def generate_zone_events(self, zone: Zone) -> List[ZoneEvent]:
        try:
            messages = get_quests_system_prompt(zone) + build_messages("user", EVENTS_PROMPT)
            generated_text = self.api_wrapper.create_completion(messages)
            return self.__get_events_from_generated_text(generated_text, zone)
        except GPTAPIError as e:
            log.error(f"could not generate quests, error: {e}")
            return []
