import unittest
from datetime import timedelta

from orm.db import decode_progress, encode_progress, PilgramORMDatabase


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

    def test_get_updates(self):
        db = PilgramORMDatabase.instance()
        db.get_all_pending_updates(timedelta(minutes=1))
