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
| `simulator_simple.py`, `simulator_visual.py`, `simulator_text.py` | Earlier self-contained prototypes. They don't use `simcore` and are kept for reference only. |
| `tests/` | `unittest` suite covering unit → integration → functional → headless GUI. |

## Determinism

All randomness flows through one `random.Random` owned by `World`
(`World.rng`). The same seed and the same sequence of calls give an identical
simulation, and tests depend on this. New code must draw randomness from
`world.rng`, never from the `random` module.

Organism `uid`s come from a module-level counter. They are unique, but they are
not reproducible across worlds, so never compare them between runs.

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

## Families

- Each founder starts a family, recorded as `family = uid`.
- Children inherit `family` and record `parent_uid`.
- Kin means the same family.

Communal organisms add `kin_affinity ×` a unit vector toward the nearest
relative to their movement heading. They stop approaching within
`KIN_SPACING` (10px), so clumps form without organisms stacking on each other.

Clumping currently carries a cost for absorbers, because cell-mates split the
light. It brings no benefit yet (see `todo.md`), so clumps only arise
sometimes.

## Organism update

1. `age += 1`
2. **Absorb:** radiation from every emitter, multiplied by the cell's
   competition share.
3. **Move:**
   - Hunters chase the nearest eligible victim. Predators skip their own
     protected young. Parasites skip other parasites.
   - Otherwise, the organism heads for the nearest sensed emitter's optimal
     ring.
   - A kin pull is added to either heading.
   - Otherwise, it wanders randomly.
4. **Steal:** if `stealing_ability > 0.05`, take
   `energy × stealing × STEAL_RATE` from the first non-parasite within 12px.
5. **Eat:** if `eating_ability > 0.05`, with a 24-tick cooldown, kill the
   weakest organism within 12px with energy below
   `WEAK_PREY_ENERGY (7) × eating_ability`. Skip own children younger than
   `offspring_protection`. Gain `min(prey.energy, 1.5)`.
   - Scaling the prey threshold matters. Without it, an absorber with a 5%
     predation share hunts as well as a real predator, and every lineage
     turns cannibal.
6. **Metabolism:**
   - Pay `MOTION_COST × speed + SENSE_COST × (sensing total)`.
   - Hunters also pay `STRATEGY_COST`.
   - Cap energy at 12.
7. **Reproduce:** if energy > 7 and the population is below `max_population`,
   there is a 1% chance per tick. The child spawns 2–12px away with mutated
   genes and 3–7 energy. The parent pays 7 and its `children` count goes up.

An organism dies when its energy reaches ≤ 0, it hits `max_age` (800–2400), or
it is eaten.

### Energy accounting

Emitters are the only source. Stealing moves energy between organisms.
Metabolism, the cap, eating and reproduction all lose it. With no emitters,
total energy never rises and the population goes extinct; a test checks this.

## GUI (`simulator.py`)

`SimulationApp` has two modes.

**Setup** opens at launch and on R. `SetupDialog` sets:

- number of emitters
- starting organisms
- absorber / parasite / predator mix (weights shown as percentages with a
  stacked bar; all zero means fully random genomes)
- world width and height, clamped to the desktop size

Use the arrows or the +/- buttons to adjust, and Enter or Start to begin. Esc
returns to the running world, or quits if there isn't one yet. The window is
resized to the world size. `max_population` scales with area.

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

## Performance

At about 330 organisms, a step takes roughly 35–55ms in CPython. About
two-thirds of that is the shading ray-march: `RadiationField._count_blockers`
plus the `SpatialGrid.query` calls it makes. The next largest cost is
neighbour search. See `todo.md` for the optimisation plan.

## Testing strategy

| Layer | File | What it pins down |
|---|---|---|
| Unit | `test_unit_radiation.py` | radiation curve, derived distances, spectral match |
| Unit | `test_unit_gene.py` | strategy budget, movement trade-off, mutation bounds, classification |
| Unit | `test_unit_social.py` | light competition, parasite rule, offspring protection, communalism, founder mix, events |
| Unit | `test_unit_shading.py` | beam geometry and which organisms shade |
| Unit | `test_unit_organism.py` | migration, lethal zone, stealing, eating, reproduction, death |
| Integration | `test_integration_world.py` | per-tick invariants, determinism, grid, shading in a live world, extinction without energy |
| Functional | `test_functional_ecosystem.py` | the default world persists; selection favours matched spectrum; a predator-free population converges to a carrying capacity |
| End-to-end | `test_e2e_gui.py` | headless pygame: setup dialog (keys and clicks), effects, inspector, pause, reset, run loop |

Run the suite with `python3 -m unittest` from the repo root. It takes about
35s, most of it in the functional tests.
