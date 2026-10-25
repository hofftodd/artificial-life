"""
Per-world balance knobs: the Rules dataclass, the named presets and
preset_rules().
"""
import dataclasses

from .constants import (BRAIN_PRESET, COVER_RANGE, CHILD_SHARE, DEPLETION_RATE,
                        DYNAMIC_PRESET, EAT_FRACTION, EAT_GAIN_CAP, GROUP_DEFENSE,
                        HIDDEN_DETECT, HUNT_COOLDOWN, KIN_BY, KIN_IMMUNITY,
                        LIFESPAN, LIFESPAN_FACTORS, MOVEMENTS, OPEN_PRESET,
                        REPRO_CHANCE, REPRO_ENERGY, REGROWTH_RATE, ROCK_RADIUS,
                        ROCK_SHADE, RULES_PRESET, SPECIATION_PRESET, STEAL_RATE,
                        STRATEGIES,
                        STRATEGY_COST, WEAK_PREY_ENERGY)

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
    # per-strategy multipliers on lifespan (absorber, parasite, predator),
    # applied to the strategy at birth
    lifespan_factors: tuple = LIFESPAN_FACTORS
    # grazing: harvesting lowers a cell's light reserve (by depletion_rate x
    # energy harvested), which regrows toward full at regrowth_rate per tick.
    # 0 = light never runs out.
    depletion_rate: float = DEPLETION_RATE
    regrowth_rate: float = REGROWTH_RATE
    # "forage": organisms without a victim to chase move to the best nearby
    # spot (light x reserve x crowding) within radiation_sensing x
    # FORAGE_RADIUS; "ring": everyone heads for the optimal ring (original)
    movement: str = "brain"
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

    def draw_max_age(self, strategy, rng):
        """A max_age from lifespan scaled by the strategy's factor."""
        f = self.lifespan_factors[STRATEGIES.index(strategy)]
        lo, hi = self.lifespan
        return rng.randint(max(1, round(lo * f)), max(1, round(hi * f)))

    @classmethod
    def brain(cls, **overrides):
        """Movement decided by each organism's evolved controller."""
        values = dict(BRAIN_PRESET)
        values.update(overrides)
        return cls(**values)

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
        if len(self.lifespan_factors) != len(STRATEGIES) or \
                any(f <= 0 for f in self.lifespan_factors):
            raise ValueError("lifespan_factors needs %d positive values (%s)"
                             % (len(STRATEGIES), ", ".join(STRATEGIES)))
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


PRESET_VALUES = {"static": {}, "dynamic": DYNAMIC_PRESET, "open": OPEN_PRESET,
                 "speciation": SPECIATION_PRESET, "brain": BRAIN_PRESET,
                 "rules": RULES_PRESET}
# evolved controllers spread absorbers evenly over ambient light and hit the
# population cap at the open world's 0.02; 0.012 meets the balance target on 12 seeds
OPEN_BRAIN_AMBIENT = 0.012


def preset_rules(*names, **overrides):
    """Rules for a combination of named presets (static, dynamic, open,
    speciation, brain), then explicit overrides."""
    values = {}
    for name in names:
        if name not in PRESET_VALUES:
            raise ValueError("unknown preset %r (choose from %s)"
                             % (name, ", ".join(PRESET_VALUES)))
        values.update(PRESET_VALUES[name])
    if "open" in names and values.get("movement", Rules.movement) == "brain":
        values["ambient_light"] = OPEN_BRAIN_AMBIENT
    values.update(overrides)
    return Rules(**values)
