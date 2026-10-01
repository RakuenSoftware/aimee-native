import unittest
from aimee_vllm.cache_identity import cache_salt


class CacheIdentityTests(unittest.TestCase):
    def test_same_revision_reuses_and_every_authority_boundary_separates(self):
        a=cache_salt('recipient-a','revision-1','bank-a')
        self.assertEqual(a,cache_salt('recipient-a','revision-1','bank-a'))
        self.assertEqual(len(a),64)
        for other in [('recipient-b','revision-1','bank-a'),
                      ('recipient-a','revision-2','bank-a'),
                      ('recipient-a','revision-1','bank-b'),
                      ('recipient-a','revision-1',None)]:
            self.assertNotEqual(a,cache_salt(*other))

    def test_canonical_tuple_encoding_avoids_separator_collision(self):
        self.assertNotEqual(cache_salt('ab','c','d'),cache_salt('a','bc','d'))


if __name__ == '__main__':
    unittest.main()
