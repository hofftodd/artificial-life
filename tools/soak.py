"""Long-run ecosystem probe: run many seeds and report strategy balance.

    python3 tools/soak.py --seeds 1 2 3 7 42 99 --ticks 3000
    python3 tools/soak.py --mix 8:1:1 --set eat_fraction=0.9 --set hunt_cooldown=16

--mix is absorber:parasite:predator founder weights (default: random genomes).
--set overrides a simcore.Rules field for every run.
"""
import argparse
import dataclasses
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import math  # noqa: E402

from simcore import (DYNAMIC_PRESET, EMITTER_RANGE, GROUP_RADIUS, MAX_POPULATION,  # noqa: E402
                     OPEN_PRESET, OPTIMAL_DISTANCE, SPECIATION_PRESET, STRATEGIES, Rules,
                     World)


def clumping(world, organisms):
    """Mean number of relatives within GROUP_RADIUS, per organism."""
    if not organisms:
        return 0.0
    world.grid.build(world.organisms)
    total = 0
    for o in organisms:
        for k in world.grid.near(o.x, o.y, GROUP_RADIUS):
            if k is not o and o.is_kin(k) and \
                    math.hypot(k.x - o.x, k.y - o.y) <= GROUP_RADIUS:
                total += 1
    return total / len(organisms)


def emitter_distance(world, o):
    return min(math.hypot(o.x - e.x, o.y - e.y) for e in world.emitters) \
        if world.emitters else 0.0


def ring_offset(world, o):
    if not world.emitters:
        return 0.0
    d = min(math.hypot(o.x - e.x, o.y - e.y) for e in world.emitters)
    return abs(d - OPTIMAL_DISTANCE)

# acceptance target for "stable coexistence" (see DESIGN.md). The ceiling
# guards against running into the hard population cap: at most 80% of
# MAX_POPULATION (600). It was 350 when populations were ~150; foraging and the
# self-shading fix legitimately raised carrying capacity.
TARGET_POPULATION = (80, int(0.8 * MAX_POPULATION))
TARGET_HUNTER_FRACTION = (0.03, 0.15)
TARGET_ABSORBER_FRACTION = 0.60
TARGET_SEEDS_WITH_ALL = 5 / 6


def parse_mix(text):
    if not text:
        return None
    weights = [float(w) for w in text.split(":")]
    if len(weights) != 3:
        raise argparse.ArgumentTypeError("mix is absorber:parasite:predator")
    return dict(zip(STRATEGIES, weights))


PRESETS = {"static": {}, "dynamic": DYNAMIC_PRESET, "open": OPEN_PRESET,
           "speciation": SPECIATION_PRESET}
ENV_HELP = ("static (defaults), dynamic (seasons, drift, rocks), open (ambient "
            "light + dispersal), speciation (marker kin + sex); join with '+', "
            "e.g. dynamic+open")


def base_rules(env):
    """Rules for an --env value: preset names joined with '+'."""
    values = {}
    for part in env.split("+"):
        if part not in PRESETS:
            raise ValueError("unknown env %r (choose from %s)" % (part, ", ".join(PRESETS)))
        values.update(PRESETS[part])
    return Rules(**values)


def env_arg(text):
    try:
        base_rules(text)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err))
    return text


def parse_rules(pairs, base=None):
    """Apply RULE=VALUE overrides on top of `base` (default Rules())."""
    fields = {f.name: f.type for f in dataclasses.fields(Rules)}
    overrides = {}
    for pair in pairs or ():
        key, _, value = pair.partition("=")
        if key not in fields:
            raise SystemExit("unknown rule %r; choose from %s" % (key, ", ".join(fields)))
        if fields[key] is bool:
            overrides[key] = value.lower() in ("1", "true", "yes", "on")
        elif fields[key] is tuple:
            overrides[key] = tuple(int(v) for v in value.split(","))
        else:
            overrides[key] = fields[key](value)
    return dataclasses.replace(base if base is not None else Rules(), **overrides)


def soak_run(seed, ticks=3000, mix=None, rules=None, sample_every=50, width=900, height=600,
             num_emitters=3):
    """Run one world and return a dict of balance metrics.

    Fractions and coefficients of variation are measured over the final third
    of the run, after the founding transient.
    """
    w = World(width, height, seed=seed, num_emitters=num_emitters, strategy_mix=mix, rules=rules,
              max_population=max(600, int(600 * width * height / (900 * 600))))
    series = {k: [] for k in ("total",) + STRATEGIES}
    for t in range(1, ticks + 1):
        w.step()
        if t % sample_every == 0:
            counts = dict.fromkeys(STRATEGIES, 0)
            for o in w.organisms:
                counts[o.strategy] += 1
            series["total"].append(len(w.organisms))
            for k in STRATEGIES:
                series[k].append(counts[k])

    tail = slice(len(series["total"]) * 2 // 3, None)
    total_tail = series["total"][tail]
    gens = sorted(o.generation for o in w.organisms)
    absorbers = [o for o in w.organisms if o.strategy == "absorber"]
    offsets = sorted(ring_offset(w, o) for o in absorbers)
    dists = sorted(emitter_distance(w, o) for o in w.organisms)
    out = {
        "far": sum(d > EMITTER_RANGE for d in dists) / len(dists) if dists else 0.0,
        "dist": dists[len(dists) // 2] if dists else 0.0,
        "clumping": clumping(w, absorbers),
        "ring_offset": offsets[len(offsets) // 2] if offsets else 0.0,
        "seed": seed,
        "gen_median": gens[len(gens) // 2] if gens else 0,
        "gen_max": gens[-1] if gens else 0,
        "final": {k: series[k][-1] for k in series},
        "mean_total": statistics.mean(total_tail) if total_tail else 0,
        "series": series,
        "stats": dict(w.stats),
    }
    for k in STRATEGIES:
        fracs = [c / n for c, n in zip(series[k][tail], total_tail) if n]
        out["frac_" + k] = statistics.mean(fracs) if fracs else 0.0
        vals = series[k][tail]
        mean = statistics.mean(vals) if vals else 0
        out["cv_" + k] = statistics.pstdev(vals) / mean if mean else 0.0
    eats = {k: v for k, v in w.stats.items() if k[0] == "eat"}
    out["kills"] = sum(eats.values())
    out["kin_kills"] = sum(v for k, v in eats.items() if k[3])
    out["kills_by_predators"] = sum(v for k, v in eats.items() if k[1] == "predator")
    deaths = {k: v for k, v in w.stats.items() if k[0] == "death"}
    out["deaths"] = {c: sum(v for k, v in deaths.items() if k[1] == c)
                     for c in ("eaten", "starved", "old age")}
    return out


def meets_target(runs):
    """Return (ok, reasons) for the stable-coexistence acceptance target."""
    reasons = []
    lo, hi = TARGET_POPULATION
    for r in runs:
        n = r["final"]["total"]
        if not lo <= n <= hi:
            reasons.append("seed %s: population %d outside %d-%d" % (r["seed"], n, lo, hi))
    with_all = sum(1 for r in runs if all(r["final"][k] > 0 for k in STRATEGIES))
    if with_all < TARGET_SEEDS_WITH_ALL * len(runs):
        reasons.append("all strategies alive at end on only %d/%d seeds" % (with_all, len(runs)))
    flo, fhi = TARGET_HUNTER_FRACTION
    for k in ("parasite", "predator"):
        m = statistics.mean(r["frac_" + k] for r in runs)
        if not flo <= m <= fhi:
            reasons.append("mean %s fraction %.3f outside %.2f-%.2f" % (k, m, flo, fhi))
    m = statistics.mean(r["frac_absorber"] for r in runs)
    if m < TARGET_ABSORBER_FRACTION:
        reasons.append("mean absorber fraction %.3f below %.2f" % (m, TARGET_ABSORBER_FRACTION))
    return not reasons, reasons


def _run(args):
    return soak_run(*args)


def run_many(seeds, ticks, mix, rules, workers=None, width=900, height=600, num_emitters=3):
    jobs = [(s, ticks, mix, rules, 50, width, height, num_emitters) for s in seeds]
    if workers == 1:
        return [_run(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run, jobs))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 7, 42, 99])
    ap.add_argument("--ticks", type=int, default=3000)
    ap.add_argument("--mix", type=parse_mix, default=None)
    ap.add_argument("--set", action="append", metavar="RULE=VALUE")
    ap.add_argument("--env", type=env_arg, default="static", help=ENV_HELP)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--emitters", type=int, default=3)
    args = ap.parse_args(argv)
    rules = parse_rules(args.set, base_rules(args.env))

    runs = run_many(args.seeds, args.ticks, args.mix, rules, args.workers,
                    args.width, args.height, args.emitters)
    print("rules:", rules)
    print("%5s %5s %13s %6s %15s %11s %6s %7s %9s %8s %6s %6s %5s %5s" % (
        "seed", "final", "A/P/X final", "mean", "frac A/P/X", "cv P/X",
        "kills", "by pred", "kin kills", "gen med", "clump", "ring", "far%", "dist"))
    for r in runs:
        f = r["final"]
        print("%5s %5d %13s %6.0f %15s %11s %6d %7d %9d %8d %6.1f %6.1f %5.0f %5.0f" % (
            r["seed"], f["total"],
            "%d/%d/%d" % (f["absorber"], f["parasite"], f["predator"]),
            r["mean_total"],
            "%.2f/%.2f/%.2f" % (r["frac_absorber"], r["frac_parasite"], r["frac_predator"]),
            "%.2f/%.2f" % (r["cv_parasite"], r["cv_predator"]),
            r["kills"], r["kills_by_predators"], r["kin_kills"], r["gen_median"],
            r["clumping"], r["ring_offset"], 100 * r["far"], r["dist"]))
    ok, reasons = meets_target(runs)
    print("target:", "MET" if ok else "NOT MET")
    for reason in reasons:
        print("  -", reason)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
