import unittest

from pilgram.classes import Quest, Zone, Player, ZoneEvent, QuickTimeEvent


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
        player.level = 4
        player.gear_level = 3
        # setup quest
        zone = Zone(0, "test", 45, "test")
        quest = Quest(0, zone, 0, "test", "", "", "")
        # do tests
        for num in range(10):
            quest.number = num
            fail_rate = _get_quest_fail_rate(quest, player)
            _print_quest_fail_rate(fail_rate, quest, player)

    def test_quest_rewards(self):
        player = Player.create_default(0, "test", "")
        zone = Zone(0, "test", 5, "test")
        quest = Quest(0, zone, 0, "test", "", "", "")
        self.assertEqual(quest.get_rewards(player), (4250, 3000))

    def test_zone_events(self):
        player = Player.create_default(0, "test", "")
        player.level = 10
        zone = Zone(9, "test", 5, "test")
        zone.level = 30
        zone_event = ZoneEvent(0, zone, "test")
        rewards_under_leveled = zone_event.get_rewards(player)
        print(rewards_under_leveled)
        player.level = 100
        rewards_normal = zone_event.get_rewards(player)
        print(rewards_normal)
        self.assertTrue(rewards_normal[0] > rewards_under_leveled[0])

    def test_quick_time_events(self):
        qte = QuickTimeEvent(
            "TEST D",
            ["s1", "s2"],
            ["f1", "f2"],
            [("test1", 100), ("test2", 50)],
            [[lambda player: player.add_money(100), lambda player: player.add_xp(50)], [lambda player: player.add_xp(500)]]
        )
        qte1 = QuickTimeEvent.LIST[0]
        print(qte1.options)
        print(qte1.rewards)
        print(qte1.successes)
        print(qte1.failures)
