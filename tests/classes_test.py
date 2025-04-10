import time
import unittest
from copy import deepcopy
from random import randint

from pilgram.classes import (
    Enemy,
    EnemyMeta,
    Player,
    Quest,
    QuickTimeEvent,
    Zone,
    ZoneEvent, Vocation,
)
from pilgram.combat_classes import CombatContainer, Damage
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.modifiers import Modifier, print_all_modifiers, get_modifier_from_name


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
    _, damage, resist = Equipment.generate_dmg_and_resist_values(player.level, time.time(), equipment_type.is_weapon)
    Damage.generate_from_seed(time.time(), player.level)
    return Equipment(
        0,
        player.level,
        equipment_type,
        "longsword",
        time.time(),
        damage,
        resist,
        modifiers,
        0
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

    def test_quest_duration(self):
        player = Player.create_default(0, "test", "")
        zone = Zone(0, "test", 1, "test", Damage.get_empty(), Damage.get_empty(), {})
        quest = Quest(0, zone, 3, "test", "", "", "")
        player.vocation = Vocation.get(0)
        duration_long = quest.get_duration(player)
        print(duration_long)
        player.vocation = Vocation.get(11)
        duration_short = quest.get_duration(player)
        print(duration_short)
        self.assertTrue(duration_long > duration_short)

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
        for qte in QuickTimeEvent.ALL_ITEMS:
            print(qte)

    def test_qte_resolve(self):
        for qte in QuickTimeEvent.ALL_ITEMS:
            print(qte.resolve(randint(0, len(qte.options)-1)))

    def test_print_modifiers(self):
        print_all_modifiers()

    def test_generate_equipment(self):
        for i in range(10):
            print("\n-----------------------\n")
            equipment = Equipment.generate(5 + (10 * i), EquipmentType.get_random(), randint(0, 3))
            print(str(equipment))

    def test_combat(self):
        # setup player
        player = Player.create_default(0, "Ombro", "")
        player.level = 14
        player.gear_level = 13
        player.stance = "b"
        # setup zone
        zone = Zone(
            1,
            "zone name",
            15,
            "AAAA",
            Damage(5, 5, 1, 0, 5, 0, 0, 0),
            Damage(3, 3, 3, 3, 3, 1, 0, 0),
            {}
        )
        # setup equipment
        weapon = _generate_equipment(
            player,
            EquipmentType.get(60),  # Ribaldequin
            [
                get_modifier_from_name("Vampiric", 2),
                get_modifier_from_name("Sneak attack", 5),
                get_modifier_from_name("True Strike", 10)
            ]
        )
        weapon.damage = Damage.load_from_json({"slash": 50})
        player.equip_item(weapon)
        player.equip_item(_generate_equipment(
            player,
            EquipmentType.get(21),  # Lorica segmentata
            []
        ))
        player.equip_item(_generate_equipment(
            player,
            EquipmentType.get(66),  # Buckler
            [
                get_modifier_from_name("Slash Optimized", 25),
                get_modifier_from_name("Slash Affinity", 50),
                get_modifier_from_name("Sword Proficiency", 50)
            ]
        )),
        player.equip_item(_generate_equipment(
            player,
            EquipmentType.get(44),  # Hood
            [
                get_modifier_from_name("Slash Optimized", 25),
                get_modifier_from_name("Unyielding Will", 2)
            ]
        ))
        # setup player satchel
        player.satchel = [ConsumableItem.get(15), ConsumableItem.get(7), ConsumableItem.get(6), ConsumableItem.get(5), ConsumableItem.get(13)]
        # setup enemy
        enemy = Enemy(
            EnemyMeta(0, zone, "Cock monger", "AAAAA", "WIN", "LOSS"),
            [
                get_modifier_from_name("Fire Absorption", 4),
                get_modifier_from_name("Acid Absorption", 4),
                get_modifier_from_name("Electric Absorption", 4),
                get_modifier_from_name("Freeze Absorption", 4),
                get_modifier_from_name("Brutality", 6),
                get_modifier_from_name("Adrenaline", 2)
            ],
            10
        )
        # use to test PvP
        enemy_player = deepcopy(player)
        enemy_player.name = "Liquid Ombro"
        enemy_player.team = 1
        # used to test multiple actor combat
        player2 = Player.create_default(1, "Ciro Esposito", "")
        player2.level = 10
        player2.gear_level = 60
        player2.equip_item(
            _generate_equipment(
                player2,
                EquipmentType.get(0),  # Longsword
                []
            )
        )
        # create & do fight
        combat = CombatContainer([player, enemy], {player: None, enemy: None})
        result = combat.fight()
        print(result)

    def test_stats(self):
        player = Player.create_default(0, "Ombro", "")
        self.assertEqual(player.get_stats().vitality, 1)
        modifier = get_modifier_from_name("Vitality imbued", 10)
        item = _generate_equipment(player, EquipmentType.get(0), [modifier])
        player.equip_item(item)
        self.assertEqual(player.get_stats().vitality, 11)
