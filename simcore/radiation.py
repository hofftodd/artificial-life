"""
The precomputed, shading-aware radiation field: intensity per field
cell per emitter, plus the per-cell absorption demand that splits the
harvest.
"""
import math

from .constants import (EMITTER_RANGE, FIELD_CELL, ROCK_SHADE,
                        SHADE_FACTOR, SHADING_RADIUS)

class RadiationField:
    """Precomputed, shading-aware radiation intensity per field cell, per emitter."""

    def __init__(self, width, height, emitters, organisms, grid, rocks=(),
                 rock_shade=ROCK_SHADE, tail_strength=0.0, tail_range=0.0, ambient=0.0):
        # spectrum-neutral light everywhere; not shaded, not per cell
        self.ambient = ambient
        extent = max(EMITTER_RANGE, tail_range) if tail_strength else EMITTER_RANGE
        self.cells_x = max(1, width // FIELD_CELL)
        self.cells_y = max(1, height // FIELD_CELL)
        self.by_emitter = []
        # organisms in the same cell compete for its photons in proportion to
        # how much of their strategy budget goes to absorption
        self.demand = {}
        for o in organisms:
            if not o.dead and o.genes.absorption > 0:
                key = (int(o.x // FIELD_CELL), int(o.y // FIELD_CELL))
                self.demand[key] = self.demand.get(key, 0.0) + o.genes.absorption
        absorbers = [o for o in organisms if not o.dead and o.strategy == "absorber"]
        reach = extent + SHADING_RADIUS
        for e in emitters:
            # only absorbers near this emitter can sit on one of its beams;
            # offsets are computed exactly as the per-beam test expects
            near = []
            for o in absorbers:
                ox, oy = o.x - e.x, o.y - e.y
                if abs(ox) <= reach and abs(oy) <= reach:
                    near.append((ox, oy, (int(o.x // FIELD_CELL), int(o.y // FIELD_CELL))))
            near_rocks = [(r.x - e.x, r.y - e.y, r.r) for r in rocks
                          if math.hypot(r.x - e.x, r.y - e.y) < extent + r.r]
            field = {}
            x0 = max(0, int((e.x - extent) // FIELD_CELL))
            x1 = min(self.cells_x - 1, int((e.x + extent) // FIELD_CELL))
            y0 = max(0, int((e.y - extent) // FIELD_CELL))
            y1 = min(self.cells_y - 1, int((e.y + extent) // FIELD_CELL))
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    px = (cx + 0.5) * FIELD_CELL
                    py = (cy + 0.5) * FIELD_CELL
                    raw = e.radiation_at(px, py, tail_strength, tail_range)
                    if raw <= 0:
                        continue
                    if near_rocks:
                        n = self._count_rocks(e, px, py, near_rocks)
                        if n < 0:
                            continue      # the cell centre is inside a rock
                        if n:
                            raw *= rock_shade ** n
                    if near:
                        n = self._count_blockers(e, px, py, near, (cx, cy))
                        if n:
                            raw *= SHADE_FACTOR ** n
                    field[(cx, cy)] = raw
            self.by_emitter.append(field)

    @staticmethod
    def _count_rocks(e, tx, ty, rocks):
        """Rocks the beam from the emitter to (tx, ty) passes through, or -1
        if (tx, ty) is itself inside a rock. Rocks are (dx, dy, r) offsets
        from the emitter."""
        dx, dy = tx - e.x, ty - e.y
        len2 = dx * dx + dy * dy
        count = 0
        for rx, ry, r in rocks:
            if (rx - dx) ** 2 + (ry - dy) ** 2 < r * r:
                return -1
            t = (rx * dx + ry * dy) / len2 if len2 else 0.0
            t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            if (rx - dx * t) ** 2 + (ry - dy * t) ** 2 < r * r:
                count += 1
        return count

    @staticmethod
    def _count_blockers(e, tx, ty, offsets, target_key=None):
        """Absorbers (given as (dx, dy, cell) offsets from the emitter) within
        SHADING_RADIUS of the beam from the emitter to (tx, ty), excluding its
        ends. Absorbers in the target cell itself don't count: they harvest
        that cell's light rather than shading it.

        Tests every candidate directly rather than ray-marching through the
        spatial grid; the result is identical, since the march only ever
        gathered candidates for this same test.
        """
        dx, dy = tx - e.x, ty - e.y
        length = math.hypot(dx, dy)
        if length < SHADING_RADIUS * 2:
            return 0
        inv = 1.0 / length
        lo, hi = SHADING_RADIUS, length - SHADING_RADIUS
        count = 0
        for ox, oy, key in offsets:
            if key == target_key:
                continue
            d_from_e = (ox * dx + oy * dy) * inv * inv * length
            if not (lo < d_from_e < hi):
                continue
            if abs(ox * dy - oy * dx) * inv < SHADING_RADIUS:
                count += 1
        return count

    def intensity_at(self, x, y, emitter_index):
        cx = int(x // FIELD_CELL)
        cy = int(y // FIELD_CELL)
        return self.by_emitter[emitter_index].get((cx, cy), 0.0)

    def share_at(self, x, y):
        """Fraction of a cell's harvestable energy one unit of absorption gets."""
        demand = self.demand.get((int(x // FIELD_CELL), int(y // FIELD_CELL)), 0.0)
        return 1.0 / max(1.0, demand)
