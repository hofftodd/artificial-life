"""
A uniform spatial hash for neighbour queries.
"""

class SpatialGrid:
    def __init__(self, cell_size=50):
        self.cell = cell_size
        self.buckets = {}

    def build(self, organisms):
        self.buckets.clear()
        for o in organisms:
            key = (int(o.x // self.cell), int(o.y // self.cell))
            self.buckets.setdefault(key, []).append(o)

    def near(self, x, y, r):
        """Yield candidates from the buckets covering radius r (a superset of
        what's actually within r), lazily and in a fixed order."""
        cx, cy = int(x // self.cell), int(y // self.cell)
        span = int(r // self.cell) + 1
        buckets = self.buckets
        for i in range(cx - span, cx + span + 1):
            for j in range(cy - span, cy + span + 1):
                bucket = buckets.get((i, j))
                if bucket:
                    yield from bucket

    def query(self, x, y, r, exclude=None):
        return [o for o in self.near(x, y, r) if o is not exclude]
