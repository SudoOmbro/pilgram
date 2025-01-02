import random
import unittest
from datetime import timedelta
from random import randint

from orm.db import (
    ENCODING,
    PilgramORMDatabase,
    decode_equipped_items_ids,
    decode_modifiers,
    decode_progress,
    decode_satchel,
    encode_equipped_items,
    encode_modifiers,
    encode_progress,
    encode_satchel, decode_vocation_ids, encode_vocation_ids, decode_vocation_progress, encode_vocation_progress,
)
from pilgram.classes import Player, Guild
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.modifiers import get_modifier


class TestORMDB(unittest.TestCase):

    def test_decode_progress(self):
        self.assertEqual(decode_progress(None), {})
        progress_dict = decode_progress(b"\x01\x00\x02\x00".decode(ENCODING))
        items = list(progress_dict.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], 1)
        self.assertEqual(items[0][1], 2)
        progress_dict = decode_progress(b"\x01\x00\x02\x00\x03\x00\x04\x00".decode(ENCODING))
        items = list(progress_dict.items())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0][0], 1)
        self.assertEqual(items[0][1], 2)
        self.assertEqual(items[1][0], 3)
        self.assertEqual(items[1][1], 4)
        progress_dict = decode_progress(b"\x00\x00\x03\x00\x01\x00\x01\x00\x02\x00\x01\x00".decode(ENCODING))
        items = list(progress_dict.items())
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0][0], 0)
        self.assertEqual(items[0][1], 3)
        self.assertEqual(items[1][0], 1)
        self.assertEqual(items[1][1], 1)
        self.assertEqual(items[2][0], 2)
        self.assertEqual(items[2][1], 1)
        progress_dict = decode_progress(b"\x01\x00\x80\x00".decode(ENCODING))
        items = list(progress_dict.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], 1)
        self.assertEqual(items[0][1], 128)

    def test_encode_progress(self):
        progress_dict = {1: 2, 3: 4}
        encoded_string = encode_progress(progress_dict)
        self.assertEqual(encoded_string, b"\x01\x00\x02\x00\x03\x00\x04\x00")

    def test_decode_satchel(self):
        satchel = decode_satchel(b"\x00".decode())
        self.assertEqual(satchel[0].consumable_id, 0)
        satchel = decode_satchel(b"\x00\x01".decode())
        self.assertEqual(satchel[0].consumable_id, 0)
        self.assertEqual(satchel[1].consumable_id, 1)
        satchel = decode_satchel(b"\x00\x01\x01".decode())
        self.assertEqual(satchel[0].consumable_id, 0)
        self.assertEqual(satchel[1].consumable_id, 1)
        self.assertEqual(satchel[2].consumable_id, 1)

    def test_encode_satchel(self):
        satchel = [ConsumableItem.get(0), ConsumableItem.get(1), ConsumableItem.get(0)]
        encoded_string = encode_satchel(satchel)
        self.assertEqual(encoded_string, b"\x00\x01\x00")

    def test_decode_modifiers(self):
        self.assertEqual([], decode_modifiers(b"".decode()))
        modifiers = decode_modifiers(b"\x01\x00\x01\x00\x00\x00".decode())
        self.assertEqual(modifiers[0], get_modifier(1, 1))
        modifiers = decode_modifiers(b"\x01\x00\x01\x00\x00\x00\x02\x00\x01\x00\x00\x00".decode())
        self.assertEqual(modifiers[0], get_modifier(1, 1))
        self.assertEqual(modifiers[1], get_modifier(2, 1))

    def test_encode_modifiers(self):
        self.assertEqual(encode_modifiers([]), b"")
        self.assertEqual(encode_modifiers([get_modifier(1, 1)]), b"\x01\x00\x01\x00\x00\x00")

    def test_encode_equipped_items(self):
        items = [Equipment.generate(5, EquipmentType.get(0), 0) for _ in range(6)]
        items_dict: dict[int, Equipment] = {}
        for i, item in enumerate(items):
            item.equipment_id = i + 200
            items_dict[i] = item
        result = encode_equipped_items(items_dict)
        self.assertEqual(len(result), 24)

    def test_decode_equipped_items(self):
        string = b"\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04\x00\x00\x00\x05\x00\x00\x00\x06\x00\x00\x00".decode(ENCODING)
        result = decode_equipped_items_ids(string)
        self.assertEqual(result, [1, 2, 3, 4, 5, 6])

    def test_get_updates(self):
        db = PilgramORMDatabase.instance()
        db.get_all_pending_updates(timedelta(minutes=1))

    def _get_or_create_player(self, player_id: int, name: str):
        db = PilgramORMDatabase.instance()
        player = db.get_player_from_name(name)
        if not player:
            player = Player.create_default(player_id, name, "AAAAAAAA")
            db.add_player(player)
        return player

    def test_save_items_to_db(self):
        # delete db in tests folder before running this test!
        db = PilgramORMDatabase.instance()
        player = self._get_or_create_player(69, "Ombro")
        generated_items: list[Equipment] = []
        for i in range(100):
            item = Equipment.generate(i, EquipmentType.get_random(), randint(0, 3))
            db.add_item(item, player)
            generated_items.append(item)
        items: list[Equipment] = db.get_player_items(player.player_id)
        for item, gen_item in zip(items, generated_items, strict=False):
            for item_modifier, gen_item_modifier in zip(item.modifiers, gen_item.modifiers, strict=False):
                self.assertEqual(item_modifier.TYPE, gen_item_modifier.TYPE)
                self.assertEqual(item_modifier.strength, gen_item_modifier.strength)

    def test_equip(self):
        # disable get_player_data cache before running this test!
        db = PilgramORMDatabase.instance()
        player = self._get_or_create_player(69, "Ombro")
        for i in range(500):
            item = Equipment.generate(i, EquipmentType.get_random(), randint(0, 3))
            db.add_item(item, player)
        for _ in range(1000):
            player.equipped_items = {}
            old_id = id(player)
            ids = [x + 1 for x in range(500)]
            random.shuffle(ids)
            items: list[Equipment] = db.get_player_items(player.player_id)
            chosen_items = []
            for i in range(random.randint(1, 6)):
                item = items[ids[i] - 1]
                player.equip_item(item)
                chosen_items.append(item.equipment_id)
            db.update_player_data(player)
            player = db.get_player_from_name("Ombro")
            self.assertNotEqual(old_id, id(player), msg="Player object is the same. Did you disable get_player_data's cache?")
            equipment_ids = [x.equipment_id for x in player.equipped_items.values()]
            for item_id in equipment_ids:
                self.assertTrue(item_id in chosen_items, msg=f"{item_id} not in {chosen_items}. equipment: {equipment_ids}")

    def test_get_guild_ids_from_name_case_insensitive(self):
        # delete pilgram db in test before running this test
        db = PilgramORMDatabase.instance()
        player = self._get_or_create_player(69, "Ombro")
        db.add_guild(Guild.create_default(player, "TurOn", "AAAA"))
        db.add_guild(Guild.create_default(player, "TURON", "AAAA"))
        db.add_guild(Guild.create_default(player, "cock", "AAAA"))
        result = db.get_guild_ids_from_name_case_insensitive("TurOn")
        self.assertTrue(len(result) == 2)
        self.assertTrue(1 in result)
        self.assertTrue(2 in result)

    def test_decode_vocation_ids(self):
        result = decode_vocation_ids(4294967295)  # 32 bit unsigned integer limit
        for item in result:
            self.assertEqual(item, 255)

    def test_encode_vocation_ids(self):
        result = encode_vocation_ids([0, 0, 0, 1])
        self.assertEqual(result, 1)
        result = encode_vocation_ids([255, 0, 0, 1])
        self.assertEqual(result, 4278190081)

    def test_decode_vocation_progress(self):
        result = decode_vocation_progress(b"\x01\x01\x02\x04\x04\x0F".decode(ENCODING))
        self.assertEqual(result[1], 1)
        self.assertEqual(result[2], 4)
        self.assertEqual(result[4], 15)

    def test_encode_vocation_progress(self):
        result = encode_vocation_progress({2: 4, 6: 8})
        self.assertEqual(result.encode(ENCODING), b'\x02\x04\x06\x08')

    def test_get_pending_updates(self):
        db = PilgramORMDatabase.instance()
        print(db.get_all_pending_updates(timedelta(hours=1)))
