"""
The genome: heritable traits, mutation, crossover and species clustering.
"""
from .brain import seed_brain
from .constants import (ABSORB_MAX, ABSORB_MOVE_TRADEOFF, BRAIN_CLAMP,
                        BRAIN_SIGMA, EAT_MAX, GENE_FIELDS, KIN_MARKER_DIST,
                        PROTECTION_MAX, STEAL_MAX, STRATEGIES, STRATEGY_MUTATION)
from .utils import clamp

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
                 dispersal=0.0, roaming=0.0, wariness=0.0, brain=None):
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
        # evolved movement controller: BRAIN_SIZE weights (see BRAIN_INPUTS),
        # used when Rules.movement == "brain"; None = the strategy's seed
        self.brain = tuple(brain) if brain else None

    @classmethod
    def random(cls, rng):
        g = cls._random_fields(rng)
        g.brain = seed_brain(g.strategy(), rng)
        return g

    @classmethod
    def _random_fields(cls, rng):
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
        g.brain = seed_brain(strategy, rng)   # reseed for the new strategy
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
            brain=(tuple(clamp(w + rng.gauss(0, BRAIN_SIGMA), -BRAIN_CLAMP, BRAIN_CLAMP)
                         for w in self.brain) if self.brain else None),
        )

    @classmethod
    def crossover(cls, a, b, rng):
        """Uniform crossover: each gene from either parent, except the three
        strategy shares, which come together from one parent."""
        ta, tb = a.as_tuple(), b.as_tuple()
        shares = ta[1:4] if rng.random() < 0.5 else tb[1:4]
        values = [x if rng.random() < 0.5 else y
                  for x, y in zip(ta[:GENE_FIELDS], tb[:GENE_FIELDS])]
        values[1:4] = shares
        if a.brain and b.brain:
            brain = [x if rng.random() < 0.5 else y for x, y in zip(a.brain, b.brain)]
        else:
            brain = a.brain or b.brain
        return cls(*values, brain=brain)

    @classmethod
    def from_tuple(cls, values):
        """Inverse of as_tuple(): gene fields, then any brain weights."""
        return cls(*values[:GENE_FIELDS], brain=values[GENE_FIELDS:] or None)

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
        ) + (self.brain or ())


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
