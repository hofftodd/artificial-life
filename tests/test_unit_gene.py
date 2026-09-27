import unittest

from simcore import ABSORB_MAX, ABSORB_MOVE_TRADEOFF, EAT_MAX, STEAL_MAX, Gene
from tests.helpers import make_gene, make_rng


def assert_budget(tc, g):
    tc.assertAlmostEqual(g.absorption + g.parasitism + g.predation, 1.0, places=12)
    for share in (g.absorption, g.parasitism, g.predation):
        tc.assertGreaterEqual(share, 0.0)
        tc.assertLessEqual(share, 1.0)


class TestGeneRandom(unittest.TestCase):
    def test_random_within_bounds(self):
        rng = make_rng()
        for _ in range(200):
            g = Gene.random(rng)
            self.assertGreaterEqual(g.absorption_spectrum, 1)
            self.assertLessEqual(g.absorption_spectrum, 100)
            assert_budget(self, g)
            self.assertGreaterEqual(g.movement_ability, 0.5)
            self.assertLessEqual(g.movement_ability, 2.0)
            self.assertGreaterEqual(g.radiation_sensing, 0.5)
            self.assertLessEqual(g.radiation_sensing, 2.0)
            self.assertGreaterEqual(g.organism_sensing, 0.5)
            self.assertLessEqual(g.organism_sensing, 2.0)

    def test_random_population_is_mostly_absorbers_with_some_of_each(self):
        rng = make_rng()
        counts = {"absorber": 0, "parasite": 0, "predator": 0}
        for _ in range(500):
            counts[Gene.random(rng).strategy()] += 1
        self.assertGreater(counts["absorber"], 0.6 * 500)
        self.assertGreater(counts["parasite"], 0)
        self.assertGreater(counts["predator"], 0)


class TestStrategyBudget(unittest.TestCase):
    def test_shares_are_normalized(self):
        g = make_gene(absorption=2.0, parasitism=1.0, predation=1.0)
        self.assertAlmostEqual(g.absorption, 0.5)
        self.assertAlmostEqual(g.parasitism, 0.25)
        self.assertAlmostEqual(g.predation, 0.25)

    def test_all_zero_falls_back_to_absorber(self):
        g = make_gene(absorption=0.0, parasitism=0.0, predation=0.0)
        self.assertEqual((g.absorption, g.parasitism, g.predation), (1.0, 0.0, 0.0))

    def test_abilities_scale_with_share(self):
        g = make_gene(absorption=0.5, parasitism=0.3, predation=0.2)
        self.assertAlmostEqual(g.absorption_efficiency, ABSORB_MAX * 0.5)
        self.assertAlmostEqual(g.stealing_ability, STEAL_MAX * 0.3)
        self.assertAlmostEqual(g.eating_ability, EAT_MAX * 0.2)

    def test_cannot_be_strong_at_everything(self):
        g = make_gene(absorption=1.0, parasitism=1.0, predation=1.0)
        self.assertAlmostEqual(g.absorption_efficiency, ABSORB_MAX / 3)
        self.assertAlmostEqual(g.stealing_ability, STEAL_MAX / 3)
        self.assertAlmostEqual(g.eating_ability, EAT_MAX / 3)

    def test_gaining_one_share_costs_the_others(self):
        before = make_gene(absorption=0.4, parasitism=0.3, predation=0.3)
        after = make_gene(absorption=0.4, parasitism=0.3, predation=0.6)
        self.assertGreater(after.eating_ability, before.eating_ability)
        self.assertLess(after.absorption_efficiency, before.absorption_efficiency)
        self.assertLess(after.stealing_ability, before.stealing_ability)


class TestMovementTradeoff(unittest.TestCase):
    def test_speed_falls_as_absorption_rises(self):
        speeds = [make_gene(absorption=a, predation=1.0 - a, movement_ability=1.0).speed
                  for a in (0.0, 0.25, 0.5, 0.75, 1.0)]
        for a, b in zip(speeds, speeds[1:]):
            self.assertGreater(a, b)

    def test_speed_endpoints(self):
        self.assertAlmostEqual(
            make_gene(absorption=0.0, predation=1.0, movement_ability=2.0).speed, 2.0)
        self.assertAlmostEqual(
            make_gene(absorption=1.0, movement_ability=2.0).speed,
            2.0 * (1.0 - ABSORB_MOVE_TRADEOFF))


class TestGeneMutation(unittest.TestCase):
    def test_mutation_stays_in_bounds_from_extremes(self):
        extremes = [
            make_gene(absorption_spectrum=1, absorption=1.0, movement_ability=0.2,
                      radiation_sensing=0.3, organism_sensing=0.3),
            make_gene(absorption_spectrum=100, absorption=0.0, predation=1.0,
                      movement_ability=2.5, radiation_sensing=3.0, organism_sensing=3.0),
            make_gene(absorption=0.0, parasitism=1.0),
        ]
        for g0 in extremes:
            rng = make_rng(7)
            g = g0
            for _ in range(100):
                g = g.mutated(rng)
                self.assertGreaterEqual(g.absorption_spectrum, 1)
                self.assertLessEqual(g.absorption_spectrum, 100)
                assert_budget(self, g)
                self.assertGreaterEqual(g.movement_ability, 0.2)
                self.assertLessEqual(g.movement_ability, 2.5)
                self.assertGreaterEqual(g.radiation_sensing, 0.3)
                self.assertLessEqual(g.radiation_sensing, 3.0)
                self.assertGreaterEqual(g.organism_sensing, 0.3)
                self.assertLessEqual(g.organism_sensing, 3.0)

    def test_strategy_can_drift_over_generations(self):
        rng = make_rng(3)
        g = make_gene(absorption=1.0)
        seen = set()
        for _ in range(2000):
            g = g.mutated(rng)
            seen.add(g.strategy())
        self.assertEqual(seen, {"absorber", "parasite", "predator"})

    def test_mutation_changes_genome(self):
        rng = make_rng(99)
        g = make_gene()
        mutated = g.mutated(rng)
        self.assertNotEqual(g.as_tuple(), mutated.as_tuple())

    def test_mutation_is_deterministic_for_seed(self):
        g = make_gene()
        a = g.mutated(make_rng(5)).as_tuple()
        b = g.mutated(make_rng(5)).as_tuple()
        self.assertEqual(a, b)


class TestStrategyClassification(unittest.TestCase):
    def test_absorber(self):
        self.assertEqual(make_gene().strategy(), "absorber")

    def test_parasite(self):
        g = make_gene(absorption=0.2, parasitism=0.8)
        self.assertEqual(g.strategy(), "parasite")

    def test_predator(self):
        g = make_gene(absorption=0.2, predation=0.8)
        self.assertEqual(g.strategy(), "predator")

    def test_dominant_share_wins(self):
        g = make_gene(absorption=0.2, parasitism=0.45, predation=0.35)
        self.assertEqual(g.strategy(), "parasite")

    def test_generalist_is_absorber(self):
        g = make_gene(absorption=1.0, parasitism=1.0, predation=1.0)
        self.assertEqual(g.strategy(), "absorber")


if __name__ == "__main__":
    unittest.main()
