from abc import ABC
from typing import Tuple

from pilgram.classes import Player
from pilgram.globals import ContentMeta


class GamblingData:

    def __init__(self, game_name: str):
        self.min_buy_in: int = ContentMeta.get(f"minigames.{game_name}.min_buy_in")
        self.max_buy_in: int = ContentMeta.get(f"minigames.{game_name}.max_buy_in")
        self.payout: float = ContentMeta.get(f"minigames.{game_name}.payout")


class PilgramMinigame(ABC):
    """ abstract minigame class, which provides the basic interface for mini-games """
    IS_GAMBLING: bool

    def __init__(self, player: Player):
        self.player = player

    def play_turn(self, command: str) -> str:
        """ Play a turn of a minigame """
        raise NotImplementedError

    def get_rewards(self) -> Tuple[int, int]:
        """ return xp & money gained """
        raise NotImplementedError


class HandsMinigame(PilgramMinigame):
    IS_GAMBLING = True

    def __init__(self, player: Player):
        super().__init__(player)
        self.gambling_data: GamblingData = GamblingData("hands")

    def play_turn(self, command: str) -> str:
        # TODO
        pass
