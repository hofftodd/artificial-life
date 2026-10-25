"""
An organism: state, sensing, movement (rule-driven and the evolved
controller), theft, predation, scavenging and reproduction.
"""
import math

from .brain import BRAIN_INPUTS, brain_throttle, default_brain
from .constants import (AMBIENT_MATCH, ARMOR_COST, ARMOR_SLOW, ARMS_BIAS,
                        ARMS_K, BITE_COST, CAMO_HARVEST, COVER_RANGE,
                        DEFENSE_CAP, DETECT_RANGE, ENERGY_CAP, FLEE_GAIN,
                        FIELD_CELL, FORAGE_EPS, FORAGE_NORM, FORAGE_RADIUS,
                        GROUP_RADIUS, KIN_SPACING, MATE_RANGE, MOTION_COST,
                        OPTIMAL_DISTANCE, PATROL_MIN_ENERGY, PREY_RANGE,
                        ROAM_LEG, ROAM_POOR, SENSE_COST, _COMPASS)
from .environment import in_cover, push_out
from .gene import Gene
from .utils import clamp, radiation_effect, spectral_match

class _UidCounter:
    """Process-wide organism id source. Restoring a checkpoint moves it past
    every id the saved world uses, so new organisms never collide."""

    def __init__(self):
        self.next_uid = 1

    def __next__(self):
        uid = self.next_uid
        self.next_uid += 1
        return uid

    def ensure_above(self, uid):
        self.next_uid = max(self.next_uid, uid + 1)


_ids = _UidCounter()


class Organism:
    def __init__(self, x, y, rng, genes=None, generation=0, parent=None):
        self.uid = next(_ids)
        self.x = float(x)
        self.y = float(y)
        self.energy = rng.uniform(3.0, 7.0)
        self.age = 0
        self.max_age = rng.randint(800, 2400)
        self.generation = generation
        self.direction = rng.uniform(0, math.pi * 2)
        self.dead = False
        self.hunt_cd = 0
        self.children = 0
        self.genes = genes if genes is not None else Gene.random(rng)
        self.strategy = self.genes.strategy()
        # founders start a family; descendants inherit it
        self.parent_uid = parent.uid if parent is not None else None
        self.family = parent.family if parent is not None else self.uid
        # None = kin means same family; a number = kin means markers within it
        self.kin_dist = parent.kin_dist if parent is not None else None
        self.mate_uid = None
        self.leg = 0                 # ticks left on a travel leg
        self.leg_dir = 0.0
        self.actual_speed = self.genes.speed   # brain mode: what it moved last tick

    @property
    def alive(self):
        return not self.dead and self.energy > 0 and self.age < self.max_age

    def is_kin(self, other):
        if self.kin_dist is None:
            return other.family == self.family
        return abs(other.genes.marker - self.genes.marker) <= self.kin_dist

    def _find_mate(self, world):
        """Nearest same-strategy organism within MATE_RANGE whose marker is
        within the world's mate_tolerance (assortative mating)."""
        tolerance = world.rules.mate_tolerance
        marker = self.genes.marker
        return self._nearest(world.grid, MATE_RANGE,
                             lambda o: o.strategy == self.strategy and o.alive
                             and abs(o.genes.marker - marker) <= tolerance)

    def spares(self, other):
        """Predators leave their own young alone until they come of age."""
        return other.parent_uid == self.uid and other.age < self.genes.offspring_protection

    def can_eat(self, other, world):
        """Whether this organism could overpower and eat `other` right now."""
        rules = world.rules
        if other.energy >= rules.weak_prey_energy * self.genes.eating_ability:
            return False
        if other.strategy == "predator" and not rules.predators_are_prey:
            return False
        if self.spares(other):
            return False
        if rules.kin_immunity == "all" or (
                rules.kin_immunity == "non_predators" and self.strategy != "predator"):
            if self.is_kin(other):
                return False
        # the neighbour scan is the expensive check, so it goes last
        return not (rules.group_defense
                    and self._defended(other, rules.group_defense, world.grid))

    def _defended(self, prey, needed, grid):
        """Whether `prey` has at least `needed` relatives close enough to fend
        off an attack."""
        return self._guards(prey, grid, needed) >= needed

    def _guards(self, prey, grid, cap):
        """Relatives of `prey` (other than this attacker) within GROUP_RADIUS,
        counted up to `cap`."""
        count = 0
        for o in grid.near(prey.x, prey.y, GROUP_RADIUS):
            if o is prey or o is self or o.dead or not prey.is_kin(o):
                continue
            if math.hypot(o.x - prey.x, o.y - prey.y) <= GROUP_RADIUS:
                count += 1
                if count >= cap:
                    break
        return count

    def _nearest(self, grid, radius, accept=None):
        best, best_d = None, radius
        for other in grid.near(self.x, self.y, radius):
            if other is self or other.dead:
                continue
            d = math.hypot(other.x - self.x, other.y - self.y)
            # distance first: accept() can be expensive (see can_eat)
            if d > best_d:
                continue
            if accept is not None and not accept(other):
                continue
            best, best_d = other, d
        return best

    def _victim_filter(self, world):
        if self.strategy == "predator":
            # only chase what could actually be eaten on arrival
            base = lambda o: self.can_eat(o, world)  # noqa: E731
        elif world.rules.host_min_energy:
            floor = world.rules.host_min_energy
            base = lambda o: o.strategy != "parasite" and o.energy > floor  # noqa: E731
        else:
            base = lambda o: o.strategy != "parasite"  # noqa: E731
        rules = world.rules
        if rules.arms_race:
            sense = self.genes.organism_sensing * 40
            lo, hi = DETECT_RANGE
            perception = self.genes.perception
            inner = base

            def detected(o):
                # camouflage shortens the range a hunter can spot a target at;
                # perception extends it
                reach = sense * clamp(1.0 - o.genes.camouflage + perception, lo, hi)
                if math.hypot(o.x - self.x, o.y - self.y) > reach:
                    return False
                return inner(o)
            base = detected
        if not world.rocks:
            return base
        chase = base

        def visible(o):
            # organisms in cover can only be spotted up close
            if (math.hypot(o.x - self.x, o.y - self.y) > rules.hidden_detect
                    and in_cover(o.x, o.y, world.rocks, rules.cover_range)):
                return False
            return chase(o)
        return visible

    def _forage_score(self, world, key, own_key, matches):
        """Expected net radiation gain per tick if this organism stood in
        field cell `key`, counting grazing and crowding; None where there's no
        light. `matches` are its spectral matches to each emitter."""
        field = world.field
        demand = field.demand.get(key, 0.0)
        if key != own_key:
            demand += self.genes.absorption   # it would join that cell
        share = 1.0 / max(1.0, demand)
        reserve = world.reserve.get(key, 1.0)
        eff = self.genes.absorption_efficiency
        total, lit = 0.0, False
        if field.ambient > 0:
            lit = True
            total += radiation_effect(field.ambient, AMBIENT_MATCH, eff) * share * reserve
        for layer, match in zip(field.by_emitter, matches):
            rad = layer.get(key, 0.0)
            if rad > 0:
                lit = True
                g = radiation_effect(rad, match, eff)
                total += g * share * reserve if g > 0 else g
        return total if lit else None

    def _forage_target(self, world):
        """The best of the current spot and 8 compass points at
        radiation_sensing x FORAGE_RADIUS, or None if none of them is lit.
        Light is per field cell, so each cell is scored once."""
        spectrum = self.genes.absorption_spectrum
        matches = [spectral_match(e.spectrum, spectrum) for e in world.emitters]
        own_key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
        here = self._forage_score(world, own_key, own_key, matches)
        best, best_score = None, here
        seen = {own_key}
        r = self.genes.radiation_sensing * FORAGE_RADIUS
        w, h = world.width, world.height
        for ux, uy in _COMPASS:
            x, y = self.x + ux * r, self.y + uy * r
            if not (0 <= x < w and 0 <= y < h):
                continue
            key = (int(x // FIELD_CELL), int(y // FIELD_CELL))
            if key in seen:
                continue            # same cell, same score: can't win by FORAGE_EPS
            seen.add(key)
            score = self._forage_score(world, key, own_key, matches)
            if score is None:
                continue
            if best_score is None or score > best_score + FORAGE_EPS:
                best, best_score = (x, y), score
        if best is not None:
            return best
        return (self.x, self.y) if here is not None else None

    def _emitter_target(self, world):
        best_e, best_d = None, self.genes.radiation_sensing * 200
        for e in world.emitters:
            d = math.hypot(e.x - self.x, e.y - self.y)
            if d < best_d:
                best_e, best_d = e, d
        if best_e is None:
            return None
        dx, dy = self.x - best_e.x, self.y - best_e.y
        d = math.hypot(dx, dy)
        if d < 1e-9:
            return None
        return (best_e.x + dx / d * OPTIMAL_DISTANCE,
                best_e.y + dy / d * OPTIMAL_DISTANCE)

    def _move(self, world):
        if world.rules.movement == "brain":
            return self._brain_move(world)
        rules = world.rules
        sense = self.genes.organism_sensing * 40
        hunter = self.strategy in ("predator", "parasite")
        tx = ty = None
        heading = None
        if hunter:
            reach = sense * DETECT_RANGE[1] if rules.arms_race else sense
            victim = self._nearest(world.grid, reach, self._victim_filter(world))
            if victim is not None:
                tx, ty = victim.x, victim.y
                self.leg = 0                 # a chase ends any travel leg
            elif self.strategy == "predator" and world.carcasses:
                food = self._nearest_carcass(world, reach)
                if food is not None:
                    tx, ty = food.x, food.y
        if tx is None and self.leg > 0:
            self.leg -= 1
            heading = self.leg_dir
        elif tx is None and self._start_leg(world, hunter):
            heading = self.leg_dir
        elif tx is None:
            target = None
            if rules.movement == "forage":
                target = self._forage_target(world)
            if target is None:
                target = self._emitter_target(world)
            if target is not None:
                tx, ty = target

        vx = vy = 0.0
        if heading is not None:
            vx, vy = math.cos(heading), math.sin(heading)
        elif tx is not None:
            d = math.hypot(tx - self.x, ty - self.y)
            if d > 0.5:
                vx, vy = (tx - self.x) / d, (ty - self.y) / d
        # wary prey run from the nearest predator they sense
        if rules.flee and self.strategy != "predator" and self.genes.wariness > 0.05:
            threat = self._nearest(world.grid, sense, lambda o: o.strategy == "predator")
            if threat is not None:
                d = math.hypot(threat.x - self.x, threat.y - self.y)
                if d > 1e-9:
                    pull = FLEE_GAIN * self.genes.wariness
                    vx -= pull * (threat.x - self.x) / d
                    vy -= pull * (threat.y - self.y) / d
        # communal organisms drift toward the nearest relative, but stop short
        # of piling onto it
        if self.genes.kin_affinity > 0.05:
            kin = self._nearest(world.grid, sense, self.is_kin)
            if kin is not None:
                d = math.hypot(kin.x - self.x, kin.y - self.y)
                if d > KIN_SPACING:
                    vx += self.genes.kin_affinity * (kin.x - self.x) / d
                    vy += self.genes.kin_affinity * (kin.y - self.y) / d
        # cover seekers drift toward the nearest sensed rock until they're
        # within cover range of its edge
        if self.genes.cover_affinity > 0.05 and world.rocks:
            rock, gap = None, sense
            for k in world.rocks:
                g = math.hypot(k.x - self.x, k.y - self.y) - k.r
                if g < gap:
                    rock, gap = k, g
            if rock is not None and gap > COVER_RANGE / 2:
                d = gap + rock.r
                vx += self.genes.cover_affinity * (rock.x - self.x) / d
                vy += self.genes.cover_affinity * (rock.y - self.y) / d

        if vx or vy:
            self.direction = math.atan2(vy, vx)
        elif tx is not None:
            self.direction += world.rng.gauss(0, 0.1)
        else:
            self.direction += world.rng.gauss(0, 0.4)
        speed = self.genes.speed
        if world.rules.arms_race:
            speed *= 1.0 - ARMOR_SLOW * self.genes.armor
        x = clamp(self.x + math.cos(self.direction) * speed, 5, world.width - 5)
        y = clamp(self.y + math.sin(self.direction) * speed, 5, world.height - 5)
        if self.leg > 0:
            # travel legs bounce off the world's edges
            if x <= 5 or x >= world.width - 5:
                self.leg_dir = math.pi - self.leg_dir
            if y <= 5 or y >= world.height - 5:
                self.leg_dir = -self.leg_dir
        if world.rocks:
            x, y = push_out(x, y, world.rocks)
        self.x, self.y = x, y

    def _brain_move(self, world):
        """Steer by the evolved controller: a hunger-modulated weighted sum
        of sensed directions, at an evolved throttle."""
        rules = world.rules
        g = self.genes
        brain = g.brain or default_brain(self.strategy)
        hunger = 1.0 - clamp(self.energy / ENERGY_CAP, 0.0, 1.0)
        sense = g.organism_sensing * 40
        x, y = self.x, self.y
        senses = {}

        def toward(tx, ty):
            d = math.hypot(tx - x, ty - y)
            return ((tx - x) / d, (ty - y) / d) if d > 0.5 else None

        t = self._forage_target(world)
        if t is not None:
            senses["light"] = toward(*t)
        t = self._emitter_target(world)
        if t is not None:
            senses["emitter"] = toward(*t)
        if self.strategy in ("predator", "parasite"):
            reach = sense * DETECT_RANGE[1] if rules.arms_race else sense
            prey = self._nearest(world.grid, reach, self._victim_filter(world))
            if prey is not None:
                senses["prey"] = toward(prey.x, prey.y)
        # one pass for the nearest predator, relative and stranger
        near = {"threat": (None, sense), "kin": (None, sense), "stranger": (None, sense)}
        for o in world.grid.near(x, y, sense):
            if o is self or o.dead:
                continue
            d = math.hypot(o.x - x, o.y - y)
            if d > sense:
                continue
            if o.strategy == "predator" and d < near["threat"][1]:
                near["threat"] = (o, d)
            slot = "kin" if self.is_kin(o) else "stranger"
            if d < near[slot][1]:
                near[slot] = (o, d)
        for name, (o, _d) in near.items():
            if o is not None:
                senses[name] = toward(o.x, o.y)
        if world.rocks:
            rock, gap = None, sense
            for k in world.rocks:
                edge = math.hypot(k.x - x, k.y - y) - k.r
                if edge < gap:
                    rock, gap = k, edge
            if rock is not None:
                senses["rock"] = toward(rock.x, rock.y)
        if world.carcasses:
            c = self._nearest_carcass(world, sense)
            if c is not None:
                senses["carcass"] = toward(c.x, c.y)
        senses["momentum"] = (math.cos(self.direction), math.sin(self.direction))
        a = world.rng.uniform(0.0, 2.0 * math.pi)
        senses["noise"] = (math.cos(a), math.sin(a))

        hx = hy = 0.0
        for i, name in enumerate(BRAIN_INPUTS):
            v = senses.get(name)
            if v is not None:
                w = brain[2 * i] + brain[2 * i + 1] * hunger
                hx += w * v[0]
                hy += w * v[1]
        if math.hypot(hx, hy) > 1e-6:
            self.direction = math.atan2(hy, hx)
        else:
            self.direction += world.rng.gauss(0, 0.1)

        own_key = (int(x // FIELD_CELL), int(y // FIELD_CELL))
        matches = [spectral_match(e.spectrum, g.absorption_spectrum) for e in world.emitters]
        here = self._forage_score(world, own_key, own_key, matches)
        light = clamp((here or 0.0) / FORAGE_NORM, 0.0, 1.0)
        speed = g.speed * brain_throttle(brain, hunger, light)
        if rules.arms_race:
            speed *= 1.0 - ARMOR_SLOW * g.armor
        self.actual_speed = speed
        nx = clamp(x + math.cos(self.direction) * speed, 5, world.width - 5)
        ny = clamp(y + math.sin(self.direction) * speed, 5, world.height - 5)
        if world.rocks:
            nx, ny = push_out(nx, ny, world.rocks)
        self.x, self.y = nx, ny

    def _start_leg(self, world, hunter):
        """Maybe set off on a straight travel leg; returns whether it did."""
        rules = world.rules
        if rules.patrol and hunter and self.energy > PATROL_MIN_ENERGY:
            # patrols keep roughly the current heading, so searches cover ground
            self.leg_dir = self.direction + world.rng.uniform(-1.0, 1.0)
        elif rules.roam_rate and self.genes.roaming > 0.05:
            chance = rules.roam_rate * self.genes.roaming
            key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
            if world.field.share_at(self.x, self.y) * world.reserve.get(key, 1.0) < ROAM_POOR:
                chance *= 3.0
            if world.rng.random() >= chance:
                return False
            self.leg_dir = world.rng.uniform(0.0, 2.0 * math.pi)
        else:
            return False
        self.leg = world.rng.randint(*ROAM_LEG)
        return True

    def _steal(self, world):
        s = self.genes.stealing_ability
        if s <= 0.05:
            return
        floor = world.rules.host_min_energy
        if floor:
            # move-on parasites drain the richest host in reach, and leave
            # hosts that are already poor
            host, best = None, floor
            for other in world.grid.near(self.x, self.y, PREY_RANGE):
                if other is self or other.dead or other.strategy == "parasite":
                    continue
                if other.energy > best and \
                        math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                    host, best = other, other.energy
            if host is not None:
                amt = host.energy * s * world.rules.steal_rate
                host.energy -= amt
                self.energy += amt
                world.events.append(("steal", self.x, self.y, host.x, host.y))
                world.stats[("steal", self.strategy, host.strategy, self.is_kin(host))] += 1
            return
        for other in world.grid.query(self.x, self.y, PREY_RANGE):
            if other is self or other.dead or other.energy <= 0.1:
                continue
            if other.strategy == "parasite":
                continue
            if math.hypot(other.x - self.x, other.y - self.y) <= PREY_RANGE:
                amt = other.energy * s * world.rules.steal_rate
                other.energy -= amt
                self.energy += amt
                world.events.append(("steal", self.x, self.y, other.x, other.y))
                world.stats[("steal", self.strategy, other.strategy, self.is_kin(other))] += 1
                break

    def _eat(self, world):
        if self.genes.eating_ability <= 0.05:
            return
        if self.hunt_cd > 0:
            self.hunt_cd -= 1
            return
        # weak eaters can only finish off prey that is nearly spent already
        # (see can_eat)
        rules = world.rules
        prey = None
        for other in world.grid.near(self.x, self.y, PREY_RANGE):
            if other is self or other.dead:
                continue
            if math.hypot(other.x - self.x, other.y - self.y) > PREY_RANGE:
                continue
            if (prey is None or other.energy < prey.energy) and self.can_eat(other, world):
                prey = other
        if prey is not None:
            if rules.defense_per_kin:
                n = self._guards(prey, world.grid, DEFENSE_CAP)
                if n and world.rng.random() >= (1.0 - rules.defense_per_kin) ** n:
                    # relatives fended it off; the attack still costs a cooldown
                    self.hunt_cd = rules.hunt_cooldown
                    world.stats[("repelled", self.strategy, prey.strategy)] += 1
                    return
            if rules.arms_race:
                edge = ARMS_K * (self.genes.bite - prey.genes.armor) + ARMS_BIAS
                if world.rng.random() >= 1.0 / (1.0 + math.exp(-edge)):
                    # the prey's armour held; the attack still costs a cooldown
                    self.hunt_cd = rules.hunt_cooldown
                    world.stats[("resisted", self.strategy, prey.strategy)] += 1
                    return
            prey.dead = True
            meal = min(max(prey.energy, 0.0) * rules.eat_fraction, rules.eat_gain_cap)
            self.energy += meal
            if rules.carcass_fraction:
                world.leave_carcass(prey.x, prey.y, (max(prey.energy, 0.0) - meal)
                                    * rules.carcass_fraction)
            self.hunt_cd = rules.hunt_cooldown
            world.events.append(("eat", self.x, self.y, prey.x, prey.y))
            world.stats[("eat", self.strategy, prey.strategy, self.is_kin(prey))] += 1

    def _nearest_carcass(self, world, radius):
        best, best_d = None, radius
        for c in world.carcass_grid.near(self.x, self.y, radius):
            if c.energy <= 0:
                continue
            d = math.hypot(c.x - self.x, c.y - self.y)
            if d <= best_d:
                best, best_d = c, d
        return best

    def _scavenge(self, world):
        """Organisms that can eat take a bite from the nearest carcass."""
        if self.genes.eating_ability <= 0.05:
            return
        c = self._nearest_carcass(world, PREY_RANGE)
        if c is None:
            return
        bite = min(c.energy, world.rules.scavenge_bite)
        c.energy -= bite
        self.energy += bite
        world.stats[("scavenge", self.strategy)] += 1

    def _reproduce(self, world):
        cost = world.rules.repro_energy
        if (self.energy > cost
                and len(world.organisms) < world.max_population
                and world.rng.random() < world.repro_chance):
            angle = world.rng.uniform(0, math.pi * 2)
            dist = world.rng.uniform(2, 12 + self.genes.dispersal * world.rules.dispersal_max)
            nx = clamp(self.x + math.cos(angle) * dist, 5, world.width - 5)
            ny = clamp(self.y + math.sin(angle) * dist, 5, world.height - 5)
            if world.rocks:
                nx, ny = push_out(nx, ny, world.rocks)
            genes, mate = self.genes, None
            if world.rules.sex_rate and world.rng.random() < world.rules.sex_rate:
                mate = self._find_mate(world)
                if mate is not None:
                    genes = Gene.crossover(self.genes, mate.genes, world.rng)
            child = Organism(nx, ny, world.rng,
                             genes.mutated(world.rng, world.strategy_mutation),
                             self.generation + 1, parent=self)
            if mate is not None:
                child.mate_uid = mate.uid
            world.stats[("birth", "sexual" if mate is not None else "asexual")] += 1
            world.organisms.append(child)
            self.children += 1
            if world.rules.lifespan is not None:
                child.max_age = world.rules.draw_max_age(child.strategy, world.rng)
            if world.rules.child_share is not None:
                child.energy = cost * world.rules.child_share
            if world.lineage is not None:
                world.record_birth(child)
            self.energy -= cost

    def update(self, world):
        self.age += 1

        share = world.field.share_at(self.x, self.y)
        if world.rules.arms_race and self.genes.camouflage:
            share *= 1.0 - CAMO_HARVEST * self.genes.camouflage
        grazing = world.rules.depletion_rate > 0
        if grazing:
            key = (int(self.x // FIELD_CELL), int(self.y // FIELD_CELL))
            share *= world.reserve.get(key, 1.0)
            harvested = 0.0
        for i, e in enumerate(world.emitters):
            rad = world.field.intensity_at(self.x, self.y, i)
            if rad > 0:
                gain = radiation_effect(
                    rad,
                    spectral_match(e.spectrum, self.genes.absorption_spectrum),
                    self.genes.absorption_efficiency,
                )
                # harvest is shared with cell-mates (and limited by the cell's
                # grazed reserve); radiation damage is not
                if gain > 0:
                    self.energy += gain * share
                    if grazing:
                        harvested += gain * share
                else:
                    self.energy += gain
        ambient = world.field.ambient
        if ambient > 0:
            gain = radiation_effect(ambient, AMBIENT_MATCH, self.genes.absorption_efficiency)
            if gain > 0:
                self.energy += gain * share
                if grazing:
                    harvested += gain * share
        if grazing and harvested:
            world.harvest[key] = world.harvest.get(key, 0.0) + harvested

        self._move(world)
        self._steal(world)
        self._eat(world)
        if world.carcasses:
            self._scavenge(world)

        moved = self.actual_speed if world.rules.movement == "brain" else self.genes.speed
        cost = (MOTION_COST * moved
                + SENSE_COST * (self.genes.radiation_sensing + self.genes.organism_sensing))
        if self.strategy in ("predator", "parasite"):
            cost += world.rules.strategy_cost
        if world.rules.arms_race:
            g = self.genes
            cost += ARMOR_COST * g.armor + SENSE_COST * g.perception
            if self.strategy in ("predator", "parasite"):
                cost += BITE_COST * g.bite
        if world.rules.flee:
            cost += SENSE_COST * self.genes.wariness
        self.energy -= cost
        self.energy = min(self.energy, ENERGY_CAP)

        self._reproduce(world)

    def death_cause(self):
        if self.dead:
            return "eaten"
        if self.age >= self.max_age:
            return "old age"
        return "starved"
