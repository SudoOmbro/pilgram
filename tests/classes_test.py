import unittest

from pilgram.classes import Quest, Zone, Player


def _get_quest_fail_rate(quest: Quest, player: Player, tests: int = 10000) -> float:
    failures = 0
    for _ in range(tests):
        failures += int(not quest.finish_quest(player))
    return failures / tests


def _print_quest_fail_rate(fail_rate: float, quest: Quest, player: Player):
    print(f"player  (lv {player.level}, gear {player.gear_level}) | quest (lv {quest.zone.level}, num {quest.number}) fail rate: {fail_rate:.2f}")


class TestClasses(unittest.TestCase):

    def test_finish_quest(self):
        # setup player
        player = Player.create_default(0, "test", "")
        player.level = 5
        player.gear_level = 6
        # setup quest
        zone = Zone(0, "test", 5, "test")
        quest = Quest(0, zone, 0, "test", "", "", "")
        # do tests
        for num in range(10):
            quest.number = num
            fail_rate = _get_quest_fail_rate(quest, player)
            _print_quest_fail_rate(fail_rate, quest, player)


