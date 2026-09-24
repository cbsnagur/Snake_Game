# Snake

Snake for the terminal, written in pure Python with no dependencies. It comes
with an autopilot you can hand the controls to at any time.

```
 Score 120   Best 340   Length 14   Level 3                  AUTOPILOT
┌────────────────────────────────────────────────────────────────┐
│                          ▒▒                      ▒▒            │
│                                                                │
│          ▓▓▓▓▓▓▓▓▓▓▓▓██                                        │
│          ▓▓                           $$                       │
│      ▒▒                                                    ()  │
└────────────────────────────────────────────────────────────────┘
```

## Play

```bash
python3 snake.py                 # classic
python3 snake.py --wrap          # walls wrap around to the other side
python3 snake.py --obstacles 15  # scatter rocks on the board
python3 snake.py --auto          # watch the autopilot play
```

On Windows, install curses first: `pip install windows-curses`.

| Key                    | Action                          |
| ---------------------- | ------------------------------- |
| Arrows / WASD / HJKL   | Steer                           |
| P or Space             | Pause / resume                  |
| C or Tab               | Toggle the autopilot            |
| R                      | Restart                         |
| Q                      | Quit                            |

Pressing a direction key while the autopilot is flying takes the controls
back.

## Features

- **Autopilot.** It takes the shortest route to the food, then checks that it
  could still reach its own tail after eating, so it doesn't trap itself. When
  that route isn't safe, it stalls in the move that leaves the most room.
  Autopilot runs never count toward high scores.
- **Bonus food (`$$`).** Sometimes appears after you eat. It's worth more the
  sooner you reach it and makes you grow by 3. It blinks just before it
  disappears.
- **Levels.** Every 5 foods is a new level: points per food go up, and the
  game speeds up.
- **Wrap mode and obstacles.** Rocks never block the starting lane and never
  cut the board into sealed-off areas.
- **High scores.** Saved in `~/.snake_scores.json`, one per mode and board
  size. Override the location with `--scores-file` or `SNAKE_SCORES_FILE`.
- **Responsive controls.** Quick turns such as up-then-left are buffered
  rather than lost. Reversing into yourself is ignored. Holding a key doesn't
  speed the game up.
- **Square board.** Each cell is drawn two characters wide, so horizontal and
  vertical movement look the same speed.

Run `python3 snake.py --help` for all options (`--width`, `--height`,
`--speed`, `--seed`, `--ascii`, ...).

## Benchmark the autopilot

Play games without a display and see how the AI does:

```bash
python3 snake.py --benchmark 20 --seed 1
python3 snake.py --benchmark 10 --wrap --obstacles 12
```

## Development

The code is split so that the game rules can be tested without a terminal:

| File            | Purpose                                      |
| --------------- | -------------------------------------------- |
| `engine.py`     | Game rules: movement, food, bonus, scoring   |
| `ai.py`         | Autopilot                                    |
| `highscores.py` | High score storage                           |
| `snake.py`      | curses UI, command-line options, benchmark   |

```bash
python3 -m unittest -v
```
