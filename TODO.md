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
- [x] UI:
  - setup dialog
  - parasitism, predation and death effects
  - size / vividness / offspring-dot encoding
  - inspector
  - per-strategy HUD

## Model

- [ ] **Give communalism a benefit.** Right now clumping only costs absorbers
  (cell-mates split the light), so selection pushes `kin_affinity` down.
  Options:
  - group defence: prey with ≥ N kin nearby can't be eaten
  - kin don't steal from or eat each other
  - kin shading doesn't count against relatives
- [ ] **Decide how kin recognition should work.** It's currently exact family
  (the founder's id), so a successful founder's descendants stay one family
  forever. An alternative is a heritable, drifting "marker" gene with kin
  meaning a similar marker, which lets families split over time.
- [ ] **Decide whether "parasites can't parasitise parasites" should be
  continuous.** It's currently a hard rule on the victim's dominant strategy.
  A continuous version would scale theft by `(1 − victim.parasitism)`, which
  fits generalists better.
- [ ] **Watch predator/prey dynamics.** In the default mixed world, hunters
  hold the population well below the predator-free carrying capacity, and
  some seeds decline slowly. Worth a soak study before tuning further.
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

- [ ] **Shading is about two-thirds of step time.** Rasterise absorbers into a
  per-cell occupancy grid once per tick, then march beams over cells rather
  than calling `grid.query` per sample. Expect about 10× faster.
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
- [ ] Initialise git.
- [ ] Remove `_fix_pygame_font()` once pygame ships a Python 3.14 fix.

## Tests

- [ ] Mark the slow functional tests (about 30s) so a quick run can skip them.
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
