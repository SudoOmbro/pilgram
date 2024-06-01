import logging
from abc import ABC
from functools import cache
from typing import Union, List

import requests

from AI.generics import PilgramGenerator


log = logging.getLogger(__name__)


WORLD_PROMPT = "You write about a low fantasy world named Borom"
STYLE_PROMPT = ""
FORMATTING_PROMPT = ""


def build_messages(role: str, *messages: str) -> List[dict]:
    return [{"role": role, "content": x} for x in messages]


class GPTAPIError(Exception):

    def __init__(self, response: requests.Response):
        super().__init__()
        self.status_code = response.status_code
        self.response = response


class GenericGPTAPI(ABC):

    def create_completion(self, messages: List[dict]) -> str:
        raise NotImplementedError


class ChatGPTAPI(GenericGPTAPI):
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
        self.project = project
        self.organization = organization
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if organization:
            self.headers["organization"] = organization
        if project:
            self.headers["project"] = project

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
            jresponse = response.json()
            log.info(jresponse)
            return jresponse["choiches"][0]["message"]["content"]
        log.error(f"could not create completion, response: {response.text}")
        raise GPTAPIError(response)


class ChatGPTGenerator(PilgramGenerator):

    QUEST_SYS = build_messages("system", WORLD_PROMPT, FORMATTING_PROMPT)
    EVENT_SYS = build_messages("system", WORLD_PROMPT, STYLE_PROMPT, FORMATTING_PROMPT)

    def __init__(self, api_wrapper: GenericGPTAPI):
        self.api_wrapper = api_wrapper

    def generate(self, prompt: str):
        pass
