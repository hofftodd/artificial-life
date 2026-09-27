import math
import unittest

from simcore import (ENERGY_CAP, MAX_POPULATION, MOTION_COST, OPTIMAL_DISTANCE,
                     SENSE_COST, SHADE_FACTOR, World, SpatialGrid)
from tests.helpers import (build_field, make_gene, make_organism, make_rng,
                           single_emitter_world)


def snapshot(w):
    return sorted(
        (round(o.x, 6), round(o.y, 6), round(o.energy, 6),
         o.generation, o.strategy)
        for o in w.organisms
    )


class TestStepInvariants(unittest.TestCase):
    def test_positions_energy_bounds(self):
        w = World(900, 600, seed=123)
        for _ in range(100):
            existing = {id(o) for o in w.organisms}
            w.step()
            self.assertLessEqual(len(w.organisms), MAX_POPULATION)
            for o in w.organisms:
                self.assertGreaterEqual(o.x, 5)
                self.assertLessEqual(o.x, 895)
                self.assertGreaterEqual(o.y, 5)
                self.assertLessEqual(o.y, 595)
                self.assertGreater(o.energy, 0)
                self.assertLessEqual(o.energy, ENERGY_CAP)
                self.assertFalse(o.dead)
                # children born during a step aren't updated until the next one
                if id(o) in existing:
                    self.assertGreater(o.age, 0)
                else:
                    self.assertEqual(o.age, 0)


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_trajectory(self):
        w1 = World(900, 600, seed=999)
        w2 = World(900, 600, seed=999)
        for _ in range(200):
            w1.step()
            w2.step()
        self.assertEqual(snapshot(w1), snapshot(w2))
        self.assertEqual([e.spectrum for e in w1.emitters],
                         [e.spectrum for e in w2.emitters])

    def test_different_seed_differs(self):
        w1 = World(900, 600, seed=1)
        w2 = World(900, 600, seed=2)
        for _ in range(50):
            w1.step()
            w2.step()
        self.assertNotEqual(snapshot(w1), snapshot(w2))


class TestSpatialGrid(unittest.TestCase):
    def test_query_finds_nearby_and_excludes(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        a = make_organism(100, 100, w.rng)
        b = make_organism(105, 105, w.rng)
        c = make_organism(300, 300, w.rng)
        g = SpatialGrid()
        g.build([a, b, c])
        found = g.query(102, 102, 10)
        self.assertIn(a, found)
        self.assertIn(b, found)
        self.assertNotIn(c, found)
        found = g.query(102, 102, 10, exclude=a)
        self.assertNotIn(a, found)
        self.assertIn(b, found)


class TestShadingIntegration(unittest.TestCase):
    def test_front_absorber_outperforms_shaded_one(self):
        w = single_emitter_world(ex=310, ey=310, spectrum=50, width=600, height=400)
        gene = make_gene(absorption_spectrum=50,
                         movement_ability=0.2, radiation_sensing=2.0)
        front = make_organism(310 + OPTIMAL_DISTANCE, 310, w.rng, gene)
        back = make_organism(410, 310, w.rng, make_gene(
            absorption_spectrum=50,
            movement_ability=0.2, radiation_sensing=2.0))
        w.organisms.extend([front, back])
        build_field(w)
        raw_back = 0.2 * (1.0 - 100 / 120.0)
        self.assertAlmostEqual(w.field.intensity_at(410, 310, 0),
                               raw_back * SHADE_FACTOR, places=9)
        raw_front = 0.2 * (1.0 - 80 / 120.0)
        self.assertAlmostEqual(w.field.intensity_at(390, 310, 0),
                               raw_front, places=9)
        f0, b0 = front.energy, back.energy
        for _ in range(20):
            w.step()
        self.assertGreater(front.energy - f0, back.energy - b0)


class TestNoEmitterStarvation(unittest.TestCase):
    def test_population_dies_out_without_emitters(self):
        # With no radiation, stealing only moves energy around while metabolism,
        # eating, the energy cap and reproduction (child gets <= REPRO_ENERGY)
        # all lose it, so total energy never rises. Every organism burns at least
        # the cost of the minimum genome each step, which bounds time to extinction.
        w = World(600, 400, seed=5, num_emitters=0, start_population=20)
        min_cost = MOTION_COST * 0.2 + SENSE_COST * (0.3 + 0.3)
        total = sum(o.energy for o in w.organisms)
        limit = int(total / min_cost) + 1
        steps = 0
        while w.organisms and steps < limit:
            w.step()
            steps += 1
            new_total = sum(o.energy for o in w.organisms)
            self.assertLessEqual(new_total, total + 1e-9)
            total = new_total
        self.assertEqual(len(w.organisms), 0)


if __name__ == "__main__":
    unittest.main()
