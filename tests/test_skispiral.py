import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import skidiag as d  # noqa: E402
import skispiral as s  # noqa: E402


class Geometry(unittest.TestCase):
    def test_one_application(self):
        segs, leaves = s.layout(d.parse("S K"))
        self.assertEqual(len(segs), 2)
        self.assertEqual(sorted(l[2] for l in leaves), ["K", "S"])
        # function edge green (False), argument edge blue (True)
        self.assertEqual([seg[4] for seg in segs], [False, True])

    def test_prune_drops_deep_arguments(self):
        t = d.parse("K" + " (K" * 30 + " I" + ")" * 30)
        _, leaves = s.layout(t, 0.02)
        self.assertLess(len(leaves), d.size(t))

    def test_disc_draws_every_leaf(self):
        t = d.parse("S (K S) K (S I I) x")
        _, _, n = s.radial_frag(t)
        self.assertEqual(n, d.size(t))


class Cli(unittest.TestCase):
    def test_example(self):
        here = os.path.dirname(__file__)
        with tempfile.TemporaryDirectory() as tmp:
            stem = os.path.join(tmp, "fix")
            r = subprocess.run([sys.executable, os.path.join(here, "..", "skispiral.py"),
                                os.path.join(here, "..", "examples", "fixpoint.ski"),
                                "-o", stem, "--min-size", "4"],
                               check=True, capture_output=True, text=True)
            self.assertIn("disc: 37 leaves", r.stdout)
            for suf in ("-spiral.svg", "-disc.svg", "-pair.svg", "-parts.svg", "-parts-disc.svg"):
                self.assertTrue(os.path.getsize(stem + suf) > 0, suf)


if __name__ == "__main__":
    unittest.main()
