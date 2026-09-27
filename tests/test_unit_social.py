import math
import unittest

from simcore import OPTIMAL_DISTANCE, PROTECTION_MAX, Gene, Organism, World
from tests.helpers import (build_field, make_gene, make_organism, make_rng,
                           single_emitter_world)


def empty_world():
    return World(600, 400, seed=1, num_emitters=0, start_population=0)


class TestEnergyCompetition(unittest.TestCase):
    def test_cellmates_split_the_harvest(self):
        w = single_emitter_world(ex=300, ey=200)
        x, y = 300 + OPTIMAL_DISTANCE, 200
        alone = make_organism(x, y, w.rng, make_gene())
        w.organisms = [alone]
        build_field(w)
        self.assertAlmostEqual(w.field.share_at(x, y), 1.0)
        mate = make_organism(x + 1, y, w.rng, make_gene())
        w.organisms = [alone, mate]
        build_field(w)
        self.assertAlmostEqual(w.field.share_at(x, y), 0.5)

    def test_demand_weighted_by_absorption_share(self):
        w = single_emitter_world(ex=300, ey=200)
        x, y = 300 + OPTIMAL_DISTANCE, 200
        w.organisms = [make_organism(x, y, w.rng, make_gene()),
                       make_organism(x + 1, y, w.rng,
                                     make_gene(absorption=0.5, predation=0.5))]
        build_field(w)
        self.assertAlmostEqual(w.field.share_at(x, y), 1.0 / 1.5)


class TestParasitism(unittest.TestCase):
    def test_parasites_cannot_parasitize_parasites(self):
        w = empty_world()
        a = make_organism(100, 100, w.rng,
                          make_gene(absorption=0.0, parasitism=1.0, movement_ability=0.2))
        b = make_organism(106, 100, w.rng,
                          make_gene(absorption=0.0, parasitism=1.0, movement_ability=0.2))
        a.energy = b.energy = 5.0
        w.organisms.extend([a, b])
        w.step()
        self.assertFalse([e for e in w.events if e[0] == "steal"])

    def test_steal_is_reported(self):
        w = empty_world()
        p = make_organism(100, 100, w.rng,
                          make_gene(absorption=0.0, parasitism=1.0, movement_ability=0.2))
        v = make_organism(106, 100, w.rng, make_gene(movement_ability=0.2))
        v.energy = 5.0
        w.organisms.extend([p, v])
        w.step()
        self.assertEqual([e[0] for e in w.events], ["steal"])


class TestOffspringProtection(unittest.TestCase):
    def setUp(self):
        self.w = empty_world()
        self.parent = make_organism(100, 100, self.w.rng, make_gene(
            absorption=0.0, predation=1.0, movement_ability=0.2,
            offspring_protection=50))
        self.child = Organism(105, 100, self.w.rng,
                              make_gene(movement_ability=0.2), parent=self.parent)
        self.child.energy = 3.0
        self.w.organisms.extend([self.parent, self.child])

    def test_child_inherits_family(self):
        self.assertEqual(self.child.parent_uid, self.parent.uid)
        self.assertEqual(self.child.family, self.parent.family)

    def test_young_offspring_are_spared(self):
        self.w.step()
        self.assertFalse(self.child.dead)

    def test_offspring_eaten_once_of_age(self):
        self.child.age = 50
        self.w.step()
        self.assertTrue(self.child.dead)
        kinds = [e[0] for e in self.w.events]
        self.assertIn("eat", kinds)
        self.assertIn(("death", "eaten"), [(e[0], e[3]) for e in self.w.events
                                           if e[0] == "death"])

    def test_unrelated_young_are_not_spared(self):
        stranger = make_organism(105, 100, self.w.rng, make_gene(movement_ability=0.2))
        stranger.energy = 3.0
        self.w.organisms = [self.parent, stranger]
        self.w.step()
        self.assertTrue(stranger.dead)


class TestCommunalism(unittest.TestCase):
    def _spread_after(self, affinity):
        # two relatives with no emitter to aim for: only kin attraction moves
        # them deliberately
        w = empty_world()
        a = make_organism(200, 200, w.rng, make_gene(kin_affinity=affinity,
                                                    organism_sensing=2.0))
        b = Organism(260, 200, w.rng, make_gene(kin_affinity=affinity,
                                                organism_sensing=2.0), parent=a)
        a.energy = b.energy = 10.0
        w.repro_chance = 0.0
        w.organisms.extend([a, b])
        for _ in range(200):
            w.step()
        return math.hypot(a.x - b.x, a.y - b.y)

    def test_kin_affinity_pulls_relatives_together(self):
        self.assertLess(self._spread_after(1.0), 20)
        self.assertGreater(self._spread_after(0.0), 20)

    def test_strangers_are_not_attracted(self):
        w = empty_world()
        a = make_organism(200, 200, w.rng, make_gene(kin_affinity=1.0))
        b = make_organism(260, 200, w.rng, make_gene(kin_affinity=1.0))
        self.assertFalse(a.is_kin(b))


class TestSocialGenesMutate(unittest.TestCase):
    def test_social_genes_mutate_within_bounds(self):
        rng = make_rng(11)
        g = make_gene(kin_affinity=0.5, offspring_protection=PROTECTION_MAX // 2)
        seen_affinity, seen_protection = set(), set()
        for _ in range(300):
            g = g.mutated(rng)
            self.assertGreaterEqual(g.kin_affinity, 0.0)
            self.assertLessEqual(g.kin_affinity, 1.0)
            self.assertGreaterEqual(g.offspring_protection, 0)
            self.assertLessEqual(g.offspring_protection, PROTECTION_MAX)
            seen_affinity.add(round(g.kin_affinity, 2))
            seen_protection.add(g.offspring_protection)
        self.assertGreater(len(seen_affinity), 10)
        self.assertGreater(len(seen_protection), 10)


class TestFounderMix(unittest.TestCase):
    def test_strategy_mix_controls_founders(self):
        w = World(600, 400, seed=3, num_emitters=1, start_population=300,
                  strategy_mix={"absorber": 1, "parasite": 0, "predator": 1})
        counts = {"absorber": 0, "parasite": 0, "predator": 0}
        for o in w.organisms:
            counts[o.strategy] += 1
        self.assertEqual(counts["parasite"], 0)
        self.assertGreater(counts["absorber"], 100)
        self.assertGreater(counts["predator"], 100)

    def test_specialist_genome(self):
        rng = make_rng(4)
        for strategy in ("absorber", "parasite", "predator"):
            for _ in range(50):
                self.assertEqual(Gene.random_specialist(rng, strategy).strategy(), strategy)


class TestDeathEvents(unittest.TestCase):
    def test_starvation_reported(self):
        w = empty_world()
        o = make_organism(100, 100, w.rng, make_gene())
        o.energy = 0.001
        w.organisms.append(o)
        w.step()
        self.assertEqual([(e[0], e[3]) for e in w.events], [("death", "starved")])


if __name__ == "__main__":
    unittest.main()
