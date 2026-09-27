import math
import unittest

from simcore import PATROL_MIN_ENERGY, ROAM_LEG, Rules, World
from tests.helpers import make_gene, make_organism


def open_world(**rules):
    rules.setdefault("arms_race", False)
    rules.setdefault("ambient_light", 0.02)
    w = World(900, 600, seed=6, num_emitters=0, start_population=0, rules=Rules(**rules))
    w.repro_chance = 0.0
    return w


def run(w, ticks):
    for _ in range(ticks):
        w.step()


class TestRoaming(unittest.TestCase):
    def test_roamers_hold_their_leg_heading(self):
        w = open_world(roam_rate=1.0)
        o = make_organism(450, 300, w.rng, make_gene(roaming=1.0, movement_ability=2.0))
        o.energy = 10.0
        w.organisms = [o]
        w.step()
        leg, heading = o.leg, o.leg_dir
        self.assertGreater(leg, 0)
        x0, y0 = o.x, o.y
        run(w, 20)
        self.assertEqual(o.leg, leg - 20)
        self.assertAlmostEqual(o.direction, heading)
        # 20 ticks at 0.5px/tick in a straight line
        self.assertAlmostEqual(math.hypot(o.x - x0, o.y - y0), 10.0, delta=0.01)

    def test_legs_last_and_bounce_off_edges(self):
        w = open_world(roam_rate=1.0)
        o = make_organism(12, 300, w.rng, make_gene(roaming=1.0, movement_ability=2.0))
        o.energy = 10.0
        w.organisms = [o]
        w.step()
        self.assertTrue(ROAM_LEG[0] - 1 <= o.leg <= ROAM_LEG[1])
        o.leg_dir = math.pi                        # head into the left wall
        o.leg = 50
        for _ in range(40):
            w.step()
        self.assertGreater(o.x, 5.0)
        self.assertGreater(math.cos(o.leg_dir), 0) # now heading back out

    def test_no_legs_when_off(self):
        w = open_world()
        o = make_organism(450, 300, w.rng, make_gene(roaming=1.0))
        w.organisms = [o]
        run(w, 50)
        self.assertEqual(o.leg, 0)


class TestPatrol(unittest.TestCase):
    def _predator(self, energy):
        w = open_world(patrol=True)
        p = make_organism(450, 300, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                     movement_ability=1.0))
        p.energy = energy
        w.organisms = [p]
        w.step()
        return p

    def test_fed_hunters_patrol_hungry_ones_do_not(self):
        self.assertGreater(self._predator(PATROL_MIN_ENERGY + 3).leg, 0)
        self.assertEqual(self._predator(PATROL_MIN_ENERGY - 0.5).leg, 0)

    def test_sighting_a_victim_ends_the_patrol(self):
        w = open_world(patrol=True)
        p = make_organism(450, 300, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                     organism_sensing=2.0))
        p.energy = 8.0
        w.organisms = [p]
        w.step()
        self.assertGreater(p.leg, 0)
        prey = make_organism(470, 300, w.rng, make_gene(movement_ability=0.2))
        prey.energy = 1.0
        w.organisms.append(prey)
        w.step()
        self.assertEqual(p.leg, 0)


class TestParasitesMoveOn(unittest.TestCase):
    def test_richest_host_above_floor_is_drained(self):
        w = open_world(host_min_energy=2.0)
        par = make_organism(100, 100, w.rng, make_gene(absorption=0.0, parasitism=1.0,
                                                       movement_ability=0.2))
        poor = make_organism(105, 100, w.rng, make_gene(movement_ability=0.2))
        rich = make_organism(100, 108, w.rng, make_gene(movement_ability=0.2))
        poor.energy, rich.energy = 1.5, 6.0
        w.organisms = [par, poor, rich]
        w.grid.build(w.organisms)
        par._steal(w)
        self.assertEqual(poor.energy, 1.5)
        self.assertLess(rich.energy, 6.0)

    def test_poor_hosts_are_not_chased(self):
        w = open_world(host_min_energy=2.0)
        par = make_organism(100, 100, w.rng, make_gene(absorption=0.0, parasitism=1.0))
        poor = make_organism(130, 100, w.rng, make_gene())
        poor.energy = 1.0
        w.organisms = [par, poor]
        w.grid.build(w.organisms)
        self.assertIsNone(par._nearest(w.grid, 60, par._victim_filter(w)))


class TestFleeing(unittest.TestCase):
    def test_wary_prey_run_and_pay_for_it(self):
        def gap(wariness):
            w = open_world(flee=True)
            prey = make_organism(450, 300, w.rng, make_gene(wariness=wariness, movement_ability=2.0,
                                                            organism_sensing=2.0))
            pred = make_organism(430, 300, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                            movement_ability=0.2))
            prey.energy = pred.energy = 10.0
            w.organisms = [prey, pred]
            run(w, 20)
            return math.hypot(prey.x - pred.x, prey.y - pred.y), prey.energy
        (g_wary, e_wary), (g_calm, e_calm) = gap(1.0), gap(0.0)
        self.assertGreater(g_wary, g_calm + 3)
        self.assertLess(e_wary, e_calm)            # wariness costs sensing upkeep


class TestValidation(unittest.TestCase):
    def test_bad_values(self):
        for bad in (dict(roam_rate=1.5), dict(host_min_energy=-1)):
            with self.assertRaises(ValueError):
                Rules(**bad)


if __name__ == "__main__":
    unittest.main()
