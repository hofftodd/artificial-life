import math
import unittest

from simcore import (AMBIENT_MATCH, EMITTER_RANGE, Carcass, Emitter, Organism, Rules, World,
                     radiation_effect)
from tests.helpers import make_gene, make_organism, make_rng


def empty(**rules):
    rules.setdefault("arms_race", False)
    rules.setdefault("movement", "forage")      # rule-driven movement and motion cost
    return World(600, 400, seed=4, num_emitters=0, start_population=0, rules=Rules(**rules))


class TestAmbientLight(unittest.TestCase):
    def _energy_change(self, ambient):
        w = empty(ambient_light=ambient, depletion_rate=0.0)
        o = make_organism(300, 200, w.rng, make_gene(movement_ability=0.2))
        o.energy = 5.0
        w.organisms = [o]
        w.repro_chance = 0.0
        w.step()
        return o.energy - 5.0

    def test_ambient_feeds_organisms_far_from_emitters(self):
        gain = self._energy_change(0.02) - self._energy_change(0.0)
        eff = make_gene().absorption_efficiency
        self.assertAlmostEqual(gain, radiation_effect(0.02, AMBIENT_MATCH, eff), places=9)

    def test_forager_in_ambient_light_does_not_fall_back(self):
        w = empty(ambient_light=0.02, movement="forage")
        o = make_organism(300, 200, w.rng, make_gene())
        w.organisms = [o]
        w.grid.build(w.organisms)
        w.field = w._build_field()
        self.assertIsNotNone(o._forage_target(w))


class TestLightTail(unittest.TestCase):
    def test_tail_reaches_beyond_the_core(self):
        e = Emitter(0, 0, make_rng(1), spectrum=50)
        self.assertEqual(e.radiation_at(EMITTER_RANGE + 40, 0), 0.0)
        tail = e.radiation_at(EMITTER_RANGE + 40, 0, tail_strength=0.03, tail_range=240)
        self.assertAlmostEqual(tail, 0.03 * (1 - (EMITTER_RANGE + 40) / 240))
        self.assertEqual(e.radiation_at(250, 0, tail_strength=0.03, tail_range=240), 0.0)

    def test_field_covers_the_tail(self):
        w = World(900, 600, seed=1, start_population=0,
                  rules=Rules(tail_strength=0.03, tail_range=240))
        e = w.emitters[0]
        far = [k for k in w.field.by_emitter[0]
               if math.hypot((k[0] + 0.5) * 20 - e.x, (k[1] + 0.5) * 20 - e.y) > EMITTER_RANGE + 20]
        self.assertTrue(far)


class TestDispersal(unittest.TestCase):
    def _birth_distances(self, dispersal_max, gene):
        out = []
        for seed in range(60):
            w = World(900, 600, seed=seed, num_emitters=0, start_population=0,
                      rules=Rules(dispersal_max=dispersal_max, repro_chance=1.0))
            p = make_organism(450, 300, w.rng, make_gene(dispersal=gene))
            p.energy = 10.0
            w.organisms = [p]
            w.grid.build(w.organisms)
            p._reproduce(w)
            c = w.organisms[1]
            out.append(math.hypot(c.x - p.x, c.y - p.y))
        return out

    def test_original_range_when_off(self):
        self.assertLessEqual(max(self._birth_distances(0.0, 1.0)), 12.0 + 1e-9)

    def test_gene_sets_how_far_children_go(self):
        far = self._birth_distances(150.0, 1.0)
        near = self._birth_distances(150.0, 0.0)
        self.assertGreater(max(far), 60)
        self.assertLessEqual(max(far), 162.0 + 1e-9)
        self.assertLessEqual(max(near), 12.0 + 1e-9)


class TestCarcasses(unittest.TestCase):
    def test_old_age_leaves_a_carcass_but_starvation_does_not(self):
        w = empty(carcass_fraction=0.5)
        old = make_organism(100, 100, w.rng, make_gene())
        old.energy, old.max_age, old.age = 4.0, 5, 5
        hungry = make_organism(300, 100, w.rng, make_gene())
        hungry.energy = 0.001
        w.organisms = [old, hungry]
        w.repro_chance = 0.0
        w.step()
        self.assertEqual(len(w.carcasses), 1)
        self.assertAlmostEqual(w.carcasses[0].energy, old.energy * 0.5)
        self.assertEqual((w.carcasses[0].x, w.carcasses[0].y), (old.x, old.y))

    def test_prey_leftovers_become_a_carcass(self):
        w = empty(carcass_fraction=1.0, eat_gain_cap=1.0)
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0))
        prey = make_organism(108, 100, w.rng, make_gene())
        prey.energy = 5.0
        w.organisms = [pred, prey]
        w.grid.build(w.organisms)
        pred._eat(w)
        self.assertTrue(prey.dead)
        self.assertAlmostEqual(w.carcasses[0].energy, 5.0 - 1.0)

    def test_carcasses_decay_and_vanish(self):
        w = empty(carcass_fraction=0.5, carcass_decay=0.5)
        w.carcasses = [Carcass(100, 100, 1.0)]
        w.step()
        self.assertAlmostEqual(w.carcasses[0].energy, 0.5)
        for _ in range(10):
            w.step()
        self.assertEqual(w.carcasses, [])

    def test_scavengers_eat_and_predators_seek_carcasses(self):
        w = empty(carcass_fraction=0.5, scavenge_bite=0.5)
        pred = make_organism(100, 100, w.rng, make_gene(absorption=0.0, predation=1.0,
                                                        organism_sensing=2.0))
        w.carcasses = [Carcass(150, 100, 3.0)]
        w.organisms = [pred]
        w.repro_chance = 0.0
        e0 = pred.energy
        for _ in range(80):
            w.step()
            if w.stats[("scavenge", "predator")]:
                break
        self.assertGreater(w.stats[("scavenge", "predator")], 0)
        self.assertGreater(pred.energy, e0 - 0.5)

    def test_absorbers_without_predation_do_not_scavenge(self):
        w = empty(carcass_fraction=0.5)
        o = make_organism(100, 100, w.rng, make_gene())      # predation 0
        w.carcasses = [Carcass(104, 100, 3.0)]
        w.organisms = [o]
        w.repro_chance = 0.0
        w.step()
        self.assertEqual(sum(v for k, v in w.stats.items() if k[0] == "scavenge"), 0)

    def test_energy_never_rises_with_carcasses_and_no_emitters(self):
        w = World(600, 400, seed=7, num_emitters=0, start_population=40,
                  rules=Rules(carcass_fraction=1.0))
        total = sum(o.energy for o in w.organisms)
        for _ in range(400):
            w.step()
            new = sum(o.energy for o in w.organisms) + sum(c.energy for c in w.carcasses)
            self.assertLessEqual(new, total + 1e-9)
            total = new


class TestOpenWorldPreset(unittest.TestCase):
    def test_preset_and_env_names(self):
        from tools import soak
        r = Rules.open_world()
        self.assertGreater(r.ambient_light, 0)
        self.assertGreater(r.dispersal_max, 0)
        self.assertEqual(Rules().ambient_light, 0.0)
        both = soak.base_rules("dynamic+open")
        self.assertGreater(both.ambient_light, 0)
        self.assertGreater(both.num_rocks, 0)
        with self.assertRaises(ValueError):
            soak.base_rules("open+swamp")


class TestValidation(unittest.TestCase):
    def test_bad_values(self):
        for bad in (dict(ambient_light=-0.1), dict(dispersal_max=-1), dict(carcass_fraction=2),
                    dict(carcass_decay=0), dict(tail_strength=0.1, tail_range=0)):
            with self.assertRaises(ValueError):
                Rules(**bad)


if __name__ == "__main__":
    unittest.main()
