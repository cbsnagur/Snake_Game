import tempfile
import unittest
from pathlib import Path

from highscores import HighScores


class HighScoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "scores.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_records_and_persists_per_mode(self):
        hs = HighScores(self.path)
        self.assertTrue(hs.submit("classic", 50))
        self.assertFalse(hs.submit("classic", 40))
        self.assertTrue(hs.submit("wrap", 10))
        reloaded = HighScores(self.path)
        self.assertEqual(reloaded.best("classic"), 50)
        self.assertEqual(reloaded.best("wrap"), 10)
        self.assertEqual(reloaded.best("unknown"), 0)

    def test_survives_corrupt_file(self):
        self.path.write_text("{not json")
        self.assertEqual(HighScores(self.path).best("classic"), 0)


if __name__ == "__main__":
    unittest.main()
