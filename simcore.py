"""Core artificial life simulation logic (pure python, no rendering).

All randomness flows through a single random.Random instance owned by World
so a given seed always produces an identical simulation.
"""
import collections
import dataclasses
import math
import pickle
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
# life cycle: short lives and cheap offspring give ~6x more generations per
# tick than the original 800-2400 lifespan / 7-energy births (tools/soak.py)
REPRO_ENERGY = 3.0
REPRO_CHANCE = 0.05
CHILD_SHARE = 0.9            # child's energy as a fraction of REPRO_ENERGY
LIFESPAN = (150, 450)        # max_age range
ENERGY_CAP = 12.0

# --- populations ---
NUM_EMITTERS = 3
START_POPULATION = 40
MAX_POPULATION = 600

# --- predation / theft ---
PREY_RANGE = 12
STEAL_RATE = 0.05
EAT_FRACTION = 0.8           # share of the prey's energy a kill yields
EAT_GAIN_CAP = 5.0
HUNT_COOLDOWN = 12
STRATEGY_COST = 0.01
WEAK_PREY_ENERGY = 9.0      # heaviest prey a pure predator can overpower
GROUP_DEFENSE = 2           # relatives within GROUP_RADIUS that make prey safe (0 = off)
GROUP_RADIUS = 15
KIN_IMMUNITY = ("none", "non_predators", "all")
DYNAMIC_PRESET = dict(pulse_period=1500, pulse_depth=0.3, spectrum_drift=0.05,
                      emitter_drift=0.1, num_rocks=8)
SPECIATION_PRESET = dict(kin_by="marker", sex_rate=0.5, mate_tolerance=6.0)
# ambient light makes the space between emitters habitable; dispersal lets
# lineages spread into it (see DESIGN.md, Spreading out)
OPEN_PRESET = dict(ambient_light=0.02, dispersal_max=150.0)

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

# --- arms race (Rules.arms_race) ---
ARMS_K = 6.0                 # steepness of the bite-vs-armour kill chance
ARMS_BIAS = 1.5              # kill chance at bite == armour: sigmoid(1.5) ~ 82%
ARMOR_SLOW = 0.5             # full armour halves movement
ARMOR_COST = 0.004           # upkeep per tick at full armour
BITE_COST = 0.004            # hunters' upkeep per tick at full bite
CAMO_HARVEST = 0.5           # full camouflage halves light harvest
DETECT_RANGE = (0.2, 1.5)    # clamp on 1 - target camouflage + own perception
ARMS_GENES = ("armor", "bite", "camouflage", "perception")

# --- spreading out (ambient light, light tails, dispersal, carcasses) ---
AMBIENT_MATCH = 0.6          # diffuse light suits every spectrum moderately
CARCASS_MIN = 0.05           # carcasses with less energy than this vanish

# --- ranging behaviour (roaming, patrols, parasites moving on, fleeing) ---
ROAM_LEG = (40, 120)         # ticks a travel leg lasts
ROAM_POOR = 0.5              # a spot with share x reserve below this is poor
PATROL_MIN_ENERGY = 2.0      # hunters only patrol when they can afford to
FLEE_GAIN = 2.0              # strength of the flee pull at wariness 1

# --- speciation ---
KIN_MARKER_DIST = 4.0        # with kin_by="marker": kin share a marker within this
MATE_RANGE = 25.0            # how far a parent looks for a mate
KIN_BY = ("family", "marker")

# --- foraging and grazing ---
FORAGE_RADIUS = 15.0         # sample distance per unit of radiation_sensing
FORAGE_EPS = 1e-4            # a spot must beat the current one by this to move
RESERVE_FLOOR = 0.05         # a grazed cell never drops below this reserve
DEPLETION_RATE = 0.03        # reserve lost per unit of energy harvested
REGROWTH_RATE = 0.01         # fraction of the missing reserve regained per tick
DEFENSE_CAP = 8              # most relatives that count toward partial defence
_COMPASS = [(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)) for k in range(8)]
MOVEMENTS = ("forage", "ring")

# --- environment (see Rules; all off by default) ---
ROCK_RADIUS = (12, 30)       # rock radius range, px
ROCK_SHADE = 0.1             # light multiplier per rock a beam passes through
COVER_RANGE = 8.0            # within this of a rock's edge an organism is in cover
HIDDEN_DETECT = 20.0         # hunters only spot organisms in cover this close
EMITTER_MARGIN = 60          # emitters stay this far from the world edges

# --- shading ---
SHADE_FACTOR = 0.6
SHADING_RADIUS = 7
FIELD_CELL = 20
BEAM_STEP = 10


@dataclasses.dataclass
class Rules:
    """Per-world balance knobs. Defaults are the module constants; pass a
    modified copy to World to experiment (e.g. with tools/soak.py)."""
    eat_fraction: float = EAT_FRACTION
    eat_gain_cap: float = EAT_GAIN_CAP
    hunt_cooldown: int = HUNT_COOLDOWN
    strategy_cost: float = STRATEGY_COST
    weak_prey_energy: float = WEAK_PREY_ENERGY
    steal_rate: float = STEAL_RATE
    # who refuses to eat its own family: "non_predators" stops absorbers and
    # parasites with a small predation share from culling their relatives,
    # while real predators (which evolve inside absorber families) still hunt
    kin_immunity: str = "non_predators"
    # predators are dangerous prey; mirrors "parasites can't parasitise
    # parasites". Without this, related predators cull each other out.
    predators_are_prey: bool = False
    # a prey refuge: an organism with at least this many relatives within
    # GROUP_RADIUS can't be eaten (0 = off). Stabilises predator-prey
    # dynamics and gives communalism (kin_affinity) a benefit.
    group_defense: int = GROUP_DEFENSE
    # life cycle: a parent needs more than repro_energy to breed and pays it.
    # child_share=None gives the child a fresh random 3-7 energy (the original
    # rule); a number in (0, 1] gives it that fraction of what the parent paid,
    # so a birth never creates energy and cheaper offspring speed generations.
    repro_energy: float = REPRO_ENERGY
    child_share: float = CHILD_SHARE
    repro_chance: float = REPRO_CHANCE
    # (min, max) max_age drawn per organism; None keeps the original 800-2400.
    # Generation time tracks the mean age of parents, so shorter lives are the
    # main lever for more generations per tick.
    lifespan: tuple = LIFESPAN
    # grazing: harvesting lowers a cell's light reserve (by depletion_rate x
    # energy harvested), which regrows toward full at regrowth_rate per tick.
    # 0 = light never runs out.
    depletion_rate: float = DEPLETION_RATE
    regrowth_rate: float = REGROWTH_RATE
    # "forage": organisms without a victim to chase move to the best nearby
    # spot (light x reserve x crowding) within radiation_sensing x
    # FORAGE_RADIUS; "ring": everyone heads for the optimal ring (original)
    movement: str = "forage"
    # partial group defence: each relative of the prey within GROUP_RADIUS
    # multiplies a kill's chance of success by (1 - defense_per_kin); 0 = off
    defense_per_kin: float = 0.0
    # arms race: armour vs bite decides kills (sigmoid(ARMS_K * (bite -
    # armor) + ARMS_BIAS)); camouflage vs perception decides how far away a
    # hunter can spot a target. All four genes carry costs (see DESIGN.md).
    arms_race: bool = True
    # spreading out. ambient_light: a weak spectrum-neutral glow everywhere
    # (intensity units, like RADIATION_ENERGY), so the space between
    # emitters is habitable. tail_strength / tail_range: each emitter also
    # casts a dim, wide cone fading to zero at tail_range. dispersal_max: a
    # child is born up to 12 + dispersal gene x dispersal_max px from its
    # parent (0 = the original 2-12px). carcass_fraction: share of a dead
    # organism's energy (and of the part of prey a predator doesn't eat) left
    # as a carcass that decays by carcass_decay per tick; organisms that can
    # eat scavenge up to scavenge_bite per tick, and predators seek them out.
    ambient_light: float = 0.0
    tail_strength: float = 0.0
    tail_range: float = 240.0
    dispersal_max: float = 0.0
    carcass_fraction: float = 0.0
    carcass_decay: float = 0.01
    scavenge_bite: float = 0.5
    # ranging behaviour. roam_rate: per-tick chance (x roaming gene, tripled
    # on a poor spot) of setting off on a straight travel leg. patrol: hunters
    # with no victim in sight search on legs instead of basking (if energy >
    # PATROL_MIN_ENERGY). host_min_energy: parasites only chase and drain
    # hosts richer than this, and pick the richest in reach (0 = the first
    # host found). flee: non-predators pull away from predators they sense,
    # in proportion to the wariness gene (which costs sensing upkeep).
    roam_rate: float = 0.0
    patrol: bool = False
    host_min_energy: float = 0.0
    flee: bool = False
    # speciation: kin_by "marker" makes kin anyone with a similar heritable
    # marker (families can split); sex_rate is the chance a birth is sexual,
    # with a nearby same-strategy mate whose marker is within mate_tolerance
    # (assortative mating) and a uniform crossover of both genomes
    kin_by: str = "family"
    sex_rate: float = 0.0
    mate_tolerance: float = 6.0
    # environment dynamics: emitters random-walk their spectrum (sd per tick)
    # and position (px sd per tick), and pulse seasonally, dipping to
    # (1 - pulse_depth) of full output once per pulse_period ticks
    spectrum_drift: float = 0.0
    emitter_drift: float = 0.0
    pulse_period: int = 0
    pulse_depth: float = 0.0
    # rocks: solid circles that cast shadows (light x rock_shade per rock on
    # the beam) and give cover: organisms within cover_range of a rock's edge
    # can only be spotted by hunters within hidden_detect
    num_rocks: int = 0
    rock_radius: tuple = ROCK_RADIUS
    rock_shade: float = ROCK_SHADE
    cover_range: float = COVER_RANGE
    hidden_detect: float = HIDDEN_DETECT

    @classmethod
    def open_world(cls, **overrides):
        """Life beyond the emitter discs: ambient light everywhere plus
        heritable long-range dispersal."""
        values = dict(OPEN_PRESET)
        values.update(overrides)
        return cls(**values)

    @classmethod
    def speciation(cls, **overrides):
        """Kin by a drifting marker gene, plus sexual reproduction with
        assortative mating, so lineages can split into species."""
        values = dict(SPECIATION_PRESET)
        values.update(overrides)
        return cls(**values)

    @classmethod
    def dynamic(cls, **overrides):
        """A changing environment: seasons, drifting emitters and rocks.

        Off by default because it makes the small default world volatile
        (populations swing harder and a bad season can wipe out a seed; see
        DESIGN.md), which is the point for evolution experiments but not for
        the balance baseline."""
        values = dict(DYNAMIC_PRESET)
        values.update(overrides)
        return cls(**values)

    def __post_init__(self):
        if self.kin_immunity not in KIN_IMMUNITY:
            raise ValueError("kin_immunity must be one of %s" % (KIN_IMMUNITY,))
        if self.child_share is not None and not 0 < self.child_share <= 1:
            raise ValueError("child_share must be in (0, 1]")
        if self.lifespan is not None:
            lo, hi = self.lifespan
            if not 0 < lo <= hi:
                raise ValueError("lifespan must be (min, max) with 0 < min <= max")
        if not 0 <= self.roam_rate <= 1 or self.host_min_energy < 0:
            raise ValueError("need 0 <= roam_rate <= 1 and host_min_energy >= 0")
        if self.ambient_light < 0 or self.tail_strength < 0 or self.dispersal_max < 0:
            raise ValueError("ambient_light, tail_strength and dispersal_max must be >= 0")
        if self.tail_strength and self.tail_range <= 0:
            raise ValueError("tail_range must be > 0")
        if not 0 <= self.carcass_fraction <= 1 or not 0 < self.carcass_decay <= 1:
            raise ValueError("need 0 <= carcass_fraction <= 1 and 0 < carcass_decay <= 1")
        if self.kin_by not in KIN_BY:
            raise ValueError("kin_by must be one of %s" % (KIN_BY,))
        if not 0 <= self.sex_rate <= 1 or self.mate_tolerance < 0:
            raise ValueError("need 0 <= sex_rate <= 1 and mate_tolerance >= 0")
        if self.movement not in MOVEMENTS:
            raise ValueError("movement must be one of %s" % (MOVEMENTS,))
        if not 0 <= self.defense_per_kin < 1:
            raise ValueError("defense_per_kin must be in [0, 1)")
        if self.depletion_rate < 0 or not 0 < self.regrowth_rate <= 1:
            raise ValueError("need depletion_rate >= 0 and 0 < regrowth_rate <= 1")
        if not 0 <= self.pulse_depth <= 1:
            raise ValueError("pulse_depth must be in [0, 1]")
        if not 0 <= self.rock_shade <= 1:
            raise ValueError("rock_shade must be in [0, 1]")


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
                 kin_affinity=0.0, offspring_protection=0, cover_affinity=0.0,
                 armor=0.0, bite=0.0, camouflage=0.0, perception=0.0, marker=50.0,
                 dispersal=0.0, roaming=0.0, wariness=0.0):
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
        # pull toward the nearest rock: cover from hunters, at the cost of
        # the rock's shadow
        self.cover_affinity = cover_affinity
        # arms race (only expressed when Rules.arms_race is on)
        self.armor = armor
        self.bite = bite
        self.camouflage = camouflage
        self.perception = perception
        # neutral heritable tag, used for kin recognition and mate choice
        # when Rules.kin_by == "marker"
        self.marker = marker
        # how far children are born from their parent (Rules.dispersal_max)
        self.dispersal = dispersal
        # tendency to set off on travel legs (Rules.roam_rate)
        self.roaming = roaming
        # how hard it runs from predators it senses (Rules.flee)
        self.wariness = wariness

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
            rng.uniform(0.0, 0.5),
            rng.uniform(0.0, 0.3),
            rng.uniform(0.0, 0.3),
            rng.uniform(0.0, 0.3),
            rng.uniform(0.0, 0.3),
            rng.uniform(1.0, 100.0),
            rng.uniform(0.0, 0.3),
            rng.uniform(0.0, 0.3),
            rng.uniform(0.0, 0.3),
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
            clamp(self.cover_affinity + rng.gauss(0, 0.08), 0.0, 1.0),
            clamp(self.armor + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.bite + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.camouflage + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.perception + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.marker + rng.gauss(0, 1.5), 1.0, 100.0),
            clamp(self.dispersal + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.roaming + rng.gauss(0, 0.05), 0.0, 1.0),
            clamp(self.wariness + rng.gauss(0, 0.05), 0.0, 1.0),
        )

    @classmethod
    def crossover(cls, a, b, rng):
        """Uniform crossover: each gene from either parent, except the three
        strategy shares, which come together from one parent."""
        ta, tb = a.as_tuple(), b.as_tuple()
        shares = ta[1:4] if rng.random() < 0.5 else tb[1:4]
        values = [x if rng.random() < 0.5 else y for x, y in zip(ta, tb)]
        values[1:4] = shares
        return cls(*values)

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
            self.cover_affinity,
            self.armor,
            self.bite,
            self.camouflage,
            self.perception,
            self.marker,
            self.dispersal,
            self.roaming,
            self.wariness,
        )


def species_clusters(markers, gap=2 * KIN_MARKER_DIST, min_size=3):
    """Split markers into clusters wherever sorted neighbours are more than
    `gap` apart; return clusters with at least `min_size` members, each as a
    sorted list."""
    clusters, current = [], []
    for m in sorted(markers):
        if current and m - current[-1] > gap:
            clusters.append(current)
            current = []
        current.append(m)
    if current:
        clusters.append(current)
    return [c for c in clusters if len(c) >= min_size]


class Carcass:
    """Energy left where an organism died, for scavengers."""

    def __init__(self, x, y, energy):
        self.x = float(x)
        self.y = float(y)
        self.energy = energy


class Rock:
    """A solid circle: casts a shadow, can't be entered, gives cover."""

    def __init__(self, x, y, r):
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)


def push_out(x, y, rocks, margin=0.0):
    """Move a point that ended up inside a rock to just outside its edge."""
    for rock in rocks:
        dx, dy = x - rock.x, y - rock.y
        d = math.hypot(dx, dy)
        limit = rock.r + margin
        if d < limit:
            if d < 1e-9:
                dx, dy, d = 1.0, 0.0, 1.0
            x = rock.x + dx / d * limit
            y = rock.y + dy / d * limit
    return x, y


def in_cover(x, y, rocks, cover_range):
    for rock in rocks:
        if math.hypot(x - rock.x, y - rock.y) - rock.r <= cover_range:
            return True
    return False


class Emitter:
    def __init__(self, x, y, rng, spectrum=None):
        self.x = float(x)
        self.y = float(y)
        self.spectrum = spectrum if spectrum is not None else rng.randint(1, 100)
        self.phase = rng.uniform(0, math.pi * 2)
        self.strength = 1.0      # seasonal output multiplier (see advance)

    def radiation_at(self, x, y, tail_strength=0.0, tail_range=0.0):
        d = math.hypot(x - self.x, y - self.y)
        if not tail_strength:
            if d < EMITTER_RANGE:
                return RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE) * self.strength
            return 0.0
        # a dim, wide second cone on top of the core
        v = RADIATION_ENERGY * (1.0 - d / EMITTER_RANGE) if d < EMITTER_RANGE else 0.0
        if d < tail_range:
            v += tail_strength * (1.0 - d / tail_range)
        return v * self.strength

    def apply_season(self, rules, tick):
        if rules.pulse_period and rules.pulse_depth:
            season = 0.5 - 0.5 * math.cos(2 * math.pi * tick / rules.pulse_period + self.phase)
            self.strength = 1.0 - rules.pulse_depth * season

    def advance(self, world):
        """Apply one tick of the world's emitter dynamics (pulse, drift)."""
        rules = world.rules
        self.apply_season(rules, world.tick)
        if rules.spectrum_drift:
            self.spectrum = clamp(self.spectrum + world.rng.gauss(0, rules.spectrum_drift),
                                  1, 100)
        if rules.emitter_drift:
            x = self.x + world.rng.gauss(0, rules.emitter_drift)
            y = self.y + world.rng.gauss(0, rules.emitter_drift)
            x, y = push_out(x, y, world.rocks, margin=5)
            self.x = clamp(x, EMITTER_MARGIN, world.width - EMITTER_MARGIN)
            self.y = clamp(y, EMITTER_MARGIN, world.height - EMITTER_MARGIN)


class SpatialGrid:
    def __init__(self, cell_size=50):
        self.cell = cell_size
        self.buckets = {}

    def build(self, organisms):
        self.buckets.clear()
        for o in organisms:
            key = (int(o.x // self.cell), int(o.y // self.cell))
            self.buckets.setdefault(key, []).append(o)

    def near(self, x, y, r):
        """Yield candidates from the buckets covering radius r (a superset of
        what's actually within r), lazily and in a fixed order."""
        cx, cy = int(x // self.cell), int(y // self.cell)
        span = int(r // self.cell) + 1
        buckets = self.buckets
        for i in range(cx - span, cx + span + 1):
            for j in range(cy - span, cy + span + 1):
                bucket = buckets.get((i, j))
                if bucket:
                    yield from bucket

    def query(self, x, y, r, exclude=None):
        return [o for o in self.near(x, y, r) if o is not exclude]


class RadiationField:
    """Precomputed, shading-aware radiation intensity per field cell, per emitter."""

    def __init__(self, width, height, emitters, organisms, grid, rocks=(),
                 rock_shade=ROCK_SHADE, tail_strength=0.0, tail_range=0.0, ambient=0.0):
        # spectrum-neutral light everywhere; not shaded, not per cell
        self.ambient = ambient
        extent = max(EMITTER_RANGE, tail_range) if tail_strength else EMITTER_RANGE
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
        reach = extent + SHADING_RADIUS
        for e in emitters:
            # only absorbers near this emitter can sit on one of its beams;
            # offsets are computed exactly as the per-beam test expects
            near = []
            for o in absorbers:
                ox, oy = o.x - e.x, o.y - e.y
                if abs(ox) <= reach and abs(oy) <= reach:
                    near.append((ox, oy, (int(o.x // FIELD_CELL), int(o.y // FIELD_CELL))))
            near_rocks = [(r.x - e.x, r.y - e.y, r.r) for r in rocks
                          if math.hypot(r.x - e.x, r.y - e.y) < extent + r.r]
            field = {}
            x0 = max(0, int((e.x - extent) // FIELD_CELL))
            x1 = min(self.cells_x - 1, int((e.x + extent) // FIELD_CELL))
            y0 = max(0, int((e.y - extent) // FIELD_CELL))
            y1 = min(self.cells_y - 1, int((e.y + extent) // FIELD_CELL))
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    px = (cx + 0.5) * FIELD_CELL
                    py = (cy + 0.5) * FIELD_CELL
                    raw = e.radiation_at(px, py, tail_strength, tail_range)
                    if raw <= 0:
                        continue
                    if near_rocks:
                        n = self._count_rocks(e, px, py, near_rocks)
                        if n < 0:
                            continue      # the cell centre is inside a rock
                        if n:
                            raw *= rock_shade ** n
                    if near:
                        n = self._count_blockers(e, px, py, near, (cx, cy))
                        if n:
                            raw *= SHADE_FACTOR ** n
                    field[(cx, cy)] = raw
            self.by_emitter.append(field)

    @staticmethod
    def _count_rocks(e, tx, ty, rocks):
        """Rocks the beam from the emitter to (tx, ty) passes through, or -1
        if (tx, ty) is itself inside a rock. Rocks are (dx, dy, r) offsets
        from the emitter."""
        dx, dy = tx - e.x, ty - e.y
        len2 = dx * dx + dy * dy
        count = 0
        for rx, ry, r in rocks:
            if (rx - dx) ** 2 + (ry - dy) ** 2 < r * r:
                return -1
            t = (rx * dx + ry * dy) / len2 if len2 else 0.0
            t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            if (rx - dx * t) ** 2 + (ry - dy * t) ** 2 < r * r:
                count += 1
        return count

    @staticmethod
    def _count_blockers(e, tx, ty, offsets, target_key=None):
        """Absorbers (given as (dx, dy, cell) offsets from the emitter) within
        SHADING_RADIUS of the beam from the emitter to (tx, ty), excluding its
        ends. Absorbers in the target cell itself don't count: they harvest
        that cell's light rather than shading it.

        Tests every candidate directly rather than ray-marching through the
        spatial grid; the result is identical, since the march only ever
        gathered candidates for this same test.
        """
        dx, dy = tx - e.x, ty - e.y
        length = math.hypot(dx, dy)
        if length < SHADING_RADIUS * 2:
            return 0
        inv = 1.0 / length
        lo, hi = SHADING_RADIUS, length - SHADING_RADIUS
        count = 0
        for ox, oy, key in offsets:
            if key == target_key:
                continue
            d_from_e = (ox * dx + oy * dy) * inv * inv * length
            if not (lo < d_from_e < hi):
                continue
            if abs(ox * dy - oy * dx) * inv < SHADING_RADIUS:
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


class _UidCounter:
    """Process-wide organism id source. Restoring a checkpoint moves it past
    every id the saved world uses, so new organisms never collide."""

    def __init__(self):
        self.next_uid = 1

    def __next__(self):
        uid = self.next_uid
        self.next_uid += 1
        return uid

    def ensure_above(self, uid):
        self.next_uid = max(self.next_uid, uid + 1)


_ids = _UidCounter()


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
        # None = kin means same family; a number = kin means markers within it
        self.kin_dist = parent.kin_dist if parent is not None else None
        self.mate_uid = None
        self.leg = 0                 # ticks left on a travel leg
        self.leg_dir = 0.0

    @property
    def alive(self):
        return not self.dead and self.energy > 0 and self.age < self.max_age

    def is_kin(self, other):
        if self.kin_dist is None:
            return other.family == self.family
        return abs(other.genes.marker - self.genes.marker) <= self.kin_dist

    def _find_mate(self, world):
        """Nearest same-strategy organism within MATE_RANGE whose marker is
        within the world's mate_tolerance (assortative mating)."""
        tolerance = world.rules.mate_tolerance
        marker = self.genes.marker
        return self._nearest(world.grid, MATE_RANGE,
                             lambda o: o.strategy == self.strategy and o.alive
                             and abs(o.genes.marker - marker) <= tolerance)

    def spares(self, other):
        """Predators leave their own young alone until they come of age."""
        return other.parent_uid == self.uid and other.age < self.genes.offspring_protection

    def can_eat(self, other, world):
        """Whether this organism could overpower and eat `other` right now."""
        rules = world.rules
        if other.energy >= rules.weak_prey_energy * self.genes.eating_ability:
            return False
        if other.strategy == "predator" and not rules.predators_are_prey:
            return False
        if self.spares(other):
            return False
        if rules.kin_immunity == "all" or (
                rules.kin_immunity == "non_predators" and self.strategy != "predator"):
            if self.is_kin(other):
                return False
        # the neighbour scan is the expensive check, so it goes last
        return not (rules.group_defense
                    and self._defended(other, rules.group_defense, world.grid))

    def _defended(self, prey, needed, grid):
        """Whether `prey` has at least `needed` relatives close enough to fend
        off an attack."""
        return self._guards(prey, grid, needed) >= needed

    def _guards(self, prey, grid, cap):
        """Relatives of `prey` (other than this attacker) within GROUP_RADIUS,
        counted up to `cap`."""
        count = 0
        for o in grid.near(prey.x, prey.y, GROUP_RADIUS):
            if o is prey or o is self or o.dead or not prey.is_kin(o):
                continue
            if math.hypot(o.x - prey.x, o.y - prey.y) <= GROUP_RADIUS:
                count += 1
                if count >= cap:
                    break
        return count

    def _nearest(self, grid, radius, accept=None):
        best, best_d = None, radius
        for other in grid.near(self.x, self.y, radius):
            if other is self or other.dead:
                continue
            d = math.hypot(other.x - self.x, other.y - self.y)
            # distance first: accept() can be expensive (see can_eat)
            if d > best_d:
                continue
            if accept is not None and not accept(other):
                continue
            best, best_d = other, d
        return best

    def _victim_filter(self, world):
        if self.strategy == "predator":
            # only chase what could actually be eaten on arrival
            base = lambda o: self.can_eat(o, world)  # noqa: E731
        elif world.rules.host_min_energy:
            floor = world.rules.host_min_energy
            base = lambda o: o.strategy != "parasite" and o.energy > floor  # noqa: E731
        else:
            base = lambda o: o.strategy != "parasite"  # noqa: E731
        rules = world.rules
        if rules.arms_race:
            sense = self.genes.organism_sensing * 40
            lo, hi = DETECT_RANGE
            perception = self.genes.perception
            inner = base

            def detected(o):
                # camouflage shortens the range a hunter can spot a target at;
                # perception extends it
                reach = sense * clamp(1.0 - o.genes.camouflage + perception, lo, hi)
                if math.hypot(o.x - self.x, o.y - self.y) > reach:
                    return False
                return inner(o)
            base = detected
        if not world.rocks:
            return base
        chase = base

        def visible(o):
            # organisms in cover can only be spotted up close
            if (math.hypot(o.x - self.x, o.y - self.y) > rules.hidden_detect
                    and in_cover(o.x, o.y, world.rocks, rules.cover_range)):
                return False
            return chase(o)
        return visible

    def _forage_score(self, world, key, own_key, matches):
        """Expected net radiation gain per tick if this organism stood in
        field cell `key`, counting grazing and crowding; None where there's no
        light. `matches` are its spectral matches to each emitter."""
        field = world.field
        demand = field.demand.get(key, 0.0)
        if key != own_key:
            demand += self.genes.absorption   # it would join that cell
        share = 1.0 / max(1.0, demand)
        reserve = world.reserve.get(key, 1.0)
        eff = self.genes.absorption_efficiency
        total, lit = 0.0, False
        if field.ambient > 0:
            lit = True
            total += radiation_effect(field.ambient, AMBIENT_MATCH, eff) * share * reserve
        for layer, match in zip(field.by_emitter, matches):
            rad = layer.get(key, 0.0)
            if rad > 0:
                lit = True
                g = radiation_effect(rad, match, eff)
                total += g * share * reserve if g > 0 else g
        return total if lit else None

    def _forage_target(self, world):
        """The best of the current spot and 8 compass points at
        radiation_sensing x FORAGE_RADIUS, or None if none of them is lit.
        Light is per field cell, so each cell is scored once."""
        spectrum = self.genes.absorption_spectrum
        matches = [spectral_match(e.spectrum, spectrum) for e in world.emitters]
        own_key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
        here = self._forage_score(world, own_key, own_key, matches)
        best, best_score = None, here
        seen = {own_key}
        r = self.genes.radiation_sensing * FORAGE_RADIUS
        w, h = world.width, world.height
        for ux, uy in _COMPASS:
            x, y = self.x + ux * r, self.y + uy * r
            if not (0 <= x < w and 0 <= y < h):
                continue
            key = (int(x // FIELD_CELL), int(y // FIELD_CELL))
            if key in seen:
                continue            # same cell, same score: can't win by FORAGE_EPS
            seen.add(key)
            score = self._forage_score(world, key, own_key, matches)
            if score is None:
                continue
            if best_score is None or score > best_score + FORAGE_EPS:
                best, best_score = (x, y), score
        if best is not None:
            return best
        return (self.x, self.y) if here is not None else None

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
        rules = world.rules
        sense = self.genes.organism_sensing * 40
        hunter = self.strategy in ("predator", "parasite")
        tx = ty = None
        heading = None
        if hunter:
            reach = sense * DETECT_RANGE[1] if rules.arms_race else sense
            victim = self._nearest(world.grid, reach, self._victim_filter(world))
            if victim is not None:
                tx, ty = victim.x, victim.y
                self.leg = 0                 # a chase ends any travel leg
            elif self.strategy == "predator" and world.carcasses:
                food = self._nearest_carcass(world, reach)
                if food is not None:
                    tx, ty = food.x, food.y
        if tx is None and self.leg > 0:
            self.leg -= 1
            heading = self.leg_dir
        elif tx is None and self._start_leg(world, hunter):
            heading = self.leg_dir
        elif tx is None:
            target = None
            if rules.movement == "forage":
                target = self._forage_target(world)
            if target is None:
                target = self._emitter_target(world)
            if target is not None:
                tx, ty = target

        vx = vy = 0.0
        if heading is not None:
            vx, vy = math.cos(heading), math.sin(heading)
        elif tx is not None:
            d = math.hypot(tx - self.x, ty - self.y)
            if d > 0.5:
                vx, vy = (tx - self.x) / d, (ty - self.y) / d
        # wary prey run from the nearest predator they sense
        if rules.flee and self.strategy != "predator" and self.genes.wariness > 0.05:
            threat = self._nearest(world.grid, sense, lambda o: o.strategy == "predator")
            if threat is not None:
                d = math.hypot(threat.x - self.x, threat.y - self.y)
                if d > 1e-9:
                    pull = FLEE_GAIN * self.genes.wariness
                    vx -= pull * (threat.x - self.x) / d
                    vy -= pull * (threat.y - self.y) / d
        # communal organisms drift toward the nearest relative, but stop short
        # of piling onto it
        if self.genes.kin_affinity > 0.05:
            kin = self._nearest(world.grid, sense, self.is_kin)
            if kin is not None:
                d = math.hypot(kin.x - self.x, kin.y - self.y)
                if d > KIN_SPACING:
                    vx += self.genes.kin_affinity * (kin.x - self.x) / d
                    vy += self.genes.kin_affinity * (kin.y - self.y) / d
        # cover seekers drift toward the nearest sensed rock until they're
        # within cover range of its edge
        if self.genes.cover_affinity > 0.05 and world.rocks:
            rock, gap = None, sense
            for k in world.rocks:
                g = math.hypot(k.x - self.x, k.y - self.y) - k.r
                if g < gap:
                    rock, gap = k, g
            if rock is not None and gap > COVER_RANGE / 2:
                d = gap + rock.r
                vx += self.genes.cover_affinity * (rock.x - self.x) / d
                vy += self.genes.cover_affinity * (rock.y - self.y) / d

        if vx or vy:
            self.direction = math.atan2(vy, vx)
        elif tx is not None:
            self.direction += world.rng.gauss(0, 0.1)
        else:
            self.direction += world.rng.gauss(0, 0.4)
        speed = self.genes.speed
        if world.rules.arms_race:
            speed *= 1.0 - ARMOR_SLOW * self.genes.armor
        x = clamp(self.x + math.cos(self.direction) * speed, 5, world.width - 5)
        y = clamp(self.y + math.sin(self.direction) * speed, 5, world.height - 5)
        if self.leg > 0:
            # travel legs bounce off the world's edges
            if x <= 5 or x >= world.width - 5:
                self.leg_dir = math.pi - self.leg_dir
            if y <= 5 or y >= world.height - 5:
                self.leg_dir = -self.leg_dir
        if world.rocks:
            x, y = push_out(x, y, world.rocks)
        self.x, self.y = x, y

    def _start_leg(self, world, hunter):
        """Maybe set off on a straight travel leg; returns whether it did."""
        rules = world.rules
        if rules.patrol and hunter and self.energy > PATROL_MIN_ENERGY:
            # patrols keep roughly the current heading, so searches cover ground
            self.leg_dir = self.direction + world.rng.uniform(-1.0, 1.0)
        elif rules.roam_rate and self.genes.roaming > 0.05:
            chance = rules.roam_rate * self.genes.roaming
            key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
            if world.field.share_at(self.x, self.y) * world.reserve.get(key, 1.0) < ROAM_POOR:
                chance *= 3.0
            if world.rng.random() >= chance:
                return False
            self.leg_dir = world.rng.uniform(0.0, 2.0 * math.pi)
        else:
            return False
        self.leg = world.rng.randint(*ROAM_LEG)
        return True

    def _steal(self, world):
        s = self.genes.stealing_ability
        if s <= 0.05:
            return
        floor = world.rules.host_min_energy
        if floor:
            # move-on parasites drain the richest host in reach, and leave
            # hosts that are already poor
            host, best = None, floor
            for other in world.grid.near(self.x, self.y, PREY_RANGE):
                if other is self or other.dead or other.strategy == "parasite":
                    continue
                if other.energy > best and \
                        math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                    host, best = other, other.energy
            if host is not None:
                amt = host.energy * s * world.rules.steal_rate
                host.energy -= amt
                self.energy += amt
                world.events.append(("steal", self.x, self.y, host.x, host.y))
                world.stats[("steal", self.strategy, host.strategy, self.is_kin(host))] += 1
            return
        for other in world.grid.query(self.x, self.y, PREY_RANGE):
            if other is self or other.dead or other.energy <= 0.1:
                continue
            if other.strategy == "parasite":
                continue
            if math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                amt = other.energy * s * world.rules.steal_rate
                other.energy -= amt
                self.energy += amt
                world.events.append(("steal", self.x, self.y, other.x, other.y))
                world.stats[("steal", self.strategy, other.strategy, self.is_kin(other))] += 1
                break

    def _eat(self, world):
        if self.genes.eating_ability <= 0.05:
            return
        if self.hunt_cd > 0:
            self.hunt_cd -= 1
            return
        # weak eaters can only finish off prey that is nearly spent already
        # (see can_eat)
        rules = world.rules
        prey = None
        for other in world.grid.near(self.x, self.y, PREY_RANGE):
            if other is self or other.dead:
                continue
            if math.hypot(other.x - self.x, other.y - self.y) > PREY_RANGE:
                continue
            if (prey is None or other.energy < prey.energy) and self.can_eat(other, world):
                prey = other
        if prey is not None:
            if rules.defense_per_kin:
                n = self._guards(prey, world.grid, DEFENSE_CAP)
                if n and world.rng.random() >= (1.0 - rules.defense_per_kin) ** n:
                    # relatives fended it off; the attack still costs a cooldown
                    self.hunt_cd = rules.hunt_cooldown
                    world.stats[("repelled", self.strategy, prey.strategy)] += 1
                    return
            if rules.arms_race:
                edge = ARMS_K * (self.genes.bite - prey.genes.armor) + ARMS_BIAS
                if world.rng.random() >= 1.0 / (1.0 + math.exp(-edge)):
                    # the prey's armour held; the attack still costs a cooldown
                    self.hunt_cd = rules.hunt_cooldown
                    world.stats[("resisted", self.strategy, prey.strategy)] += 1
                    return
            prey.dead = True
            meal = min(max(prey.energy, 0.0) * rules.eat_fraction, rules.eat_gain_cap)
            self.energy += meal
            if rules.carcass_fraction:
                world.leave_carcass(prey.x, prey.y, (max(prey.energy, 0.0) - meal)
                                    * rules.carcass_fraction)
            self.hunt_cd = rules.hunt_cooldown
            world.events.append(("eat", self.x, self.y, prey.x, prey.y))
            world.stats[("eat", self.strategy, prey.strategy, self.is_kin(prey))] += 1

    def _nearest_carcass(self, world, radius):
        best, best_d = None, radius
        for c in world.carcass_grid.near(self.x, self.y, radius):
            if c.energy <= 0:
                continue
            d = math.hypot(c.x - self.x, c.y - self.y)
            if d <= best_d:
                best, best_d = c, d
        return best

    def _scavenge(self, world):
        """Organisms that can eat take a bite from the nearest carcass."""
        if self.genes.eating_ability <= 0.05:
            return
        c = self._nearest_carcass(world, PREY_RANGE)
        if c is None:
            return
        bite = min(c.energy, world.rules.scavenge_bite)
        c.energy -= bite
        self.energy += bite
        world.stats[("scavenge", self.strategy)] += 1

    def _reproduce(self, world):
        cost = world.rules.repro_energy
        if (self.energy > cost
                and len(world.organisms) < world.max_population
                and world.rng.random() < world.repro_chance):
            angle = world.rng.uniform(0, math.pi * 2)
            dist = world.rng.uniform(2, 12 + self.genes.dispersal * world.rules.dispersal_max)
            nx = clamp(self.x + math.cos(angle) * dist, 5, world.width - 5)
            ny = clamp(self.y + math.sin(angle) * dist, 5, world.height - 5)
            if world.rocks:
                nx, ny = push_out(nx, ny, world.rocks)
            genes, mate = self.genes, None
            if world.rules.sex_rate and world.rng.random() < world.rules.sex_rate:
                mate = self._find_mate(world)
                if mate is not None:
                    genes = Gene.crossover(self.genes, mate.genes, world.rng)
            child = Organism(nx, ny, world.rng,
                             genes.mutated(world.rng, world.strategy_mutation),
                             self.generation + 1, parent=self)
            if mate is not None:
                child.mate_uid = mate.uid
            world.stats[("birth", "sexual" if mate is not None else "asexual")] += 1
            world.organisms.append(child)
            self.children += 1
            if world.rules.lifespan is not None:
                child.max_age = world.rng.randint(*world.rules.lifespan)
            if world.rules.child_share is not None:
                child.energy = cost * world.rules.child_share
            if world.lineage is not None:
                world.record_birth(child)
            self.energy -= cost

    def update(self, world):
        self.age += 1

        share = world.field.share_at(self.x, self.y)
        if world.rules.arms_race and self.genes.camouflage:
            share *= 1.0 - CAMO_HARVEST * self.genes.camouflage
        grazing = world.rules.depletion_rate > 0
        if grazing:
            key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
            share *= world.reserve.get(key, 1.0)
            harvested = 0.0
        for i, e in enumerate(world.emitters):
            rad = world.field.intensity_at(self.x, self.y, i)
            if rad > 0:
                gain = radiation_effect(
                    rad,
                    spectral_match(e.spectrum, self.genes.absorption_spectrum),
                    self.genes.absorption_efficiency,
                )
                # harvest is shared with cell-mates (and limited by the cell's
                # grazed reserve); radiation damage is not
                if gain > 0:
                    self.energy += gain * share
                    if grazing:
                        harvested += gain * share
                else:
                    self.energy += gain
        ambient = world.field.ambient
        if ambient > 0:
            gain = radiation_effect(ambient, AMBIENT_MATCH, self.genes.absorption_efficiency)
            if gain > 0:
                self.energy += gain * share
                if grazing:
                    harvested += gain * share
        if grazing and harvested:
            world.harvest[key] = world.harvest.get(key, 0.0) + harvested

        self._move(world)
        self._steal(world)
        self._eat(world)
        if world.carcasses:
            self._scavenge(world)

        cost = (MOTION_COST * self.genes.speed
                + SENSE_COST * (self.genes.radiation_sensing + self.genes.organism_sensing))
        if self.strategy in ("predator", "parasite"):
            cost += world.rules.strategy_cost
        if world.rules.arms_race:
            g = self.genes
            cost += ARMOR_COST * g.armor + SENSE_COST * g.perception
            if self.strategy in ("predator", "parasite"):
                cost += BITE_COST * g.bite
        if world.rules.flee:
            cost += SENSE_COST * self.genes.wariness
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
                o.max_age = self.rng.randint(*self.rules.lifespan)
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
