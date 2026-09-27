import math
import unittest

from simcore import (EMITTER_RANGE, LETHAL_DISTANCE, OPTIMAL_DISTANCE,
                     RADIATION_DANGER, RADIATION_ENERGY, Emitter,
                     radiation_effect, spectral_match)
from tests.helpers import make_rng


class TestRadiationEffect(unittest.TestCase):
    def test_zero_intensity_zero_effect(self):
        self.assertEqual(radiation_effect(0.0, 1.0, 1.0), 0.0)

    def test_zero_at_danger_level(self):
        self.assertAlmostEqual(
            radiation_effect(RADIATION_DANGER, 1.0, 1.0), 0.0, places=12)

    def test_positive_below_danger(self):
        self.assertGreater(radiation_effect(0.06, 1.0, 1.0), 0.0)
        self.assertGreater(radiation_effect(0.11, 1.0, 1.0), 0.0)

    def test_negative_above_danger(self):
        self.assertLess(radiation_effect(0.13, 1.0, 1.0), 0.0)
        self.assertLess(radiation_effect(RADIATION_ENERGY, 1.0, 1.0), 0.0)

    def test_peak_at_danger_over_sqrt3(self):
        peak = RADIATION_DANGER / math.sqrt(3.0)
        best = peak
        best_v = radiation_effect(best, 1.0, 1.0)
        for i in range(1, 100):
            v = i * 0.002
            val = radiation_effect(v, 1.0, 1.0)
            if val > best_v:
                best, best_v = v, val
        self.assertAlmostEqual(best, peak, delta=0.002)

    def test_matches_formula(self):
        i, m, e = 0.06, 0.8, 1.5
        expected = i * m * e * (1.0 - (i / RADIATION_DANGER) ** 2)
        self.assertAlmostEqual(radiation_effect(i, m, e), expected, places=12)

    def test_scales_with_match_and_efficiency(self):
        base = radiation_effect(0.06, 1.0, 1.0)
        self.assertAlmostEqual(radiation_effect(0.06, 0.5, 1.0), base * 0.5, places=12)
        self.assertAlmostEqual(radiation_effect(0.06, 1.0, 2.0), base * 2.0, places=12)


class TestEmitterIntensity(unittest.TestCase):
    def setUp(self):
        self.e = Emitter(300, 300, make_rng(1), spectrum=50)

    def test_center_is_max(self):
        self.assertAlmostEqual(self.e.radiation_at(300, 300), RADIATION_ENERGY)

    def test_linear_falloff(self):
        self.assertAlmostEqual(self.e.radiation_at(360, 300),
                               RADIATION_ENERGY * (1.0 - 60 / EMITTER_RANGE), places=9)

    def test_zero_beyond_range(self):
        self.assertEqual(self.e.radiation_at(300 + EMITTER_RANGE, 300), 0.0)
        self.assertEqual(self.e.radiation_at(10, 10), 0.0)

    def test_monotonically_decreasing(self):
        vals = [self.e.radiation_at(300 + d, 300) for d in range(0, EMITTER_RANGE, 10)]
        for a, b in zip(vals, vals[1:]):
            self.assertGreater(a, b)


class TestDistances(unittest.TestCase):
    def test_lethal_distance_exact(self):
        self.assertAlmostEqual(LETHAL_DISTANCE, 48.0, places=9)
        self.assertAlmostEqual(RADIATION_ENERGY * (1.0 - LETHAL_DISTANCE / EMITTER_RANGE),
                               RADIATION_DANGER, places=9)

    def test_inside_lethal_is_dangerous(self):
        d = LETHAL_DISTANCE - 5
        self.assertGreater(RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE), RADIATION_DANGER)

    def test_optimal_distance_is_peak(self):
        def net(d):
            i = RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE)
            return radiation_effect(i, 1.0, 1.0)
        best = net(OPTIMAL_DISTANCE)
        for d in (OPTIMAL_DISTANCE - 20, OPTIMAL_DISTANCE - 10,
                  OPTIMAL_DISTANCE + 10, OPTIMAL_DISTANCE + 20):
            self.assertLess(net(d), best)


class TestSpectralMatch(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertEqual(spectral_match(50, 50), 1.0)

    def test_opposite_is_zero(self):
        self.assertEqual(spectral_match(1, 100), 0.0)

    def test_symmetric(self):
        self.assertAlmostEqual(spectral_match(10, 90), spectral_match(90, 10), places=12)

    def test_linear(self):
        self.assertAlmostEqual(spectral_match(1, 51), 1.0 - 50.0 / 99.0, places=12)


if __name__ == "__main__":
    unittest.main()
