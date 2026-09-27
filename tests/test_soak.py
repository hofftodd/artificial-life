"""Slow ecosystem soak tests. Skipped unless AIL_SLOW=1 (about 1-2 minutes).

    AIL_SLOW=1 python3 -m unittest tests.test_soak
"""
import os
import statistics
import unittest

from simcore import Rules

from tools.soak import meets_target, run_many

# the 6 seeds tools/soak.py uses by default happen to pass the coexistence
# target; this broader set shows predators are still fragile
SEEDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 42, 99]
TICKS = 3000


@unittest.skipUnless(os.environ.get("AIL_SLOW") == "1", "set AIL_SLOW=1 to run soak tests")
class TestSoak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = run_many(SEEDS, TICKS, None, Rules())

    def test_no_population_collapse(self):
        for r in self.runs:
            self.assertGreaterEqual(r["final"]["total"], 40, "seed %s" % r["seed"])

    def test_absorbers_dominate(self):
        self.assertGreaterEqual(statistics.mean(r["frac_absorber"] for r in self.runs), 0.6)

    def test_no_incidental_kin_cannibalism(self):
        for r in self.runs:
            kin_kills = sum(v for k, v in r["stats"].items()
                            if k[0] == "eat" and k[1] != "predator" and k[3])
            self.assertEqual(kin_kills, 0, "seed %s" % r["seed"])

    def test_parasites_persist(self):
        alive = sum(1 for r in self.runs if r["final"]["parasite"] > 0)
        self.assertGreaterEqual(alive, len(self.runs) - 3)

    @unittest.expectedFailure
    def test_stable_coexistence_target(self):
        # With foraging and grazing, all strategies survive on all 12 seeds
        # (predators ~10%); the only miss is one seed ending a few organisms
        # over the 350 population ceiling (see TODO.md). Remove the decorator
        # once tools/soak.py reports "target: MET" on these seeds.
        ok, reasons = meets_target(self.runs)
        self.assertTrue(ok, "; ".join(reasons))


if __name__ == "__main__":
    unittest.main()
