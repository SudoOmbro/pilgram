import unittest
from datetime import timedelta

from orm.db import decode_progress, encode_progress, PilgramORMDatabase, decode_satchel, encode_satchel
from pilgram.equipment import ConsumableItem


class TestORMDB(unittest.TestCase):

    def test_decode_progress(self):
        self.assertEqual(decode_progress(None), {})
        progress_dict = decode_progress(b"\x01\x00\x02\x00".decode())
        items = list(progress_dict.items())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], 1)
        self.assertEqual(items[0][1], 2)
        progress_dict = decode_progress(b"\x01\x00\x02\x00\x03\x00\x04\x00".decode())
        items = list(progress_dict.items())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0][0], 1)
        self.assertEqual(items[0][1], 2)
        self.assertEqual(items[1][0], 3)
        self.assertEqual(items[1][1], 4)
        progress_dict = decode_progress(b"\x00\x00\x03\x00\x01\x00\x01\x00\x02\x00\x01\x00".decode())
        items = list(progress_dict.items())
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0][0], 0)
        self.assertEqual(items[0][1], 3)
        self.assertEqual(items[1][0], 1)
        self.assertEqual(items[1][1], 1)
        self.assertEqual(items[2][0], 2)
        self.assertEqual(items[2][1], 1)

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

    def test_get_updates(self):
        db = PilgramORMDatabase.instance()
        db.get_all_pending_updates(timedelta(minutes=1))
