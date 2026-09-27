import math
import unittest

from simcore import EMITTER_RANGE, FIELD_CELL, OPTIMAL_DISTANCE, Organism, Rules, World
from tests.helpers import build_field, make_gene, make_organism, single_emitter_world


def emitter_world(**rules):
    w = single_emitter_world(ex=300, ey=200)
    w.rules = Rules(**rules)
    w.repro_chance = 0.0
    return w


def cell(x, y):
    return (int(x // FIELD_CELL), int(y // FIELD_CELL))


class TestGrazing(unittest.TestCase):
    def test_harvest_lowers_reserve_and_it_regrows(self):
        w = emitter_world(depletion_rate=0.5, regrowth_rate=0.05, movement="ring")
        o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng, make_gene(movement_ability=0.2))
        o.energy = 5.0
        w.organisms.append(o)
        for _ in range(50):
            w.step()
        key = cell(o.x, o.y)
        self.assertLess(w.reserve.get(key, 1.0), 0.95)
        w.organisms = []
        for _ in range(300):
            w.step()
        self.assertEqual(w.reserve, {})   # fully regrown cells are dropped

    def test_grazed_cell_yields_less(self):
        def gain(reserve):
            w = emitter_world(depletion_rate=0.5)
            o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng, make_gene(movement_ability=0.2))
            w.organisms.append(o)
            build_field(w)
            if reserve is not None:
                w.reserve[cell(o.x, o.y)] = reserve
            before = o.energy
            o.update(w)
            return o.energy - before
        self.assertLess(gain(0.2), gain(None) * 0.5)

    def test_no_grazing_when_off(self):
        w = emitter_world(depletion_rate=0.0)
        o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng, make_gene())
        w.organisms.append(o)
        for _ in range(30):
            w.step()
        self.assertEqual((w.reserve, w.harvest), ({}, {}))


class TestForaging(unittest.TestCase):
    def test_leaves_a_grazed_cell_for_fresh_light(self):
        w = emitter_world(movement="forage", depletion_rate=0.5)
        o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng, make_gene(radiation_sensing=1.0))
        w.organisms.append(o)
        build_field(w)
        here = cell(o.x, o.y)
        w.reserve[here] = 0.05
        target = o._forage_target(w)
        self.assertNotEqual(cell(*target), here)

    def test_stays_put_when_nothing_is_better(self):
        w = emitter_world(movement="forage")
        o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng, make_gene(radiation_sensing=0.3))
        w.organisms.append(o)
        build_field(w)
        self.assertEqual(o._forage_target(w), (o.x, o.y))

    def test_dark_forager_falls_back_to_seeking_an_emitter(self):
        w = emitter_world(movement="forage")
        o = make_organism(300 + EMITTER_RANGE + 60, 200, w.rng,
                          make_gene(radiation_sensing=1.0, movement_ability=2.0))
        w.organisms.append(o)
        build_field(w)
        self.assertIsNone(o._forage_target(w))
        d0 = math.hypot(o.x - 300, o.y - 200)
        for _ in range(40):
            w.step()
        self.assertLess(math.hypot(o.x - 300, o.y - 200), d0 - 15)  # 0.5px/tick

    def test_lone_forager_settles_near_the_optimal_ring(self):
        w = emitter_world(movement="forage")
        o = make_organism(300 + 110, 200, w.rng, make_gene(movement_ability=2.0))
        o.energy = 10.0
        w.organisms.append(o)
        for _ in range(300):
            w.step()
        self.assertLess(abs(math.hypot(o.x - 300, o.y - 200) - OPTIMAL_DISTANCE), 12)

    def test_ring_mode_heads_for_the_radial_ring_point(self):
        w = emitter_world(movement="ring")
        o = make_organism(300 + 110, 200, w.rng, make_gene(movement_ability=2.0))
        w.organisms.append(o)
        for _ in range(60):
            w.step()
        self.assertAlmostEqual(math.hypot(o.x - 300, o.y - 200), OPTIMAL_DISTANCE, delta=3)


class TestPartialDefense(unittest.TestCase):
    def _success_rate(self, relatives, d, trials=400):
        wins = 0
        for seed in range(trials):
            w = World(600, 400, seed=seed, num_emitters=0, start_population=0,
                      rules=Rules(group_defense=0, defense_per_kin=d))
            founder = make_organism(500, 350, w.rng, make_gene())
            pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0))
            prey = Organism(108, 100, w.rng, make_gene(), parent=founder)
            prey.energy = 1.0
            kin = [Organism(108 + 3 * (i + 1), 104, w.rng, make_gene(), parent=founder)
                   for i in range(relatives)]
            w.organisms = [pred, prey, *kin]
            w.grid.build(w.organisms)
            pred._eat(w)
            wins += prey.dead
        return wins / trials

    def test_success_falls_with_each_relative(self):
        self.assertEqual(self._success_rate(0, 0.3, trials=20), 1.0)
        self.assertAlmostEqual(self._success_rate(2, 0.3), 0.7 ** 2, delta=0.07)
        self.assertAlmostEqual(self._success_rate(4, 0.3), 0.7 ** 4, delta=0.07)

    def test_failed_attack_still_costs_a_cooldown(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0,
                  rules=Rules(group_defense=0, defense_per_kin=0.99))
        founder = make_organism(500, 350, w.rng, make_gene())
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0))
        prey = Organism(108, 100, w.rng, make_gene(), parent=founder)
        prey.energy = 1.0
        guard = Organism(111, 104, w.rng, make_gene(), parent=founder)
        w.organisms = [pred, prey, guard]
        w.grid.build(w.organisms)
        pred._eat(w)
        self.assertFalse(prey.dead)
        self.assertEqual(pred.hunt_cd, w.rules.hunt_cooldown)
        self.assertEqual(w.stats[("repelled", "predator", "absorber")], 1)

    def test_rules_validated(self):
        for bad in (dict(movement="teleport"), dict(defense_per_kin=1.0),
                    dict(depletion_rate=-1), dict(regrowth_rate=0)):
            with self.assertRaises(ValueError):
                Rules(**bad)


if __name__ == "__main__":
    unittest.main()
