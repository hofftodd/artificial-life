import math
import unittest

from simcore import ARMS_BIAS, ARMS_K, OPTIMAL_DISTANCE, Rules, World
from tests.helpers import build_field, make_gene, make_organism, make_rng, single_emitter_world


def arms_world(seed=1, **rules):
    rules.setdefault("group_defense", 0)
    return World(600, 400, seed=seed, num_emitters=0, start_population=0,
                 rules=Rules(arms_race=True, **rules))


def kill_chance(bite, armor):
    return 1.0 / (1.0 + math.exp(-(ARMS_K * (bite - armor) + ARMS_BIAS)))


class TestArmourVsBite(unittest.TestCase):
    def _success_rate(self, bite, armor, trials=400):
        wins = 0
        for seed in range(trials):
            w = arms_world(seed)
            pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0, bite=bite))
            prey = make_organism(108, 100, w.rng, make_gene(armor=armor))
            prey.energy = 1.0
            w.organisms = [pred, prey]
            w.grid.build(w.organisms)
            pred._eat(w)
            wins += prey.dead
        return wins / trials

    def test_kill_chance_follows_bite_minus_armour(self):
        for bite, armor in ((0.0, 0.0), (0.0, 0.5), (0.5, 0.0), (0.4, 0.6)):
            self.assertAlmostEqual(self._success_rate(bite, armor), kill_chance(bite, armor),
                                   delta=0.06, msg="bite %s armour %s" % (bite, armor))

    def test_armour_ignored_when_arms_race_is_off(self):
        w = World(600, 400, seed=1, num_emitters=0, start_population=0,
                  rules=Rules(arms_race=False, group_defense=0))
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0))
        prey = make_organism(108, 100, w.rng, make_gene(armor=1.0))
        prey.energy = 1.0
        w.organisms = [pred, prey]
        w.grid.build(w.organisms)
        pred._eat(w)
        self.assertTrue(prey.dead)

    def test_resisted_attack_costs_a_cooldown(self):
        w = arms_world()
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0, bite=0.0))
        prey = make_organism(108, 100, w.rng, make_gene(armor=1.0))   # ~1% kill chance
        prey.energy = 1.0
        w.organisms = [pred, prey]
        w.grid.build(w.organisms)
        pred._eat(w)
        self.assertFalse(prey.dead)
        self.assertEqual(pred.hunt_cd, w.rules.hunt_cooldown)
        self.assertEqual(w.stats[("resisted", "predator", "absorber")], 1)


class TestCamouflageVsPerception(unittest.TestCase):
    def _spots(self, camouflage, perception):
        w = arms_world()
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                        organism_sensing=1.0,
                                                        perception=perception))
        prey = make_organism(130, 100, w.rng, make_gene(camouflage=camouflage))  # 30px away
        prey.energy = 1.0
        w.organisms = [pred, prey]
        w.grid.build(w.organisms)
        return pred._nearest(w.grid, 60, pred._victim_filter(w)) is prey

    def test_camouflage_hides_and_perception_finds(self):
        self.assertTrue(self._spots(0.0, 0.0))     # reach 40px
        self.assertFalse(self._spots(0.5, 0.0))    # reach 20px
        self.assertTrue(self._spots(0.5, 0.5))     # reach back to 40px

    def test_perception_extends_beyond_base_sense(self):
        w = arms_world()
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                        organism_sensing=1.0, perception=0.4))
        prey = make_organism(150, 100, w.rng, make_gene())    # 50px: beyond 40, within 56
        prey.energy = 1.0
        w.organisms = [pred, prey]
        w.repro_chance = 0.0
        d0 = 50.0
        for _ in range(5):
            w.step()
        self.assertLess(math.hypot(prey.x - pred.x, prey.y - pred.y), d0 - 2)


class TestArmsCosts(unittest.TestCase):
    def test_armour_costs_upkeep_and_slows(self):
        def run(armor):
            w = arms_world()
            o = make_organism(100, 100, w.rng, make_gene(armor=armor, movement_ability=2.0))
            o.energy = 10.0
            w.organisms = [o]
            w.repro_chance = 0.0
            x0 = o.x
            for _ in range(20):
                w.step()
            return o.energy, abs(o.x - x0) + abs(o.y - 100)
        e0, d0 = run(0.0)
        e1, d1 = run(1.0)
        self.assertLess(e1, e0 - 0.05)
        self.assertLess(d1, d0)

    def test_camouflage_costs_light(self):
        def gain(camouflage):
            w = single_emitter_world(ex=300, ey=200)
            w.rules = Rules(arms_race=True, depletion_rate=0.0)
            o = make_organism(300 + OPTIMAL_DISTANCE, 200, w.rng,
                              make_gene(camouflage=camouflage, movement_ability=0.2))
            w.organisms = [o]
            build_field(w)
            before = o.energy
            o.update(w)
            return o.energy - before
        self.assertLess(gain(1.0), gain(0.0) * 0.6)

    def test_arms_genes_mutate_within_bounds(self):
        rng = make_rng(3)
        g = make_gene(armor=0.9, bite=0.1, camouflage=0.5, perception=0.95)
        for _ in range(300):
            g = g.mutated(rng)
            for name in ("armor", "bite", "camouflage", "perception"):
                self.assertTrue(0.0 <= getattr(g, name) <= 1.0)


if __name__ == "__main__":
    unittest.main()
