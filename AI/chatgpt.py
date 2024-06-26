import logging
import re
from functools import cache
from typing import Union, List

import requests

from AI.utils import filter_string_list_remove_empty, get_string_list_from_tuple_list, remove_leading_numbers, \
    filter_strings_list_remove_too_short
from pilgram.classes import Zone, Quest, ZoneEvent, Artifact
from pilgram.generics import PilgramGenerator
from pilgram.globals import ContentMeta


log = logging.getLogger(__name__)


QUESTS_PER_BATCH: int = 5
EVENTS_PER_BATCH: int = 25
ARTIFACTS_PER_BATCH: int = 25

WORLD_PROMPT = f"You write about a dark fantasy world named {ContentMeta.get('world.name')}"
STYLE_PROMPT = "Refer to the protagonist as \"You\"."
QUEST_FORMATTING_PROMPT = "Leave 2 lines between each quest"
EVENT_FORMATTING_PROMPT = "Leave 2 lines between events"
ARTIFACTS_FORMATTING_PROMPT = "Separate name and description with ':' putting the name before and the description after. Do not write 'Name' & 'Description'."

ZONE_PROMPT = "The current zone is called \"{name}\", it is a {descr}"
QUESTS_PROMPT = f"Write {QUESTS_PER_BATCH} quests set in the current zone with objective, success and failure descriptions"
EVENTS_PROMPT = f"Write {EVENTS_PER_BATCH} short events set in the current zone"
ARTIFACTS_PROMPT = f"Write name and description of {ARTIFACTS_PER_BATCH} unique & rare artifacts found in the world"

QUEST_NAME_REGEX: str = r"^\d*\.?\**#*\s?[Qq]uest\s?[\d]*:\s(.*)$"
QUEST_DESCRIPTION_REGEX: str = r"^\**[Oo]bjective\**:\**\s(.*)$"
QUEST_SUCCESS_REGEX: str = r"^\**[Ss]uccess\**:\**\s(.*)$"
QUEST_FAILURE_REGEX: str = r"^\**[Ff]ailure\**:\**\s(.*)$"

EVENT_REGEX: str = r"^([\d]+\.\s)?(.*)$"
ARTIFACT_REGEX: str = r"^([\d]+\.\s)?\**(.*)[:\-]{1}\s(.*)$"


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


def get_artifacts_system_prompt():
    return build_messages(
        "system",
        WORLD_PROMPT,
        ARTIFACTS_PROMPT,
        ARTIFACTS_FORMATTING_PROMPT
    )


class GPTAPIError(Exception):

    def __init__(self, response: requests.Response):
        super().__init__()
        self.status_code = response.status_code
        self.response = response


class GPTMisbehaveError(Exception):
    """ thrown when the AI did not generate what it was supposed to generate. """
    pass


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
            content = json_response["choices"][0]["message"]["content"]
            log.debug(f"AI input:\n\n{messages}\n\nAI output:\n\n{content}")
            return content
        log.error(f"could not create completion, response: {response.text}")
        raise GPTAPIError(response)

    def create_batch_line(self, messages: List[dict]) -> str:
        # TODO (?) adding batches would half the cost of API calls
        pass


class ChatGPTGenerator(PilgramGenerator):

    def __init__(self, api_wrapper: ChatGPTAPI):
        self.api_wrapper = api_wrapper

    @staticmethod
    def __get_regex_match(regex: str, text: str, attr_name: str) -> List[str]:
        result = re.findall(regex, text, re.MULTILINE)
        if result:
            return result
        raise GPTMisbehaveError(f"Could not find {attr_name} in generated text:\n\n{text}")

    def _get_quests_from_generated_text(self, input_text: str, zone: Zone, starting_number: int) -> List[Quest]:
        result = []
        titles = self.__get_regex_match(QUEST_NAME_REGEX, input_text, "quest name")
        descriptions = self.__get_regex_match(QUEST_DESCRIPTION_REGEX, input_text, "description")
        successes = self.__get_regex_match(QUEST_SUCCESS_REGEX, input_text, "success")
        failures = self.__get_regex_match(QUEST_FAILURE_REGEX, input_text, "failure")
        if not (len(titles) == len(successes) == len(failures) == len(descriptions)):
            raise GPTMisbehaveError(f"AI generated quests in an unrecognized format:\n\n{input_text}")
        if len(titles) != QUESTS_PER_BATCH:
            raise GPTMisbehaveError(f"AI did not generate {QUESTS_PER_BATCH} quests. AI output:\n\n{input_text}")
        for title, descr, success, failure in zip(titles, descriptions, successes, failures):
            new_quest = Quest.create_default(
                zone,
                starting_number,
                title.replace("*", "").replace("\"", "").replace(":", ""),
                descr,
                success,
                failure
            )
            starting_number += 1
            result.append(new_quest)
        return result

    def _get_events_from_generated_text(self, input_text: str, zone: Zone) -> List[ZoneEvent]:
        result = []
        matches = re.findall(EVENT_REGEX, input_text.replace("\n\n", "\n"), re.MULTILINE)
        if not matches:
            raise GPTMisbehaveError(f"AI output events in an unknown format:\n\n{input_text}")
        event_strings = filter_string_list_remove_empty(get_string_list_from_tuple_list(matches, -1))
        event_strings = filter_strings_list_remove_too_short(event_strings, 5)
        if len(event_strings) != EVENTS_PER_BATCH:
            raise GPTMisbehaveError(f"AI did not generate {EVENTS_PER_BATCH} events. AI output:\n\n{input_text}")
        for text in event_strings:
            new_event = ZoneEvent.create_default(zone, remove_leading_numbers(text))
            result.append(new_event)
        return result

    def _get_artifacts_from_generated_text(self, input_text: str) -> List[Artifact]:
        result = []
        matches = re.findall(ARTIFACT_REGEX, input_text.replace("\n\n", "\n"), re.MULTILINE)
        if not matches:
            raise GPTMisbehaveError(f"AI output artifacts in an unknown format:\n\n{input_text}")
        artifact_names = filter_string_list_remove_empty(get_string_list_from_tuple_list(matches, -2))
        artifact_names = filter_strings_list_remove_too_short(artifact_names, 5)
        artifact_descriptions = filter_string_list_remove_empty(get_string_list_from_tuple_list(matches, -1))
        artifact_descriptions = filter_strings_list_remove_too_short(artifact_descriptions, 5)
        if len(artifact_names) != EVENTS_PER_BATCH:
            raise GPTMisbehaveError(f"AI did not generate {EVENTS_PER_BATCH} events. AI output:\n\n{input_text}")
        for name, description in zip(artifact_names, artifact_descriptions):
            new_artifact = Artifact(
                0,
                name.replace("*", "").replace("\"", "").replace(":", "").replace("Name", "").replace("Description", ""),
                description,
                None
            )
            result.append(new_artifact)
        return result

    def generate_quests(self, zone: Zone, quest_numbers: List[int]) -> List[Quest]:
        messages = get_quests_system_prompt(zone) + build_messages("user", QUESTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        starting_number = quest_numbers[zone.zone_id - 1]
        return self._get_quests_from_generated_text(generated_text, zone, starting_number)

    def generate_zone_events(self, zone: Zone) -> List[ZoneEvent]:
        messages = get_quests_system_prompt(zone) + build_messages("user", EVENTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        return self._get_events_from_generated_text(generated_text, zone)

    def generate_artifacts(self) -> List[Artifact]:
        messages = get_artifacts_system_prompt() + build_messages("user", ARTIFACTS_PROMPT)
        generated_text = self.api_wrapper.create_completion(messages)
        return self._get_artifacts_from_generated_text(generated_text)
