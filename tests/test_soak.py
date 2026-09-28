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

    def test_stable_coexistence_target(self):
        # met since foraging/grazing (predators viable) and the arms race
        # (armour/camouflage keep parasites and predators in check)
        ok, reasons = meets_target(self.runs)
        self.assertTrue(ok, "; ".join(reasons))



@unittest.skipUnless(os.environ.get("AIL_SLOW") == "1", "set AIL_SLOW=1 to run soak tests")
class TestBrainSelection(unittest.TestCase):
    """With evolved controllers, absorbers should keep steering away from
    predators (selection maintains fleeing). Predators' pull toward prey is
    NOT reliably maintained: most predators are recent converts carrying an
    absorber-like controller (see DESIGN.md, Evolved controller)."""

    def test_absorbers_keep_fleeing(self):
        from simcore import World, brain_weight, default_brain, preset_rules
        keeps = 0
        for seed in (1, 42, 99):
            w = World(900, 600, seed=seed, rules=preset_rules("dynamic", "open", "brain"))
            for _ in range(3000):
                w.step()
            prey = [o.genes.brain or default_brain("absorber")
                    for o in w.organisms if o.strategy == "absorber"]
            if prey and statistics.mean(brain_weight(b, "threat", 0.5) for b in prey) < 0:
                keeps += 1
        self.assertGreaterEqual(keeps, 2)

if __name__ == "__main__":
    unittest.main()
