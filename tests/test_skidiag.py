import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import skidiag as d  # noqa: E402

Y = "S (K (S I I)) (S (S (K S) K) (K (S I I)))"


def term(src):
    return d.hashcons(d.parse(src), {})


class Parse(unittest.TestCase):
    def test_left_assoc(self):
        self.assertEqual(d.parse("S K I"), (("S", "K"), "I"))

    def test_dot_is_application(self):
        self.assertEqual(d.parse("S ⬝ K ⬝ (K ⬝ I)"), d.parse("S K (K I)"))

    def test_roundtrip(self):
        self.assertEqual(d.show(d.parse(Y)), Y)

    def test_rejects_junk(self):
        for bad in ["S K +", "(S K", "S K)", "", "X"]:
            with self.assertRaises(SyntaxError, msg=bad):
                d.parse(bad)


class Reduce(unittest.TestCase):
    def test_skk_is_identity(self):
        self.assertEqual(d.normalize(d.parse("S K K x"), [100]), "x")

    def test_fuel(self):
        with self.assertRaises(d.OutOfFuel):
            d.normalize(d.parse("S I I (S I I)"), [50])

    def test_behaviours(self):
        cases = {"S (K S) K": "λabc. a (b c)",
                 "S (S (K S) (S (K K) S)) (K K)": "λabc. a c b",
                 "S (K (S I)) K": "λab. b a",
                 "K I": "λab. b",
                 "S I I": "λa. a a"}
        for src, want in cases.items():
            self.assertEqual(d.behaviour(d.parse(src), 6, 1000), want, src)

    def test_no_behaviour_for_y(self):
        self.assertIsNone(d.behaviour(d.parse(Y), 4, 1000))


class Naming(unittest.TestCase):
    def test_shared_subterm_named_once(self):
        b = "S (K S) K"
        t = term(f"({b}) ({b}) x")
        names, order = d.name_shared(t, 4)
        self.assertEqual(len(order), 1)
        self.assertEqual(d.show(order[0]), b)

    def test_inner_parts_not_named(self):
        # every occurrence of S (K S) sits once inside B, so only B is named
        t = term("(S (K S) K) (S (K S) K)")
        _, order = d.name_shared(t, 3)
        self.assertEqual([d.show(u) for u in order], ["S (K S) K"])


class Cli(unittest.TestCase):
    def test_example(self):
        here = os.path.dirname(__file__)
        with tempfile.TemporaryDirectory() as tmp:
            stem = os.path.join(tmp, "fix")
            subprocess.run([sys.executable, os.path.join(here, "..", "skidiag.py"),
                            os.path.join(here, "..", "examples", "fixpoint.ski"),
                            "-o", stem, "--min-size", "4"],
                           check=True, capture_output=True)
            legend = open(stem + ".txt", encoding="utf-8").read()
            self.assertIn("Y = S D (S B D)", legend)
            self.assertIn("D = K (S I I)", legend)
            self.assertIn("B = S (K S) K", legend)
            for ext in (".svg", ".tex"):
                self.assertTrue(os.path.getsize(stem + ext) > 0)


if __name__ == "__main__":
    unittest.main()
