import math
import unittest

from simcore import EMITTER_MARGIN, OPTIMAL_DISTANCE, Emitter, Rock, Rules, World, in_cover
from tests.helpers import build_field, make_gene, make_organism, make_rng, single_emitter_world


def rocky_world(**rules):
    return World(900, 600, seed=11, rules=Rules(**rules))


class TestRocks(unittest.TestCase):
    def test_no_rocks_by_default(self):
        self.assertEqual(World(300, 200, seed=1).rocks, [])

    def test_rocks_are_placed_clear_of_emitters_and_each_other(self):
        w = rocky_world(num_rocks=10)
        self.assertGreater(len(w.rocks), 5)
        for i, a in enumerate(w.rocks):
            for e in w.emitters:
                self.assertGreater(math.hypot(a.x - e.x, a.y - e.y), a.r + 25)
            for b in w.rocks[i + 1:]:
                self.assertGreater(math.hypot(a.x - b.x, a.y - b.y), a.r + b.r)

    def test_organisms_never_inside_rocks(self):
        w = rocky_world(num_rocks=12)
        for _ in range(300):
            w.step()
            for o in w.organisms:
                for k in w.rocks:
                    self.assertGreaterEqual(math.hypot(o.x - k.x, o.y - k.y), k.r - 1e-6)

    def _field_with_rock(self, rock, shade=0.1):
        w = single_emitter_world(ex=300, ey=200)
        w.rocks = [rock]
        w.rules = Rules(rock_shade=shade)
        return w, build_field(w)

    def test_rock_casts_a_shadow_and_is_dark_inside(self):
        rock = Rock(350, 210, 12)      # centred on a field cell's centre
        w, field = self._field_with_rock(rock, shade=0.1)
        w_open = single_emitter_world(ex=300, ey=200)
        open_field = build_field(w_open)
        behind = (300 + 90, 200)
        self.assertAlmostEqual(field.intensity_at(*behind, 0),
                               open_field.intensity_at(*behind, 0) * 0.1)
        beside = (300, 200 + 90)       # not on the beam through the rock
        self.assertAlmostEqual(field.intensity_at(*beside, 0), open_field.intensity_at(*beside, 0))
        self.assertEqual(field.intensity_at(rock.x, rock.y, 0), 0.0)


class TestCover(unittest.TestCase):
    def setUp(self):
        self.w = World(600, 400, seed=2, num_emitters=0, start_population=0,
                       rules=Rules(num_rocks=0))
        self.w.rocks = [Rock(300, 200, 15)]
        self.pred = make_organism(300 - 60, 200 + 40, self.w.rng,
                                  make_gene(absorption=0.0, predation=1.0, organism_sensing=2.0))

    def _chase_target(self, prey):
        self.w.organisms = [self.pred, prey]
        self.w.grid.build(self.w.organisms)
        return self.pred._nearest(self.w.grid, 80, self.pred._victim_filter(self.w))

    def test_prey_in_cover_is_invisible_from_afar(self):
        prey = make_organism(300 - 20, 200, self.w.rng, make_gene())  # 5px from the edge
        prey.energy = 1.0
        self.assertTrue(in_cover(prey.x, prey.y, self.w.rocks, self.w.rules.cover_range))
        self.assertIsNone(self._chase_target(prey))

    def test_prey_in_cover_is_visible_up_close(self):
        prey = make_organism(300 - 20, 200, self.w.rng, make_gene())
        prey.energy = 1.0
        self.pred.x, self.pred.y = 300 - 35, 200
        self.assertIs(self._chase_target(prey), prey)

    def test_prey_in_the_open_is_visible(self):
        prey = make_organism(300 - 60, 200, self.w.rng, make_gene())
        prey.energy = 1.0
        self.assertIs(self._chase_target(prey), prey)

    def test_cover_affinity_pulls_toward_rocks(self):
        def gap_after(affinity):
            w = World(600, 400, seed=3, num_emitters=0, start_population=0,
                      rules=Rules(movement="forage"))     # cover pull is a movement rule
            w.rocks = [Rock(300, 200, 15)]
            o = make_organism(240, 200, w.rng, make_gene(cover_affinity=affinity,
                                                        organism_sensing=2.0))
            o.energy = 10.0
            w.repro_chance = 0.0
            w.organisms.append(o)
            for _ in range(150):
                w.step()
            return math.hypot(o.x - 300, o.y - 200) - 15
        self.assertLess(gap_after(1.0), 8)
        self.assertGreater(gap_after(0.0), 8)


class TestDynamicPreset(unittest.TestCase):
    def test_preset_turns_the_environment_on(self):
        r = Rules.dynamic()
        self.assertGreater(r.pulse_depth, 0)
        self.assertGreater(r.pulse_period, 0)
        self.assertGreater(r.spectrum_drift, 0)
        self.assertGreater(r.num_rocks, 0)
        self.assertEqual(Rules.dynamic(num_rocks=2).num_rocks, 2)

    def test_defaults_are_static(self):
        r = Rules()
        self.assertEqual((r.pulse_depth, r.spectrum_drift, r.emitter_drift, r.num_rocks),
                         (0.0, 0.0, 0.0, 0))


class TestEmitterDynamics(unittest.TestCase):
    def test_static_by_default(self):
        w = World(900, 600, seed=4)
        before = [(e.x, e.y, e.spectrum) for e in w.emitters]
        for _ in range(50):
            w.step()
        self.assertEqual([(e.x, e.y, e.spectrum) for e in w.emitters], before)
        self.assertTrue(all(e.strength == 1.0 for e in w.emitters))

    def test_pulse_spans_depth(self):
        w = World(900, 600, seed=4, rules=Rules(pulse_period=100, pulse_depth=0.6))
        seen = []
        for _ in range(100):
            w.step()
            seen.append(w.emitters[0].strength)
        self.assertAlmostEqual(min(seen), 0.4, places=2)
        self.assertAlmostEqual(max(seen), 1.0, places=2)

    def test_pulse_scales_radiation(self):
        e = Emitter(0, 0, make_rng(1), spectrum=50)
        full = e.radiation_at(OPTIMAL_DISTANCE, 0)
        e.strength = 0.5
        self.assertAlmostEqual(e.radiation_at(OPTIMAL_DISTANCE, 0), full * 0.5)

    def test_drift_stays_in_bounds(self):
        w = World(900, 600, seed=5, start_population=0,
                  rules=Rules(spectrum_drift=5.0, emitter_drift=20.0, num_rocks=6))
        for _ in range(300):
            w.step()
            for e in w.emitters:
                self.assertTrue(1 <= e.spectrum <= 100)
                self.assertTrue(EMITTER_MARGIN <= e.x <= 900 - EMITTER_MARGIN)
                self.assertTrue(EMITTER_MARGIN <= e.y <= 600 - EMITTER_MARGIN)

    def test_environment_rules_are_validated(self):
        for bad in (dict(pulse_depth=1.5), dict(rock_shade=-0.1)):
            with self.assertRaises(ValueError):
                Rules(**bad)


if __name__ == "__main__":
    unittest.main()
