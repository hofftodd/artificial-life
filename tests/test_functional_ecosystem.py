import math
import os
import unittest

from simcore import MAX_POPULATION, OPTIMAL_DISTANCE, Organism, World
from tests.helpers import make_gene, single_emitter_world


@unittest.skipIf(os.environ.get("AIL_QUICK") == "1", "AIL_QUICK=1 skips functional tests")
class TestEcosystem(unittest.TestCase):
    def test_survives_and_reproduces(self):
        w = World(900, 600, seed=42)
        pop_at_300 = None
        for i in range(1000):
            w.step()
            if i == 299:
                pop_at_300 = len(w.organisms)
        self.assertGreater(pop_at_300, 0)
        self.assertGreaterEqual(len(w.organisms), 5)
        self.assertGreater(w.total_births, 0)
        self.assertGreaterEqual(w.generation, 1)

    def test_selection_favors_matched_spectrum(self):
        # Seed the optimal ring with alternating absorbers: half tuned to the
        # emitter (spectrum 20), half badly mismatched (90, which barely breaks
        # even). Nothing else differs, so after several generations the matched
        # lineage should dominate. Pooled over a few seeds because a single
        # small population is noisy.
        matched = mismatched = 0
        for seed in (1, 2, 3):
            w = single_emitter_world(seed=seed, ex=450, ey=300, spectrum=20,
                                     width=900, height=600)
            n = 24
            for k in range(n):
                a = 2 * math.pi * k / n
                w.organisms.append(Organism(
                    450 + OPTIMAL_DISTANCE * math.cos(a),
                    300 + OPTIMAL_DISTANCE * math.sin(a), w.rng,
                    make_gene(absorption_spectrum=20 if k % 2 == 0 else 90)))
            for _ in range(800):
                w.step()
            self.assertGreater(len(w.organisms), 0)
            self.assertGreaterEqual(w.generation, 2)
            for o in w.organisms:
                if abs(o.genes.absorption_spectrum - 20) < 35:
                    matched += 1
                else:
                    mismatched += 1
        self.assertGreater(matched, 1.5 * mismatched)

    def test_predator_free_population_levels_off(self):
        # Absorbers sharing a cell split its energy, so an emitter supports a
        # limited population. With strategy mutation off (no predators can
        # evolve), a sparse founding group should grow and a crowded one shrink
        # toward the same carrying capacity, far below the hard cap.
        def run(n):
            w = single_emitter_world(seed=1, ex=300, ey=300, spectrum=50,
                                     width=600, height=600)
            w.strategy_mutation = 0.0
            for _ in range(n):
                a = w.rng.uniform(0, 2 * math.pi)
                r = w.rng.uniform(55, 110)
                w.organisms.append(Organism(300 + r * math.cos(a), 300 + r * math.sin(a),
                                            w.rng, make_gene(absorption_spectrum=50)))
            for _ in range(2500):
                w.step()
            self.assertEqual({o.strategy for o in w.organisms}, {"absorber"})
            return len(w.organisms)

        sparse, crowded = run(10), run(300)
        self.assertGreater(sparse, 50)
        self.assertLess(crowded, 250)
        self.assertLess(crowded, MAX_POPULATION / 2)
        self.assertLess(crowded / sparse, 2.5)


if __name__ == "__main__":
    unittest.main()
