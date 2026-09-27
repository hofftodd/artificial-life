# Artificial Life Simulator

A small evolutionary sandbox. Organisms carry a genome that splits a single
strategy budget between three ways of getting energy:

- **absorbing** radiation from emitters
- **parasitising** (stealing energy from neighbours)
- **predation** (eating weaker organisms)

Gaining in one costs the other two, and absorbers are slow. Other genes cover
spectrum, speed, sensing, communalism (attraction to family) and how long
predators spare their own young. Everything is heritable and mutates.

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
- the number of rocks, and whether seasons and emitter drift are on (on by
  default in the GUI)

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
| Dimmer patches of light | grazed cells: harvesting drains a cell's light, which slowly regrows, so absorbers keep foraging |
| Grey discs | rocks: they shade the light behind them and hide organisms near their edge from hunters |
| Emitter label "output 70%" | the emitter's current seasonal output |

The top-left HUD shows each strategy's count, mean energy, mean offspring,
and the best offspring count.

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

## Tests

```sh
python3 -m unittest
```

There are 139 fast tests (unit, integration, functional, and a headless
pygame GUI test), and they take about 45s. The GUI tests use SDL's dummy video
driver, so they don't need a display.

A slower soak tier (5 more tests, about a minute) checks long-run ecosystem
balance:

```sh
AIL_SLOW=1 python3 -m unittest tests.test_soak
```

For a quick run (about 13s) that skips the slower functional tests (about 30s of the
total), set `AIL_QUICK=1`:

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
- **Arms race:** the report's "Arms race" section plots prey defences
  (armour, camouflage) against predator weapons (bite, perception).
- **Changing environment:** `--env dynamic` adds seasons, drifting emitters and
  rocks. Rocks cast shade and give organisms cover from hunters. Tune it with
  `--set`, e.g. `--set num_rocks=15 --set pulse_depth=0.5`.

## More

- [DESIGN.md](DESIGN.md): how the model works (strategy budget, light
  competition, shading, genes, tick order, UI encoding).
- [TODO.md](TODO.md): open questions and next steps, including performance
  and GPU notes.

`legacy/` holds earlier standalone prototypes (`simulator_simple.py`,
`simulator_visual.py`, `simulator_text.py`) that don't use `simcore`.
