import math
import unittest

from simcore import OPTIMAL_DISTANCE, PROTECTION_MAX, Gene, Organism, Rules, World
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


class TestEatingRules(unittest.TestCase):
    def setUp(self):
        self.w = empty_world()
        self.founder = make_organism(500, 350, self.w.rng, make_gene(movement_ability=0.2))

    def _relative(self, x, y, genes=None):
        """A child of the (distant) founder: kin of every other relative, but
        nobody's protected offspring except the founder's."""
        return Organism(x, y, self.w.rng, genes or make_gene(movement_ability=0.2),
                        parent=self.founder)

    def _eat_once(self, eater, *others):
        self.w.organisms = [eater, *others]
        self.w.grid.build(self.w.organisms)
        before = eater.energy
        eater._eat(self.w)
        return eater.energy - before

    def test_absorber_spares_weak_kin_but_eats_weak_stranger(self):
        eater = self._relative(100, 100, make_gene(absorption=0.7, predation=0.3,
                                                   movement_ability=0.2))
        self.assertEqual(eater.strategy, "absorber")
        kin = self._relative(105, 100)
        kin.energy = 1.0
        self._eat_once(eater, kin)
        self.assertFalse(kin.dead)
        stranger = make_organism(105, 100, self.w.rng, make_gene(movement_ability=0.2))
        stranger.energy = 1.0
        self._eat_once(eater, stranger)
        self.assertTrue(stranger.dead)

    def test_predator_eats_weak_kin_that_is_not_its_young(self):
        pred = self._relative(100, 100, make_gene(absorption=0.0, predation=1.0,
                                                  movement_ability=0.2))
        sibling = self._relative(105, 100)
        sibling.energy = 2.0
        self._eat_once(pred, sibling)
        self.assertTrue(sibling.dead)

    def test_meal_is_a_fraction_of_prey_energy_capped(self):
        pred = make_organism(100, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0))
        prey = make_organism(105, 100, self.w.rng, make_gene())
        prey.energy = 2.0
        self.assertAlmostEqual(self._eat_once(pred, prey), 2.0 * self.w.rules.eat_fraction)
        self.w.rules = Rules(eat_gain_cap=1.0)
        pred.hunt_cd = 0
        prey2 = make_organism(105, 100, self.w.rng, make_gene())
        prey2.energy = 4.0
        self.assertAlmostEqual(self._eat_once(pred, prey2), 1.0)

    def test_predator_chases_edible_prey_not_the_nearest(self):
        pred = make_organism(100, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0,
                                                             organism_sensing=2.0))
        strong = make_organism(110, 100, self.w.rng, make_gene())
        strong.energy = 11.0
        weak = make_organism(140, 100, self.w.rng, make_gene())
        weak.energy = 1.0
        self.w.organisms = [pred, strong, weak]
        self.w.grid.build(self.w.organisms)
        self.assertIs(pred._nearest(self.w.grid, 80, pred._victim_filter(self.w)), weak)

    def test_predators_are_not_prey_by_default(self):
        pred = make_organism(100, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0))
        other = make_organism(105, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0))
        other.energy = 1.0
        self._eat_once(pred, other)
        self.assertFalse(other.dead)
        self.w.rules = Rules(predators_are_prey=True)
        self._eat_once(pred, other)
        self.assertTrue(other.dead)

    def test_group_defense_protects_prey_among_relatives(self):
        pred = make_organism(100, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0))
        prey = self._relative(108, 100)
        prey.energy = 1.0
        guards = [self._relative(115, 100), self._relative(108, 108)]
        self.w.rules = Rules(group_defense=2)
        self._eat_once(pred, prey, *guards)
        self.assertFalse(prey.dead)
        self.w.rules = Rules(group_defense=3)
        self._eat_once(pred, prey, *guards)
        self.assertTrue(prey.dead)

    def test_rules_are_per_world_and_validated(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0,
                  rules=Rules(eat_fraction=0.5))
        self.assertEqual(w.rules.eat_fraction, 0.5)
        self.assertEqual(empty_world().rules, Rules())
        with self.assertRaises(ValueError):
            Rules(kin_immunity="sometimes")

    def test_kills_are_tallied_in_stats(self):
        pred = make_organism(100, 100, self.w.rng, make_gene(absorption=0.0, predation=1.0,
                                                             movement_ability=0.2))
        prey = make_organism(105, 100, self.w.rng, make_gene(movement_ability=0.2))
        prey.energy = 1.0
        self.w.organisms = [pred, prey]
        self.w.step()
        self.assertEqual(self.w.stats[("eat", "predator", "absorber", False)], 1)
        self.assertEqual(self.w.stats[("death", "eaten", "absorber")], 1)


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
