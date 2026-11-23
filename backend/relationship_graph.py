from collections import defaultdict, deque
from itertools import combinations

from .schema_context import ForeignKey, SchemaSnapshot


class UnresolvedJoin(ValueError):
    pass


class RelationshipGraph:
    def __init__(self, snapshot: SchemaSnapshot):
        self.adjacent = defaultdict(list)
        for edge in sorted(set(snapshot.foreign_keys)):
            if edge.source == edge.target or not all(
                left in snapshot.catalog.get(edge.source, {}) and right in snapshot.catalog.get(edge.target, {})
                for left, right in edge.columns
            ):
                continue
            self.adjacent[edge.source].append((edge.target, edge))
            self.adjacent[edge.target].append((edge.source, edge))

    def path(self, start: str, target: str) -> tuple[ForeignKey, ...]:
        distances = {start: 0}
        paths = {start: ()}
        counts = {start: 1}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if current == target:
                if counts[current] > 1:
                    raise UnresolvedJoin(f"Several equally short joins connect {start} and {target}. Specify the relationship.")
                return paths[current]
            distance = distances[current] + 1
            for neighbor, edge in self.adjacent[current]:
                if neighbor not in distances:
                    distances[neighbor] = distance
                    paths[neighbor] = paths[current] + (edge,)
                    counts[neighbor] = counts[current]
                    queue.append(neighbor)
                elif distance == distances[neighbor]:
                    counts[neighbor] = min(2, counts[neighbor] + counts[current])
        raise UnresolvedJoin(f"No authorized foreign-key path connects {start} and {target}.")

    def expand(self, tables: list[str]) -> tuple[set[str], tuple[ForeignKey, ...]]:
        edges = set()
        for source, target in combinations(tables, 2):
            edges.update(self.path(source, target))
        return set(tables) | {table for edge in edges for table in (edge.source, edge.target)}, tuple(sorted(edges))
