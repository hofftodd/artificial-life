import math
import unittest

from simcore import (EAT_FRACTION, EAT_GAIN_CAP, ENERGY_CAP, OPTIMAL_DISTANCE, PREY_RANGE,
                     STEAL_RATE, World)
from tests.helpers import (make_gene, make_organism, make_rng,
                           single_emitter_world)


class TestMigration(unittest.TestCase):
    def test_absorber_migrates_to_optimal_ring(self):
        w = single_emitter_world(ex=450, ey=300, spectrum=50, width=900, height=600)
        w.repro_chance = 0.0
        o = make_organism(450, 180, w.rng,
                          make_gene(absorption_spectrum=50, radiation_sensing=2.0))
        w.organisms.append(o)
        for _ in range(300):
            w.step()
        d = math.hypot(o.x - 450, o.y - 300)
        self.assertLess(abs(d - OPTIMAL_DISTANCE), 8)
        self.assertTrue(o.alive)


class TestRadiationDynamics(unittest.TestCase):
    def test_lethal_zone_kills(self):
        w = single_emitter_world(ex=450, ey=300, spectrum=50, width=900, height=600)
        o = make_organism(450, 300, w.rng,
                          make_gene(absorption_spectrum=50, movement_ability=0.2))
        o.energy = 5.0
        w.organisms.append(o)
        steps = 0
        while o.alive and steps < 200:
            w.step()
            steps += 1
        self.assertFalse(o.alive)
        self.assertLess(steps, 60)

    def test_optimal_ring_gains_energy(self):
        w = single_emitter_world(ex=450, ey=300, spectrum=50, width=900, height=600)
        o = make_organism(450 + OPTIMAL_DISTANCE, 300, w.rng,
                          make_gene(absorption_spectrum=50,
                                    movement_ability=0.2))
        w.organisms.append(o)
        e0 = o.energy
        for _ in range(20):
            w.step()
        self.assertGreater(o.energy, e0 + 0.5)

    def test_mismatched_spectrum_gains_less(self):
        w = single_emitter_world(ex=450, ey=300, spectrum=50, width=900, height=600)
        good = make_organism(450 + OPTIMAL_DISTANCE, 300, w.rng,
                             make_gene(absorption_spectrum=50,
                                       movement_ability=0.2))
        bad = make_organism(450, 300 - OPTIMAL_DISTANCE, w.rng,
                            make_gene(absorption_spectrum=1,
                                      movement_ability=0.2))
        w.organisms.extend([good, bad])
        g0, b0 = good.energy, bad.energy
        for _ in range(40):
            w.step()
        self.assertGreater(good.energy - g0, bad.energy - b0 + 0.5)


class TestInteraction(unittest.TestCase):
    def test_stealing_transfers_energy(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        parasite = make_organism(100, 100, w.rng,
                              make_gene(absorption=0.0, parasitism=1.0, movement_ability=0.2))
        victim = make_organism(108, 100, w.rng, make_gene(movement_ability=0.2))
        victim.energy = 5.0
        parasite0 = parasite.energy
        w.organisms.extend([parasite, victim])
        w.step()
        expected = 5.0 * parasite.genes.stealing_ability * STEAL_RATE
        self.assertLess(victim.energy, 5.0 - expected * 0.8)
        self.assertGreater(parasite.energy, parasite0 + expected * 0.8)

    def test_eating_kills_prey(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        pred = make_organism(100, 100, w.rng,
                             make_gene(absorption=0.0, predation=1.0, movement_ability=0.2))
        prey = make_organism(105, 100, w.rng, make_gene(movement_ability=0.2))
        prey.energy = 3.0
        pred0 = pred.energy
        w.organisms.extend([pred, prey])
        w.step()
        self.assertTrue(prey.dead)
        self.assertGreater(pred.energy, pred0 + min(3.0 * EAT_FRACTION, EAT_GAIN_CAP) - 0.5)


class TestLifecycle(unittest.TestCase):
    def test_reproduction(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        w.repro_chance = 1.0
        o = make_organism(100, 100, w.rng, make_gene(movement_ability=0.2))
        o.energy = 10.0
        w.organisms.append(o)
        w.step()
        self.assertEqual(len(w.organisms), 2)
        child = w.organisms[1]
        self.assertEqual(child.generation, 1)
        self.assertEqual(o.generation, 0)
        self.assertLess(o.energy, 4.0)
        self.assertGreater(o.energy, 0.0)

    def test_energy_cap(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        o = make_organism(100, 100, w.rng, make_gene(movement_ability=0.2))
        o.energy = 20.0
        w.organisms.append(o)
        w.step()
        self.assertEqual(o.energy, ENERGY_CAP)

    def test_starvation_death(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        o = make_organism(100, 100, w.rng, make_gene(movement_ability=0.2))
        o.energy = 0.05
        w.organisms.append(o)
        steps = 0
        while o in w.organisms and steps < 50:
            w.step()
            steps += 1
        self.assertLess(steps, 20)

    def test_max_age_death(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0)
        o = make_organism(100, 100, w.rng, make_gene(movement_ability=0.2))
        o.energy = 5.0
        o.max_age = 2
        w.organisms.append(o)
        w.step()
        self.assertIn(o, w.organisms)
        w.step()
        self.assertNotIn(o, w.organisms)


if __name__ == "__main__":
    unittest.main()
