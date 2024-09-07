import logging
import math
import random
import re
from collections.abc import Iterable

from minigames.generics import GamblingMinigame, PilgramMinigame
from minigames.utils import (
    MAZE,
    generate_maze,
    get_positive_integer_from_string,
    get_random_word,
    print_maze,
    roll,
)
from minigames.utils import TILE_REPRESENTATIONS as TR
from pilgram.classes import Player
from pilgram.globals import POSITIVE_INTEGER_REGEX
from pilgram.strings import Strings

AAA = ""


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class HandsMinigame(GamblingMinigame, game="hands"):
    INTRO_TEXT = Strings.start_hands_minigame
    BET_BIASED = (3, 4, 6, 7, 8, 9, 11, 11, 11, 11, 11, 11, 12, 12, 12, 12, 13, 13, 14, 15, 16, 17, 18)

    def __init__(self, player: Player):
        super().__init__(player)
        self.state: int = 0

    @staticmethod
    def __get_rolls() -> tuple[list[int], int]:
        """ returns the 3 rolls and the sum of all the rolls  """
        rolls = [roll(6) for _ in range(3)]
        return rolls, sum(rolls)

    @staticmethod
    def __generate_message(subject: str, rolls: list[int], result: int) -> str:
        return f"{subject} Rolls: " + " + ".join(str(x) for x in rolls) + f" = {result}"

    @staticmethod
    def __check_win(bet: int, rolls: list[int], result: int) -> bool:
        if result == bet:
            return True
        for i, x in enumerate(rolls):
            for j, y in enumerate(rolls):
                if i == j:
                    continue
                if (x + y) == bet:
                    return True
        return False

    def turn_text(self) -> str:
        return Strings.hands_minigame_bet

    def play_turn(self, command: str) -> str:
        bet = get_positive_integer_from_string(command, boundaries=(3, 18), exclude=(5, 10))
        if not bet:
            return Strings.invalid_bet
        enemy_bet = random.choice(self.BET_BIASED)
        message = f"You bet {bet}, the stranger bets {enemy_bet}\n\n"
        for i in range(40):
            your_rolls, your_result = self.__get_rolls()
            enemy_rolls, enemy_result = self.__get_rolls()
            message += f"Turn {i + 1}\n"
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


class FateMinigame(GamblingMinigame, game="fate"):
    INTRO_TEXT = Strings.start_fate_minigame
    DICE_FACES = 13
    MAX_SCORE = 27

    def __init__(self, player: Player):
        super().__init__(player)
        self.score: int = 0
        self.pilgrim_score: int = 0
        self.turns_remaining: int = 3
        self.pilgrim_safety: int = random.randint(1, 4)

    def __print_too_high(self, score: int):
        if score > self.MAX_SCORE:
            return " --> *OUT!*"
        return ""

    def print_game_state(self):
        return f"*Pilgrim's score*: {self.pilgrim_score}{self.__print_too_high(self.pilgrim_score)}\n*Your score*: {self.score}{self.__print_too_high(self.score)}"

    def __pilgrim_turn(self) -> int:
        if self.pilgrim_score > (self.MAX_SCORE - self.pilgrim_safety):
            return 0
        return roll(self.DICE_FACES)

    def __check_win(self, message: str) -> str | None:
        if self.score > self.MAX_SCORE:
            return self.lose(message + Strings.fate_minigame_lose)
        if self.pilgrim_score > self.MAX_SCORE:
            return self.win(message + Strings.fate_minigame_win)
        if self.turns_remaining == 0:
            if self.pilgrim_score > self.score:
                return self.lose(message + Strings.fate_minigame_lose)
            else:
                return self.win(message + Strings.fate_minigame_win)
        return None

    def turn_text(self) -> str:
        return f"{self.print_game_state()}\n\nWhat do you want to do? (r)oll d13 or (s)tay?"

    def play_turn(self, command: str) -> str:
        action = command[0].lower()
        message = f"Turns remaining {self.turns_remaining - 1}:\n\n"
        if action == "r":
            your_roll = roll(self.DICE_FACES)
            self.score += your_roll
            message += f"You rolled {your_roll}.\n"
        elif action != "s":
            return "Invalid input. Send either 'r' or 's'"
        else:
            message += "You stayed.\n\n"
        pilgrim_roll = self.__pilgrim_turn()
        self.pilgrim_score += pilgrim_roll
        if pilgrim_roll == 0:
            message += "The Pilgrim stayed.\n\n"
        else:
            message += f"The Pilgrim rolled {pilgrim_roll}.\n\n"
        self.turns_remaining -= 1
        has_game_ended = self.__check_win(message + self.print_game_state() + "\n\n")
        if has_game_ended:
            return has_game_ended
        return message + self.turn_text()


class HangmanMinigame(PilgramMinigame, game="open"):
    INTRO_TEXT = "You stumble upon a door that won't open. It whispers _Say the word and I'll finally be free..._"

    def __init__(self, player: Player):
        super().__init__(player)
        self.has_started = True  # skip active setup, not needed
        self.word = get_random_word().lower()
        self.remaining_tries: int = 3 + (len(self.word) // 2)
        # setup game
        self.guessed_word = ["\\_" for _ in range(len(self.word))]
        index = random.randint(0, len(self.guessed_word) - 1)
        self.guessed_word[index] = self.word[index]

    def __print_word_to_guess(self) -> str:
        return "  ".join([x.upper() for x in self.guessed_word])

    def __get_guessed_letters_number(self):
        result: int = 0
        for letter in self.guessed_word:
            if letter != "\\_":
                result += 1
        return result

    def turn_text(self) -> str:
        return "*Word:*\n\n" + self.__print_word_to_guess() + f"\n\n_guesses left: {self.remaining_tries}_"

    def play_turn(self, user_input: str) -> str:
        guess = user_input.lower()
        if len(user_input) > len(self.word):
            return "Guess too long"
        if len(user_input) < len(self.word):
            return "Guess too short"
        if guess == self.word:
            return self.win("You guessed correctly, the door opens with a relieved breath.")
        for index, letter in enumerate(guess):
            if self.word[index] == letter:
                self.guessed_word[index] = letter
        self.remaining_tries -= 1
        if self.remaining_tries == 0:
            return self.lose(f"The word was '{self.word}'. The door remains closed. It whimpers.")
        return self.turn_text()

    def get_rewards(self) -> tuple[int, int]:
        multiplier = ((len(self.word) // 2) * self.remaining_tries) + 1
        return ((self.XP_REWARD * multiplier) + self.__get_guessed_letters_number()), (self.MONEY_REWARD * multiplier)


class MazeMinigame(PilgramMinigame, game="illusion"):
    INTRO_TEXT = "You spot a wall that looks transparent. Upon closer inspection it turns out that is is indeed an illusion.\nAn illusion you want to explore."
    REFERENCE = f"{TR[0]}: Empty space\n{TR[1]}: Wall\n{TR[2]}: You\n{TR[3]}: Active trap\n{TR[4]}: Deactivated trap\n{TR[5]}: Treasure\n{TR[-1]}: Visited tiles"
    DIRECTIONS = {
        "n": (-1, 0),
        "s": (1, 0),
        "e": (0, 1),
        "w": (0, -1),
        "i": (0, 0)
    }
    INSTRUCTIONS = "Where do you want to go? Write n/w/e/s/i \\[steps (optional)]"

    def __init__(self, player: Player):
        super().__init__(player)
        self.hp: int = 0
        self.maze: list[list[int]] = []
        self.remaining_turns: int = 10
        self.difficulty: int = 1

    def __update_maze(self, player_direction: tuple[int, int]) -> int:
        """
        updates the maze by switching traps on & off and moving the player.

        :param player_direction: direction where the player wants to move (or stay)
        :return: 0 if player hasn't hit anything, 1 if player hit a wall, 2 if player hit a trap, 3 if player wins, 4 if player idled
        """
        return_code: int = 0
        px, py = player_direction
        for y, row in enumerate(self.maze):
            for x, tile in enumerate(row):
                if tile < 2:
                    continue  # optimize for the most common scenario
                if tile == MAZE.TRAP_ON:
                    self.maze[y][x] = MAZE.TRAP_OFF
                elif tile == MAZE.TRAP_OFF:
                    self.maze[y][x] = MAZE.TRAP_ON
                elif tile == MAZE.PLAYER:
                    px, py = x, y
        if player_direction == (0, 0):
            return 4
        next_x, next_y = px + player_direction[1], py + player_direction[0]
        if self.maze[next_y][next_x] == MAZE.WALL:
            return 1
        if self.maze[next_y][next_x] == MAZE.TRAP_ON:
            self.hp -= 1
            return_code = 2
        elif self.maze[next_y][next_x] == MAZE.END:
            return_code = 3
        self.maze[py][px] = MAZE.VISITED
        self.maze[next_y][next_x] = MAZE.PLAYER
        return return_code

    def setup_text(self) -> str:
        return "How brave are you feeling? send a number from 1 to 5\n\n(note that numbers greater than 2 might not render correctly on android due to limitations on emojis, while 4 & 5 might be too wide for some phones)"

    def turn_text(self) -> str:
        return "*Illusion*:\n\n" + print_maze(self.maze) + f"\nHP: {self.hp}, turns left: {self.remaining_turns}\n\n{self.INSTRUCTIONS}"

    def setup_game(self, command: str) -> str:
        if not re.match(POSITIVE_INTEGER_REGEX, command):
            return "Not a number"
        number = int(command)
        if number not in range(1, 6):
            return "send a number ONLY from 1 to 5"
        self.difficulty = number
        size = 7 + 2 * (number - 1)
        self.maze = generate_maze(size, size, 7)
        self.hp = 3
        self.remaining_turns = 10 * number
        self.has_started = True
        return "You take a deep breath and run into the illusion.\n\n" + self.REFERENCE

    def play_turn(self, command: str) -> str:
        split_command = command.split()
        direction_command = split_command[0].lower()
        direction = self.DIRECTIONS.get(direction_command, None)
        if not direction:
            return "Invalid command. Example of 2 valid commands:\n`n`\n`n 2`\n\n" + self.turn_text()
        steps: int = -1
        if len(split_command) > 1:
            steps_string = split_command[1]
            if re.match(POSITIVE_INTEGER_REGEX, steps_string):
                steps = int(steps_string)
                if steps == 0:
                    steps = -1
        code: int = 0
        while (code == 0) and steps != 0:
            code = self.__update_maze(direction)
            steps -= 1
        message = "You hit a wall." if code == 1 else "You idled for a turn."
        if code == 2:
            message = "You hit a trap!"
            if self.hp < 1:
                return self.lose("You hit too many traps. Just as you feel your life slipping away you are ejected from the illusion, bruised but in one piece.")
        elif code == 3:
            return self.win(print_maze(self.maze) + "\n\nYou manage to find the treasure hidden in the illusion.")
        self.remaining_turns -= 1
        if self.remaining_turns == 0:
            return self.lose("The illusion has become too unstable. You are ejected empty-handed.")
        return f"{message}\n\n{self.turn_text()}"

    def get_rewards(self) -> tuple[int, int]:
        multiplier = (2 * self.difficulty) + self.hp
        bonus = self.remaining_turns
        # return (self.XP_REWARD * multiplier + bonus), (self.MONEY_REWARD * multiplier + bonus)
        return -1, (self.MONEY_REWARD * multiplier + bonus)


class RockPaperScissors(PilgramMinigame, game="war"):
    INTRO_TEXT = "You meet a strange looking guy holding a box of minis that wants to play 'War'"

    TROOPS: dict[str, str] = {
        "c": "Cavalry",
        "a": "Archers",
        "s": "Spears"
    }

    BEATS: dict[str, str] = {
        "c": "a",
        "a": "s",
        "s": "c"
    }

    def __init__(self, player: Player):
        super().__init__(player)
        self.has_started = True  # skip active setup, not needed
        self.player_supply = 5
        self.opponent_supply = 5

    def turn_text(self) -> str:
        return f"Your supply: {self.player_supply}\nOpponent supply: {self.opponent_supply}\n\nWhich troop do you want to deploy?\nCavalry \[c]\nSpears \[s]\nArchers \[a]"

    def play_turn(self, command: str) -> str:
        # choose troops
        chosen_troop = command.lower()[0]
        if chosen_troop not in self.TROOPS:
            return "The selected troop is not valid."
        enemy_troop = random.choice(("c", "a", "s"))
        text = f"You deploy {self.TROOPS[chosen_troop]}\nThe enemy deploys {self.TROOPS[enemy_troop]}\n\n"
        # calculate counters
        if chosen_troop == enemy_troop:
            self.opponent_supply -= 1
            self.player_supply -= 1
            text += "Your troops destroy each-other!\n\n"
        elif self.BEATS[chosen_troop] == enemy_troop:
            self.opponent_supply -= 1
            text += "Your opponent loses their troops!\n\n"
        elif self.BEATS[enemy_troop] == chosen_troop:
            self.player_supply -= 1
            text += "You lose your troops!\n\n"
        # check win
        if self.player_supply == 0:
            return text + self.lose("You ran out of supply!")
        elif self.opponent_supply == 0:
            return text + self.win("Your opponent ran out of supply!")
        return text + self.turn_text()

    def get_rewards(self) -> tuple[int, int]:
        multiplier = self.player_supply + 1
        return multiplier * self.XP_REWARD, multiplier + self.MONEY_REWARD


class AvoidArrows(PilgramMinigame, game="trap"):
    INTRO_TEXT = "You fall into a trap room!"
    FIELD_SIZE = 5

    class Tiles:
        EMPTY = 0
        PLAYER = 1
        ARROW_RIGHT = 2
        ARROW_DOWN = 3
        ARROW_LEFT = 4
        ARROW_UP = 5

    ARROWS = (
        Tiles.ARROW_RIGHT,
        Tiles.ARROW_DOWN,
        Tiles.ARROW_LEFT,
        Tiles.ARROW_UP
    )

    GRAPHICS = {
        0: "⬜",
        1: "🧑",
        2: "➡️",
        3: "⬇️",
        4: "⬅️",
        5: "⬆️"
    }

    HALF_PI = math.pi / 2

    def __init__(self, player: Player):
        super().__init__(player)
        self.has_started = True  # skip active setup, not needed
        self.play_field: list[list[int]] = [[0 for _ in range(self.FIELD_SIZE)] for _ in range(self.FIELD_SIZE)]
        self._set_tile(2, 2, self.Tiles.PLAYER)
        self.turns_left = 15
        self._try_spawn_arrow()

    def _get_tile(self, x: int, y: int) -> int:
        return self.play_field[y][x]

    def _set_tile(self, x: int, y: int, tile: int) -> None:
        self.play_field[y][x] = tile

    def _spawn_arrow(self, x: int, y: int, direction: int):
        if self.play_field[y][x] == 0:
            self._set_tile(x, y, direction + 2)

    def _try_spawn_arrow(self):
        direction: int = random.randint(0, 3)
        offset: int = random.randint(1, self.FIELD_SIZE - 2)
        if direction == 0:
            self._spawn_arrow(0, offset, direction)
        elif direction == 1:
            self._spawn_arrow(offset, 0, direction)
        elif direction == 2:
            self._spawn_arrow(self.FIELD_SIZE - 1, offset, direction)
        elif direction == 3:
            self._spawn_arrow(offset, self.FIELD_SIZE - 1, direction)

    def _field_iterator(self):
        for y in range(self.FIELD_SIZE):
            for x in range(self.FIELD_SIZE):
                yield x, y, self.play_field[y][x]

    def turn_text(self) -> str:
        text = f"{self.turns_left} turns left\n\n"
        # print trap room
        for x, y, tile in self._field_iterator():
            text += self.GRAPHICS.get(tile, "A")
            if x == self.FIELD_SIZE - 1:
                text += "\n"
        # add instructions & return
        return text + "\nWhat do you want to do? (Write n/w/e/s/i)"

    def _check_collision(self, x: int, y: int, entities_to_check_for: Iterable[int]) -> bool:
        tile: int = self.play_field[y][x]
        return (tile != self.Tiles.EMPTY) and (tile in entities_to_check_for)

    def _is_out_of_bounds(self, x: int, y: int):
        return (x > (self.FIELD_SIZE - 1)) or (y > (self.FIELD_SIZE - 1)) or (x < 0) or (y < 0)

    def play_turn(self, command: str) -> str:
        # get player direction
        direction_command = command[0].lower()
        direction = MazeMinigame.DIRECTIONS.get(direction_command, None)
        if not direction:
            return "Invalid command.\n\n" + self.turn_text()
        # move player
        for x, y, tile in self._field_iterator():
            if tile == self.Tiles.PLAYER:
                new_x = x + direction[1]
                new_y = y + direction[0]
                if self._is_out_of_bounds(new_x, new_y):
                    continue
                if self._check_collision(new_x, new_y, self.ARROWS):
                    return self.lose(Strings.trap_minigame_lose)
                self._set_tile(x, y, self.Tiles.EMPTY)
                self._set_tile(new_x, new_y, tile)
                break
        # try move arrows
        arrows: list[tuple[int, int, int]] = []  # arrow direction, x, y
        for x, y, tile in self._field_iterator():
            if tile >= self.Tiles.ARROW_RIGHT:
                new_x = x + int(math.cos((tile - 2) * self.HALF_PI))
                new_y = y + int(math.sin((tile - 2) * self.HALF_PI))
                if self._is_out_of_bounds(new_x, new_y):
                    self._set_tile(x, y, self.Tiles.EMPTY)
                    continue
                if self._check_collision(new_x, new_y, (self.Tiles.PLAYER,)):
                    return self.lose(Strings.trap_minigame_lose)
                self._set_tile(x, y, self.Tiles.EMPTY)
                arrows.append((tile, new_x, new_y))
        # actually move arrows
        for arrow, x, y in arrows:
            self._set_tile(x, y, arrow)
        # spawn new arrow every turn
        self._try_spawn_arrow()
        # advance turn & check win
        if self.turns_left > 1:
            self.turns_left -= 1
            return self.turn_text()
        return self.win("You manged to survive the arrows!")

    def get_rewards(self) -> tuple[int, int]:
        return -1, self.MONEY_REWARD
