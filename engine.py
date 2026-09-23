"""Pure Snake game logic.

Nothing in here touches the terminal, so the rules can be unit tested and
reused by the autopilot and the headless benchmark.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Iterator, List, Optional, Set, Tuple

Point = Tuple[int, int]  # (x, y), origin in the top-left corner


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    def is_opposite(self, other: "Direction") -> bool:
        return self.dx == -other.dx and self.dy == -other.dy


@dataclass
class Config:
    width: int = 30
    height: int = 20
    wrap: bool = False  # walls teleport you to the other side instead of killing you
    obstacles: int = 0
    start_length: int = 3
    base_delay: float = 0.12  # seconds per tick at the start
    min_delay: float = 0.045  # speed cap
    speedup: float = 0.97  # delay multiplier per food eaten
    bonus_chance: float = 0.25  # chance a bonus appears after eating food
    bonus_lifetime: int = 45  # ticks before a bonus disappears
    seed: Optional[int] = None

    MIN_WIDTH = 8
    MIN_HEIGHT = 5

    def __post_init__(self) -> None:
        if self.width < self.MIN_WIDTH or self.height < self.MIN_HEIGHT:
            raise ValueError(
                f"board must be at least {self.MIN_WIDTH}x{self.MIN_HEIGHT}, "
                f"got {self.width}x{self.height}"
            )
        if not 2 <= self.start_length <= self.width // 2:
            raise ValueError("start_length must fit in the left half of the board")
        # Never let obstacles eat more than ~15% of the board.
        self.obstacles = max(0, min(self.obstacles, (self.width * self.height) // 7))

    @property
    def mode(self) -> str:
        """Key used to keep separate high scores per rule set."""
        parts = ["wrap" if self.wrap else "classic"]
        if self.obstacles:
            parts.append(f"obstacles{self.obstacles}")
        parts.append(f"{self.width}x{self.height}")
        return "+".join(parts)


@dataclass
class Bonus:
    pos: Point
    ttl: int


class Game:
    FOOD_POINTS = 10
    BONUS_BASE_POINTS = 20
    BONUS_GROWTH = 3
    MAX_QUEUED_TURNS = 3

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.rng = random.Random(self.config.seed)
        self.reset()

    # ------------------------------------------------------------------ setup

    def reset(self) -> None:
        cfg = self.config
        y = cfg.height // 2
        x0 = max(cfg.start_length, cfg.width // 4)
        self.body: Deque[Point] = deque((x0 - i, y) for i in range(cfg.start_length))
        self.occupied: Set[Point] = set(self.body)
        self.direction = Direction.RIGHT
        self._turns: Deque[Direction] = deque()
        self.pending_growth = 0
        self.score = 0
        self.foods_eaten = 0
        self.ticks = 0
        self.alive = True
        self.won = False
        self.death_cause: Optional[str] = None
        self.bonus: Optional[Bonus] = None
        self.obstacles: Set[Point] = set()
        self.food: Optional[Point] = None
        self._place_obstacles(cfg.obstacles)
        self.food = self._random_free_cell()

    def _place_obstacles(self, count: int) -> None:
        """Scatter obstacles without blocking the start lane or splitting the board."""
        cfg = self.config
        head_x, head_y = self.head
        tail_x = self.body[-1][0]

        def reserved(p: Point) -> bool:
            x, y = p
            return y == head_y or (abs(y - head_y) == 1 and tail_x - 1 <= x <= head_x + 3)

        attempts = count * 30
        while len(self.obstacles) < count and attempts > 0:
            attempts -= 1
            p = (self.rng.randrange(cfg.width), self.rng.randrange(cfg.height))
            if p in self.obstacles or reserved(p):
                continue
            self.obstacles.add(p)
            if not self._board_connected():
                self.obstacles.discard(p)

    def _board_connected(self) -> bool:
        free = self.config.width * self.config.height - len(self.obstacles)
        seen = {self.head}
        stack = [self.head]
        while stack:
            for _, n in self.neighbors(stack.pop()):
                if n is not None and n not in seen and n not in self.obstacles:
                    seen.add(n)
                    stack.append(n)
        return len(seen) == free

    # ---------------------------------------------------------------- queries

    @property
    def head(self) -> Point:
        return self.body[0]

    @property
    def length(self) -> int:
        return len(self.body)

    @property
    def level(self) -> int:
        return self.foods_eaten // 5 + 1

    @property
    def delay(self) -> float:
        cfg = self.config
        return max(cfg.min_delay, cfg.base_delay * cfg.speedup ** self.foods_eaten)

    @property
    def over(self) -> bool:
        return not self.alive or self.won

    def next_cell(self, p: Point, d: Direction) -> Optional[Point]:
        """Cell reached by moving from ``p`` in ``d``; None if that leaves the board."""
        w, h = self.config.width, self.config.height
        x, y = p[0] + d.dx, p[1] + d.dy
        if self.config.wrap:
            return x % w, y % h
        if 0 <= x < w and 0 <= y < h:
            return x, y
        return None

    def neighbors(self, p: Point) -> Iterator[Tuple[Direction, Optional[Point]]]:
        for d in Direction:
            yield d, self.next_cell(p, d)

    def _random_free_cell(self) -> Optional[Point]:
        taken = self.occupied | self.obstacles
        if self.food is not None:
            taken.add(self.food)
        if self.bonus is not None:
            taken.add(self.bonus.pos)
        free = [
            (x, y)
            for y in range(self.config.height)
            for x in range(self.config.width)
            if (x, y) not in taken
        ]
        return self.rng.choice(free) if free else None

    # --------------------------------------------------------------- actions

    def queue_turn(self, d: Direction) -> bool:
        """Buffer a turn so quick key combos (e.g. up-then-left) are not lost.

        Turns that repeat or reverse the previously queued direction are
        ignored, which makes instant self-collisions impossible.
        """
        last = self._turns[-1] if self._turns else self.direction
        if d == last or d.is_opposite(last) or len(self._turns) >= self.MAX_QUEUED_TURNS:
            return False
        self._turns.append(d)
        return True

    def clear_turns(self) -> None:
        self._turns.clear()

    def step(self) -> List[str]:
        """Advance one tick. Returns the events that happened."""
        if self.over:
            return []
        if self._turns:
            self.direction = self._turns.popleft()
        self.ticks += 1
        events: List[str] = []

        new_head = self.next_cell(self.head, self.direction)
        if new_head is None:
            return self._die("wall")
        if new_head in self.obstacles:
            return self._die("obstacle")

        eats_food = new_head == self.food
        eats_bonus = self.bonus is not None and new_head == self.bonus.pos
        grows = self.pending_growth > 0 or eats_food or eats_bonus
        # Moving into the tail is fine when the tail moves out of the way.
        if new_head in self.occupied and (grows or new_head != self.body[-1]):
            return self._die("self")

        if eats_food:
            self.pending_growth += 1
            self.score += self.FOOD_POINTS * self.level
            self.foods_eaten += 1
            events.append("eat")
        if eats_bonus:
            assert self.bonus is not None
            self.pending_growth += self.BONUS_GROWTH
            self.score += self.BONUS_BASE_POINTS + 2 * self.bonus.ttl
            self.bonus = None
            events.append("bonus")

        if self.pending_growth > 0:
            self.pending_growth -= 1
        else:
            self.occupied.discard(self.body.pop())
        self.body.appendleft(new_head)
        self.occupied.add(new_head)

        if eats_food:
            self.food = self._random_free_cell()
            if self.bonus is None and self.rng.random() < self.config.bonus_chance:
                pos = self._random_free_cell()
                if pos is not None:
                    self.bonus = Bonus(pos, self.config.bonus_lifetime)
                    events.append("bonus_spawn")
        elif self.bonus is not None:
            self.bonus.ttl -= 1
            if self.bonus.ttl <= 0:
                self.bonus = None
                events.append("bonus_expired")

        if self.food is None:
            self.won = True
            events.append("win")
        return events

    def _die(self, cause: str) -> List[str]:
        self.alive = False
        self.death_cause = cause
        return ["die"]
