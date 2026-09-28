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
      strategy_mutation=0.1, strategy_mix=None, rules=None, record_lineage=False)
```

- `strategy_mix` is a set of weights, e.g. `{"absorber": 8, "parasite": 1,
  "predator": 1}`. Each founder picks a strategy by weight and gets
  `Gene.random_specialist` for it (dominant share 0.6–1.0).
- With no mix, founders get `Gene.random`: mostly absorbers, plus about 20%
  with each hunting trait.
- `strategy_mutation=0` freezes the strategy shares across generations. Use
  it to study, for example, a truly predator-free population.
- `rules` is a `Rules` (see Balance rules); `preset_rules(*names, **overrides)`
  builds one from named presets.
- `record_lineage` keeps `world.lineage` (see Lineage and reports).

At construction, emitters are placed first, then rocks (if any), then
founders, which are pushed out of rocks. Seasons set each emitter's starting
output, and `lifespan` redraws each founder's `max_age`.

`World.step()` runs one tick:

1. Advance each emitter: season, spectrum drift, position drift
   (`Emitter.advance`).
2. Decay carcasses and drop spent ones, then rebuild the carcass grid.
3. Rebuild the `SpatialGrid` (50px buckets) and the `RadiationField`. The
   field holds light per 20px cell per emitter (including light tails, rock
   shadows and absorber shading), the ambient level, and the absorption demand
   in each cell.
4. Call `update(world)` on every organism alive at the start of the tick, in
   list order. Children are appended and first update on the next tick
   (age 0).
5. Drop organisms that are no longer alive. Each death is recorded as an
   event and in `world.stats`, and old-age deaths may leave a carcass.
6. Apply this tick's grazing to the light reserves, then let them regrow.

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

## Spreading out: the open world

**Why:** a measurement (3 seeds, static and dynamic) found that 0% of
organisms ever lived beyond `EMITTER_RANGE` (120px); every strategy stayed
55–85px from an emitter. Light ends at 120px, and the three emitter discs
cover only about 25% of a 900×600 world, so the rest held no energy.

There are four mechanisms, all off in `Rules()`:

| Rule | Mechanic |
|---|---|
| `ambient_light` | A weak, spectrum-neutral glow everywhere (`AMBIENT_MATCH` 0.6). It is harvested and grazed like emitter light and counts as light for foraging, so an organism in the open doesn't fall back to seeking an emitter. |
| `dispersal_max` + `dispersal` gene | A child is born up to `12 + dispersal × dispersal_max` px from its parent. The gene starts at 0–0.3, with mutation σ 0.05. |
| `tail_strength`, `tail_range` | Each emitter also casts a dim, wide cone that fades to zero at `tail_range`. |
| `carcass_fraction`, `carcass_decay`, `scavenge_bite` | Old-age deaths, and whatever part of prey a predator doesn't eat, leave a decaying carcass. Anything with `eating_ability > 0.05` scavenges it, and predators without a victim seek carcasses. Total energy still never rises (a test counts carcass energy). |

**`Rules.open_world()`** (`--env open`, and the GUI's "Open world" toggle,
which is on by default there) sets `ambient_light=0.02` and
`dispersal_max=150`, plus the ranging rules below.

**Measurements** (6 seeds × 5000 ticks):

| Config | Beyond 120px | Balance |
|---|---|---|
| baseline | 0% | target met |
| ambient only | 1–12% | populations hit the 600 cap |
| **ambient + dispersal** | **2–39%** (median distance 73–90px) | populations 160–386, all strategies alive; parasites 19% |
| tails + dispersal | about 1% | harsh (one seed extinct) |
| carcasses + dispersal | about 1% | overfeeds hunters |
| all four | 1–42% | predators take over (25–32%) |

- **12 seeds:** ambient + dispersal kept every strategy alive on all 12 seeds,
  with 1–32% of organisms beyond the discs. But predators averaged 21%, which
  misses the static target.
- **Dynamic environment:** with `Rules.dynamic()`, it met the target.
- **Tuning attempts:** lowering `steal_rate` let predators boom, because
  parasites were holding them in check. A longer hunt cooldown didn't help.
- **Conclusion:** the open world is opt-in, like the dynamic environment. It
  is more alive but more volatile.
- **What it looks like:** colonies settle in the open. Since ambient light
  suits every spectrum, they evolve spectra unlike the emitter populations',
  and predators follow them out.

## Ranging behaviour

**Why:** with the open world on, absorbers still barely moved: the median
distance travelled was 7px per 100 ticks, and parasites 7px. Foragers stop
once no nearby spot is better, and in even ambient light nothing ever is.
Parasites stayed latched to one host, and predators without a victim went
back to basking at an emitter.

| Rule | Gene | Mechanic |
|---|---|---|
| `roam_rate` | `roaming` | Per-tick chance (`roam_rate × roaming`, tripled on a poor spot where share × reserve < 0.5) of starting a straight travel leg of 40–120 ticks. Legs bounce off edges, and a victim sighting ends one. |
| `patrol` | – | Hunters with no victim in sight search on legs, roughly holding their heading, instead of basking. They do this only while energy > `PATROL_MIN_ENERGY` (2), so hunger still sends them back to the light. |
| `host_min_energy` | – | Parasites only chase and drain hosts richer than this, and pick the richest in reach, so they leave drained hosts. |
| `flee` | `wariness` | Non-predators pull away from the nearest sensed predator (`FLEE_GAIN × wariness`). Wariness costs `SENSE_COST × wariness` per tick. |

**The open world preset now includes these:** `roam_rate` 0.02, patrol,
`host_min_energy` 2 and flee. Wider-ranging hunters find far more prey and
overexploit it; with patrols alone, 2 of 6 seeds went extinct. So the preset
also makes each kill costlier: `hunt_cooldown` 24 and `strategy_cost` 0.02.

Result under `dynamic+open` (6 seeds × 5000 ticks, final third):

| | Absorbers | Parasites | Predators |
|---|---|---|---|
| Time beyond the discs | 33–76% | 6–23% | 19–45% |
| Travel per 100 ticks | 9–19px | 14–24px | 29–54px |

Without the ranging rules it was 4–53% / 0–14% / 1–34% beyond the discs,
with travel of about 6 / 8 / 20px.

**Validation, 12 seeds × 3000 ticks under `dynamic+open` (the GUI default):**

- the full stable-coexistence target is met
- time beyond the discs: absorbers 21–70%, parasites 4–21%, predators 4–40%
- travel per 100 ticks: 10–26px, 8–26px and 20–59px

**Use it with seasons.** Without them (`--env open`), the preset is fragile:
on 6 seeds, one went extinct and one fell to 29.

### What is inherited and what is a rule

Evolution tunes the knobs; hand-written rules write the program.

- **Heritable (18 genes):**
  - absorption spectrum and the three strategy shares
  - movement ability, radiation sensing, organism sensing
  - kin affinity, offspring protection, cover affinity
  - armour, bite, camouflage, perception
  - marker
  - dispersal, roaming, wariness
- **Fixed rules (the same for every organism):**
  - the movement decision order: chase → carcass → travel leg → forage /
    seek an emitter, plus kin, cover and flee pulls
  - behaviour chosen by dominant strategy (a category, not a blend)
  - who may eat or rob whom
  - the life cycle (breeding threshold and chance, lifespan, child energy)
  - the ranging triggers (leg length, patrol energy threshold, poor-spot
    multiplier)
  - mate choice and crossover

In a ranging run (3 seeds, 4000 ticks), dispersal rose the most
(0.15 → 0.30–0.69), which is selection spreading offspring out. Cover
affinity, armour and the hunting shares also rose, and radiation sensing fell
(1.3 → 0.7–0.9). Roaming and wariness rose only mildly. The evolved controller
(next section) replaces the fixed movement decision order with 23 heritable
weights, so in brain mode how an organism steers is inherited. Who may eat or
rob whom, strategy classification and the life cycle remain rules.

## Evolved controller (opt-in, `movement="brain"`)

`Rules.brain()`, `--env brain` and the GUI's "Evolved behaviour" toggle
replace the fixed movement decision order with a heritable controller.

- **Genome:** `Gene.brain` holds `BRAIN_SIZE` = 23 weights, clamped to ±3,
  with mutation σ 0.1 per weight. It crosses over per weight and is appended
  flat to `as_tuple()`; `Gene.from_tuple` inverts that.
- **Inputs** (`BRAIN_INPUTS`): best light nearby, nearest emitter,
  prey/host (through the usual victim filter, so camouflage, cover and host
  floors still apply), nearest predator, nearest relative, nearest stranger,
  nearest rock, nearest carcass, current heading, and random noise.
- **Steering:** heading = Σ (`base_i + hunger_i × hunger`) × unit vector,
  where `hunger = 1 − energy / ENERGY_CAP`.
- **Throttle:** speed fraction = `sigmoid(t0 + t1·hunger + t2·local light)`.
  Motion cost is charged on the speed actually moved, so sitting still can
  pay.
- **Founders:** `Gene.random` seeds the dominant strategy's rule-like weights
  (`BRAIN_SEEDS`) plus N(0, 0.2) noise. Genomes without a brain use the
  noise-free seed (`default_brain`).
- **Still fixed rules:** who may eat or rob whom, strategy classification,
  shading, and the life cycle.
- **Ignored in brain mode:** the rule-driven pulls and triggers (kin, cover,
  flee, legs, patrol). The `kin_affinity`, `cover_affinity`, `roaming` and
  `wariness` genes drift neutrally.

**Balance.**

- With the open world's ambient light (0.02), controllers spread absorbers
  evenly over the whole map and populations hit the 600 cap on 5 of 6 seeds.
  Stronger grazing (0.05) didn't fix that.
- `preset_rules(..., "open", "brain")` therefore uses ambient 0.015
  (`OPEN_BRAIN_AMBIENT`). That meets the stable-coexistence target on 6 seeds
  under `dynamic+open+brain`. Absorbers then spend 10–37% of their time beyond
  the discs, and hunters 0–9%, because hunters aren't seeded to roam; whether
  they learn to is up to selection.
- **Cost:** a brain-mode step costs about 1.5× rules mode per organism (more
  neighbour queries).

The report's "Evolved behaviour" section plots each strategy's mean
steering weights and throttle over time.

**What evolves** (3 seeds × 3000 ticks, `dynamic+open+brain`):

- **Absorbers keep fleeing:** their threat weight stays −0.8 to −1.1 on 3/3
  seeds.
- **Everyone leans harder on light**, and absorbers, and on some seeds all
  strategies, learn to avoid carcasses.
- **Predators do not keep chasing:** their prey weight drifted to −0.3 and
  −0.1 on 2 of 3 seeds, and they steer by light instead. The likely reason is
  that a genome has one controller, and most predators are recent converts
  from absorber lineages whose shares crossed the strategy boundary. They
  arrive with absorber-like controllers, and predator lineages don't persist
  long enough for chasing to be re-selected.
- **Next step:** strategy-specific controllers (one per strategy, expressing
  the current one), so hunting weights are inherited even through absorber
  lineages (TODO).

**Long run** (seed 42, 20k ticks, 153 generations; the report is
`runs/brain-demo.html`):

- **Absorbers:** they learned to **avoid relatives** (kin weight
  +0.2 → about −1.5, since relatives compete for the same light). They also
  lean harder on light (1.0 → about 1.4), keep fleeing (about −1), and gained
  momentum (+0.2 → about 0.8), so they travel further.
- **Parasites:** they sharpened host-seeking (to about 2) alongside strong
  fleeing.
- **Predators:** their weights stayed noisy around zero.
- **Population:** unlike the 3000-tick soak, it sat at the 600 cap for most
  of the run, as evolved controllers harvest more efficiently. Brain mode
  needs a carrying-capacity rethink before it could become the default.

## Speciation (opt-in)

`Rules.speciation()` (and `--env speciation`, or `--env dynamic+speciation`)
sets `kin_by="marker"`, `sex_rate=0.5` and `mate_tolerance=6`.

- **Marker gene:** `marker` (1..100, mutation σ 1.5) is a neutral heritable
  tag. With `kin_by="marker"`, kin means `|Δmarker| ≤ KIN_MARKER_DIST` (4)
  rather than the same founder, so families can drift apart and split.
  - The mode is stored per organism (`kin_dist`, inherited), so `is_kin`
    needs no world.
  - Kin immunity, group defence, `kin_affinity`, the inspector outline and the
    report's clumping metric all go through `is_kin`.
  - `family` still records founder lineage for the Families chart.
- **Sexual reproduction:** a birth is sexual with probability `sex_rate`.
  - The parent picks the nearest organism within `MATE_RANGE` (25px) with the
    same strategy and a marker within `mate_tolerance`. This is assortative
    mating.
  - If there is one, the child's genome is `Gene.crossover`: each gene from
    either parent, with the three strategy shares taken as one block, then
    mutation.
  - Otherwise the birth is asexual.
  - The parent alone pays the energy cost. `child.mate_uid` and the lineage
    record (8th field) name the mate.
  - `world.stats[("birth", "sexual" | "asexual")]` counts births.
- **Species:** `species_clusters(markers)` splits sorted markers at gaps
  > 2 × `KIN_MARKER_DIST` and keeps clusters of 3+. The report adds a marker ×
  time heatmap, a species-count chart and a "Species" tile with the sexual
  share.

**Why opt-in:** it redefines kin for every behaviour. On 6 seeds × 5000
ticks it's close to balanced (only seed 7 ends at 73, just under the 80
floor). But non-predators make 30–45% of kills, because relatives with
drifted markers stop counting as kin.

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
| marker | 1..100 | 1.5 | 1..100 | neutral tag for kin and mate choice (see Speciation) |
| dispersal | 0..0.3 | 0.05 | 0..1 | how far children are born (× `dispersal_max`) |
| roaming | 0..0.3 | 0.05 | 0..1 | chance of setting off on travel legs (× `roam_rate`) |
| wariness | 0..0.3 | 0.05 | 0..1 | how hard it flees predators (with `flee`) |

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
2. **Absorb:**
   - Harvest the cell's light from every emitter, plus any ambient light.
   - A positive gain is multiplied by the cell's crowding share, its grazed
     reserve, and (in the arms race) `1 − 0.5 × camouflage`. Radiation damage
     in the lethal zone is taken in full.
   - The harvest is tallied for grazing.
3. **Move**, by `Rules.movement`:
   - **`"forage"` (default):**
     - Hunters chase the nearest eligible victim (see `_victim_filter`):
       predators only what they could eat; parasites non-parasites, above
       `host_min_energy` if set. Camouflage, perception and rock cover
       limit how far away they can spot a target.
     - Predators with no victim head for carcasses.
     - Otherwise the organism continues a travel leg, or may start one
       (roaming, patrol).
     - Otherwise it forages for the best of its own cell and 8 points at
       `radiation_sensing × 15px`, falling back to the nearest emitter's
       optimal ring when nothing sensed is lit.
     - Kin, cover and flee pulls are added to the heading.
   - **`"ring"`:** the original steering toward the optimal ring.
   - **`"brain"`:** the evolved controller (see Evolved controller).
   - Rocks are solid: the new position is pushed out of any rock, and legs
     bounce off the world's edges.
4. **Steal:** if `stealing_ability > 0.05`, take
   `energy × stealing × steal_rate` from a non-parasite within 12px. By
   default that's the first host found with more than 0.1 energy. With
   `host_min_energy` set, it's the richest host above that floor.
5. **Eat:** if `eating_ability > 0.05`, with a `hunt_cooldown` (12 ticks),
   pick the weakest organism within 12px that `can_eat` allows. `can_eat`
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
   - not defended by `group_defense` relatives (see Families)

   The kill can then still fail, twice over:
   - the partial group-defence roll (`defense_per_kin`, if set)
   - the armour roll (arms race)

   Either failure costs the cooldown. On success the eater gains
   `min(prey.energy × eat_fraction (0.8), eat_gain_cap (5))`, and with
   carcasses on, part of the uneaten remainder becomes a carcass.
6. **Scavenge:** with carcasses around, organisms that can eat take up to
   `scavenge_bite` from the nearest carcass within 12px.
7. **Metabolism:**
   - Pay motion and sensing: `MOTION_COST × speed + SENSE_COST × (sensing
     total)`. In brain mode, speed is the speed actually moved.
   - Hunters also pay `strategy_cost`.
   - The arms race adds armour upkeep, perception (as sensing), and bite for
     hunters.
   - `flee` adds wariness (as sensing).
   - Cap energy at 12.
8. **Reproduce:** if energy > `repro_energy` (3) and the population is below
   `max_population`, there is a `repro_chance` (5%) chance per tick.
   - With `sex_rate`, the birth may be sexual: a compatible nearby mate, then
     crossover.
   - The child spawns up to `12 + dispersal × dispersal_max` px away (pushed
     out of rocks) with mutated genes, `child_share` (90%) of
     `repro_energy`, and a `lifespan` draw.
   - The parent pays `repro_energy`, and its `children` count goes up.

An organism dies when its energy reaches ≤ 0, it hits `max_age` (`lifespan`,
150–450), or it is eaten.

### Balance rules (`Rules`)

Every tunable of the ecology lives in the `Rules` dataclass, one per world
(`World(..., rules=Rules(...))`, stored as `world.rules`). `Rules.__post_init__`
validates it.

**Presets.** Each is a dict of `Rules` values, and `preset_rules(*names, **overrides)`
combines them. The tools take the names as `--env a+b`, and the GUI toggles
dynamic, open and brain.

| Preset | Values |
|---|---|
| `static` | the defaults |
| `dynamic` (`DYNAMIC_PRESET`) | seasons 1500 ticks at 30%, spectrum drift 0.05, position drift 0.1, 8 rocks |
| `open` (`OPEN_PRESET`) | ambient 0.02, dispersal 150, roam 0.02, patrol, host floor 2, flee, hunt cooldown 24, strategy cost 0.02 |
| `speciation` (`SPECIATION_PRESET`) | marker kin, sex rate 0.5, mate tolerance 6 |
| `brain` (`BRAIN_PRESET`) | `movement="brain"`; with `open`, ambient drops to 0.015 (`OPEN_BRAIN_AMBIENT`) |

**Fields:**

| Field | Default | Meaning |
|---|---|---|
| `eat_fraction` | 0.8 | share of the prey's energy a kill yields |
| `eat_gain_cap` | 5.0 | most energy a kill yields |
| `hunt_cooldown` | 12 | ticks between kills |
| `strategy_cost` | 0.01 | per-tick upkeep for hunters |
| `weak_prey_energy` | 9.0 | heaviest prey a pure predator can take |
| `steal_rate` | 0.05 | parasite drain per tick, × stealing ability |
| `depletion_rate` | 0.03 | reserve lost per unit harvested (0 = light never runs out) |
| `regrowth_rate` | 0.01 | fraction of the missing reserve regrown per tick |
| `defense_per_kin` | 0.0 | partial group defence per relative (0 = off) |
| `arms_race` | True | express armour/bite and camouflage/perception (see Arms race) |
| `ambient_light` | 0.0 | spectrum-neutral light everywhere (open world uses 0.02) |
| `dispersal_max` | 0.0 | extra birth distance at dispersal 1 (open world uses 150) |
| `tail_strength`, `tail_range` | 0.0, 240 | dim wide emitter cone |
| `carcass_fraction`, `carcass_decay`, `scavenge_bite` | 0.0, 0.01, 0.5 | carcasses and scavenging |
| `roam_rate`, `patrol`, `host_min_energy`, `flee` | 0.0, False, 0.0, False | ranging behaviour (see Ranging behaviour; on in the open world preset) |
| `movement` | `"forage"` | `"forage"`, `"ring"` (original) or `"brain"` (evolved controller) |
| `kin_by` | `"family"` | kin = same founder, or `"marker"` = similar marker |
| `sex_rate` | 0.0 | chance a birth is sexual (needs a nearby compatible mate) |
| `mate_tolerance` | 6.0 | largest marker difference a mate may have |
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

Environment fields (see Environment): `spectrum_drift`, `emitter_drift`,
`pulse_period`, `pulse_depth`, `num_rocks`, `rock_radius`, `rock_shade`,
`cover_range`, `hidden_detect`. All are off or zero by default.

`world.stats` is a `Counter` of cumulative tallies for analysis. Its keys:

| Key | Counts |
|---|---|
| `("eat" \| "steal", actor_strategy, victim_strategy, is_kin)` | kills and thefts |
| `("death", cause, strategy)` | deaths by cause |
| `("repelled", ...)` | kills stopped by partial group defence |
| `("resisted", ...)` | kills stopped by armour |
| `("scavenge", strategy)` | carcass bites |
| `("birth", "sexual" \| "asexual")` | births by kind |

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
- rocks, "Seasons & drift" on/off (`dynamic`), "Open world" on/off (`open`),
  and "Evolved behaviour" on/off (`brain`). The first two are on by default,
  brain is off. `world_rules()` turns the toggles into
  `preset_rules(...)`.

Rocks are drawn as grey discs. Each emitter's halo dims with its seasonal
output, and its label shows the output % and current spectrum.

Use the arrows or the +/- buttons to adjust, and Enter or Start to begin. Esc
returns to the running world, or quits if there isn't one yet. The window is
the world plus a 300px side pane (`window_size`). `max_population` scales with area (never below
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

**The side pane** (`draw_pane`, right of the world) keeps the world view free
of overlays. Only emitter labels and the selected organism's ring and kin
outlines are drawn in the world. From the top, the pane shows:

- the HUD: generation, population and tick, running/stopped, and
  per-strategy count, mean energy and offspring
- then either the inspector for the clicked organism (energy and age bars,
  strategy budget, abilities, social, arms-race, marker and dispersal genes)
  or the legend (H toggles it)
- the key help at the bottom

Clicks inside the pane don't select anything. Clicking empty world space
closes the inspector.

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

At about 150–300 organisms, a step takes about 4–6ms in CPython in rules
mode (it was about 30ms before the speedups below). Brain mode costs about
1.5× per organism, because of its extra neighbour queries. The exact
speedups, all bit-identical to the previous behaviour:

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
| Unit | `test_unit_brain.py` | steering toward prey and away from threats, momentum, throttle and motion cost, the hunger term, genome round-trip, crossover, mutation bounds, seeding |
| Unit | `test_unit_ranging.py` | travel legs and edge bounces, patrols (fed vs hungry, ended by a sighting), parasites moving on, fleeing and its cost |
| Unit | `test_unit_spread.py` | ambient harvest, tails, dispersal distances, carcasses (leaving, decay, scavenging, seeking, energy conservation), open-world preset |
| Unit | `test_unit_speciation.py` | marker kin, crossover, assortative mating, asexual fallback, lineage mate field, species clusters, presets |
| Unit | `test_unit_arms.py` | kill chance vs bite − armour (statistical), camouflage and perception reach, costs, mutation bounds |
| Unit | `test_unit_foraging.py` | grazing and regrowth, foraging choices and fallback, ring mode, partial defence statistics |
| Unit | `test_unit_environment.py` | rocks (placement, solidity, shadow, cover), `cover_affinity`, seasons, drift bounds, the dynamic preset |
| Unit | `test_unit_organism.py` | migration, lethal zone, stealing, eating, reproduction, death |
| Integration | `test_integration_world.py` | per-tick invariants, determinism, grid, shading in a live world, extinction without energy |
| Functional | `test_functional_ecosystem.py` | the default world persists; selection favours matched spectrum; a predator-free population converges to a carrying capacity |
| End-to-end | `test_e2e_gui.py` | headless pygame: setup dialog (keys and clicks), effects, inspector, pause, reset, run loop |
| Tools | `test_tools.py` | `evolve.py` report, lineage and resume; soak rule and mix parsing, presets |
| Soak (opt-in) | `test_soak.py` | 12 seeds × 3000 ticks: no collapse, absorbers dominate, no incidental kin cannibalism, parasites persist, and the full stable-coexistence target; in brain mode, absorbers keep fleeing |

Run the suite with `python3 -m unittest` from the repo root. It takes about
45s, most of it in the functional tests. The soak tier is skipped unless
`AIL_SLOW=1` is set, and then adds a few minutes. `AIL_QUICK=1` skips the
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

**Current status:**

- The default world meets the target on 12 seeds, and so does
  `dynamic+open`, the GUI default.
- `open` without seasons is fragile.
- `dynamic+open+brain` meets it at 3000 ticks, but reaches the population cap
  over long runs.

The soak output also reports, per strategy, the time spent beyond the
emitter discs and the median travel per 100 ticks. Runs of 3000 ticks are
still partly the growth phase, especially in bigger worlds, so use
`--ticks 10000` to judge equilibrium.
