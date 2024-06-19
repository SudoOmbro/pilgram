import logging
import random
from typing import Tuple, List

from minigames.generics import GamblingMinigame, PilgramMinigame
from minigames.utils import get_positive_integer_from_string, roll, get_random_word, get_word_letters
from pilgram.classes import Player
from ui.strings import Strings


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class HandsMinigame(GamblingMinigame, game="hands"):
    INTRO_TEXT = Strings.start_hands_minigame
    BET_BIASED = (3, 4, 6, 7, 8, 9, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 13, 13, 14, 15, 16, 17, 18)

    def __init__(self, player: Player):
        super().__init__(player)
        self.state: int = 0

    @staticmethod
    def __get_rolls() -> Tuple[List[int], int]:
        """ returns the 3 rolls and the sum of all the rolls  """
        rolls = [roll(6) for _ in range(3)]
        return rolls, sum(rolls)

    @staticmethod
    def __generate_message(subject: str, rolls: List[int], result: int) -> str:
        return f"{subject} Rolls: " + " + ".join(str(x) for x in rolls) + f" = {result}"

    @staticmethod
    def __check_win(bet: int, rolls: List[int], result: int) -> bool:
        if result == bet:
            return True
        for i, x in enumerate(rolls):
            for j, y in enumerate(rolls):
                if i == j:
                    continue
                if (x + y) == result:
                    return True
        return False

    def turn_text(self) -> str:
        return Strings.hands_minigame_bet

    def play_turn(self, command: str) -> str:
        bet = get_positive_integer_from_string(command, boundaries=(3, 18), exclude=(5, 10))
        if not bet:
            return Strings.invalid_bet
        enemy_bet = random.choice(self.BET_BIASED)
        message = f"You bet {bet}, the stranger bet {enemy_bet}\n\n"
        for i in range(40):
            your_rolls, your_result = self.__get_rolls()
            enemy_rolls, enemy_result = self.__get_rolls()
            message += f"Turn {i+1}\n"
            your_message = self.__generate_message("Your", your_rolls, your_result)
            enemy_message = self.__generate_message("The stranger", enemy_rolls, enemy_result)
            message += f"{your_message}\n{enemy_message}\n\n"
            if your_result in (5, 10):
                return self.lose(message)
            if enemy_result in (5, 10):
                return self.win(message)
            if self.__check_win(bet, your_rolls, your_result):
                return self.win(message)
            if self.__check_win(enemy_bet, enemy_rolls, enemy_result):
                return self.lose(message)
        # we should never get here but just in case let the player win, they won't question it.
        return self.win(message)


class HangmanMinigame(PilgramMinigame, game="open"):
    INTRO_TEXT = "You stumble upon a door that won't open. It whispers _Say the word and i'll finally be free..._"

    def __init__(self, player: Player):
        super().__init__(player)
        self.has_started = True  # skip active setup, not needed
        self.word = get_random_word()
        self.remaining_tries: int = 2 + (len(self.word) // 2)
        # setup game
        self.guessed_word = ["\\_" for _ in range(len(self.word))]
        index = random.randint(0, len(self.guessed_word) - 1)
        self.guessed_word[index] = self.word[index]

    def __print_word_to_guess(self) -> str:
        return "  ".join([x.upper() for x in self.guessed_word])

    def turn_text(self) -> str:
        return "*Word:*\n\n" + self.__print_word_to_guess() + f"\n\n_guesses left: {self.remaining_tries}_"

    def play_turn(self, user_input: str) -> str:
        guess = user_input.lower()
        if len(user_input) > len(self.word):
            return "Guess too long"
        if len(user_input) < len(self.word):
            return "Guess too short"
        if guess == self.word:
            return self.win("You guessed correctly, the door opens silently.")
        for index, letter in enumerate(guess):
            if self.word[index] == letter:
                self.guessed_word[index] = letter
        self.remaining_tries -= 1
        if self.remaining_tries == 0:
            return self.lose(f"The word was '{self.word}'. The door remains closed.")
        return self.turn_text()

    def get_rewards(self) -> Tuple[int, int]:
        multiplier = ((len(self.word) // 2) * self.remaining_tries) + 1
        return (self.XP_REWARD * multiplier), (self.MONEY_REWARD * multiplier)
