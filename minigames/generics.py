import re
from abc import ABC
from random import randint
from typing import Tuple, Union, Type, Dict

from pilgram.classes import Player
from pilgram.globals import ContentMeta, POSITIVE_INTEGER_REGEX
from ui.strings import Strings


MINIGAMES: Dict[str, Type["PilgramMinigame"]] = {}


def roll(dice_faces: int) -> int:
    return randint(1, dice_faces)


def get_positive_integer_from_string(
        string: str,
        boundaries: Union[Tuple[int, int], None] = None,
        exclude: Union[Tuple[int, ...], None] = None
) -> Union[int, None]:
    """
    returns a positive integer from the given string if it passes all checks.
    :param string: the input string
    :param boundaries: the boundaries within which the number must be (boundaries included)
    :param exclude: values that the number must not assume.
    :return: a positive integer if all checks pass, None otherwise.
    """
    if not re.match(POSITIVE_INTEGER_REGEX, string):
        return None
    result = int(string)
    if boundaries and ((result < boundaries[0]) or (result > boundaries[1])):
        return None
    if exclude and (result in exclude):
        return None
    return result


class PilgramMinigame(ABC):
    """ abstract minigame class, which provides the basic interface for mini-games """
    INTRO_TEXT: str
    SETUP_TEXT: str
    START_TEXT: str

    def __init_subclass__(cls, game: str = "hands", **kwargs):
        super().__init_subclass__(**kwargs)
        cls.XP_REWARD = ContentMeta.get(f"minigames.{game}.xp_reward")
        cls.EXPLANATION = ContentMeta.get(f"minigames.{game}.explanation")
        MINIGAMES[game] = cls

    def __init__(self, player: Player):
        self.player = player
        self.has_started: bool = False
        self.has_ended: bool = False
        self.won: bool = False

    def win(self, message: str) -> str:
        self.has_ended = True
        self.won = True
        return f"{message}{Strings.you_win}"

    def lose(self, message: str) -> str:
        self.has_ended = True
        self.won = False
        return f"{message}{Strings.you_lose}"

    @classmethod
    def can_play(cls, player: Player) -> Tuple[bool, str]:
        """ returns True & empty string if the player can play the minigame, otherwise returns False & error string """
        raise NotImplementedError

    def setup_game(self, command: str) -> str:
        """ do everything that needs to be done before starting the game here, like betting & stuff like that """
        raise NotImplementedError

    def play_turn(self, command: str) -> str:
        """ Play a turn of a minigame """
        raise NotImplementedError

    def get_rewards(self) -> Tuple[int, int]:
        """ return xp & money gained """
        raise NotImplementedError


class GamblingMinigame(PilgramMinigame):

    def __init_subclass__(cls, game: str = "hands", **kwargs):
        super().__init_subclass__(game=game, **kwargs)
        cls.MIN_BUY_IN: int = ContentMeta.get(f"minigames.{game}.min_buy_in")
        cls.MAX_BUY_IN: int = ContentMeta.get(f"minigames.{game}.max_buy_in")
        cls.PAYOUT: float = ContentMeta.get(f"minigames.{game}.payout")
        cls.SETUP_TEXT = Strings.how_much_do_you_bet.format(min=cls.MIN_BUY_IN, max=cls.MAX_BUY_IN)

    def __init__(self, player: Player):
        super().__init__(player)
        self.money_pot: int = 0

    def __get_entry_pot(self, amount: int) -> str:
        if amount > self.player.money:
            return Strings.not_enough_money.format(amount=amount - self.player.money)
        if amount < self.MIN_BUY_IN:
            return Strings.money_pot_too_low.format(amount=self.MIN_BUY_IN)
        if amount > self.MAX_BUY_IN:
            return Strings.money_pot_too_high.format(amount=self.MAX_BUY_IN)
        self.player -= amount
        self.money_pot = amount
        self.has_started = True
        return Strings.money_pot_ok.format(amount=amount)

    @classmethod
    def can_play(cls, player: Player) -> Tuple[bool, str]:
        if player.money >= cls.MIN_BUY_IN:
            return True, ""
        return False, Strings.not_enough_money.format(amount=cls.MIN_BUY_IN - player.money)

    def get_rewards(self) -> Tuple[int, int]:
        return self.XP_REWARD, int(self.money_pot * self.PAYOUT)

    def setup_game(self, command: str) -> str:
        if not re.match(POSITIVE_INTEGER_REGEX, command):
            return Strings.invalid_money_amount
        return self.__get_entry_pot(int(command))
