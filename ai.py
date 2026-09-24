"""Autopilot for the snake.

Strategy, in order:
1. Take the shortest path to the food, but only if the snake could still
   reach its own tail after eating, or would have plenty of room anyway
   (so it never seals itself into a small pocket).
2. Otherwise stall safely: choose the move that keeps the tail reachable and
   leaves the most open space, drifting away from the food so the board
   opens up again.
3. If every move is bad, pick the one with the most room to survive longest.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Sequence, Set, Tuple

from engine import Direction, Game, Point


def choose_direction(game: Game) -> Direction:
    body = list(game.body)
    if game.food is not None:
        path = _path_to(game, body, game.food)
        if path is not None:
            virtual = _simulate(body, [p for _, p in path], game.pending_growth, eats=True)
            # Roomy boards are safe even when our own coils hide the tail;
            # without this the snake can circle its tail forever.
            if _tail_reachable(game, virtual) or _open_space(game, virtual) > 2 * len(virtual):
                return path[0][0]

    best: Optional[Tuple[Tuple[int, int, int], Direction]] = None
    for d, nxt in game.neighbors(game.head):
        if nxt is None or d.is_opposite(game.direction) or not _safe_now(game, body, nxt):
            continue
        eats = nxt == game.food
        virtual = _simulate(body, [nxt], game.pending_growth, eats=eats)
        rank = (
            int(_tail_reachable(game, virtual)),
            _open_space(game, virtual),
            _distance(game, nxt, game.food),
        )
        if best is None or rank > best[0]:
            best = (rank, d)
    return best[1] if best else game.direction


def _safe_now(game: Game, body: Sequence[Point], cell: Point) -> bool:
    if cell in game.obstacles:
        return False
    if cell not in game.occupied:
        return True
    return cell == body[-1] and game.pending_growth == 0 and cell != game.food


def _path_to(game: Game, body: Sequence[Point], goal: Point) -> Optional[List[Tuple[Direction, Point]]]:
    """Time-aware BFS: body segments count as free once the tail has moved past them."""
    length = len(body)
    index: Dict[Point, int] = {p: i for i, p in enumerate(body)}
    start = body[0]
    parent: Dict[Point, Tuple[Point, Direction]] = {}
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        t = dist[cur] + 1
        vacated_from = length - max(0, t - game.pending_growth)
        for d, nxt in game.neighbors(cur):
            if nxt is None or nxt in dist or nxt in game.obstacles:
                continue
            if nxt in index and index[nxt] < vacated_from:
                continue
            dist[nxt] = t
            parent[nxt] = (cur, d)
            queue.append(nxt)
    if goal not in parent:
        return None
    path: List[Tuple[Direction, Point]] = []
    node = goal
    while node != start:
        prev, d = parent[node]
        path.append((d, node))
        node = prev
    path.reverse()
    return path


def _simulate(body: Sequence[Point], cells: Sequence[Point], pending: int, eats: bool) -> List[Point]:
    """Body after walking through ``cells`` (head first in the result)."""
    moves = len(cells)
    growth = min(moves - (1 if eats else 0), pending) + (1 if eats else 0)
    return (list(reversed(cells)) + list(body))[: len(body) + growth]


def _tail_reachable(game: Game, virtual: Sequence[Point]) -> bool:
    head, tail = virtual[0], virtual[-1]
    blocked: Set[Point] = set(virtual[1:-1]) | game.obstacles
    seen = {head}
    queue = deque([head])
    while queue:
        cur = queue.popleft()
        for _, nxt in game.neighbors(cur):
            # A two-cell snake can't turn around onto its own tail.
            if nxt == tail and (cur != head or len(virtual) > 2):
                return True
            if nxt is None or nxt in seen or nxt in blocked:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return False


def _open_space(game: Game, virtual: Sequence[Point]) -> int:
    blocked: Set[Point] = set(virtual[:-1]) | game.obstacles
    head = virtual[0]
    seen = {head}
    stack = [head]
    while stack:
        for _, nxt in game.neighbors(stack.pop()):
            if nxt is not None and nxt not in seen and nxt not in blocked:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen)


def _distance(game: Game, a: Point, b: Optional[Point]) -> int:
    if b is None:
        return 0
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if game.config.wrap:
        dx = min(dx, game.config.width - dx)
        dy = min(dy, game.config.height - dy)
    return dx + dy
