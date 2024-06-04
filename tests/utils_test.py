import unittest

from pilgram.utils import PathDict


class TestUtils(unittest.TestCase):

    def test_pathdict(self):
        pd = PathDict({'a': 1, 'b': 2, 'c': 3, "d": {"e": 4}})
        self.assertEqual(pd.path_get("a"), 1)
        self.assertEqual(pd.path_get("b"), 2)
        self.assertEqual(pd.path_get("c"), 3)
        self.assertEqual(pd.path_get("d.e"), 4)
        pd = PathDict()
        pd.path_set("a.b.c", 1)
        self.assertEqual(pd.path_get("a.b.c"), 1)
