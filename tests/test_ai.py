import unittest

import ai
from engine import Config, Game


def play(game, max_ticks):
    for _ in range(max_ticks):
        if game.over:
            break
        game.clear_turns()
        game.queue_turn(ai.choose_direction(game))
        game.step()
    return game


class AutopilotTests(unittest.TestCase):
    def test_never_picks_an_immediately_fatal_move(self):
        for seed in range(5):
            g = Game(Config(width=12, height=8, seed=seed))
            for _ in range(400):
                if g.over:
                    break
                d = ai.choose_direction(g)
                nxt = g.next_cell(g.head, d)
                safe = [n for _, n in g.neighbors(g.head) if n is not None and ai._safe_now(g, list(g.body), n)]
                if safe:
                    self.assertIn(nxt, safe)
                g.clear_turns()
                g.queue_turn(d)
                g.step()

    def test_eats_plenty_of_food(self):
        for cfg in (Config(width=12, height=10, seed=1), Config(width=12, height=10, wrap=True, obstacles=6, seed=2)):
            g = play(Game(cfg), 3000)
            self.assertGreaterEqual(g.foods_eaten, 30, cfg.mode)

    def test_finds_food_through_wrap(self):
        g = Game(Config(width=10, height=6, wrap=True, seed=0))
        g.food = (0, g.head[1]) if g.head[0] > 5 else (g.config.width - 1, g.head[1])
        start_eaten = g.foods_eaten
        play(g, 10)
        self.assertGreater(g.foods_eaten, start_eaten)


if __name__ == "__main__":
    unittest.main()
