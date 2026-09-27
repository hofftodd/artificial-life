import unittest

from simcore import SHADE_FACTOR
from tests.helpers import (build_field, make_gene, make_organism,
                           make_rng, single_emitter_world)

EX, EY = 310, 310
TX, TY = 410, 310  # cell center 100px from the emitter, on the +x beam


def raw_intensity():
    return 0.2 * (1.0 - 100 / 120.0)


def field_with(world, organisms):
    world.organisms = organisms
    return build_field(world)


class TestShading(unittest.TestCase):
    def test_no_blockers_no_shading(self):
        w = single_emitter_world(ex=EX, ey=EY)
        field = field_with(w, [])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_absorber_on_beam_shades(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(360, 310, make_rng(1), make_gene())
        self.assertEqual(o.strategy, "absorber")
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0),
                               raw_intensity() * SHADE_FACTOR, places=9)

    def test_two_blockers_compound(self):
        w = single_emitter_world(ex=EX, ey=EY)
        a = make_organism(360, 310, make_rng(1), make_gene())
        b = make_organism(390, 310, make_rng(2), make_gene())
        field = field_with(w, [a, b])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0),
                               raw_intensity() * SHADE_FACTOR ** 2, places=9)

    def test_non_absorber_does_not_shade(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(360, 310, make_rng(1), make_gene(absorption=0.0, predation=1.0))
        self.assertEqual(o.strategy, "predator")
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_dead_absorber_does_not_shade(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(360, 310, make_rng(1), make_gene())
        o.dead = True
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_offbeam_does_not_shade(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(360, 330, make_rng(1), make_gene())
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_blocker_behind_target_does_not_shade(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(420, 310, make_rng(1), make_gene())
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_blocker_too_close_to_emitter_does_not_shade(self):
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(315, 310, make_rng(1), make_gene())
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)

    def test_absorber_does_not_shade_its_own_cell(self):
        # (401.5, 310) is inside the target cell (400-420) and nearer the
        # emitter than its centre, so it sits on the beam to that centre
        w = single_emitter_world(ex=EX, ey=EY)
        o = make_organism(401.5, 310, make_rng(1), make_gene())
        field = field_with(w, [o])
        self.assertAlmostEqual(field.intensity_at(TX, TY, 0), raw_intensity(), places=12)
        # ...but it still shades the cell behind it
        self.assertLess(field.intensity_at(TX + 20, TY, 0), raw_intensity())


if __name__ == "__main__":
    unittest.main()
