import math
import statistics
import unittest

from simcore import (BRAIN_CLAMP, BRAIN_INPUTS, BRAIN_SEEDS, BRAIN_SIZE, ENERGY_CAP,
                     OPTIMAL_DISTANCE, Gene, Rules, World, brain_weight, seed_brain)
from tests.helpers import make_gene, make_organism, make_rng, single_emitter_world


def brain(throttle=10.0, **weights):
    """A controller with only the given (base) weights; hunger weights via
    name_h=value. Throttle bias defaults to full speed."""
    w = [0.0] * BRAIN_SIZE
    for key, value in weights.items():
        name, _, h = key.partition("_h")
        i = 2 * BRAIN_INPUTS.index(name)
        w[i + (1 if key.endswith("_h") else 0)] = value
    w[-3] = throttle
    return tuple(w)


def brain_world(**rules):
    rules.setdefault("arms_race", False)
    w = World(900, 600, seed=3, num_emitters=0, start_population=0,
              rules=Rules(movement="brain", **rules))
    w.repro_chance = 0.0
    return w


class TestSteering(unittest.TestCase):
    def test_positive_prey_weight_closes_in(self):
        w = brain_world(group_defense=0)
        pred = make_organism(300, 300, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                        organism_sensing=2.0,
                                                        brain=brain(prey=2.0)))
        prey = make_organism(360, 300, w.rng, make_gene(movement_ability=0.2, brain=brain(throttle=-10)))
        prey.energy = 1.0
        pred.hunt_cd = 10 ** 6                       # can chase but not eat
        w.organisms = [pred, prey]
        run_for(w, 20)
        self.assertLess(math.hypot(prey.x - pred.x, prey.y - pred.y), 45)

    def test_negative_threat_weight_flees(self):
        w = brain_world()
        prey = make_organism(300, 300, w.rng, make_gene(movement_ability=2.0, organism_sensing=2.0,
                                                        brain=brain(threat=-2.0)))
        pred = make_organism(280, 300, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                        brain=brain(throttle=-10)))
        w.organisms = [prey, pred]
        run_for(w, 20)
        self.assertGreater(math.hypot(prey.x - pred.x, prey.y - pred.y), 28)
        self.assertGreater(prey.x, 300)

    def test_momentum_holds_heading(self):
        w = brain_world()
        o = make_organism(300, 300, w.rng, make_gene(brain=brain(momentum=1.0)))
        o.direction = 0.7
        w.organisms = [o]
        run_for(w, 15)
        self.assertAlmostEqual(o.direction, 0.7)


class TestThrottleAndHunger(unittest.TestCase):
    def test_low_throttle_barely_moves_and_costs_less(self):
        def run(throttle):
            w = brain_world()
            o = make_organism(300, 300, w.rng, make_gene(movement_ability=2.0,
                                                        brain=brain(throttle=throttle, momentum=1.0)))
            o.energy = 10.0
            w.organisms = [o]
            run_for(w, 20)
            return math.hypot(o.x - 300, o.y - 300), o.energy
        d_slow, e_slow = run(-10.0)
        d_fast, e_fast = run(10.0)
        self.assertLess(d_slow, 0.1)
        self.assertGreater(d_fast, 9.0)
        self.assertGreater(e_slow, e_fast)          # motion cost follows actual speed

    def test_hunger_term_switches_light_seeking(self):
        def turned_toward_light(energy):
            w = single_emitter_world(ex=300, ey=200)
            w.rules = Rules(movement="brain", arms_race=False)
            o = make_organism(300 + OPTIMAL_DISTANCE + 40, 200, w.rng,
                              make_gene(radiation_sensing=2.0, brain=brain(light_h=3.0)))
            o.energy = energy
            o.direction = math.pi / 2               # heading "down", light is to the left
            w.organisms = [o]
            w.grid.build(w.organisms)
            w.field = w._build_field()
            o._move(w)
            return math.cos(o.direction) < -0.5      # now heading toward the emitter
        self.assertTrue(turned_toward_light(0.5))    # hungry
        self.assertFalse(turned_toward_light(ENERGY_CAP))  # full: weight 0


class TestBrainGenome(unittest.TestCase):
    def test_round_trip_crossover_and_mutation(self):
        rng = make_rng(2)
        a, b = Gene.random(rng), Gene.random(rng)
        self.assertEqual(Gene.from_tuple(a.as_tuple()).as_tuple(), a.as_tuple())
        c = Gene.crossover(a, b, rng)
        for x, wa, wb in zip(c.brain, a.brain, b.brain):
            self.assertIn(x, (wa, wb))
        g = a
        for _ in range(200):
            g = g.mutated(rng)
            self.assertTrue(all(-BRAIN_CLAMP <= x <= BRAIN_CLAMP for x in g.brain))

    def test_founders_are_seeded_by_strategy(self):
        rng = make_rng(5)
        for strategy in ("absorber", "predator"):
            brains = [seed_brain(strategy, rng) for _ in range(300)]
            for name in ("prey", "threat", "light"):
                base, _h = BRAIN_SEEDS[strategy].get(name, (0.0, 0.0))
                mean = statistics.fmean(brain_weight(b, name, 0.0) for b in brains)
                self.assertAlmostEqual(mean, base, delta=0.05)
        g = Gene.random_specialist(rng, "predator")
        self.assertGreater(brain_weight(g.brain, "prey", 0.0), 1.0)

    def test_genomes_without_a_brain_use_the_default(self):
        w = brain_world()
        o = make_organism(300, 300, w.rng, make_gene())     # brain None
        w.organisms = [o]
        run_for(w, 5)                                       # no crash
        self.assertIsNone(o.genes.brain)


def run_for(w, ticks):
    for _ in range(ticks):
        w.step()


if __name__ == "__main__":
    unittest.main()
