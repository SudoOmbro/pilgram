import unittest

from pilgram.globals import ContentMeta


class TestGlobals(unittest.TestCase):

    def test_content_meta(self):
        self.assertEqual(ContentMeta.get("test"), "test")
        self.assertEqual(ContentMeta.get("aaa.bbb"), 42)