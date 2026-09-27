import unittest

from simcore import KIN_MARKER_DIST, Gene, Organism, Rules, World, species_clusters
from tests.helpers import make_gene, make_organism, make_rng
from tools import soak


def breeding_world(**rules):
    rules.setdefault("repro_chance", 1.0)
    return World(600, 400, seed=5, num_emitters=0, start_population=0, rules=Rules(**rules))


class TestMarkerKin(unittest.TestCase):
    def test_family_mode_by_default(self):
        rng = make_rng()
        a = make_organism(0, 0, rng, make_gene(marker=50.0))
        b = make_organism(0, 0, rng, make_gene(marker=50.0))
        self.assertFalse(a.is_kin(b))          # different founders
        child = Organism(0, 0, rng, make_gene(marker=90.0), parent=a)
        self.assertTrue(a.is_kin(child))

    def test_marker_mode_uses_marker_distance(self):
        rng = make_rng()
        a = make_organism(0, 0, rng, make_gene(marker=50.0))
        near = make_organism(0, 0, rng, make_gene(marker=50.0 + KIN_MARKER_DIST - 0.5))
        far = make_organism(0, 0, rng, make_gene(marker=50.0 + KIN_MARKER_DIST + 0.5))
        a.kin_dist = KIN_MARKER_DIST
        self.assertTrue(a.is_kin(near))
        self.assertFalse(a.is_kin(far))

    def test_world_sets_and_children_inherit_marker_kin(self):
        w = World(600, 400, seed=2, start_population=10, rules=Rules.speciation())
        self.assertTrue(all(o.kin_dist == KIN_MARKER_DIST for o in w.organisms))
        child = Organism(0, 0, w.rng, make_gene(), parent=w.organisms[0])
        self.assertEqual(child.kin_dist, KIN_MARKER_DIST)
        self.assertTrue(all(o.kin_dist is None for o in World(600, 400, seed=2).organisms))


class TestCrossover(unittest.TestCase):
    def test_genes_come_from_the_two_parents(self):
        rng = make_rng(9)
        a = Gene.random(rng)
        b = Gene.random(rng)
        ta, tb = a.as_tuple(), b.as_tuple()
        for _ in range(50):
            c = Gene.crossover(a, b, rng).as_tuple()
            self.assertIn(c[1:4], (ta[1:4], tb[1:4]))      # shares as one block
            for i, v in enumerate(c):
                if i not in (1, 2, 3):
                    self.assertIn(v, (ta[i], tb[i]))


class TestMating(unittest.TestCase):
    def _breed(self, mate_marker, mate_strategy="absorber", mate_dx=10, **rules):
        w = breeding_world(sex_rate=1.0, **rules)
        parent = make_organism(100, 100, w.rng, make_gene(marker=50.0))
        parent.energy = 10.0
        mate_gene = make_gene(marker=mate_marker) if mate_strategy == "absorber" else \
            make_gene(marker=mate_marker, absorption=0.0, parasitism=1.0)
        mate = make_organism(100 + mate_dx, 100, w.rng, mate_gene)
        w.organisms = [parent, mate]
        w.grid.build(w.organisms)
        parent._reproduce(w)
        return w, mate, w.organisms[2] if len(w.organisms) > 2 else None

    def test_close_marker_mates(self):
        w, mate, child = self._breed(53.0)
        self.assertEqual(child.mate_uid, mate.uid)
        self.assertEqual(w.stats[("birth", "sexual")], 1)

    def test_distant_marker_is_rejected(self):
        w, _, child = self._breed(50.0 + 7.0, mate_tolerance=6.0)
        self.assertIsNotNone(child)                     # still breeds...
        self.assertIsNone(child.mate_uid)               # ...asexually
        self.assertEqual(w.stats[("birth", "asexual")], 1)

    def test_other_strategies_are_not_mates(self):
        _, _, child = self._breed(50.0, mate_strategy="parasite")
        self.assertIsNone(child.mate_uid)

    def test_no_mate_in_range_breeds_asexually(self):
        _, _, child = self._breed(50.0, mate_dx=60)
        self.assertIsNotNone(child)
        self.assertIsNone(child.mate_uid)

    def test_lineage_records_the_mate(self):
        w = World(900, 600, seed=3, record_lineage=True, rules=Rules.speciation(sex_rate=1.0))
        for _ in range(400):
            w.step()
        births = [r for r in w.lineage if r[0] == "birth" and r[3] is not None]
        self.assertTrue(births)
        self.assertTrue(any(r[7] is not None for r in births))
        self.assertEqual(sum(1 for r in births if r[7] is not None), w.stats[("birth", "sexual")])


class TestSpeciesClusters(unittest.TestCase):
    def test_gaps_split_clusters_and_small_ones_are_dropped(self):
        markers = [10, 11, 12, 13, 40, 41, 42, 70, 71, 95]
        clusters = species_clusters(markers, gap=8, min_size=3)
        self.assertEqual([len(c) for c in clusters], [4, 3])
        self.assertEqual(species_clusters([], gap=8), [])


class TestPresets(unittest.TestCase):
    def test_speciation_preset_and_env_combinations(self):
        r = Rules.speciation()
        self.assertEqual(r.kin_by, "marker")
        self.assertGreater(r.sex_rate, 0)
        both = soak.base_rules("dynamic+speciation")
        self.assertEqual(both.kin_by, "marker")
        self.assertGreater(both.num_rocks, 0)
        self.assertEqual(soak.base_rules("static"), Rules())
        with self.assertRaises(ValueError):
            soak.base_rules("volcanic")
        with self.assertRaises(ValueError):
            Rules(kin_by="smell")


if __name__ == "__main__":
    unittest.main()
