"""
Tuning constants for the model.

Each section mirrors a feature of the simulation; the defaults of the
matching Rules fields (see rules.py) come from these values.
"""
import math

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
# lifespan multiplier per strategy, in STRATEGIES order (absorber, parasite,
# predator): absorbers live longest, predators next, parasites briefly.
# (1.3, 0.6, 1.0) let absorbers pile up to the population cap in the open
# world; these meet the balance target on 12 seeds, static and dynamic+open
LIFESPAN_FACTORS = (1.1, 0.6, 0.9)
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
# lineages spread into it; roaming, patrols, parasites moving on and fleeing
# make every strategy range over it. Wider-ranging hunters find more prey, so
# hunting is made costlier per kill (cooldown 24, upkeep 0.02) to keep them
# from overexploiting it (see DESIGN.md, Spreading out / Ranging)
GENE_FIELDS = 18                 # Gene fields before the brain weights
BRAIN_PRESET = dict(movement="brain")
RULES_PRESET = dict(movement="forage")     # rule-driven movement instead
OPEN_PRESET = dict(ambient_light=0.02, dispersal_max=150.0, roam_rate=0.02, patrol=True,
                   host_min_energy=2.0, flee=True, hunt_cooldown=24, strategy_cost=0.02)

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

# --- evolved controller (Rules.movement = "brain") ---
BRAIN_INPUTS = ("light", "emitter", "prey", "threat", "kin", "stranger", "rock", "carcass",
                "momentum", "noise")
BRAIN_SIZE = 2 * len(BRAIN_INPUTS) + 3   # (base, hunger) per input + 3 throttle weights
BRAIN_CLAMP = 3.0
BRAIN_SIGMA = 0.1            # mutation per weight
BRAIN_SEED_NOISE = 0.2       # founders: seed weights + N(0, this)
FORAGE_NORM = 0.05           # a forage score this high counts as full light
# founders start from today's rule-driven behaviour, written as weights:
# input -> (base, hunger); "throttle" -> (bias, hunger, local light)
BRAIN_SEEDS = {
    "absorber": {"light": (1.0, 0.0), "emitter": (0.3, 0.0), "threat": (-1.0, 0.0),
                 "kin": (0.2, 0.0), "rock": (0.2, 0.0), "momentum": (0.2, 0.0),
                 "noise": (0.1, 0.0), "throttle": (1.0, 0.5, -1.0)},
    "parasite": {"light": (0.4, 0.8), "emitter": (0.2, 0.0), "prey": (1.5, 0.0),
                 "threat": (-0.5, 0.0), "momentum": (0.6, 0.0), "noise": (0.2, 0.0),
                 "throttle": (3.0, 0.0, 0.0)},
    "predator": {"light": (0.3, 1.2), "emitter": (0.2, 0.0), "prey": (2.0, 0.0),
                 "carcass": (0.8, 0.0), "momentum": (0.8, -0.8), "noise": (0.2, 0.0),
                 "throttle": (3.0, 0.0, 0.0)},
}

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
MOVEMENTS = ("forage", "ring", "brain")

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
