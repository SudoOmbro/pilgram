import unittest
from random import choice

from minigames.games import HandsMinigame
from minigames.generics import PilgramMinigame
from minigames.utils import (
    generate_maze,
    get_direction_plus_90_degrees,
    get_random_word,
    get_word_letters,
    print_maze,
)
from pilgram.classes import Player


class TestMinigames(unittest.TestCase):

    def test_can_play(self):
        player = Player.create_default(0, "ombro", "test")
        player.money = HandsMinigame.MIN_BUY_IN - 1
        can_play, error = HandsMinigame.can_play(player)
        self.assertFalse(can_play)
        self.assertTrue(error)
        player.money = HandsMinigame.MAX_BUY_IN
        can_play, error = HandsMinigame.can_play(player)
        self.assertTrue(can_play)
        self.assertFalse(error)

    def __play_minigame(
            self,
            minigame: PilgramMinigame,
            setup_commands: list[str],
            game_commands: list[str]
    ) -> bool:
        for command in setup_commands:
            result = minigame.setup_game(command)
        for command in game_commands:
            result = minigame.play_turn(command)
        return minigame.has_ended and minigame.won

    def test_hands_minigame(self):
        player = Player.create_default(0, "ombro", "test")
        minigame = HandsMinigame(player)
        result = minigame.setup_game("100")
        # print(result)
        result = minigame.play_turn("12")
        # print(result)
        self.assertTrue(minigame.has_ended)

    def test_hands_minigame_winrate(self):
        # a gambling game should have a win rate lower or equal to 50%
        sample_size: int = 100000
        player = Player.create_default(0, "ombro", "test")
        losses_and_wins = [0, 0]
        for _ in range(sample_size):
            minigame = HandsMinigame(player)
            result: bool = self.__play_minigame(minigame, ["100"], [str(choice(HandsMinigame.BET_BIASED))])
            losses_and_wins[int(result)] += 1
        # print(f"HANDS biased win rate: {losses_and_wins[1] / sample_size:.2f}% ({losses_and_wins[0]} losses & {losses_and_wins[1]} wins)")
        self.assertLessEqual(losses_and_wins[1], losses_and_wins[0])
        losses_and_wins = [0, 0]
        for _ in range(sample_size):
            minigame = HandsMinigame(player)
            result: bool = self.__play_minigame(minigame, ["100"], [str(choice((3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18)))])
            losses_and_wins[int(result)] += 1
        # print(f"HANDS random win rate: {losses_and_wins[1] / sample_size:.2f}% ({losses_and_wins[0]} losses & {losses_and_wins[1]} wins)")
        self.assertLessEqual(losses_and_wins[1], losses_and_wins[0])

    def test_get_random_word(self):
        word = get_random_word()
        self.assertTrue(word in ["elden", "cock", "ring"])

    def test_get_word_letters(self):
        letters = get_word_letters("ombro")
        self.assertEqual(letters, ['o', 'm', 'b', 'r'])

    def test_get_direction_plus_90_degrees(self):
        result = get_direction_plus_90_degrees(0)
        self.assertEqual(result, (0, 1))
        result = get_direction_plus_90_degrees(3)
        self.assertEqual(result, (1, 0))

    def test_generate_maze(self):
        maze = generate_maze(15, 15, 7)
        string = print_maze(maze)
        print(string)
