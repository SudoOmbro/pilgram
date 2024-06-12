from abc import ABC
from typing import List


class GenericLLMInterface(ABC):

    def create_completion(self, messages: List[dict]) -> str:
        raise NotImplementedError
