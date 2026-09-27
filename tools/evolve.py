"""Run one world headless and write an HTML report of how it evolved.

    python3 tools/evolve.py --seed 42 --ticks 20000 --out runs/seed42.html
    python3 tools/evolve.py --seed 42 --ticks 5000 --checkpoint runs/s42.ckpt
    python3 tools/evolve.py --resume runs/s42.ckpt --ticks 5000 --out runs/s42b.html

The report shows strategy counts, trait trends (mean with a 10-90% band),
absorption spectrum against the emitters over time, family shares, and
generations. --lineage also writes every birth and death as JSON lines.
"""
import argparse
import json
import math
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simcore import STRATEGIES, World  # noqa: E402
from tools.soak import parse_mix, parse_rules  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")
SPECTRUM_BINS = 20            # 1..100 in bins of 5
TOP_FAMILIES = 7              # plus "Other"

# (key, label, accessor)
TRAITS = [
    ("mismatch", "Spectral mismatch to local light", None),
    ("absorption", "Absorption share", lambda o: o.genes.absorption),
    ("parasitism", "Parasitism share", lambda o: o.genes.parasitism),
    ("predation", "Predation share", lambda o: o.genes.predation),
    ("speed", "Speed", lambda o: o.genes.speed),
    ("movement_ability", "Movement ability", lambda o: o.genes.movement_ability),
    ("radiation_sensing", "Radiation sensing", lambda o: o.genes.radiation_sensing),
    ("organism_sensing", "Organism sensing", lambda o: o.genes.organism_sensing),
    ("kin_affinity", "Kin affinity", lambda o: o.genes.kin_affinity),
    ("offspring_protection", "Offspring protection (ticks)",
     lambda o: o.genes.offspring_protection),
]


def spectral_mismatch(world, o):
    """|spectrum - spectrum of the emitter lighting this spot most|, or None
    when the organism sits in no light."""
    best, best_i = 0.0, None
    for i in range(len(world.emitters)):
        v = world.field.intensity_at(o.x, o.y, i)
        if v > best:
            best, best_i = v, i
    if best_i is None:
        return None
    return abs(world.emitters[best_i].spectrum - o.genes.absorption_spectrum)


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


class Sampler:
    def __init__(self, world):
        self.world = world
        self.t = []
        self.counts = {k: [] for k in ("total",) + STRATEGIES}
        self.gen = {"median": [], "max": []}
        self.traits = {k: {"mean": [], "p10": [], "p90": []} for k, _, _ in TRAITS}
        self.spectrum = []           # per sample: counts per bin
        self.family_counts = []      # per sample: {family: count}

    def sample(self):
        w = self.world
        orgs = w.organisms
        self.t.append(w.tick)
        self.counts["total"].append(len(orgs))
        for k in STRATEGIES:
            self.counts[k].append(sum(1 for o in orgs if o.strategy == k))
        gens = sorted(o.generation for o in orgs)
        self.gen["median"].append(quantile(gens, 0.5))
        self.gen["max"].append(gens[-1] if gens else None)
        for key, _, get in TRAITS:
            if key == "mismatch":
                vals = [m for m in (spectral_mismatch(w, o) for o in orgs) if m is not None]
            else:
                vals = [get(o) for o in orgs]
            vals.sort()
            slot = self.traits[key]
            slot["mean"].append(statistics.fmean(vals) if vals else None)
            slot["p10"].append(quantile(vals, 0.1))
            slot["p90"].append(quantile(vals, 0.9))
        bins = [0] * SPECTRUM_BINS
        for o in orgs:
            bins[min(SPECTRUM_BINS - 1, (o.genes.absorption_spectrum - 1) * SPECTRUM_BINS // 100)] += 1
        self.spectrum.append(bins)
        fam = {}
        for o in orgs:
            fam[o.family] = fam.get(o.family, 0) + 1
        self.family_counts.append(fam)

    def families(self):
        """Top families by total presence over the run, plus Other. Colours
        follow the family, so the order here is fixed for the whole run."""
        area = {}
        for fam in self.family_counts:
            for f, c in fam.items():
                area[f] = area.get(f, 0) + c
        top = [f for f, _ in sorted(area.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_FAMILIES]]
        series = {str(f): [fam.get(f, 0) for fam in self.family_counts] for f in top}
        series["Other"] = [sum(c for f, c in fam.items() if f not in top)
                           for fam in self.family_counts]
        alive = [len(fam) for fam in self.family_counts]
        return {"order": [str(f) for f in top] + ["Other"], "series": series, "alive": alive}


def round_floats(x, nd=4):
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, list):
        return [round_floats(v, nd) for v in x]
    if isinstance(x, dict):
        return {k: round_floats(v, nd) for k, v in x.items()}
    return x


def build_report_data(world, sampler, args, wall):
    w = world
    deaths = {c: sum(v for k, v in w.stats.items() if k[0] == "death" and k[1] == c)
              for c in ("eaten", "starved", "old age")}
    return round_floats({
        "meta": {
            "seed": w.seed, "ticks": w.tick, "width": w.width, "height": w.height,
            "emitters": [e.spectrum for e in w.emitters],
            "rules": vars(w.rules), "mix": args.mix, "wall_seconds": round(wall, 1),
            "sample_every": args.sample_every, "resumed_from": args.resume,
            "total_births": w.total_births, "deaths": deaths,
        },
        "t": sampler.t,
        "counts": sampler.counts,
        "generation": sampler.gen,
        "traits": sampler.traits,
        "trait_labels": {k: label for k, label, _ in TRAITS},
        "spectrum": {"bins": SPECTRUM_BINS, "counts": sampler.spectrum},
        "families": sampler.families(),
    })


def write_report(data, path):
    with open(TEMPLATE) as f:
        html = f.read()
    title = "Evolution run: seed %s, %s ticks" % (data["meta"]["seed"], data["meta"]["ticks"])
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("__TITLE__", title).replace("__DATA__", payload)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write(html)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ticks", type=int, default=10000, help="ticks to run (after --resume)")
    ap.add_argument("--mix", type=parse_mix, default=None, help="absorber:parasite:predator")
    ap.add_argument("--set", action="append", metavar="RULE=VALUE")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--emitters", type=int, default=3)
    ap.add_argument("--sample-every", type=int, default=50)
    ap.add_argument("--out", default="runs/report.html")
    ap.add_argument("--lineage", metavar="PATH.jsonl", help="also write births/deaths")
    ap.add_argument("--checkpoint", metavar="PATH", help="save the world at the end")
    ap.add_argument("--resume", metavar="PATH", help="continue a saved world")
    args = ap.parse_args(argv)

    if args.resume:
        if args.set or args.mix:
            ap.error("--set/--mix can't change a resumed world")
        world = World.load(args.resume)
    else:
        area = args.width * args.height / (900 * 600)
        world = World(args.width, args.height, seed=args.seed, num_emitters=args.emitters,
                      strategy_mix=args.mix, rules=parse_rules(args.set),
                      max_population=max(600, int(600 * area)),
                      record_lineage=bool(args.lineage))
    sampler = Sampler(world)
    sampler.sample()
    t0 = time.time()
    end = world.tick + args.ticks
    while world.tick < end:
        world.step()
        if world.tick % args.sample_every == 0:
            sampler.sample()
            if world.tick % (args.sample_every * 20) == 0:
                print("tick %d  pop %d  gen %s" % (world.tick, len(world.organisms),
                                                   sampler.gen["median"][-1]),
                      file=sys.stderr)
        if not world.organisms:
            print("extinct at tick %d" % world.tick, file=sys.stderr)
            sampler.sample()
            break
    wall = time.time() - t0

    write_report(build_report_data(world, sampler, args, wall), args.out)
    print("report:", args.out)
    if args.lineage:
        if world.lineage is None:
            print("no lineage recorded (a resumed world keeps its original setting)",
                  file=sys.stderr)
        else:
            with open(args.lineage, "w") as f:
                for rec in world.lineage:
                    f.write(json.dumps(rec) + "\n")
            print("lineage:", args.lineage)
    if args.checkpoint:
        world.save(args.checkpoint)
        print("checkpoint:", args.checkpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
