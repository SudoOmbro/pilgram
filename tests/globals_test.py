import unittest

from pilgram.globals import ContentMeta


class TestGlobals(unittest.TestCase):

    def test_content_meta(self):
        self.assertEqual(ContentMeta.get("guilds.max_level"), 10)
        self.assertEqual(ContentMeta.get("test"), "test")
