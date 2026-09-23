"""Tiny JSON-backed high score table, one best score per game mode."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional, Union

DEFAULT_PATH = Path.home() / ".snake_scores.json"


class HighScores:
    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path = Path(path or os.environ.get("SNAKE_SCORES_FILE") or DEFAULT_PATH)
        self._scores: Dict[str, int] = self._load()

    def _load(self) -> Dict[str, int]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items() if isinstance(v, int)}

    def best(self, mode: str) -> int:
        return self._scores.get(mode, 0)

    def submit(self, mode: str, score: int) -> bool:
        """Record ``score`` if it beats the current best. Returns True on a new record."""
        if score <= self.best(mode):
            return False
        self._scores[mode] = score
        self._save()
        return True

    def _save(self) -> None:
        # Losing a high score is not worth crashing the game over.
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._scores, indent=2, sort_keys=True))
            tmp.replace(self.path)
        except OSError:
            pass
