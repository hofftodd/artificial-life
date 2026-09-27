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
  alive on all seeds). Remaining: one of 12 seeds overshoots the 350
  population ceiling, and parasites run about 22% under `Rules.dynamic()`.
- [ ] **Boom/bust preset.** Add a `Rules` preset (e.g. `Rules.cycles()`) that
  gives predator–prey oscillations, and a soak metric for cycle period and
  amplitude (the CV columns are a start).
- [ ] **Soak runs need longer horizons.** 3000 ticks is still partly the
  growth phase, especially in bigger worlds; the slow tier should move to
  10k ticks once steps are faster (see Performance).
- [ ] **Does communalism pay now?** Check whether `kin_affinity` rises under
  group defence.
- [ ] **Decide how kin recognition should work.** It's currently exact family
  (the founder's id), so a successful founder's descendants stay one family
  forever. An alternative is a heritable, drifting "marker" gene with kin
  meaning a similar marker, which lets families split over time.
- [ ] **Decide whether "parasites can't parasitise parasites" should be
  continuous.** It's currently a hard rule on the victim's dominant strategy.
  A continuous version would scale theft by `(1 − victim.parasitism)`, which
  fits generalists better.
- [ ] **Recheck spectral adaptation in the full ecosystem.** It's now
  plausible with light competition in place; consider restoring an
  ecosystem-level test.
- [ ] **Stop absorbers shading their own cell.** Shading is traced to the cell
  centre, so an absorber sitting nearer the emitter than its cell's centre
  shades its own cell. Verified 0.6× on itself. Fix by skipping blockers inside
  the target cell.
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

- [ ] Delete, or move to `legacy/`, `simulator_simple.py`,
  `simulator_visual.py` and `simulator_text.py`.
- [ ] Add `requirements.txt` / `pyproject.toml` (pygame 2.6.1; Python 3.14
  tested).
- [x] Initialise git.
- [ ] Remove `_fix_pygame_font()` once pygame ships a Python 3.14 fix.

## Evolution experiments

- [x] Lineage recording, checkpoints, and the `tools/evolve.py` HTML report.
- [ ] Phylogeny view from the lineage file (tree or Muller by lineage, not just
  family).
- [x] Seasons, drifting emitters, and rocks (shade, solidity, cover, and the
  `cover_affinity` gene), available through `Rules.dynamic()` / `--env dynamic`.
- [ ] Tune `Rules.dynamic()` for bigger worlds (more emitters buffer bad
  seasons), and check whether `cover_affinity` rises when predators are
  common.
- [ ] Let organisms track the seasonal optimal ring (evolvable ring-distance
  gene) rather than the fixed `OPTIMAL_DISTANCE`.
- [ ] Heritable kin marker instead of permanent founder `family`; sexual
  reproduction with assortative mating (speciation).
- [ ] Energy-sharing gene to test Hamilton's rule.

## Tests

- [ ] Mark the slow functional tests (about 30s) so a quick run can skip them
  (the soak tier already uses `AIL_SLOW=1`).
- [ ] Add a regression test for self-shading once it's fixed.

## GPU note

The hot loops are branchy, per-organism Python operating on small data (a few
hundred organisms): ray-marching shade, neighbour queries, and sequential
steal/eat, where each action mutates shared state that later organisms read.
That profile suits neither the GPU nor a transfer-per-tick setup, and the
sequential semantics would need reworking into parallel conflict resolution.
The order of wins is:

1. a better algorithm (cell-based shading)
2. NumPy vectorisation
3. GPU (e.g. PyTorch MPS on the Mac), and only for much larger worlds
