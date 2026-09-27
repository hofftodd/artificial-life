"""Core artificial life simulation logic (pure python, no rendering).

All randomness flows through a single random.Random instance owned by World
so a given seed always produces an identical simulation.
"""
import itertools
import math
import random

# --- world / emitter constants ---
EMITTER_RANGE = 120
RADIATION_ENERGY = 0.2
RADIATION_DANGER = 0.12
LETHAL_DISTANCE = EMITTER_RANGE * (1.0 - RADIATION_DANGER / RADIATION_ENERGY)
OPTIMAL_DISTANCE = EMITTER_RANGE * (1.0 - (RADIATION_DANGER / math.sqrt(3.0)) / RADIATION_ENERGY)

# --- metabolism ---
MOTION_COST = 0.005
SENSE_COST = 0.002
REPRO_ENERGY = 7.0
REPRO_CHANCE = 0.01
ENERGY_CAP = 12.0

# --- populations ---
NUM_EMITTERS = 3
START_POPULATION = 40
MAX_POPULATION = 600

# --- predation / theft ---
PREY_RANGE = 12
STEAL_RATE = 0.08
EAT_GAIN_CAP = 1.5
HUNT_COOLDOWN = 24
STRATEGY_COST = 0.02
WEAK_PREY_ENERGY = REPRO_ENERGY  # heaviest prey a pure predator can overpower

# --- strategy trade-offs ---
ABSORB_MAX = 2.0            # absorption_efficiency of a pure absorber
STEAL_MAX = 1.0             # stealing_ability of a pure parasite
EAT_MAX = 1.0               # eating_ability of a pure predator
ABSORB_MOVE_TRADEOFF = 0.75  # a pure absorber moves at 25% of movement_ability
STRATEGY_MUTATION = 0.1
STRATEGIES = ("absorber", "parasite", "predator")

# --- social genes ---
KIN_SPACING = 10             # communal organisms stop approaching kin this close
PROTECTION_MAX = 800         # upper bound on offspring_protection (ticks)

# --- shading ---
SHADE_FACTOR = 0.6
SHADING_RADIUS = 7
FIELD_CELL = 20
BEAM_STEP = 10


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def spectral_match(a, b):
    return 1.0 - abs(a - b) / 99.0


def radiation_effect(intensity, match, efficiency):
    """Net energy gained (or lost, when intensity exceeds RADIATION_DANGER)."""
    return intensity * match * efficiency * (1.0 - (intensity / RADIATION_DANGER) ** 2)


class Gene:
    """Heritable traits.

    absorption, parasitism and predation are shares of a single strategy
    budget and always sum to 1: drifting toward one strategy necessarily
    weakens the other two. A generalist (~1/3 each) is weak at everything;
    nothing can be strong at all three. Absorption also slows the organism
    (see speed), so committed absorbers are sessile and hunters are fast.
    """

    def __init__(self, absorption_spectrum, absorption, parasitism, predation,
                 movement_ability, radiation_sensing, organism_sensing,
                 kin_affinity=0.0, offspring_protection=0):
        self.absorption_spectrum = absorption_spectrum
        total = absorption + parasitism + predation
        if total <= 0:
            absorption, parasitism, predation, total = 1.0, 0.0, 0.0, 1.0
        self.absorption = absorption / total
        self.parasitism = parasitism / total
        self.predation = predation / total
        self.movement_ability = movement_ability
        self.radiation_sensing = radiation_sensing
        self.organism_sensing = organism_sensing
        # communalism: pull toward the nearest member of the same family
        self.kin_affinity = kin_affinity
        # ticks during which a predator won't eat its own children
        self.offspring_protection = offspring_protection

    @classmethod
    def random(cls, rng):
        return cls(
            rng.randint(1, 100),
            rng.uniform(0.0, 1.0),
            rng.uniform(0.0, 1.0) if rng.random() < 0.2 else 0.0,
            rng.uniform(0.0, 1.0) if rng.random() < 0.2 else 0.0,
            rng.uniform(0.5, 2.0),
            rng.uniform(0.5, 2.0),
            rng.uniform(0.5, 2.0),
            rng.uniform(0.0, 0.5),
            rng.randint(0, PROTECTION_MAX // 2),
        )

    @classmethod
    def random_specialist(cls, rng, strategy):
        """A random genome whose dominant share is the given strategy."""
        g = cls.random(rng)
        main = rng.uniform(0.6, 1.0)
        rest = 1.0 - main
        split = rng.random()
        others = [k for k in STRATEGIES if k != strategy]
        shares = {strategy: main, others[0]: rest * split, others[1]: rest * (1 - split)}
        g.absorption = shares["absorber"]
        g.parasitism = shares["parasite"]
        g.predation = shares["predator"]
        return g

    def mutated(self, rng, strategy_sigma=STRATEGY_MUTATION):
        # the constructor renormalizes, so a gain in one share is paid for
        # proportionally by the other two
        return Gene(
            int(clamp(self.absorption_spectrum + rng.gauss(0, 8), 1, 100)),
            clamp(self.absorption + rng.gauss(0, strategy_sigma), 0.0, 1.0),
            clamp(self.parasitism + rng.gauss(0, strategy_sigma), 0.0, 1.0),
            clamp(self.predation + rng.gauss(0, strategy_sigma), 0.0, 1.0),
            clamp(self.movement_ability + rng.gauss(0, 0.15), 0.2, 2.5),
            clamp(self.radiation_sensing + rng.gauss(0, 0.1), 0.3, 3.0),
            clamp(self.organism_sensing + rng.gauss(0, 0.1), 0.3, 3.0),
            clamp(self.kin_affinity + rng.gauss(0, 0.08), 0.0, 1.0),
            int(clamp(self.offspring_protection + rng.gauss(0, 40), 0, PROTECTION_MAX)),
        )

    @property
    def absorption_efficiency(self):
        return ABSORB_MAX * self.absorption

    @property
    def stealing_ability(self):
        return STEAL_MAX * self.parasitism

    @property
    def eating_ability(self):
        return EAT_MAX * self.predation

    @property
    def speed(self):
        return self.movement_ability * (1.0 - ABSORB_MOVE_TRADEOFF * self.absorption)

    def strategy(self):
        """Behavior follows the dominant share; ties favor absorber, then predator."""
        if self.predation > self.absorption and self.predation >= self.parasitism:
            return "predator"
        if self.parasitism > self.absorption and self.parasitism > self.predation:
            return "parasite"
        return "absorber"

    def as_tuple(self):
        return (
            self.absorption_spectrum,
            self.absorption,
            self.parasitism,
            self.predation,
            self.movement_ability,
            self.radiation_sensing,
            self.organism_sensing,
            self.kin_affinity,
            self.offspring_protection,
        )


class Emitter:
    def __init__(self, x, y, rng, spectrum=None):
        self.x = float(x)
        self.y = float(y)
        self.spectrum = spectrum if spectrum is not None else rng.randint(1, 100)
        self.phase = rng.uniform(0, math.pi * 2)

    def radiation_at(self, x, y):
        d = math.hypot(x - self.x, y - self.y)
        if d < EMITTER_RANGE:
            return RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE)
        return 0.0


class SpatialGrid:
    def __init__(self, cell_size=50):
        self.cell = cell_size
        self.buckets = {}

    def build(self, organisms):
        self.buckets.clear()
        for o in organisms:
            key = (int(o.x // self.cell), int(o.y // self.cell))
            self.buckets.setdefault(key, []).append(o)

    def query(self, x, y, r, exclude=None):
        cx, cy = int(x // self.cell), int(y // self.cell)
        span = int(r // self.cell) + 1
        out = []
        for i in range(cx - span, cx + span + 1):
            for j in range(cy - span, cy + span + 1):
                for o in self.buckets.get((i, j), ()):
                    if o is not exclude:
                        out.append(o)
        return out


class RadiationField:
    """Precomputed, shading-aware radiation intensity per field cell, per emitter."""

    def __init__(self, width, height, emitters, organisms, grid):
        self.cells_x = max(1, width // FIELD_CELL)
        self.cells_y = max(1, height // FIELD_CELL)
        self.by_emitter = []
        # organisms in the same cell compete for its photons in proportion to
        # how much of their strategy budget goes to absorption
        self.demand = {}
        for o in organisms:
            if not o.dead and o.genes.absorption > 0:
                key = (int(o.x // FIELD_CELL), int(o.y // FIELD_CELL))
                self.demand[key] = self.demand.get(key, 0.0) + o.genes.absorption
        absorbers = [o for o in organisms if not o.dead and o.strategy == "absorber"]
        for e in emitters:
            field = {}
            x0 = max(0, int((e.x - EMITTER_RANGE) // FIELD_CELL))
            x1 = min(self.cells_x - 1, int((e.x + EMITTER_RANGE) // FIELD_CELL))
            y0 = max(0, int((e.y - EMITTER_RANGE) // FIELD_CELL))
            y1 = min(self.cells_y - 1, int((e.y + EMITTER_RANGE) // FIELD_CELL))
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    px = (cx + 0.5) * FIELD_CELL
                    py = (cy + 0.5) * FIELD_CELL
                    raw = e.radiation_at(px, py)
                    if raw <= 0:
                        continue
                    if absorbers:
                        n = self._count_blockers(e, px, py, absorbers, grid)
                        if n:
                            raw *= SHADE_FACTOR ** n
                    field[(cx, cy)] = raw
            self.by_emitter.append(field)

    @staticmethod
    def _count_blockers(e, tx, ty, absorbers, grid):
        dx, dy = tx - e.x, ty - e.y
        length = math.hypot(dx, dy)
        if length < SHADING_RADIUS * 2:
            return 0
        inv = 1.0 / length
        seen = set()
        count = 0
        for dist in range(BEAM_STEP, int(length) + 1, BEAM_STEP):
            px = e.x + dx * dist * inv
            py = e.y + dy * dist * inv
            for o in grid.query(px, py, SHADING_RADIUS):
                if o in seen:
                    continue
                seen.add(o)
                if o.dead or o.strategy != "absorber":
                    continue
                ox, oy = o.x - e.x, o.y - e.y
                d_from_e = (ox * dx + oy * dy) * inv * inv * length
                if not (SHADING_RADIUS < d_from_e < length - SHADING_RADIUS):
                    continue
                perp = abs(ox * dy - oy * dx) * inv
                if perp < SHADING_RADIUS:
                    count += 1
        return count

    def intensity_at(self, x, y, emitter_index):
        cx = int(x // FIELD_CELL)
        cy = int(y // FIELD_CELL)
        return self.by_emitter[emitter_index].get((cx, cy), 0.0)

    def share_at(self, x, y):
        """Fraction of a cell's harvestable energy one unit of absorption gets."""
        demand = self.demand.get((int(x // FIELD_CELL), int(y // FIELD_CELL)), 0.0)
        return 1.0 / max(1.0, demand)


_ids = itertools.count(1)


class Organism:
    def __init__(self, x, y, rng, genes=None, generation=0, parent=None):
        self.uid = next(_ids)
        self.x = float(x)
        self.y = float(y)
        self.energy = rng.uniform(3.0, 7.0)
        self.age = 0
        self.max_age = rng.randint(800, 2400)
        self.generation = generation
        self.direction = rng.uniform(0, math.pi * 2)
        self.dead = False
        self.hunt_cd = 0
        self.children = 0
        self.genes = genes if genes is not None else Gene.random(rng)
        self.strategy = self.genes.strategy()
        # founders start a family; descendants inherit it
        self.parent_uid = parent.uid if parent is not None else None
        self.family = parent.family if parent is not None else self.uid

    @property
    def alive(self):
        return not self.dead and self.energy > 0 and self.age < self.max_age

    def is_kin(self, other):
        return other.family == self.family

    def spares(self, other):
        """Predators leave their own young alone until they come of age."""
        return other.parent_uid == self.uid and other.age < self.genes.offspring_protection

    def _nearest(self, grid, radius, accept=None):
        best, best_d = None, radius
        for other in grid.query(self.x, self.y, radius):
            if other is self or other.dead:
                continue
            if accept is not None and not accept(other):
                continue
            d = math.hypot(other.x - self.x, other.y - self.y)
            if d <= best_d:
                best, best_d = other, d
        return best

    def _victim_filter(self):
        if self.strategy == "predator":
            return lambda o: not self.spares(o)
        return lambda o: o.strategy != "parasite"

    def _emitter_target(self, world):
        best_e, best_d = None, self.genes.radiation_sensing * 200
        for e in world.emitters:
            d = math.hypot(e.x - self.x, e.y - self.y)
            if d < best_d:
                best_e, best_d = e, d
        if best_e is None:
            return None
        dx, dy = self.x - best_e.x, self.y - best_e.y
        d = math.hypot(dx, dy)
        if d < 1e-9:
            return None
        return (best_e.x + dx / d * OPTIMAL_DISTANCE,
                best_e.y + dy / d * OPTIMAL_DISTANCE)

    def _move(self, world):
        sense = self.genes.organism_sensing * 40
        tx = ty = None
        if self.strategy in ("predator", "parasite"):
            victim = self._nearest(world.grid, sense, self._victim_filter())
            if victim is not None:
                tx, ty = victim.x, victim.y
        if tx is None:
            target = self._emitter_target(world)
            if target is not None:
                tx, ty = target

        vx = vy = 0.0
        if tx is not None:
            d = math.hypot(tx - self.x, ty - self.y)
            if d > 0.5:
                vx, vy = (tx - self.x) / d, (ty - self.y) / d
        # communal organisms drift toward the nearest relative, but stop short
        # of piling onto it
        if self.genes.kin_affinity > 0.05:
            kin = self._nearest(world.grid, sense, self.is_kin)
            if kin is not None:
                d = math.hypot(kin.x - self.x, kin.y - self.y)
                if d > KIN_SPACING:
                    vx += self.genes.kin_affinity * (kin.x - self.x) / d
                    vy += self.genes.kin_affinity * (kin.y - self.y) / d

        if vx or vy:
            self.direction = math.atan2(vy, vx)
        elif tx is not None:
            self.direction += world.rng.gauss(0, 0.1)
        else:
            self.direction += world.rng.gauss(0, 0.4)
        speed = self.genes.speed
        self.x = clamp(self.x + math.cos(self.direction) * speed, 5, world.width - 5)
        self.y = clamp(self.y + math.sin(self.direction) * speed, 5, world.height - 5)

    def _steal(self, world):
        s = self.genes.stealing_ability
        if s <= 0.05:
            return
        for other in world.grid.query(self.x, self.y, PREY_RANGE):
            if other is self or other.dead or other.energy <= 0.1:
                continue
            if other.strategy == "parasite":
                continue
            if math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                amt = other.energy * s * STEAL_RATE
                other.energy -= amt
                self.energy += amt
                world.events.append(("steal", self.x, self.y, other.x, other.y))
                break

    def _eat(self, world):
        if self.genes.eating_ability <= 0.05:
            return
        if self.hunt_cd > 0:
            self.hunt_cd -= 1
            return
        # weak eaters can only finish off prey that is nearly spent already
        max_prey = WEAK_PREY_ENERGY * self.genes.eating_ability
        prey = None
        for other in world.grid.query(self.x, self.y, PREY_RANGE):
            if other is self or other.dead or other.energy >= max_prey:
                continue
            if self.spares(other):
                continue
            if math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                if prey is None or other.energy < prey.energy:
                    prey = other
        if prey is not None:
            prey.dead = True
            self.energy += min(prey.energy, EAT_GAIN_CAP)
            self.hunt_cd = HUNT_COOLDOWN
            world.events.append(("eat", self.x, self.y, prey.x, prey.y))

    def _reproduce(self, world):
        if (self.energy > REPRO_ENERGY
                and len(world.organisms) < world.max_population
                and world.rng.random() < world.repro_chance):
            angle = world.rng.uniform(0, math.pi * 2)
            dist = world.rng.uniform(2, 12)
            nx = clamp(self.x + math.cos(angle) * dist, 5, world.width - 5)
            ny = clamp(self.y + math.sin(angle) * dist, 5, world.height - 5)
            child = Organism(nx, ny, world.rng,
                             self.genes.mutated(world.rng, world.strategy_mutation),
                             self.generation + 1, parent=self)
            world.organisms.append(child)
            self.children += 1
            self.energy -= REPRO_ENERGY

    def update(self, world):
        self.age += 1

        share = world.field.share_at(self.x, self.y)
        for i, e in enumerate(world.emitters):
            rad = world.field.intensity_at(self.x, self.y, i)
            if rad > 0:
                gain = radiation_effect(
                    rad,
                    spectral_match(e.spectrum, self.genes.absorption_spectrum),
                    self.genes.absorption_efficiency,
                )
                # harvest is shared with cell-mates; radiation damage is not
                self.energy += gain * share if gain > 0 else gain

        self._move(world)
        self._steal(world)
        self._eat(world)

        cost = (MOTION_COST * self.genes.speed
                + SENSE_COST * (self.genes.radiation_sensing + self.genes.organism_sensing))
        if self.strategy in ("predator", "parasite"):
            cost += STRATEGY_COST
        self.energy -= cost
        self.energy = min(self.energy, ENERGY_CAP)

        self._reproduce(world)

    def death_cause(self):
        if self.dead:
            return "eaten"
        if self.age >= self.max_age:
            return "old age"
        return "starved"


class World:
    def __init__(self, width=900, height=600, seed=None, num_emitters=NUM_EMITTERS,
                 start_population=START_POPULATION, max_population=MAX_POPULATION,
                 strategy_mutation=STRATEGY_MUTATION, strategy_mix=None):
        """strategy_mix: optional {"absorber": w, "parasite": w, "predator": w}
        weights for the founding population; None draws fully random genomes."""
        self.width = int(width)
        self.height = int(height)
        self.seed = seed
        self.rng = random.Random(seed)
        self.max_population = max_population
        self.repro_chance = REPRO_CHANCE
        self.strategy_mutation = strategy_mutation
        self.emitters = [
            Emitter(self.rng.randint(60, self.width - 60),
                    self.rng.randint(60, self.height - 60), self.rng)
            for _ in range(num_emitters)
        ]
        self.organisms = [
            Organism(self.rng.randint(30, self.width - 30),
                     self.rng.randint(30, self.height - 30), self.rng,
                     self._founder_genes(strategy_mix))
            for _ in range(start_population)
        ]
        self.grid = SpatialGrid()
        self.total_births = 0
        self.tick = 0
        self.events = []
        self.field = RadiationField(self.width, self.height, self.emitters,
                                    self.organisms, self.grid)

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
        self.grid.build(self.organisms)
        self.field = RadiationField(self.width, self.height, self.emitters,
                                    self.organisms, self.grid)
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
                self.events.append(("death", o.x, o.y, o.death_cause(), o.strategy))
        self.organisms = survivors

    @property
    def generation(self):
        return max((o.generation for o in self.organisms), default=0)
