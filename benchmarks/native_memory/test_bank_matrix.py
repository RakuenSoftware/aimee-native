import unittest

from bank_matrix import banks, score


class MatrixTests(unittest.TestCase):
    def test_exact_requested_interventions(self):
        m = banks()
        self.assertEqual({name:len(rows) for name,rows in m.items()}, dict(A=1,B=2,C=4,D=4,E=3,F=4))
        self.assertEqual(m["D"], list(reversed(m["C"])))
        self.assertEqual(m["E"], m["C"][1:])
        self.assertEqual(m["F"][0], ("target","wrong"))
        self.assertEqual(m["F"][1:], m["C"][1:])
        self.assertNotIn("target", [payload for _,payload in m["E"]+m["F"]])
        self.assertEqual([identity for identity,_ in m["F"]], [identity for identity,_ in m["C"]])

    def test_positive_and_negative_controls(self):
        self.assertTrue(score("A", "Teal", "teal", True)["passed"])
        self.assertFalse(score("B", "oolong", "teal", True)["passed"])
        self.assertTrue(score("E", "unknown", "teal", True)["passed"])
        self.assertFalse(score("F", "The color is teal.", "teal", True)["passed"])
        self.assertFalse(score("E", "", "teal", True)["passed"])
        self.assertFalse(score("A", "teal", "teal", False)["passed"])


if __name__=="__main__":
    unittest.main(verbosity=2)
