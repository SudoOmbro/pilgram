from functools import cache
from typing import Union

import requests

from AI.generics import PilgramGenerator


class _ChatGPTAPI:
    """ Wrapper around the ChatGpt API, used by the generator """

    BASE_URL = 'https://api.openai.com'

    def __init__(
            self,
            token: str,
            model: str,
            api_version: str = "v1",
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
    def build_request_url(self, endpoint: str) -> str:
        return f"{self.BASE_URL}/{self.api_version}/{endpoint}"

    def create_completion(self, system_message: str, user_message: str) -> str:
        pass


class ChatGPTGenerator(PilgramGenerator):

    def generate(self, prompt: str):
        pass
