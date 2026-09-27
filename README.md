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
pip install pygame
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

There are 92 tests (unit, integration, functional, and a headless pygame GUI
test), and they take about 35s. The GUI tests use SDL's dummy video driver, so
they don't need a display.

## More

- [design.md](design.md): how the model works (strategy budget, light
  competition, shading, genes, tick order, UI encoding).
- [todo.md](todo.md): open questions and next steps, including performance
  and GPU notes.

`simulator_simple.py`, `simulator_visual.py` and `simulator_text.py` are
earlier standalone prototypes that don't use `simcore`.
