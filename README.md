# Artificial Life Simulator

A small evolutionary sandbox. Organisms carry a genome that splits a single
strategy budget between three ways of getting energy:

- **absorbing** radiation from emitters
- **parasitising** (stealing energy from neighbours)
- **predation** (eating weaker organisms)

Gaining in one costs the other two, and absorbers are slow. There are 18
heritable genes, plus an optional 23-weight movement controller. They cover:

- spectrum, speed and sensing
- communalism and offspring protection
- cover-seeking
- armour, bite, camouflage and perception (an arms race)
- a neutral marker (for speciation)
- dispersal, roaming and wariness

Short lives and quick breeding give about 130 generations per 10,000 ticks.

**The default model:**

- Absorbers forage for fresh light, and harvesting drains a patch until it
  regrows.
- Predators and parasites hunt them, with the arms race switched on.

**Presets** add more, and combine with `+` (e.g. `dynamic+open+brain`):

| Preset | Adds |
|---|---|
| **dynamic** | seasons, drifting emitters, and rocks that shade and give cover |
| **open** | ambient light, dispersal, roaming, patrols and fleeing, so life spreads between the emitters |
| **speciation** | kin by marker, and sexual reproduction with assortative mating |
| **brain** | movement from an evolved controller instead of rules |

The GUI turns on dynamic and open by default.

## Requirements

- Python 3 (tested on 3.14)
- `pygame` 2.6 (only for the GUI; the model in `simcore.py` is pure Python)

```sh
pip install -r requirements.txt
```

## Run

```sh
python3 simulator.py
```

A setup dialog opens first. In it you choose:

- the number of emitters
- how many organisms to start with
- the mix of absorbers, parasites and predators
- the world size
- the number of rocks, whether seasons and emitter drift are on, and whether
  the world is "open" (weak light everywhere plus long-range dispersal, so
  life spreads beyond the emitters). Both are on by default in the GUI.
- whether behaviour is evolved (each organism steers by its own heritable
  controller) instead of rule-driven. It's off by default.

Use the arrow keys or the +/- buttons, then press **Enter** or click **Start**.

| Key / mouse | Action |
|---|---|
| SPACE | pause / resume |
| R | new simulation (reopens the dialog) |
| click | inspect an organism: genes, energy, age, offspring; relatives are outlined |
| H | show / hide the legend |
| ESC | quit (in the dialog: back to the running world) |

### Reading the screen

| Visual | Meaning |
|---|---|
| Circle / diamond / triangle | absorber / parasite / predator |
| Fill colour | absorption spectrum |
| Size | energy |
| Vividness | how specialised the organism is |
| Gold dots | offspring so far (fitness) |
| Violet tether | a parasite draining a victim |
| Red strike and burst | a predator kill |
| Fading ring | a death: red ✕ eaten, grey starved, white old age |
| Red / green rings round an emitter | lethal zone / optimal distance |
| Small brown dots | carcasses (only with `carcass_fraction` set) |
| Dimmer patches of light | grazed cells: harvesting drains a cell's light, which slowly regrows, so absorbers keep foraging |
| Grey discs | rocks: they shade the light behind them and hide organisms near their edge from hunters |
| Emitter label "output 70%" | the emitter's current seasonal output |

The world view shows only the world. A side pane on the right holds:

- the stats: each strategy's count, mean energy, mean offspring and best
  offspring count
- the inspector, when you click an organism (click empty space to close it)
- otherwise the legend (H hides it)
- the key help

To exit automatically after N frames (this skips the dialog):

```sh
AIL_AUTOQUIT_FRAMES=300 python3 simulator.py
```

### Headless

```python
from simcore import World

w = World(900, 600, seed=42, strategy_mix={"absorber": 8, "parasite": 1, "predator": 1})
for _ in range(1000):
    w.step()
print(len(w.organisms), w.generation)
```

The same seed always produces the same simulation. Pass
`strategy_mutation=0` to keep strategies from evolving; for example, a
predator-free world stays predator-free.

Presets by name, with any rule overrides:

```python
from simcore import World, preset_rules

w = World(900, 600, seed=42, rules=preset_rules("dynamic", "open", "brain", num_rocks=12))
```

## Tests

```sh
python3 -m unittest
```

There are 189 fast tests (unit, integration, functional, and a headless
pygame GUI test), and they take about 45s. The GUI tests use SDL's dummy video
driver, so they don't need a display.

A slower soak tier (6 more tests, a few minutes) checks long-run ecosystem
balance. It covers the stable-coexistence target on 12 seeds, and that
evolved controllers keep absorbers fleeing:

```sh
AIL_SLOW=1 python3 -m unittest tests.test_soak
```

For a quick run (about 12s) that skips the slower functional tests, set
`AIL_QUICK=1`:

```sh
AIL_QUICK=1 python3 -m unittest
```

To probe balance directly, or to try other rules, use the soak tool:

```sh
python3 tools/soak.py --seeds 1 2 3 7 42 99 --ticks 3000
python3 tools/soak.py --mix 8:1:1 --set hunt_cooldown=16 --set group_defense=3
```

## Evolution reports

Run a world headless and get an HTML report of how it evolved: strategies,
generations, spectrum vs. emitters, family takeover and trait trends.

```sh
python3 tools/evolve.py --seed 42 --ticks 10000 --out runs/seed42.html
open runs/seed42.html
```

- **Add a lineage file:** `--lineage runs/seed42.jsonl` also writes every birth
  and death.
- **Checkpoint and resume:** `--checkpoint runs/s42.ckpt` saves the world at the
  end, and `--resume runs/s42.ckpt --ticks 5000 --out runs/s42b.html` continues
  it exactly.
- **Change the rules:** `--mix` and `--set` work as in `tools/soak.py`.
- **Open world:** `--env open` adds weak ambient light everywhere and a
  dispersal gene, so colonies can live between the emitters. It also adds
  ranging behaviour: travel legs (roaming gene), hunter patrols, parasites
  that move between hosts, and prey that flee predators (wariness gene). Presets combine
  with `+`, e.g. `--env dynamic+open+speciation`.
- **Evolved behaviour:** `--env brain` (or the GUI toggle) makes movement
  come from each organism's heritable controller, which weighs light, prey,
  predators, relatives, rocks, carcasses, momentum and noise, and adjusts with
  hunger. The report's "Evolved behaviour" section shows how those weights
  change. Try `--env dynamic+open+brain`.
- **Speciation:** `--env speciation` switches kin to a drifting marker gene
  and adds sexual reproduction with assortative mating. The report then shows
  a marker heatmap and a species count. Combine it with a changing world using
  `--env dynamic+speciation`.
- **Arms race:** the report's "Arms race" section plots prey defences
  (armour, camouflage) against predator weapons (bite, perception).
- **Changing environment:** `--env dynamic` adds seasons, drifting emitters and
  rocks. Rocks cast shade and give organisms cover from hunters. Tune it with
  `--set`, e.g. `--set num_rocks=15 --set pulse_depth=0.5`.

## More

- [DESIGN.md](DESIGN.md): how the model works, including the tick order,
  light, foraging, the arms race, the open world, ranging, the evolved
  controller, speciation, genes, `Rules` and presets, the GUI, and every
  balance measurement behind the defaults.
- [TODO.md](TODO.md): open questions and next steps, including performance
  and GPU notes.

Generated reports, lineage files and checkpoints go in `runs/`, which git
ignores.

`legacy/` holds earlier standalone prototypes (`simulator_simple.py`,
`simulator_visual.py`, `simulator_text.py`) that don't use `simcore`.
