import logging
import re
from abc import ABC

from pilgram.classes import Player
from pilgram.globals import POSITIVE_INTEGER_REGEX, ContentMeta
from pilgram.strings import Strings
from pilgram.utils import has_recently_accessed_cache

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


MINIGAMES: dict[str, type["PilgramMinigame"]] = {}


class PilgramMinigame(ABC):
    """ abstract minigame class, which provides the basic interface for mini-games """
    INTRO_TEXT: str

    def __init_subclass__(cls, game=None, **kwargs):
        super().__init_subclass__()
        if game:
            cls.XP_REWARD = ContentMeta.get(f"minigames.{game}.xp_reward", default=0)
            cls.MONEY_REWARD = ContentMeta.get(f"minigames.{game}.money_reward", default=0)
            cls.EXPLANATION = ContentMeta.get(f"minigames.{game}.explanation")
            cls.COOLDOWN = ContentMeta.get(f"minigames.{game}.cooldown", default=60)
            cls.RENOWN = ContentMeta.get(f"minigames.{game}.renown", default=0)
            cls.STORAGE: dict[int, float] = {}  # player id --> cooldown expire timestamp map
            print(f"minigame {game} registered")
            MINIGAMES[game] = cls

    def __init__(self, player: Player):
        self.player = player
        self.has_started: bool = False
        self.has_ended: bool = False
        self.won: bool = False

    def win(self, message: str) -> str:
        self.has_ended = True
        self.won = True
        return f"{message}\n{Strings.you_win}"

    def lose(self, message: str) -> str:
        self.has_ended = True
        self.won = False
        return f"{message}\n{Strings.you_lose}"

    @classmethod
    def has_played_too_recently(cls, user_id: int) -> bool:
        return has_recently_accessed_cache(cls.STORAGE, user_id, cls.COOLDOWN)

    @classmethod
    def can_play(cls, player: Player) -> tuple[bool, str]:
        """
        returns True & empty string if the player can play the minigame, otherwise returns False & error string.
        By default, it returns True & empty string.
        """
        return True, ""

    def setup_game(self, command: str) -> str:
        """ do everything that needs to be done before starting the game here, like betting & stuff like that """
        raise NotImplementedError

    def setup_text(self) -> str:
        """ return the current setup text """
        raise NotImplementedError

    def turn_text(self) -> str:
        """ return the current turn text """
        raise NotImplementedError

    def play_turn(self, command: str) -> str:
        """ Play a turn of a minigame """
        raise NotImplementedError

    def get_rewards(self) -> tuple[int, int]:
        """ return xp & money gained """
        raise NotImplementedError

    def get_rewards_apply_bonuses(self) -> tuple[int, int]:
        """ return xp & money gained and apply player related bonuses """
        xp, money = self.get_rewards()
        return int(xp * self.player.vocation.minigame_xp_mult), int(money * self.player.vocation.minigame_money_mult)


class GamblingMinigame(PilgramMinigame):

    def __init_subclass__(cls, game=None, **kwargs):
        super().__init_subclass__(game=game, **kwargs)
        if game:
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
        self.player.money -= amount
        self.money_pot = amount
        self.has_started = True
        return Strings.money_pot_ok.format(amount=amount)

    @classmethod
    def can_play(cls, player: Player) -> tuple[bool, str]:
        if player.money >= cls.MIN_BUY_IN:
            return True, ""
        return False, Strings.not_enough_money.format(amount=cls.MIN_BUY_IN - player.money)

    def get_rewards(self) -> tuple[int, int]:
        return self.XP_REWARD, int(self.money_pot * self.PAYOUT)

    def setup_text(self) -> str:
        return self.SETUP_TEXT

    def setup_game(self, command: str) -> str:
        if not re.match(POSITIVE_INTEGER_REGEX, command):
            return Strings.invalid_money_amount
        return self.__get_entry_pot(int(command))
