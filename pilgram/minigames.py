from abc import ABC
from typing import Tuple


class PilgramMinigame(ABC):

    def play_turn(self, command: str) -> str:
        """ Play a turn of a minigame """
        raise NotImplementedError

    def get_rewards(self) -> Tuple[int, int]:
        """ return xp & money gained """
        raise NotImplementedError


class HandsMinigame(PilgramMinigame):
    pass
