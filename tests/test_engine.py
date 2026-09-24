import unittest
from collections import deque

from engine import Bonus, Config, Direction, Game


def make_game(**kw):
    kw.setdefault("seed", 0)
    kw.setdefault("bonus_chance", 0.0)
    return Game(Config(**kw))


def place(game, body, food=None):
    """Put the snake (head first) and food exactly where a test wants them."""
    game.body = deque(body)
    game.occupied = set(body)
    game.food = food if food is not None else (game.config.width - 1, game.config.height - 1)


class DirectionTests(unittest.TestCase):
    def test_opposites(self):
        self.assertTrue(Direction.UP.is_opposite(Direction.DOWN))
        self.assertTrue(Direction.LEFT.is_opposite(Direction.RIGHT))
        self.assertFalse(Direction.UP.is_opposite(Direction.LEFT))


class ConfigTests(unittest.TestCase):
    def test_rejects_tiny_board(self):
        with self.assertRaises(ValueError):
            Config(width=4, height=4)

    def test_caps_obstacles(self):
        self.assertLessEqual(Config(width=10, height=10, obstacles=1000).obstacles, 14)

    def test_mode_names(self):
        self.assertEqual(Config(width=10, height=8).mode, "classic+10x8")
        self.assertEqual(Config(width=10, height=8, wrap=True, obstacles=3).mode, "wrap+obstacles3+10x8")


class MovementTests(unittest.TestCase):
    def test_moves_forward(self):
        g = make_game()
        head = g.head
        g.step()
        self.assertEqual(g.head, (head[0] + 1, head[1]))
        self.assertEqual(g.length, 3)

    def test_reverse_is_ignored(self):
        g = make_game()
        self.assertFalse(g.queue_turn(Direction.LEFT))
        g.step()
        self.assertTrue(g.alive)

    def test_quick_double_turn_is_buffered(self):
        g = make_game()
        start = g.head
        self.assertTrue(g.queue_turn(Direction.UP))
        self.assertTrue(g.queue_turn(Direction.LEFT))
        g.step()
        g.step()
        self.assertEqual(g.head, (start[0] - 1, start[1] - 1))
        self.assertTrue(g.alive)

    def test_wall_kills_in_classic(self):
        g = make_game(width=10, height=6)
        place(g, [(9, 2), (8, 2), (7, 2)])
        g.step()
        self.assertFalse(g.alive)
        self.assertEqual(g.death_cause, "wall")

    def test_wall_wraps_in_wrap_mode(self):
        g = make_game(width=10, height=6, wrap=True)
        place(g, [(9, 2), (8, 2), (7, 2)])
        g.step()
        self.assertTrue(g.alive)
        self.assertEqual(g.head, (0, 2))

    def test_self_collision(self):
        g = make_game()
        place(g, [(5, 5), (6, 5), (6, 6), (5, 6), (4, 6)])
        g.direction = Direction.DOWN
        g.step()
        self.assertEqual(g.death_cause, "self")

    def test_can_follow_own_tail(self):
        g = make_game()
        place(g, [(5, 5), (6, 5), (6, 6), (5, 6)])
        g.direction = Direction.DOWN
        g.step()
        self.assertTrue(g.alive)
        self.assertEqual(g.head, (5, 6))

    def test_obstacle_kills(self):
        g = make_game()
        g.obstacles = {(g.head[0] + 1, g.head[1])}
        g.step()
        self.assertEqual(g.death_cause, "obstacle")


class EatingTests(unittest.TestCase):
    def test_eating_grows_scores_and_respawns(self):
        g = make_game()
        food = (g.head[0] + 1, g.head[1])
        g.food = food
        events = g.step()
        self.assertIn("eat", events)
        self.assertEqual(g.length, 4)
        self.assertEqual(g.score, Game.FOOD_POINTS)
        self.assertNotEqual(g.food, food)
        self.assertNotIn(g.food, g.occupied)

    def test_speed_increases(self):
        g = make_game()
        before = g.delay
        g.food = (g.head[0] + 1, g.head[1])
        g.step()
        self.assertLess(g.delay, before)
        g.foods_eaten = 10_000
        self.assertEqual(g.delay, g.config.min_delay)

    def test_bonus_grows_more_and_expires(self):
        g = make_game()
        g.bonus = Bonus((g.head[0] + 1, g.head[1]), ttl=10)
        events = g.step()
        self.assertIn("bonus", events)
        self.assertEqual(g.score, Game.BONUS_BASE_POINTS + 20)
        for _ in range(Game.BONUS_GROWTH):
            g.step()
        self.assertEqual(g.length, 3 + Game.BONUS_GROWTH)

        g.bonus = Bonus((0, 0), ttl=2)
        g.step()
        events = g.step()
        self.assertIsNone(g.bonus)
        self.assertIn("bonus_expired", events)

    def test_win_when_board_full(self):
        g = make_game(width=8, height=5)
        cells = [(x, y) for y in range(5) for x in (range(8) if y % 2 == 0 else range(7, -1, -1))]
        # Snake fills everything except the last cell, which holds the food.
        place(g, list(reversed(cells[:-1])), food=cells[-1])
        g.direction = Direction.RIGHT
        events = g.step()
        self.assertIn("win", events)
        self.assertTrue(g.won)


class ObstacleTests(unittest.TestCase):
    def test_obstacles_keep_board_connected_and_start_clear(self):
        for seed in range(20):
            g = make_game(obstacles=40, seed=seed)
            self.assertTrue(g._board_connected())
            self.assertFalse(g.obstacles & g.occupied)
            ahead = {(x, g.head[1]) for x in range(g.config.width)}
            self.assertFalse(g.obstacles & ahead)
            self.assertNotIn(g.food, g.obstacles)

    def test_seed_is_reproducible(self):
        a, b = make_game(obstacles=10, seed=42), make_game(obstacles=10, seed=42)
        self.assertEqual(a.obstacles, b.obstacles)
        self.assertEqual(a.food, b.food)


if __name__ == "__main__":
    unittest.main()
