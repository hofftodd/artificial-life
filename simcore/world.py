"""
The world: emitters, rocks and the population, plus the tick loop,
grazing, lineage records and checkpoints.
"""
import collections
import math
import pickle
import random

from .constants import (CARCASS_MIN, KIN_MARKER_DIST, MAX_POPULATION,
                        NUM_EMITTERS, RESERVE_FLOOR, START_POPULATION,
                        STRATEGIES, STRATEGY_MUTATION)
from .environment import Carcass, Emitter, Rock, push_out
from .gene import Gene
from .organism import Organism, _ids
from .radiation import RadiationField
from .rules import Rules
from .spatial import SpatialGrid

class World:
    def __init__(self, width=900, height=600, seed=None, num_emitters=NUM_EMITTERS,
                 start_population=START_POPULATION, max_population=MAX_POPULATION,
                 strategy_mutation=STRATEGY_MUTATION, strategy_mix=None, rules=None,
                 record_lineage=False):
        """strategy_mix: optional {"absorber": w, "parasite": w, "predator": w}
        weights for the founding population; None draws fully random genomes.
        rules: optional Rules overriding the balance knobs for this world.
        record_lineage: keep self.lineage, a list of birth and death records
        (see record_birth) for phylogenies and lineage plots."""
        self.width = int(width)
        self.height = int(height)
        self.seed = seed
        self.rng = random.Random(seed)
        self.max_population = max_population
        self.strategy_mutation = strategy_mutation
        self.rules = rules if rules is not None else Rules()
        self.repro_chance = self.rules.repro_chance
        # cumulative tallies for analysis: ("eat"|"steal", actor, victim, kin)
        # and ("death", cause, strategy)
        self.stats = collections.Counter()
        # grazing state: field cell -> light reserve (missing = 1.0), and this
        # tick's harvest per cell
        self.reserve = {}
        self.harvest = {}
        self.carcasses = []
        self.carcass_grid = SpatialGrid()
        self.emitters = [
            Emitter(self.rng.randint(60, self.width - 60),
                    self.rng.randint(60, self.height - 60), self.rng)
            for _ in range(num_emitters)
        ]
        self.rocks = self._place_rocks()
        for e in self.emitters:
            e.apply_season(self.rules, 0)
        self.organisms = [
            Organism(self.rng.randint(30, self.width - 30),
                     self.rng.randint(30, self.height - 30), self.rng,
                     self._founder_genes(strategy_mix))
            for _ in range(start_population)
        ]
        if self.rocks:
            for o in self.organisms:
                o.x, o.y = push_out(o.x, o.y, self.rocks)
        if self.rules.kin_by == "marker":
            for o in self.organisms:
                o.kin_dist = KIN_MARKER_DIST
        self.grid = SpatialGrid()
        self.total_births = 0
        self.tick = 0
        self.events = []
        self.field = self._build_field()
        if self.rules.lifespan is not None:
            for o in self.organisms:
                o.max_age = self.rules.draw_max_age(o.strategy, self.rng)
        self.lineage = [] if record_lineage else None
        if record_lineage:
            for o in self.organisms:
                self.record_birth(o)

    def _place_rocks(self):
        """Scatter rules.num_rocks rocks, clear of the emitters and each other."""
        rocks = []
        lo, hi = self.rules.rock_radius
        for _ in range(self.rules.num_rocks):
            for _attempt in range(50):
                r = self.rng.uniform(lo, hi)
                x = self.rng.uniform(r + 10, max(r + 10, self.width - r - 10))
                y = self.rng.uniform(r + 10, max(r + 10, self.height - r - 10))
                if all(math.hypot(x - e.x, y - e.y) > r + 25 for e in self.emitters) and \
                        all(math.hypot(x - k.x, y - k.y) > r + k.r + 4 for k in rocks):
                    rocks.append(Rock(x, y, r))
                    break
        return rocks

    def _build_field(self):
        r = self.rules
        return RadiationField(self.width, self.height, self.emitters, self.organisms,
                              self.grid, self.rocks, r.rock_shade,
                              r.tail_strength, r.tail_range, r.ambient_light)

    def leave_carcass(self, x, y, energy):
        if energy >= CARCASS_MIN:
            self.carcasses.append(Carcass(x, y, energy))

    def record_birth(self, o):
        """("birth", tick, uid, parent_uid, family, generation, genes tuple,
        mate_uid); founders have parent_uid None and tick 0, and asexual
        births have mate_uid None."""
        self.lineage.append(("birth", self.tick, o.uid, o.parent_uid, o.family,
                             o.generation, o.genes.as_tuple(), o.mate_uid))

    def save(self, path):
        """Write a checkpoint. World.load(path) resumes it exactly: the same
        subsequent steps give the same organisms and events."""
        with open(path, "wb") as f:
            pickle.dump((1, _ids.next_uid, self), f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            version, next_uid, world = pickle.load(f)
        if version != 1:
            raise ValueError("unsupported checkpoint version %r" % (version,))
        _ids.ensure_above(next_uid - 1)
        return world

    def _founder_genes(self, mix):
        if not mix:
            return Gene.random(self.rng)
        names = [k for k in STRATEGIES if mix.get(k, 0) > 0]
        if not names:
            return Gene.random(self.rng)
        strategy = self.rng.choices(names, weights=[mix[k] for k in names])[0]
        return Gene.random_specialist(self.rng, strategy)

    def step(self):
        """Advance one tick. self.events then lists what happened during it:
        ("steal", x, y, vx, vy), ("eat", x, y, px, py) and
        ("death", x, y, cause, strategy)."""
        self.tick += 1
        self.events = []
        for e in self.emitters:
            e.advance(self)
        if self.carcasses:
            keep = 1.0 - self.rules.carcass_decay
            for c in self.carcasses:
                c.energy *= keep
            self.carcasses = [c for c in self.carcasses if c.energy >= CARCASS_MIN]
            self.carcass_grid.build(self.carcasses)
        self.grid.build(self.organisms)
        self.field = self._build_field()
        before = len(self.organisms)
        for o in list(self.organisms):
            if not o.alive:
                continue
            o.update(self)
        self.total_births += len(self.organisms) - before
        survivors = []
        for o in self.organisms:
            if o.alive:
                survivors.append(o)
            else:
                cause = o.death_cause()
                if self.rules.carcass_fraction and cause != "eaten" and o.energy > 0:
                    self.leave_carcass(o.x, o.y, o.energy * self.rules.carcass_fraction)
                self.events.append(("death", o.x, o.y, cause, o.strategy))
                self.stats[("death", cause, o.strategy)] += 1
                if self.lineage is not None:
                    self.lineage.append(("death", self.tick, o.uid, cause))
        self.organisms = survivors
        if self.rules.depletion_rate:
            self._graze()

    def _graze(self):
        """Apply this tick's harvest to the reserves, then let them regrow."""
        rules = self.rules
        reserve = self.reserve
        for key, h in self.harvest.items():
            reserve[key] = max(RESERVE_FLOOR, reserve.get(key, 1.0) - rules.depletion_rate * h)
        self.harvest = {}
        full = []
        for key, v in reserve.items():
            v += rules.regrowth_rate * (1.0 - v)
            if v > 0.999:
                full.append(key)
            else:
                reserve[key] = v
        for key in full:
            del reserve[key]

    @property
    def generation(self):
        return max((o.generation for o in self.organisms), default=0)
