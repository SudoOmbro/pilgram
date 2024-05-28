from abc import ABC
from typing import Any, List

from pilgram.classes import Zone, ZoneEvent, Quest


class PilgramGenerator(ABC):

    def generate(self, prompt: str) -> Any:
        raise NotImplementedError

    def generate_zone_events(self, zone: Zone) -> List[ZoneEvent]:
        raise NotImplementedError

    def generate_quests(self, zone: Zone) -> List[Quest]:
        raise NotImplementedError
