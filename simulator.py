"""Pygame GUI for the artificial life simulator (see simcore.py for the model)."""
import colorsys
import math
import os
import sys
import types

import pygame


def _fix_pygame_font():
    # pygame 2.6.1 has a circular import between pygame.font and pygame.sysfont
    # that breaks on Python 3.14; pre-seed a stub to break the cycle
    try:
        import pygame.font  # noqa: F401
    except Exception:
        from pygame._freetype import Font as _FTFont
        stub = types.ModuleType("pygame.font")
        stub.Font = _FTFont
        sys.modules["pygame.font"] = stub
        import pygame.sysfont
        del sys.modules["pygame.font"]
        import pygame.font  # noqa: F401


_fix_pygame_font()

import simcore
from simcore import (EMITTER_RANGE, ENERGY_CAP, FIELD_CELL, LETHAL_DISTANCE,
                     OPTIMAL_DISTANCE, RADIATION_DANGER, RADIATION_ENERGY,
                     STRATEGIES, clamp)

WIDTH, HEIGHT = 900, 600
BACKGROUND = (8, 10, 24)
TEXT = (220, 220, 235)
DIM_TEXT = (150, 150, 170)

STRATEGY_COLORS = {
    "absorber": (110, 220, 130),
    "parasite": (190, 120, 255),
    "predator": (255, 90, 80),
}
STRATEGY_PLURALS = {"absorber": "absorbers", "parasite": "parasites", "predator": "predators"}
DEATH_COLORS = {
    "eaten": (255, 80, 60),
    "starved": (150, 150, 170),
    "old age": (235, 235, 245),
}
EFFECT_FRAMES = {"steal": 8, "eat": 24, "death": 30}
PANE_W = 300                 # side pane for stats, legend and inspector
PANE_MIN_H = 600
PANE_BG = (16, 17, 28)
PANE_EDGE = (55, 57, 80)
ROCK_FILL = (62, 58, 54)
CARCASS_COLOR = (150, 110, 70)
ROCK_RIM = (104, 98, 90)
MAX_PIPS = 6

DEFAULT_SETTINGS = {
    "emitters": simcore.NUM_EMITTERS,
    "rocks": simcore.Rules.dynamic().num_rocks,
    "dynamic": 1,
    "open": 1,
    "organisms": simcore.START_POPULATION,
    "absorber": 80,
    "parasite": 10,
    "predator": 10,
    "width": WIDTH,
    "height": HEIGHT,
}


def spectrum_color(s):
    hue = (s - 1) / 99.0 * 0.66
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def scale(color, k):
    return tuple(int(clamp(c * k, 0, 255)) for c in color)


def specialization(genes):
    """0 for a perfect generalist (1/3 each), 1 for a pure specialist."""
    top = max(genes.absorption, genes.parasitism, genes.predation)
    return (top - 1.0 / 3.0) / (2.0 / 3.0)


def organism_radius(o):
    return 3 + 4 * clamp(o.energy / ENERGY_CAP, 0.0, 1.0)


def draw_organism(screen, o):
    """Shape = strategy, hue = absorption spectrum, size = energy, vividness =
    how specialized the genome is, outline dots = offspring so far."""
    base = spectrum_color(o.genes.absorption_spectrum)
    color = scale(base, 0.35 + 0.65 * specialization(o.genes))
    outline = STRATEGY_COLORS[o.strategy]
    x, y = int(o.x), int(o.y)
    s = organism_radius(o)
    if o.strategy == "absorber":
        pygame.draw.circle(screen, color, (x, y), int(s))
        pygame.draw.circle(screen, outline, (x, y), int(s), 1)
    elif o.strategy == "parasite":
        pts = [(x, y - s - 1), (x + s + 1, y), (x, y + s + 1), (x - s - 1, y)]
        pygame.draw.polygon(screen, color, pts)
        pygame.draw.polygon(screen, outline, pts, 1)
    else:
        a = o.direction
        pts = [
            (x + math.cos(a) * s * 1.5, y + math.sin(a) * s * 1.5),
            (x + math.cos(a + 2.5) * s, y + math.sin(a + 2.5) * s),
            (x + math.cos(a - 2.5) * s, y + math.sin(a - 2.5) * s),
        ]
        pygame.draw.polygon(screen, color, pts)
        pygame.draw.polygon(screen, outline, pts, 1)
    pips = min(o.children, MAX_PIPS)
    for i in range(pips):
        a = -math.pi / 2 + i * 2 * math.pi / MAX_PIPS
        pygame.draw.circle(screen, (255, 230, 120),
                           (int(x + math.cos(a) * (s + 4)), int(y + math.sin(a) * (s + 4))), 1)


class FieldLayer:
    """Reusable alpha surface for the radiation overlay."""

    def __init__(self):
        self.surf = None

    def draw(self, screen, world):
        size = (world.width, world.height)
        if self.surf is None or self.surf.get_size() != size:
            self.surf = pygame.Surface(size, pygame.SRCALPHA)
        for i, e in enumerate(world.emitters):
            self.surf.fill((0, 0, 0, 0))
            base = spectrum_color(e.spectrum)
            for (cx, cy), intensity in world.field.by_emitter[i].items():
                color = (255, 60, 60) if intensity > RADIATION_DANGER else base
                # grazed cells (see World.reserve) show dimmer
                reserve = world.reserve.get((cx, cy), 1.0)
                alpha = int(clamp(intensity * reserve / RADIATION_ENERGY, 0.0, 1.0) * 110)
                if alpha > 0:
                    pygame.draw.rect(self.surf, (*color, alpha),
                                     (cx * FIELD_CELL, cy * FIELD_CELL, FIELD_CELL, FIELD_CELL))
            screen.blit(self.surf, (0, 0))


def draw_carcasses(screen, world):
    for c in world.carcasses:
        r = 1 + int(min(4, c.energy))
        pygame.draw.circle(screen, CARCASS_COLOR, (int(c.x), int(c.y)), r)


def draw_rocks(screen, world):
    for rock in world.rocks:
        c = (int(rock.x), int(rock.y))
        pygame.draw.circle(screen, ROCK_FILL, c, int(rock.r))
        pygame.draw.circle(screen, ROCK_RIM, c, int(rock.r), 2)


def draw_emitters(screen, world, font, t):
    for i, e in enumerate(world.emitters):
        col = spectrum_color(e.spectrum)
        # the halo dims with the emitter's seasonal output
        k = 6.0 / max(e.strength, 0.05)
        pygame.draw.circle(screen, (int(col[0] / k), int(col[1] / k), int(col[2] / k)),
                           (int(e.x), int(e.y)), EMITTER_RANGE)
        pygame.draw.circle(screen, (255, 70, 70), (int(e.x), int(e.y)), int(LETHAL_DISTANCE), 1)
        pygame.draw.circle(screen, (90, 220, 120), (int(e.x), int(e.y)), int(OPTIMAL_DISTANCE), 1)
        pulse = 0.5 + 0.5 * math.sin(t * 2 + e.phase)
        pygame.draw.circle(screen, col, (int(e.x), int(e.y)), 5 + int(pulse * 6), 1)
        pygame.draw.circle(screen, (255, 255, 255), (int(e.x), int(e.y)), 4)


def draw_emitter_labels(screen, world, font):
    for i, e in enumerate(world.emitters):
        col = spectrum_color(e.spectrum)
        if font is not None:
            label = "E%d  spectrum %d" % (i + 1, round(e.spectrum))
            if e.strength < 0.995:
                label += "  output %d%%" % round(100 * e.strength)
            img = font.render(label, True, col)
            px = clamp(int(e.x) + 10, 2, world.width - img.get_width() - 4)
            py = clamp(int(e.y) - 28, 2, world.height - img.get_height() - 4)
            bg = pygame.Surface((img.get_width() + 8, img.get_height() + 6), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 160))
            screen.blit(bg, (px - 4, py - 3))
            screen.blit(img, (px, py))


class Effects:
    """Short-lived markers for things that happened in the last few ticks."""

    def __init__(self):
        self.items = []  # [kind, data, frames_left]
        self.surf = None

    def add_world_events(self, events):
        for ev in events:
            kind = ev[0]
            self.items.append([kind, ev[1:], EFFECT_FRAMES[kind]])

    def age(self):
        for item in self.items:
            item[2] -= 1
        self.items = [item for item in self.items if item[2] > 0]

    def clear(self):
        self.items = []

    def draw(self, screen):
        if not self.items:
            return
        size = screen.get_size()
        if self.surf is None or self.surf.get_size() != size:
            self.surf = pygame.Surface(size, pygame.SRCALPHA)
        self.surf.fill((0, 0, 0, 0))
        for kind, data, left in self.items:
            fade = left / EFFECT_FRAMES[kind]
            if kind == "steal":
                x, y, vx, vy = data
                pygame.draw.line(self.surf, (*STRATEGY_COLORS["parasite"], int(220 * fade)),
                                 (x, y), (vx, vy), 2)
            elif kind == "eat":
                x, y, px, py = data
                a = int(255 * fade)
                pygame.draw.line(self.surf, (255, 90, 60, a), (x, y), (px, py), 3)
                pygame.draw.circle(self.surf, (255, 200, 80, a), (int(px), int(py)),
                                   int(4 + 10 * (1 - fade)), 2)
            else:
                x, y, cause, _strategy = data
                col = DEATH_COLORS.get(cause, (220, 220, 220))
                pygame.draw.circle(self.surf, (*col, int(200 * fade)), (int(x), int(y)),
                                   int(3 + 12 * (1 - fade)), 1)
                if cause == "eaten":
                    d = 4
                    pygame.draw.line(self.surf, (*col, int(230 * fade)),
                                     (x - d, y - d), (x + d, y + d), 2)
                    pygame.draw.line(self.surf, (*col, int(230 * fade)),
                                     (x - d, y + d), (x + d, y - d), 2)
        screen.blit(self.surf, (0, 0))


def strategy_stats(world):
    stats = {k: {"n": 0, "energy": 0.0, "children": 0, "best": 0} for k in STRATEGIES}
    for o in world.organisms:
        s = stats[o.strategy]
        s["n"] += 1
        s["energy"] += o.energy
        s["children"] += o.children
        s["best"] = max(s["best"], o.children)
    return stats


def panel(screen, rect, alpha=150):
    bg = pygame.Surface(rect.size, pygame.SRCALPHA)
    bg.fill((0, 0, 0, alpha))
    screen.blit(bg, rect.topleft)


def bar(screen, x, y, w, h, frac, color):
    pygame.draw.rect(screen, (50, 50, 65), (x, y, w, h))
    pygame.draw.rect(screen, color, (x, y, int(w * clamp(frac, 0.0, 1.0)), h))


def budget_bar(screen, x, y, w, h, shares):
    """Stacked bar of absorber / parasite / predator shares."""
    for k, share in zip(STRATEGIES, shares):
        seg = int(round(w * share))
        if seg > 0:
            pygame.draw.rect(screen, STRATEGY_COLORS[k], (x, y, seg, h))
        x += seg


def pane_rect(world):
    """The side pane to the right of the world view."""
    return pygame.Rect(world.width, 0, PANE_W, max(world.height, PANE_MIN_H))


def draw_pane(screen, fonts, world, paused, show_legend, selected):
    """Everything that isn't the world itself: stats, then the inspector (when
    an organism is selected) or the legend, then the key help."""
    font, big, small = fonts
    rect = pane_rect(world)
    pygame.draw.rect(screen, PANE_BG, rect)
    pygame.draw.line(screen, PANE_EDGE, rect.topleft, rect.bottomleft, 1)
    x = rect.x + 14
    y = draw_hud(screen, fonts, world, paused, x, 10)
    y += 10
    pygame.draw.line(screen, PANE_EDGE, (x, y), (rect.right - 14, y), 1)
    y += 10
    if selected is not None:
        draw_inspector(screen, fonts, world, selected, x, y)
    elif show_legend and small is not None:
        draw_legend(screen, small, x, y)
    if small is not None:
        for i, text in enumerate(("SPACE start/stop   R new simulation",
                                  "click: inspect   H legend   ESC quit")):
            screen.blit(small.render(text, True, DIM_TEXT), (x, rect.bottom - 36 + 16 * i))


def draw_hud(screen, fonts, world, paused, x, y):
    """Generation, population and per-strategy stats. Returns the bottom y."""
    font, big, small = fonts
    if big is not None:
        screen.blit(big.render("generation %d" % world.generation, True, (240, 240, 250)), (x, y))
        y += 32
    if font is not None:
        stats = strategy_stats(world)
        state = "STOPPED" if paused else "RUNNING"
        screen.blit(font.render("population %d   tick %d" % (len(world.organisms), world.tick),
                                True, TEXT), (x, y))
        y += 20
        screen.blit(font.render(state, True, (255, 200, 80) if paused else DIM_TEXT), (x, y))
        y += 24
        for k in STRATEGIES:
            s = stats[k]
            n = s["n"]
            screen.blit(font.render("%s %d" % (STRATEGY_PLURALS[k], n), True,
                                    STRATEGY_COLORS[k]), (x, y))
            y += 18
            if n and small is not None:
                screen.blit(small.render("energy %.1f   offspring %.1f (best %d)" % (
                    s["energy"] / n, s["children"] / n, s["best"]), True, TEXT), (x + 10, y))
                y += 16
    return y


def draw_legend(screen, small, x0, y0):
    for i in range(12):
        pygame.draw.rect(screen, spectrum_color(1 + i * 8), (x0 + i * 12, y0, 12, 10))
    screen.blit(small.render("spectrum 1", True, TEXT), (x0, y0 + 14))
    screen.blit(small.render("100", True, TEXT), (x0 + 132, y0 + 14))
    y0 += 38

    def row(text):
        nonlocal y0
        screen.blit(small.render(text, True, TEXT), (x0 + 18, y0))
        y0 += 18

    pygame.draw.circle(screen, STRATEGY_COLORS["absorber"], (x0 + 6, y0 + 5), 5)
    row("circle: absorber")
    pygame.draw.polygon(screen, STRATEGY_COLORS["parasite"],
                        [(x0 + 6, y0), (x0 + 11, y0 + 5), (x0 + 6, y0 + 10), (x0 + 1, y0 + 5)])
    row("diamond: parasite")
    pygame.draw.polygon(screen, STRATEGY_COLORS["predator"],
                        [(x0 + 11, y0 + 5), (x0 + 1, y0), (x0 + 1, y0 + 10)])
    row("triangle: predator")
    row("size = energy,  vivid = specialist")
    for i in range(3):
        pygame.draw.circle(screen, (255, 230, 120), (x0 + 2 + i * 4, y0 + 6), 1)
    row("dots = offspring (fitness)")
    pygame.draw.line(screen, STRATEGY_COLORS["parasite"], (x0, y0 + 5), (x0 + 12, y0 + 5), 2)
    row("parasite draining a victim")
    pygame.draw.line(screen, (255, 90, 60), (x0, y0 + 5), (x0 + 12, y0 + 5), 3)
    row("predator kill")
    for cause, label in (("eaten", "death: eaten"), ("starved", "death: starved"),
                         ("old age", "death: old age")):
        pygame.draw.circle(screen, DEATH_COLORS[cause], (x0 + 6, y0 + 5), 5, 1)
        row(label)
    pygame.draw.circle(screen, (255, 70, 70), (x0 + 6, y0 + 5), 5, 1)
    pygame.draw.circle(screen, (90, 220, 120), (x0 + 6, y0 + 5), 3, 1)
    row("red/green ring: lethal / optimal")
    pygame.draw.circle(screen, ROCK_FILL, (x0 + 6, y0 + 5), 6)
    pygame.draw.circle(screen, ROCK_RIM, (x0 + 6, y0 + 5), 6, 1)
    row("rock: shade and cover from hunters")
    pygame.draw.circle(screen, CARCASS_COLOR, (x0 + 6, y0 + 5), 3)
    row("carcass: food for scavengers")


def draw_selection(screen, world, o):
    """In-world marks for the inspected organism: a ring, and outlines on kin."""
    for other in world.organisms:
        if other is not o and o.is_kin(other):
            pygame.draw.circle(screen, (200, 200, 220), (int(other.x), int(other.y)),
                               int(organism_radius(other)) + 3, 1)
    pygame.draw.circle(screen, (255, 255, 255), (int(o.x), int(o.y)),
                       int(organism_radius(o)) + 6, 2)


def draw_inspector(screen, fonts, world, o, x, y):
    font, _big, small = fonts
    if small is None or font is None:
        return
    g = o.genes
    screen.blit(font.render("#%d  %s  (gen %d)" % (o.uid, o.strategy, o.generation),
                            True, STRATEGY_COLORS[o.strategy]), (x, y))
    y += 24

    def line(text):
        nonlocal y
        screen.blit(small.render(text, True, TEXT), (x, y))
        y += 17

    screen.blit(small.render("energy", True, TEXT), (x, y))
    bar(screen, x + 60, y + 2, 180, 9, o.energy / ENERGY_CAP, STRATEGY_COLORS[o.strategy])
    y += 17
    screen.blit(small.render("age", True, TEXT), (x, y))
    bar(screen, x + 60, y + 2, 180, 9, o.age / o.max_age, (170, 170, 190))
    y += 17
    line("offspring %d   family #%d (%d alive)" % (
        o.children, o.family, sum(1 for k in world.organisms if k.family == o.family)))
    screen.blit(small.render("strategy", True, TEXT), (x, y))
    budget_bar(screen, x + 60, y + 2, 180, 9, (g.absorption, g.parasitism, g.predation))
    y += 17
    line("absorb %.2f   steal %.2f   eat %.2f" % (
        g.absorption_efficiency, g.stealing_ability, g.eating_ability))
    line("spectrum %d   speed %.2f" % (g.absorption_spectrum, g.speed))
    line("sensing: radiation %.1f   organisms %.1f" % (g.radiation_sensing, g.organism_sensing))
    line("kin affinity %.2f   spares young %d ticks" % (g.kin_affinity, g.offspring_protection))
    line("cover affinity %.2f   dispersal %.2f" % (g.cover_affinity, g.dispersal))
    line("roaming %.2f   wariness %.2f%s" % (g.roaming, g.wariness,
                                             "   (travelling)" if o.leg else ""))
    line("armour %.2f  bite %.2f  camo %.2f  percep %.2f" % (
        g.armor, g.bite, g.camouflage, g.perception))
    line("marker %.1f%s" % (g.marker, "   (sexual birth)" if o.mate_uid else ""))
    line("outlined: relatives   click empty space to close")


class SetupDialog:
    """Pre-run settings. Arrow keys or +/- buttons adjust, Enter starts."""

    ROW_H = 32

    def __init__(self, settings, max_width=1800, max_height=1100):
        self.values = dict(settings)
        self.fields = [
            ("emitters", "Emitters", 0, 10, 1),
            ("rocks", "Rocks", 0, 40, 1),
            ("dynamic", "Seasons & drift", 0, 1, 1),
            ("open", "Open world", 0, 1, 1),
            ("organisms", "Starting organisms", 0, 600, 10),
            ("absorber", "Absorbers", 0, 100, 5),
            ("parasite", "Parasites", 0, 100, 5),
            ("predator", "Predators", 0, 100, 5),
            ("width", "World width", 600, max(600, max_width), 100),
            ("height", "World height", 450, max(450, max_height), 50),
        ]
        for key, _label, lo, hi, _step in self.fields:
            self.values[key] = int(clamp(self.values[key], lo, hi))
        self.index = 0

    def adjust(self, key, direction):
        for k, _label, lo, hi, step in self.fields:
            if k == key:
                self.values[k] = int(clamp(self.values[k] + direction * step, lo, hi))

    def mix_percent(self):
        total = sum(self.values[k] for k in STRATEGIES)
        if total == 0:
            return None
        return {k: 100.0 * self.values[k] / total for k in STRATEGIES}

    def layout(self, screen_size):
        sw, sh = screen_size
        w, h = 460, 170 + self.ROW_H * len(self.fields)
        rect = pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)
        rows = []
        y = rect.y + 56
        for key, *_ in self.fields:
            minus = pygame.Rect(rect.right - 150, y, 26, 24)
            plus = pygame.Rect(rect.right - 44, y, 26, 24)
            rows.append((key, pygame.Rect(rect.x + 10, y - 3, w - 20, self.ROW_H - 2), minus, plus))
            y += self.ROW_H
        start = pygame.Rect(rect.centerx - 60, rect.bottom - 70, 120, 34)
        return rect, rows, start

    def handle_event(self, event, screen_size):
        """Returns "start", "cancel" or None."""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "start"
            if event.key == pygame.K_ESCAPE:
                return "cancel"
            if event.key == pygame.K_UP:
                self.index = (self.index - 1) % len(self.fields)
            elif event.key == pygame.K_DOWN or event.key == pygame.K_TAB:
                self.index = (self.index + 1) % len(self.fields)
            elif event.key == pygame.K_LEFT:
                self.adjust(self.fields[self.index][0], -1)
            elif event.key == pygame.K_RIGHT:
                self.adjust(self.fields[self.index][0], 1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            _rect, rows, start = self.layout(screen_size)
            if start.collidepoint(event.pos):
                return "start"
            for i, (key, row, minus, plus) in enumerate(rows):
                if minus.collidepoint(event.pos):
                    self.adjust(key, -1)
                elif plus.collidepoint(event.pos):
                    self.adjust(key, 1)
                if row.collidepoint(event.pos):
                    self.index = i
        return None

    def draw(self, screen, fonts):
        font, big, small = fonts
        rect, rows, start = self.layout(screen.get_size())
        panel(screen, rect, 215)
        pygame.draw.rect(screen, (90, 90, 120), rect, 1)
        if big is not None:
            screen.blit(big.render("New simulation", True, (240, 240, 250)),
                        (rect.x + 20, rect.y + 16))
        mix = self.mix_percent()
        for i, (key, row, minus, plus) in enumerate(rows):
            _k, label, *_ = self.fields[i]
            if i == self.index:
                pygame.draw.rect(screen, (45, 45, 75), row)
            color = STRATEGY_COLORS.get(key, TEXT)
            value = str(self.values[key])
            if key in ("dynamic", "open"):
                value = "on" if self.values[key] else "off"
            if key in STRATEGIES:
                value = "%d%%" % round(mix[key]) if mix else "-"
            for r, sign in ((minus, "-"), (plus, "+")):
                pygame.draw.rect(screen, (70, 70, 100), r)
                if font is not None:
                    img = font.render(sign, True, TEXT)
                    screen.blit(img, img.get_rect(center=r.center))
            if font is not None:
                screen.blit(font.render(label, True, color), (row.x + 10, row.y + 6))
                img = font.render(value, True, TEXT)
                screen.blit(img, img.get_rect(center=((minus.right + plus.left) // 2,
                                                      minus.centery)))
        bar_y = rows[-1][1].bottom + 10
        if mix:
            budget_bar(screen, rect.x + 20, bar_y, rect.width - 40, 8,
                       [mix[k] / 100.0 for k in STRATEGIES])
        elif small is not None:
            screen.blit(small.render("no mix set: founders get fully random genomes",
                                     True, DIM_TEXT), (rect.x + 20, bar_y - 2))
        pygame.draw.rect(screen, (60, 130, 80), start)
        if font is not None:
            img = font.render("Start", True, (255, 255, 255))
            screen.blit(img, img.get_rect(center=start.center))
        if small is not None:
            screen.blit(small.render("arrows / +- adjust   Enter start   Esc back",
                                     True, DIM_TEXT), (rect.x + 20, rect.bottom - 24))


class SimulationApp:
    def __init__(self, width=WIDTH, height=HEIGHT, seed=None, setup=True, settings=None):
        self.settings = dict(DEFAULT_SETTINGS, width=width, height=height)
        if settings:
            self.settings.update(settings)
        self._seed = seed
        info = pygame.display.Info()
        # leave room for the side pane, but never offer less than 900px of world
        screen_w = info.current_w - 40 if info.current_w and info.current_w > 0 else 2100
        self.max_width = max(900, screen_w - PANE_W)
        self.max_height = info.current_h - 80 if info.current_h and info.current_h > 0 else 1100
        self.screen = pygame.display.set_mode(
            window_size(self.settings["width"], self.settings["height"]))
        pygame.display.set_caption("Artificial Life Simulator")
        self.clock = pygame.time.Clock()
        self.font, self.big, self.small = self._make_fonts()
        self.field_layer = FieldLayer()
        self.effects = Effects()
        self.world = None
        self.selected = None
        self.paused = False
        self.show_legend = True
        self.dialog = None
        if setup:
            self.open_setup()
        else:
            self.reset()

    @property
    def fonts(self):
        return self.font, self.big, self.small

    @staticmethod
    def _make_fonts():
        try:
            pygame.font.init()
            big = pygame.font.SysFont(None, 30)
            font = pygame.font.SysFont(None, 22)
            small = pygame.font.SysFont(None, 16)
            return font, big, small
        except Exception:
            return None, None, None

    @property
    def mode(self):
        return "setup" if self.dialog is not None else "run"

    def open_setup(self):
        self.dialog = SetupDialog(self.settings, self.max_width, self.max_height)

    def reset(self):
        """Start a fresh world from the current settings."""
        st = self.settings
        size = window_size(st["width"], st["height"])
        if self.screen.get_size() != size:
            self.screen = pygame.display.set_mode(size)
        mix = {k: st[k] for k in STRATEGIES}
        if not any(mix.values()):
            mix = None
        area = st["width"] * st["height"] / float(WIDTH * HEIGHT)
        self.world = simcore.World(
            st["width"], st["height"], seed=self._seed,
            num_emitters=st["emitters"], start_population=st["organisms"],
            max_population=max(simcore.MAX_POPULATION, int(simcore.MAX_POPULATION * area)),
            strategy_mix=mix,
            rules=simcore.Rules(**world_rule_values(st)))
        self.effects.clear()
        self.selected = None
        self.paused = False
        self.dialog = None

    def select_at(self, pos):
        if pos[0] >= self.world.width:
            return                     # clicks in the side pane
        best, best_d = None, 14
        for o in self.world.organisms:
            d = math.hypot(o.x - pos[0], o.y - pos[1])
            if d < best_d:
                best, best_d = o, d
        self.selected = best

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.dialog is not None:
                result = self.dialog.handle_event(event, self.screen.get_size())
                if result == "start":
                    self.settings = dict(self.dialog.values)
                    self.reset()
                elif result == "cancel":
                    if self.world is None:
                        return False
                    self.dialog = None
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_r:
                    self.open_setup()
                elif event.key == pygame.K_h:
                    self.show_legend = not self.show_legend
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.select_at(event.pos)
        return True

    def update(self):
        if self.dialog is not None or self.world is None or self.paused:
            return
        self.world.step()
        self.effects.age()
        self.effects.add_world_events(self.world.events)
        if self.selected is not None and not self.selected.alive:
            self.selected = None

    def draw(self):
        self.screen.fill(BACKGROUND)
        if self.world is not None:
            self.field_layer.draw(self.screen, self.world)
            draw_emitters(self.screen, self.world, self.font, pygame.time.get_ticks() / 1000.0)
            draw_rocks(self.screen, self.world)
            draw_carcasses(self.screen, self.world)
            draw_emitter_labels(self.screen, self.world, self.font)
            for o in self.world.organisms:
                draw_organism(self.screen, o)
            self.effects.draw(self.screen)
            if self.selected is not None:
                draw_selection(self.screen, self.world, self.selected)
            draw_pane(self.screen, self.fonts, self.world, self.paused, self.show_legend,
                      self.selected)
        if self.dialog is not None:
            self.dialog.draw(self.screen, self.fonts)
        pygame.display.flip()

    def frame(self):
        if not self.handle_events():
            return False
        self.update()
        self.draw()
        self.clock.tick(60)
        return True

    def run(self, max_frames=None):
        frames = 0
        while self.frame():
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        return frames


def world_rule_values(settings):
    """Rules fields for the setup dialog's environment toggles."""
    values = {}
    if settings.get("dynamic"):
        values.update(simcore.DYNAMIC_PRESET)
    if settings.get("open"):
        values.update(simcore.OPEN_PRESET)
    values["num_rocks"] = settings["rocks"]
    return values


def window_size(width, height):
    """The world view plus the side pane."""
    return width + PANE_W, max(height, PANE_MIN_H)


def run(max_frames=None, seed=None, width=WIDTH, height=HEIGHT, setup=None):
    env = os.environ.get("AIL_AUTOQUIT_FRAMES")
    if max_frames is None and env:
        max_frames = int(env)
    if setup is None:
        # unattended smoke runs skip the dialog so the simulation actually runs
        setup = not env
    pygame.init()
    app = SimulationApp(width=width, height=height, seed=seed, setup=setup)
    frames = app.run(max_frames=max_frames)
    pygame.quit()
    return frames


if __name__ == "__main__":
    run()
