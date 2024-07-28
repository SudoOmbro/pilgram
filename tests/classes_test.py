import time
import unittest
from random import randint

from pilgram.classes import (
    Enemy,
    EnemyMeta,
    Player,
    Quest,
    QuickTimeEvent,
    Zone,
    ZoneEvent,
)
from pilgram.combat_classes import CombatContainer, Damage
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.modifiers import Modifier, print_all_modifiers


def _get_quest_fail_rate(quest: Quest, player: Player, tests: int = 100) -> float:
    failures = 0
    for _ in range(tests):
        result, roll, roll_to_beat = quest.finish_quest(player)
        if not result:
            print(f"Fail! (rolled {roll}, {roll_to_beat} to beat)")
        failures += int(not result)
    return failures / tests


def _print_quest_fail_rate(fail_rate: float, quest: Quest, player: Player):
    print(f"player  (lv {player.level}, gear {player.gear_level}) | quest (lv {quest.zone.level}, num {quest.number}) fail rate: {fail_rate:.2f}")


def _generate_equipment(player: Player, equipment_type: EquipmentType, modifiers: list[Modifier]) -> Equipment:
    _, damage, resist = Equipment.get_dmg_and_resist_values(player.level, time.time(), equipment_type.is_weapon)
    Damage.generate_from_seed(time.time(), player.level)
    return Equipment(
        0,
        player.level,
        equipment_type,
        "longsword",
        time.time(),
        damage,
        resist,
        modifiers
    )


class TestClasses(unittest.TestCase):

    def test_finish_quest(self):
        # setup player
        player = Player.create_default(0, "test", "")
        player.level = 11
        player.gear_level = 9
        # setup quest
        zone = Zone(0, "test", 5, "test", Damage.get_empty(), Damage.get_empty(), {})
        quest = Quest(0, zone, 4, "test", "", "", "")
        # do tests
        for num in range(100):
            quest.number = num
            fail_rate = _get_quest_fail_rate(quest, player)
            _print_quest_fail_rate(fail_rate, quest, player)

    def test_quest_rewards(self):
        player = Player.create_default(0, "test", "")
        zone = Zone(0, "test", 5, "test", Damage.get_empty(), Damage.get_empty(), {})
        quest = Quest(0, zone, 0, "test", "", "", "")
        self.assertEqual(quest.get_rewards(player), (4250, 3000))

    def test_zone_events(self):
        player = Player.create_default(0, "test", "")
        player.level = 10
        zone = Zone(9, "test", 5, "test", Damage.get_empty(), Damage.get_empty(), {})
        zone.level = 30
        zone_event = ZoneEvent(0, zone, "test")
        rewards_under_leveled = zone_event.get_rewards(player)
        print(rewards_under_leveled)
        player.level = 100
        rewards_normal = zone_event.get_rewards(player)
        print(rewards_normal)
        self.assertTrue(rewards_normal[0] > rewards_under_leveled[0])

    def test_print_quick_time_events(self):
        for qte in QuickTimeEvent.LIST:
            print(qte)

    def test_print_modifiers(self):
        print_all_modifiers()

    def test_generate_equipment(self):
        for i in range(10):
            print("\n-----------------------\n")
            equipment = Equipment.generate(5 + (10 * i), EquipmentType.get_random(), randint(0, 3))
            print(str(equipment))

    def test_combat(self):
        player = Player.create_default(0, "Ombro", "")
        player.level = 2
        player.gear_level = 2
        zone = Zone(
            1,
            "zone name",
            8,
            "AAAA",
            Damage(0, 0, 1, 0, 0, 0, 0, 0),
            Damage(0, 0, 0, 0, 0, 0, 0, 0),
            {}
        )
        player.equip_item(_generate_equipment(
            player,
            EquipmentType.get(0),  # longsword
            []
        ))
        player.equip_item(_generate_equipment(
            player,
            EquipmentType.get(21),  # Lorica segmentata
            []
        ))
        player.satchel = [ConsumableItem.get(15), ConsumableItem.get(7), ConsumableItem.get(6), ConsumableItem.get(5), ConsumableItem.get(13)]
        enemy = Enemy(
            EnemyMeta(0, zone, "Cock monger", "AAAAA", "WIN", "LOSS"),
            [],
            0
        )
        combat = CombatContainer([player, enemy], {player: None, enemy: None})
        result = combat.fight()
        print(result)
