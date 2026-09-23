#!/usr/bin/env python3
"""Terminal Snake.

Controls: arrows / WASD / HJKL move, P or Space pause, C or Tab toggles autopilot,
R restarts, Q quits. Run with --help for game options.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import statistics
import sys
import time
from typing import List, Optional

from ai import choose_direction
from engine import Config, Direction, Game
from highscores import HighScores

CELL_WIDTH = 2  # terminal cells are ~2x taller than wide; 2 columns per cell keeps the board square

GLYPHS = {
    "unicode": {"head": "██", "body": "▓▓", "food": "()", "bonus": "$$", "obstacle": "▒▒",
                "h": "─", "v": "│", "corners": "┌┐└┘"},
    "ascii": {"head": "@@", "body": "[]", "food": "()", "bonus": "$$", "obstacle": "##",
              "h": "-", "v": "|", "corners": "++++"},
}

HINTS = (  # longest first; the first that fits under the board is shown
    "arrows/WASD move  P pause  C autopilot  R restart  Q quit",
    "P pause  C autopilot  R restart  Q quit",
    "P pause C auto R new Q quit",
)

DEATH_MESSAGES = {
    "wall": "You hit the wall.",
    "obstacle": "You crashed into a rock.",
    "self": "You bit your own tail.",
}


# --------------------------------------------------------------------- UI

class Screen:
    """Draws a Game onto a curses window."""

    def __init__(self, stdscr, glyphs: dict) -> None:
        import curses

        self.curses = curses
        self.scr = stdscr
        self.glyphs = glyphs
        self.attr = {name: 0 for name in ("head", "body", "food", "bonus", "obstacle", "hud", "auto", "wall", "title")}
        if curses.has_colors():
            curses.start_color()
            bg = -1
            try:
                curses.use_default_colors()
            except curses.error:
                bg = curses.COLOR_BLACK
            palette = {
                "head": curses.COLOR_YELLOW,
                "body": curses.COLOR_GREEN,
                "food": curses.COLOR_RED,
                "bonus": curses.COLOR_MAGENTA,
                "obstacle": curses.COLOR_WHITE,
                "hud": curses.COLOR_CYAN,
                "auto": curses.COLOR_MAGENTA,
                "wall": curses.COLOR_BLUE,
                "title": curses.COLOR_GREEN,
            }
            for i, (name, fg) in enumerate(palette.items(), start=1):
                curses.init_pair(i, fg, bg)
                self.attr[name] = curses.color_pair(i)
        bold = curses.A_BOLD
        for name in ("head", "food", "bonus", "hud", "auto", "title"):
            self.attr[name] |= bold

    def put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            self.scr.addstr(y, x, text, attr)
        except self.curses.error:
            pass  # writing the bottom-right cell or off-screen raises; ignore it

    def fits(self, game: Game) -> bool:
        rows, cols = self.scr.getmaxyx()
        return cols >= game.config.width * CELL_WIDTH + 2 and rows >= game.config.height + 4

    def draw(self, game: Game, state: str, best: int, autopilot: bool, new_record: bool) -> None:
        c = self.curses
        self.scr.erase()
        rows, cols = self.scr.getmaxyx()
        if not self.fits(game):
            self.put(0, 0, "Terminal too small - enlarge it or press Q.", c.A_BOLD)
            self.scr.refresh()
            return

        w, h = game.config.width, game.config.height
        box_w = w * CELL_WIDTH + 2
        top = max(1, (rows - (h + 4)) // 2 + 1)
        left = max(0, (cols - box_w) // 2)

        # HUD
        hud = f" Score {game.score}   Best {max(best, game.score)}   Length {game.length}   Level {game.level} "
        self.put(top - 1, left, hud, self.attr["hud"])
        if autopilot:
            tag = " AUTOPILOT "
            self.put(top - 1, left + box_w - len(tag), tag, self.attr["auto"] | c.A_REVERSE)

        # Border: dotted when walls wrap around, solid when they kill.
        g = self.glyphs
        if game.config.wrap:
            horiz, vert, corners = ".", ":", "++++"
        else:
            horiz, vert, corners = g["h"], g["v"], g["corners"]
        wall = self.attr["wall"]
        self.put(top, left, corners[0] + horiz * (box_w - 2) + corners[1], wall)
        self.put(top + h + 1, left, corners[2] + horiz * (box_w - 2) + corners[3], wall)
        for y in range(1, h + 1):
            self.put(top + y, left, vert, wall)
            self.put(top + y, left + box_w - 1, vert, wall)

        def cell(p, kind: str, extra: int = 0) -> None:
            self.put(top + 1 + p[1], left + 1 + p[0] * CELL_WIDTH, self.glyphs[kind], self.attr[kind] | extra)

        for p in game.obstacles:
            cell(p, "obstacle")
        if game.food is not None:
            cell(game.food, "food")
        if game.bonus is not None:
            # Blink during the last few ticks as a warning.
            blink = c.A_BLINK if game.bonus.ttl <= 10 else 0
            cell(game.bonus.pos, "bonus", blink)
        body = list(game.body)
        for p in body[1:]:
            cell(p, "body")
        cell(body[0], "head", 0 if game.alive else c.A_REVERSE)

        # Footer: bonus timer or key hints.
        footer_y = top + h + 2
        if game.bonus is not None and state == "playing":
            bar_w = box_w - 10
            filled = round(bar_w * game.bonus.ttl / game.config.bonus_lifetime)
            self.put(footer_y, left, " BONUS ", self.attr["bonus"])
            self.put(footer_y, left + 8, "=" * filled, self.attr["bonus"])
        else:
            hints = next((t for t in HINTS if len(t) <= box_w), HINTS[-1])
            self.put(footer_y, left + max(0, (box_w - len(hints)) // 2), hints[:box_w], c.A_DIM)

        # Overlays
        if state == "ready":
            self._banner(top, left, box_w, h, ["S N A K E", "", "Press an arrow key to start", "or C to let the computer play"])
        elif state == "paused":
            self._banner(top, left, box_w, h, ["PAUSED", "", "P to resume"])
        elif state == "over":
            if game.won:
                lines = ["YOU WIN!", "The board is full."]
            else:
                lines = ["GAME OVER", DEATH_MESSAGES.get(game.death_cause or "", "")]
            lines += ["", f"Score {game.score}"]
            if new_record:
                lines.append("** New high score! **")
            lines += ["", "R to play again, Q to quit"]
            self._banner(top, left, box_w, h, lines)
        self.scr.refresh()

    def _banner(self, top: int, left: int, box_w: int, h: int, lines: List[str]) -> None:
        inner = max(len(s) for s in lines) + 4
        y0 = top + 1 + max(0, (h - len(lines)) // 2)
        for i, text in enumerate(lines):
            attr = self.attr["title"] if i == 0 else 0
            self.put(y0 + i, left + (box_w - inner) // 2, text.center(inner), attr | self.curses.A_REVERSE)


def _keymap():
    import curses

    keys = {
        curses.KEY_UP: Direction.UP,
        curses.KEY_DOWN: Direction.DOWN,
        curses.KEY_LEFT: Direction.LEFT,
        curses.KEY_RIGHT: Direction.RIGHT,
    }
    for chars, d in (("wk", Direction.UP), ("sj", Direction.DOWN), ("ah", Direction.LEFT), ("dl", Direction.RIGHT)):
        for ch in chars:
            keys[ord(ch)] = d
            keys[ord(ch.upper())] = d
    return keys


def play(stdscr, config: Config, args: argparse.Namespace) -> None:
    import curses

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)

    screen = Screen(stdscr, GLYPHS["ascii" if args.ascii else "unicode"])
    scores = HighScores(args.scores_file)
    keymap = _keymap()

    game = Game(config)
    autopilot = args.auto
    used_autopilot = autopilot  # autopilot runs never count toward high scores
    state = "ready"
    new_record = False
    next_tick = time.monotonic()

    while True:
        screen.draw(game, state, scores.best(config.mode), autopilot, new_record)

        if state == "playing" and screen.fits(game):
            stdscr.timeout(max(0, int((next_tick - time.monotonic()) * 1000)))
        else:
            stdscr.timeout(-1)
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return
        if key in (ord("r"), ord("R")):
            game = Game(config)
            autopilot = args.auto
            used_autopilot = autopilot
            state, new_record = "ready", False
            continue
        if key in (ord("c"), ord("C"), 9) and state != "over":
            autopilot = not autopilot
            used_autopilot |= autopilot
            game.clear_turns()
            if state == "ready":
                state, next_tick = "playing", time.monotonic()
        elif key in (ord("p"), ord("P"), ord(" ")):
            if state == "playing":
                state = "paused"
            elif state in ("paused", "ready"):
                state, next_tick = "playing", time.monotonic()
        elif key in keymap and state in ("ready", "playing"):
            if autopilot:  # grabbing the controls hands them back to you
                autopilot = False
                game.clear_turns()
            game.queue_turn(keymap[key])
            if state == "ready":
                state, next_tick = "playing", time.monotonic()

        now = time.monotonic()
        if state == "playing" and screen.fits(game) and now >= next_tick:
            if autopilot:
                game.clear_turns()
                game.queue_turn(choose_direction(game))
            game.step()
            # Schedule from the previous tick so key presses never speed the game up.
            next_tick = max(next_tick + game.delay, now)
            if game.over:
                state = "over"
                if not used_autopilot:
                    new_record = scores.submit(config.mode, game.score)


# -------------------------------------------------------------- benchmark

def benchmark(config: Config, games: int) -> None:
    """Play the autopilot headless and report how it does."""
    results = []
    stall_limit = config.width * config.height * 3
    for i in range(games):
        seed = None if config.seed is None else config.seed + i
        game = Game(dataclasses.replace(config, seed=seed))
        since_food = 0
        while not game.over and since_food < stall_limit:
            game.clear_turns()
            game.queue_turn(choose_direction(game))
            events = game.step()
            since_food = 0 if "eat" in events else since_food + 1
        outcome = "win" if game.won else (game.death_cause or "stalled")
        results.append((game.score, game.length, outcome))
        print(f"game {i + 1:>3}: score {game.score:>6}  length {game.length:>4}  {outcome}")

    scores = [r[0] for r in results]
    cells = config.width * config.height - config.obstacles
    print("-" * 44)
    print(f"mode        {config.mode}")
    print(f"mean score  {statistics.mean(scores):.0f}   best {max(scores)}")
    print(f"mean length {statistics.mean(r[1] for r in results):.1f} / {cells} cells")
    print(f"wins        {sum(r[2] == 'win' for r in results)} / {games}")


# -------------------------------------------------------------------- CLI

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Snake for the terminal, with an autopilot.")
    p.add_argument("--width", type=int, help="board width in cells (default: fit the terminal, max 32)")
    p.add_argument("--height", type=int, help="board height in cells (default: fit the terminal, max 20)")
    p.add_argument("--wrap", action="store_true", help="walls wrap around instead of killing you")
    p.add_argument("--obstacles", type=int, default=0, metavar="N", help="scatter N rocks on the board")
    p.add_argument("--speed", type=float, default=1.0, help="speed multiplier, e.g. 1.5 for faster")
    p.add_argument("--auto", action="store_true", help="start with the autopilot flying")
    p.add_argument("--ascii", action="store_true", help="use plain ASCII glyphs")
    p.add_argument("--seed", type=int, help="random seed for reproducible games")
    p.add_argument("--scores-file", help="where to keep high scores (default: ~/.snake_scores.json)")
    p.add_argument("--benchmark", type=int, metavar="GAMES", help="run the autopilot headless for GAMES games")
    args = p.parse_args(argv)
    if args.speed <= 0:
        p.error("--speed must be positive")
    return args


def make_config(args: argparse.Namespace, width: int, height: int) -> Config:
    return Config(
        width=width,
        height=height,
        wrap=args.wrap,
        obstacles=args.obstacles,
        base_delay=Config.base_delay / args.speed,
        min_delay=Config.min_delay / args.speed,
        seed=args.seed,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.benchmark:
        try:
            config = make_config(args, args.width or 20, args.height or 15)
        except ValueError as e:
            print(f"snake: {e}", file=sys.stderr)
            return 2
        benchmark(config, args.benchmark)
        return 0

    try:
        import curses
    except ImportError:
        print("snake: curses is missing. On Windows run: pip install windows-curses", file=sys.stderr)
        return 1

    import locale

    locale.setlocale(locale.LC_ALL, "")

    size = os.get_terminal_size() if sys.stdout.isatty() else os.terminal_size((80, 24))
    width = args.width or min(32, (size.columns - 2) // CELL_WIDTH)
    height = args.height or min(20, size.lines - 4)
    try:
        config = make_config(args, width, height)
    except ValueError as e:
        print(f"snake: {e} (try a bigger terminal)", file=sys.stderr)
        return 2

    curses.wrapper(play, config, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
