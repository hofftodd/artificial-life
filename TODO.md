# TODO

## Done (2026-09-27)

- [x] Strategy budget: absorption, parasitism and predation shares sum to 1.
- [x] Absorption slows movement.
- [x] Prey threshold scales with `eating_ability`. Incidental cannibalism
  from tiny predation shares no longer collapses populations.
- [x] Per-cell light competition. Predator-free populations now converge to a
  carrying capacity instead of hitting the cap.
- [x] Genes for communalism (`kin_affinity`) and `offspring_protection`.
- [x] Parasites can't parasitise parasites.
- [x] Renamed "thief" to "parasite".
- [x] Balance pass (tools/soak.py, `Rules`):
  - non-predators don't eat kin (this was ~80% of all kills and held the
    population near 50)
  - predators aren't prey
  - predators chase only edible prey
  - bigger meals (80% of prey energy, cap 5)
  - cheaper hunting (cooldown 12, upkeep 0.01, prey limit 9)
  - group defence (2 relatives nearby make prey safe); this is also
    communalism's benefit
- [x] UI:
  - setup dialog
  - parasitism, predation and death effects
  - size / vividness / offspring-dot encoding
  - inspector
  - per-strategy HUD

## Model

- [x] **Predators too rare** (fixed by foraging and grazing: about 7–10% now,
  alive on all seeds). With the arms race, the full coexistence target is met
  on 12 seeds and under `Rules.dynamic()`.
- [ ] **Boom/bust preset.** Add a `Rules` preset (e.g. `Rules.cycles()`) that
  gives predator–prey oscillations, and a soak metric for cycle period and
  amplitude (the CV columns are a start).
- [ ] **Soak runs need longer horizons.** 3000 ticks is still partly the
  growth phase, especially in bigger worlds; the slow tier should move to
  10k ticks once steps are faster (see Performance).
- [ ] **Does communalism pay now?** Check whether `kin_affinity` rises under
  group defence.
- [x] **Kin recognition:** `Rules.kin_by` offers family or a drifting marker
  (see Speciation).
- [ ] **Decide whether "parasites can't parasitise parasites" should be
  continuous.** It's currently a hard rule on the victim's dominant strategy.
  A continuous version would scale theft by `(1 − victim.parasitism)`, which
  fits generalists better.
- [ ] **Recheck spectral adaptation in the full ecosystem.** It's now
  plausible with light competition in place; consider restoring an
  ecosystem-level test.
- [x] **Absorbers no longer shade their own cell.** Blockers inside the
  target cell are skipped; a regression test covers it.
- [ ] **Model mixed strategies.** Strategy is still categorical for
  behaviour and shading; only the abilities are continuous. Consider
  probabilistic behaviour for generalists.
- [ ] **Shuffle update order.** It's list order, so older organisms always
  act first; shuffle with `world.rng` each tick.

## Performance (see the GPU note below)

- [x] **Exact speedups (3–4×):** direct beam test for shading, lazy grid
  iteration, and distance-before-predicate neighbour search.
- [x] **More generations per run** (about 5–6×). Generation time tracks the
  average age of parents. The fix was short lifespans (150–450) with cheap,
  quick breeding (cost 3, 90% to the child, 5% per tick). All four are
  `Rules` fields (see DESIGN.md, Life-cycle tuning).
- [ ] **Vectorise with NumPy:**
  - the field and demand grids as arrays
  - organism positions and energies as structured arrays for neighbour search
    (e.g. `scipy.spatial.cKDTree`)
- [ ] **GPU:** only worth it at around 10k+ organisms, and after the NumPy
  rewrite (see the note below).

## Code / project hygiene

- [x] Moved the old prototypes to `legacy/`.
- [x] Added `requirements.txt` (pygame 2.6.1; Python 3.14 tested).
- [x] Initialise git.
- [ ] Remove `_fix_pygame_font()` once pygame ships a Python 3.14 fix.

## Evolution experiments

- [x] Spreading out: ambient light, light tails, dispersal gene and carcasses
  (all `Rules` fields); `Rules.open_world()` / `--env open` / GUI "Open world".
- [ ] Balance the open world without seasons. It meets the target with
  seasons (`dynamic+open`, 12 seeds); `open` alone is fragile (1 of 6 seeds
  went extinct). Carcasses and tails still overfeed hunters; consider a
  scavenger strategy.
- [x] UI: stats, legend and inspector in a side pane; the world view is clear.
- [x] Ranging: roaming and wariness genes, patrols, parasites moving on,
  fleeing; part of the open world preset.
- [x] **Evolved controller** (opt-in, `movement="brain"`): 23 heritable
  weights for steering and throttle, seeded from the rules.
- [ ] **Strategy-specific controllers:** in brain mode predators stop
  chasing (prey weight drifts negative on 2/3 seeds), because converts from
  absorber lineages bring absorber controllers. Carry one controller per
  strategy and express the current one.
- [x] The evolved controller is the default (`--env rules` for the movement
  rules). Balance holds on 12 seeds (static and dynamic+open, with
  open-world ambient 0.012).
- [ ] Evolved controllers range less than the ranging rules (absorbers 4–17%
  beyond the discs vs 21–70%). Find what would make ranging pay under
  selection.
- [ ] Try from-scratch (random) founders as an experiment.
- [ ] Brain mode's carrying capacity: over 20k ticks, evolved controllers
  harvest well enough to sit at the 600 cap.
- [x] Arms race: armour vs bite and camouflage vs perception, each with
  costs, on by default (`Rules.arms_race`), with an "Arms race" report
  section.
- [x] Lineage recording, checkpoints, and the `tools/evolve.py` HTML report.
- [ ] Phylogeny view from the lineage file (tree or Muller by lineage, not just
  family).
- [x] Seasons, drifting emitters, and rocks (shade, solidity, cover, and the
  `cover_affinity` gene), available through `Rules.dynamic()` / `--env dynamic`.
- [ ] Tune `Rules.dynamic()` for bigger worlds (more emitters buffer bad
  seasons), and check whether `cover_affinity` rises when predators are
  common.
- [x] ~~Let organisms track the seasonal optimal ring.~~ Superseded:
  foragers (and brain controllers) follow the actual light, including
  seasonal shifts.
- [x] Speciation (opt-in, `Rules.speciation()` / `--env speciation`): marker
  gene for kin, sexual reproduction with assortative mating, species
  clustering, and marker/species report panels.
- [ ] Decide whether speciation should become the default (non-predators do
  30–45% of kills under marker kin).
- [ ] Energy-sharing gene to test Hamilton's rule.

## Tests

- [x] `AIL_QUICK=1` skips the slow functional tests (the soak tier uses
  `AIL_SLOW=1`).
- [x] Regression test for self-shading.

## GPU note

The hot loops are branchy, per-organism Python operating on small data (a few
hundred organisms): ray-marching shade, neighbour queries, and sequential
steal/eat, where each action mutates shared state that later organisms read.
That profile suits neither the GPU nor a transfer-per-tick setup, and the
sequential semantics would need reworking into parallel conflict resolution.
The order of wins is:

1. a better algorithm (done for shading: a direct beam test, 3–4× faster)
2. NumPy vectorisation
3. GPU (e.g. PyTorch MPS on the Mac), and only for much larger worlds
