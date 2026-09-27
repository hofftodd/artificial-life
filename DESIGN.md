# Design

An artificial life sandbox. Organisms with a small genome live on a 2D plane
and harvest energy from radiation emitters, or steal it (parasitism), or eat
each other (predation). They reproduce asexually with mutation. The three
strategies compete for a single genetic budget, so evolution trades them off
against each other rather than maximising all of them.

## Layout

| File | Role |
|---|---|
| `simcore.py` | The model. Pure Python, no rendering, deterministic per seed. |
| `simulator.py` | Pygame front-end: setup dialog, rendering, event effects, inspector. |
| `legacy/` | Earlier self-contained prototypes (`simulator_simple.py`, `simulator_visual.py`, `simulator_text.py`). They don't use `simcore` and are kept for reference only. |
| `requirements.txt` | `pygame` for the GUI; the model and tools need only the standard library. |
| `tests/` | `unittest` suite covering unit → integration → functional → headless GUI, plus an opt-in slow soak tier. |
| `tools/soak.py` | Multi-seed ecosystem probe: strategy balance, deaths, kin kills, target check. |
| `tools/evolve.py`, `tools/report_template.html` | Headless single run that writes an HTML evolution report, and optionally a lineage file and checkpoint. |

## Determinism

All randomness flows through one `random.Random` owned by `World`
(`World.rng`). The same seed and the same sequence of calls give an identical
simulation, and tests depend on this. New code must draw randomness from
`world.rng`, never from the `random` module.

Organism `uid`s come from a module-level counter. They are unique, but they are
not reproducible across worlds, so never compare them between runs. The model
only ever tests uids for equality, so their values never affect a simulation.

### Checkpoints

`world.save(path)` pickles the whole world, including its RNG state.
`World.load(path)` restores it and moves the uid counter past every id it
uses, so a resumed world continues exactly as the original would have (a test
checks this).

## World and tick

```
World(width, height, seed, num_emitters, start_population, max_population,
      strategy_mutation=0.1, strategy_mix=None)
```

- `strategy_mix` is a set of weights, e.g. `{"absorber": 8, "parasite": 1,
  "predator": 1}`. Each founder picks a strategy by weight and gets
  `Gene.random_specialist` for it (dominant share 0.6–1.0).
- With no mix, founders get `Gene.random`: mostly absorbers, plus about 20%
  with each hunting trait.
- `strategy_mutation=0` freezes the strategy shares across generations. Use
  it to study, for example, a truly predator-free population.

`World.step()` runs one tick:

1. Rebuild the `SpatialGrid` (50px buckets).
2. Rebuild the `RadiationField`. This holds shading-aware intensity per 20px
   cell, per emitter, plus the absorption demand in each cell.
3. Call `update(world)` on every organism alive at the start of the tick, in
   list order. Children are appended and first update on the next tick (age 0).
4. Drop organisms that are no longer alive, recording a death event for each.

After the step, `world.events` holds what happened during it, for the UI:

| Event | Fields |
|---|---|
| `steal` | `x, y, victim_x, victim_y` |
| `eat` | `x, y, prey_x, prey_y` |
| `death` | `x, y, cause, strategy`, where `cause` is `eaten`, `starved` or `old age` |

## Radiation

Each emitter has a spectrum in 1..100. Raw intensity falls off linearly to
zero at `EMITTER_RANGE` (120px).

```
radiation_effect(I, match, eff) = I * match * eff * (1 - (I / RADIATION_DANGER)^2)
match = 1 - |emitter.spectrum - gene.absorption_spectrum| / 99
```

- Gain peaks at `OPTIMAL_DISTANCE` (about 78px), drawn as the green ring.
- Gain is negative inside `LETHAL_DISTANCE` (48px), drawn as the red ring.

### Competition for light (carrying capacity)

Each cell's harvest is shared. An organism's positive gain is multiplied by
`1 / max(1, Σ absorption share of all organisms in its cell)`. Radiation damage
is not shared: everyone in the lethal zone takes the full burn.

This is what makes a population level off. Once cells are crowded, per-capita
gain falls until births balance deaths. Without it, a predator-free
population runs straight into the `max_population` hard cap.

In tests and probes, a single emitter supports roughly 100–200 absorbers. A
sparse group grows toward that level and a crowded one shrinks toward it.

### Shading

Live organisms whose strategy is absorber cast shade along beams traced from
the emitter to each cell centre. Each blocker within 7px of the beam
multiplies that cell's intensity by 0.6, and blockers compound.

## Foraging and light depletion

**Why:** a measurement before this change (3 seeds) found:

- Every organism lived on the optimal ring, 77–80px from an emitter, because
  everyone steered at the same radial ring point.
- Light never ran out, so nothing moved them on.
- The ring became a band of relatives, and about 99% of absorbers had 2+
  relatives within 15px, which made them immune to predators (group defence).
- Predators starved beside them. None died near the emitters.

**Grazing:**

- Each field cell has a light reserve in `world.reserve` (missing = 1.0).
- Harvest is multiplied by the cell's reserve.
- After each tick, a cell loses `depletion_rate` (0.03) × energy harvested
  there (floor 0.05), and every grazed cell regrows `regrowth_rate` (0.01) of
  its shortfall.
- The GUI draws grazed cells dimmer.

**Foraging** (`Rules.movement = "forage"`, the default; `"ring"` restores the
old steering):

- An organism with no victim to chase scores its own cell and 8 compass points
  at `radiation_sensing × FORAGE_RADIUS` (15px). Each cell is scored once.
- Score = expected net radiation gain there, × the cell's reserve, × its
  crowding share (counting itself as joining).
- It heads for the best point if that beats staying by `FORAGE_EPS`.
- If nothing it can sense is lit, it falls back to seeking an emitter's ring.
- Wider sensing now buys a wider search, at its `SENSE_COST`.

**Partial group defence** (`defense_per_kin`, off by default): each relative
near the prey multiplies a kill's success by `(1 - defense_per_kin)`. A failed
attack still costs the predator its cooldown. It's available, but tuning
found it unnecessary once absorbers move.

**Result** (6 seeds, 5000 ticks):

| | Before | After |
|---|---|---|
| Predators | about 1.4% | about 7% |
| Predator kills per seed | 38–145 | 480–950 |
| Distance from the ring | 0.5px | 7–11px |
| Clumping (relatives within 15px) | 7–16 | 5–9 |

With `steal_rate` lowered to 0.05, the default world meets the stable
coexistence target on the 6 standard seeds. On 12 seeds × 3000 ticks, all
strategies survive on all 12, and the only miss is one seed ending at 353
against the (then) 350 ceiling. After the self-shading fix, the ceiling is
80% of the cap, and seed 4 misses it at 489 of 480. `Rules.dynamic()` improved too: populations went
from 27–212 to 70–340, and all strategies survive on 6/6 seeds; parasites
run high there (about 22%).

Heavier grazing (0.2) collapsed the ecosystem. `group_defense=3` weakens
protection (it needs more relatives), and predators then overran the prey.

## Arms race

`Rules.arms_race` is on by default. There are four genes (0..1, founders
0..0.3, mutation σ 0.05), in two opposed pairs, and each carries a cost.

| Pair | Mechanic | Cost |
|---|---|---|
| `armor` vs `bite` | A kill that passes `can_eat` (and any partial-defence roll) succeeds with probability `sigmoid(ARMS_K (6) × (bite − armor) + ARMS_BIAS (1.5))`, which is about 82% when they're equal. A resisted attack still costs the cooldown. | Armour slows movement (`× (1 − 0.5·armor)`) and costs `0.004·armor` per tick. Hunters pay `0.004·bite`. |
| `camouflage` vs `perception` | A hunter only spots a target within `organism_sensing × 40 × clamp(1 − camouflage + perception, 0.2, 1.5)`, so it may search up to 1.5× its base range. This applies to chasing by predators and parasites. | Camouflage cuts light harvest (`× (1 − 0.5·camouflage)`). Perception is charged like sensing (`SENSE_COST`). |

**Balance.** Adding the genes shifts the RNG stream. On 6 seeds × 5000
ticks, the arms-race-off baseline under the new stream lost seed 3 to a
parasite takeover (89% parasites), and parasites averaged 26%. With the arms
race on, the stable-coexistence target was met: 6/6 seeds; 12 seeds × 3000
ticks (populations 91–357, predators 3–10%, parasites 8–17%); and under
`Rules.dynamic()` (6/6 seeds; parasites fell from about 22% to 7–15%). The
strict soak test is now a regular test. In seed 42 over 10k ticks, both sides
escalate: armour 0.16 → about 0.30 and camouflage 0.17 → about 0.23 among
absorbers, and bite 0.14 → 0.6–0.8 and perception 0.12 → 0.2–0.7 among
predators. The report has an
"Arms race" section plotting absorber defences against predator weapons.

## Environment: seasons, drift and rocks

All of this is off in `Rules()` and switched on by `Rules.dynamic()`, which
sets: seasons every 1500 ticks at 30% depth, spectrum drift 0.05/tick,
position drift 0.1px/tick, and 8 rocks. Tools take `--env dynamic`. The GUI
has "Rocks" and "Seasons & drift" rows, with drift on by default there.

Each tick, before the field is rebuilt, `Emitter.advance()` applies:

- **Seasons:** `strength = 1 - pulse_depth × (0.5 - 0.5·cos(2π·tick/pulse_period + phase))`.
  Output multiplies raw intensity, so a dim season also moves the danger and
  optimal zones inward. Organisms still aim for the fixed `OPTIMAL_DISTANCE`
  ring. Each emitter has its own random phase.
- **Spectrum drift:** a Gaussian random walk of `spectrum_drift` per tick,
  clamped to 1..100. This gives adaptation a moving target.
- **Position drift:** a Gaussian random walk of `emitter_drift` px per tick,
  kept `EMITTER_MARGIN` (60px) from the edges and out of rocks.

**Rocks** (`world.rocks`, `num_rocks` of them, radius `rock_radius` 12–30px)
are placed clear of the emitters and of each other.

- **Shade:** a field cell whose beam from an emitter passes through a rock gets
  `× rock_shade` (0.1) per rock. A cell whose centre is inside a rock gets no
  light.
- **Solid:** movement, births and founders are pushed out to the rock's edge.
- **Cover:** an organism within `cover_range` (8px) of a rock's edge can only
  be spotted by chasing hunters within `hidden_detect` (20px). Stealing and
  eating at 12px are unaffected, so cover stops the chase, not the bite.
- **`cover_affinity` gene:** pulls an organism toward the nearest sensed rock
  until it's in cover, in the same way `kin_affinity` pulls toward kin. Cover
  is safer but shadier, so selection decides whether hiding pays.

**Balance impact** (6 seeds, 5000 ticks). Each factor makes the small default
world more volatile. Pulse at 40% depth was the harshest: 4 of 6 seeds ended
at 27–55 organisms. Drift alone nearly wiped out one seed. This is why the
environment is opt-in, and why `Rules.dynamic()` uses a gentler 30% depth.
A 10k-tick dynamic run (seed 42) still reached median generation 123, with
the population's spectrum tracking the drifting emitters.

## Genome (`Gene`)

### Strategy budget

`absorption`, `parasitism` and `predation` are shares that always sum to 1.
The constructor normalises them, and mutation perturbs each share
(σ = `strategy_mutation`) before renormalising. So drifting toward one
strategy weakens the other two. A generalist (about ⅓ each) is weak at
everything, and no organism can be strong at all three.

| Expressed trait | Formula |
|---|---|
| `absorption_efficiency` | `ABSORB_MAX (2.0) × absorption` |
| `stealing_ability` | `STEAL_MAX (1.0) × parasitism` |
| `eating_ability` | `EAT_MAX (1.0) × predation` |
| `speed` | `movement_ability × (1 − ABSORB_MOVE_TRADEOFF (0.75) × absorption)` |

The `speed` line means absorption is inversely tied to movement: a pure
absorber moves at 25% of its `movement_ability`, while pure hunters move at
full speed. Motion cost is charged on actual speed.

**Strategy** is the dominant share. A tie goes to absorber, then to predator.
Strategy decides:

- behaviour (chase victims, or seek the optimal ring)
- whether the organism casts shade
- the `STRATEGY_COST` upkeep that hunters pay
- whether parasites will target it

### Other genes

| Gene | Initial | Mutation σ | Clamp | Effect |
|---|---|---|---|---|
| absorption_spectrum | 1..100 | 8 | 1..100 | spectral match |
| movement_ability | 0.5..2.0 | 0.15 | 0.2..2.5 | base speed |
| radiation_sensing | 0.5..2.0 | 0.1 | 0.3..3.0 | emitter detection ×200px |
| organism_sensing | 0.5..2.0 | 0.1 | 0.3..3.0 | victim/kin detection ×40px |
| kin_affinity | 0..0.5 | 0.08 | 0..1 | communalism: pull toward nearest same-family organism |
| offspring_protection | 0..400 | 40 | 0..800 | ticks a predator spares its own children |
| cover_affinity | 0..0.5 | 0.08 | 0..1 | pull toward the nearest rock (cover from hunters, at the cost of shade) |
| armor, bite, camouflage, perception | 0..0.3 | 0.05 | 0..1 | arms race pairs (see Arms race) |

## Families

- Each founder starts a family, recorded as `family = uid`.
- Children inherit `family` and record `parent_uid`.
- Kin means the same family.

Communal organisms add `kin_affinity ×` a unit vector toward the nearest
relative to their movement heading. They stop approaching within
`KIN_SPACING` (10px), so clumps form without organisms stacking on each other.

Clumping costs absorbers light, because cell-mates split it. Its benefit is
**group defence**: prey with at least `group_defense` (2) relatives within
`GROUP_RADIUS` (15px) can't be eaten.

## Organism update

1. `age += 1`
2. **Absorb:** radiation from every emitter, multiplied by the cell's
   competition share.
3. **Move:**
   - Hunters chase the nearest eligible victim. Predators chase only what
     they could eat on arrival (`Organism.can_eat`). Parasites skip other
     parasites.
   - Otherwise, the organism heads for the nearest sensed emitter's optimal
     ring.
   - A kin pull is added to either heading.
   - Otherwise, it wanders randomly.
4. **Steal:** if `stealing_ability > 0.05`, take
   `energy × stealing × steal_rate` from the first non-parasite within 12px
   that has more than 0.1 energy.
5. **Eat:** if `eating_ability > 0.05`, with a `hunt_cooldown` (12 ticks),
   kill the weakest organism within 12px that `can_eat` allows, and gain
   `min(prey.energy × eat_fraction (0.8), eat_gain_cap (5))`. `can_eat`
   requires all of the following:
   - prey energy below `weak_prey_energy (9) × eating_ability`. Scaling by
     ability matters: without it, an absorber with a 5% predation share
     hunts as well as a real predator.
   - not the eater's own child younger than `offspring_protection`
   - not a predator (`predators_are_prey=False`). Otherwise related
     predators cull each other out.
   - not kin, when the eater is not a predator (`kin_immunity=
     "non_predators"`). Before this rule, about 80% of kills were absorbers
     with a small predation share eating weak relatives in their own crowded
     light cell, which held the population near 50. Real predators may eat
     kin, because they evolve inside absorber families and would otherwise
     have nothing to eat.
   - not defended by `group_defense` relatives (see Families).
6. **Metabolism:**
   - Pay `MOTION_COST × speed + SENSE_COST × (sensing total)`.
   - Hunters also pay `strategy_cost` (0.01).
   - Cap energy at 12.
7. **Reproduce:** if energy > `repro_energy` (3) and the population is below
   `max_population`, there is a `repro_chance` (5%) chance per tick. The child
   spawns 2–12px away with mutated genes and `child_share` (90%) of
   `repro_energy`. The parent pays `repro_energy` and its `children` count
   goes up.

An organism dies when its energy reaches ≤ 0, it hits `max_age` (`lifespan`, 150–450), or
it is eaten.

### Balance rules (`Rules`)

The hunting knobs live in the `Rules` dataclass, one per world
(`World(..., rules=Rules(...))`, stored as `world.rules`):

| Field | Default | Meaning |
|---|---|---|
| `eat_fraction` | 0.8 | share of the prey's energy a kill yields |
| `eat_gain_cap` | 5.0 | most energy a kill yields |
| `hunt_cooldown` | 12 | ticks between kills |
| `strategy_cost` | 0.01 | per-tick upkeep for hunters |
| `weak_prey_energy` | 9.0 | heaviest prey a pure predator can take |
| `steal_rate` | 0.05 | parasite drain per tick, × stealing ability |
| `movement` | `"forage"` | `"forage"` (seek the best nearby light) or `"ring"` (original) |
| `depletion_rate` | 0.03 | reserve lost per unit harvested (0 = light never runs out) |
| `regrowth_rate` | 0.01 | fraction of the missing reserve regrown per tick |
| `defense_per_kin` | 0.0 | partial group defence per relative (0 = off) |
| `arms_race` | True | express armour/bite and camouflage/perception (see Arms race) |
| `kin_immunity` | `"non_predators"` | who won't eat kin: `"none"`, `"non_predators"` or `"all"` |
| `predators_are_prey` | False | whether predators can be eaten |
| `group_defense` | 2 | relatives nearby that make prey safe (0 = off) |
| `repro_energy` | 3.0 | energy a parent must exceed to breed, and pays |
| `child_share` | 0.9 | child's energy as a fraction of `repro_energy`; None = a fresh random 3–7 (original rule) |
| `repro_chance` | 0.05 | per-tick breeding chance once over `repro_energy` (sets `world.repro_chance`) |
| `lifespan` | (150, 450) | `(min, max)` range for `max_age`; None = 800–2400 (original rule) |

**Life-cycle tuning.** The generation time is set by the average age of
parents, not by energy or breeding chance. Under the original rules (lifespan
800–2400, 7-energy births, 1% chance), organisms breed throughout long lives,
so a generation took about 430 ticks.

| Change (10k ticks, 6 seeds) | Median generation |
|---|---|
| original rules | 22–25 |
| 2× breeding chance | 23–26 |
| cheaper children | 27–40, and populations hit the 600 cap |

Short lives with quick, cheap breeding raise this to about 60 generations
per 5000 ticks, with populations of 94–212 and all strategies present.

The defaults come from the module constants of the same name. They were
tuned with `tools/soak.py` toward stable coexistence (see Testing). The
dataclass exists so that alternative regimes, such as a boom/bust preset,
can sit beside the default without code changes.

`world.stats` is a `Counter` of cumulative tallies for analysis:
`("eat" | "steal", actor_strategy, victim_strategy, is_kin)` and
`("death", cause, strategy)`.

### Energy accounting

Emitters are the only source. Stealing moves energy between organisms.
Metabolism, the cap, eating (at most 80% of the prey's energy) and
reproduction all lose it. With no emitters,
total energy never rises and the population goes extinct; a test checks this.

## GUI (`simulator.py`)

`SimulationApp` has two modes.

**Setup** opens at launch and on R. `SetupDialog` sets:

- number of emitters
- starting organisms
- absorber / parasite / predator mix (weights shown as percentages with a
  stacked bar; all zero means fully random genomes)
- world width and height, clamped to the desktop size
- rocks, and "Seasons & drift" on/off (`Rules.dynamic()` when on)

Rocks are drawn as grey discs. Each emitter's halo dims with its seasonal
output, and its label shows the output % and current spectrum.

Use the arrows or the +/- buttons to adjust, and Enter or Start to begin. Esc
returns to the running world, or quits if there isn't one yet. The window is
resized to the world size. `max_population` scales with area (never below
`MAX_POPULATION`, 600).

**Run:** step, draw, 60fps.

How an organism is drawn:

| Visual | Meaning |
|---|---|
| Shape | strategy: circle absorber, diamond parasite, triangle predator |
| Outline colour | strategy (green, violet, red) |
| Fill hue | absorption spectrum |
| Size | energy |
| Vividness | specialisation (how dominant the top strategy share is) |
| Gold dots | offspring so far (fitness), up to 6 |

Event effects fade over a few frames:

- **Parasitism:** violet tether from parasite to victim.
- **Predation:** red strike line and a burst on the prey.
- **Death:** an expanding ring, coloured by cause: red with an ✕ for eaten,
  grey for starved, white for old age.

Effects freeze while the simulation is paused.

The HUD shows per-strategy count, mean energy, mean offspring, and the best
offspring count. Click an organism to open the inspector: energy and age bars,
strategy budget bar, expressed abilities, social genes, and family size, with
relatives outlined. H toggles the legend.

`AIL_AUTOQUIT_FRAMES=N` runs without the dialog and exits after N frames.

## Lineage and reports

`World(..., record_lineage=True)` keeps `world.lineage`, a list of:

- `("birth", tick, uid, parent_uid, family, generation, genes_tuple)`.
  Founders have tick 0 and `parent_uid` None.
- `("death", tick, uid, cause)`

`tools/evolve.py` runs one world and samples it every `--sample-every`
ticks. It writes a self-contained HTML report (`tools/report_template.html`
with the data inlined) showing:

- per-strategy counts
- generations
- an absorption spectrum × time heatmap against the emitters
- a stacked family chart (top 7 founders plus Other)
- trait means with 10–90% bands
- a data table

Spectral mismatch is measured against the emitter giving each organism the
most light at its position. Add `#light` or `#dark` to the report URL to force
a theme.

## Performance

At about 180 organisms, a step takes about 5–7ms in CPython (it was about
30ms). Three changes, all bit-identical to the previous behaviour:

- Shading tests the absorbers near each emitter against each beam directly,
  rather than ray-marching through `SpatialGrid`.
- `SpatialGrid.near()` iterates lazily.
- Neighbour searches check distance before the costly `can_eat` predicate,
  and `can_eat` runs the group-defence scan last.

With the life-cycle defaults, a 10,000-tick run reaches about generation
130 (median; seed 42 reached 133, against 23 under the original rules). At
that depth, evolution shows up in the report:

- spectral mismatch falls from about 28 to about 10
- one founder family takes over
- host–parasite boom/bust cycles appear (parasites peak at about 25 while
  absorbers fall to about 45, then crash while absorbers recover)

## Testing strategy

| Layer | File | What it pins down |
|---|---|---|
| Unit | `test_unit_radiation.py` | radiation curve, derived distances, spectral match |
| Unit | `test_unit_gene.py` | strategy budget, movement trade-off, mutation bounds, classification |
| Unit | `test_unit_social.py` | light competition, parasite rule, offspring protection, communalism, founder mix, events |
| Unit | `test_unit_shading.py` | beam geometry and which organisms shade |
| Unit | `test_unit_arms.py` | kill chance vs bite − armour (statistical), camouflage and perception reach, costs, mutation bounds |
| Unit | `test_unit_foraging.py` | grazing and regrowth, foraging choices and fallback, ring mode, partial defence statistics |
| Unit | `test_unit_environment.py` | rocks (placement, solidity, shadow, cover), `cover_affinity`, seasons, drift bounds, the dynamic preset |
| Unit | `test_unit_organism.py` | migration, lethal zone, stealing, eating, reproduction, death |
| Integration | `test_integration_world.py` | per-tick invariants, determinism, grid, shading in a live world, extinction without energy |
| Functional | `test_functional_ecosystem.py` | the default world persists; selection favours matched spectrum; a predator-free population converges to a carrying capacity |
| End-to-end | `test_e2e_gui.py` | headless pygame: setup dialog (keys and clicks), effects, inspector, pause, reset, run loop |
| Soak (opt-in) | `test_soak.py` | 12 seeds × 3000 ticks: no collapse, absorbers dominate, no incidental kin cannibalism, parasites persist; the full coexistence target is an expected failure |

Run the suite with `python3 -m unittest` from the repo root. It takes about
45s, most of it in the functional tests. The soak tier is skipped unless
`AIL_SLOW=1` is set, and then adds about a minute. `AIL_QUICK=1` skips the
functional tests for a fast inner loop.

### Balance target and `tools/soak.py`

```sh
python3 tools/soak.py                          # seeds 1 2 3 7 42 99, 3000 ticks
python3 tools/soak.py --mix 8:1:1 --ticks 10000 --set group_defense=3
```

It prints per-seed final counts, mean strategy fractions and coefficients of
variation over the last third of the run, plus kills, and checks the
**stable coexistence** target:

- population between 80 and 80% of `MAX_POPULATION` (480) at the end. It
  was 350 until foraging and the self-shading fix raised carrying capacity;
  the ceiling exists to catch populations running into the hard cap.
- all three strategies alive on at least 5/6 of seeds
- mean parasite and predator fractions each 3–15%
- absorbers at least 60%

Current status: populations and parasites are healthy, but predators remain
at about 1–3% and die out on some seeds (see `TODO.md`). Runs of 3000 ticks
are still partly the growth phase, especially in bigger worlds, so use
`--ticks 10000` to judge equilibrium.
