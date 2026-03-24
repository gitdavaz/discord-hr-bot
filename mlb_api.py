"""Async client for the MLB Stats API (statsapi.mlb.com)."""
from __future__ import annotations

import aiohttp

BASE_URL = "https://statsapi.mlb.com"


class MLBApi:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with self.session.get(f"{BASE_URL}{path}", params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_todays_games(self, date: str) -> list[dict]:
        """Return list of game dicts for a given date (YYYY-MM-DD)."""
        data = await self._get("/api/v1/schedule", {"sportId": 1, "date": date})
        if not data.get("dates"):
            return []
        return data["dates"][0].get("games", [])

    async def get_live_feed(self, game_pk: int) -> dict:
        """Return full live feed for a game."""
        return await self._get(f"/api/v1.1/game/{game_pk}/feed/live")

    async def get_linescore(self, game_pk: int) -> dict:
        """Return linescore for a game."""
        return await self._get(f"/api/v1/game/{game_pk}/linescore")


def extract_home_runs(all_plays: list[dict], seen_indices: set[int]) -> list[dict]:
    """Find new home run plays that haven't been seen yet.

    Returns list of dicts with HR details.
    """
    home_runs = []
    for play in all_plays:
        idx = play.get("about", {}).get("atBatIndex")
        if idx is None or idx in seen_indices:
            continue

        result = play.get("result", {})
        if result.get("eventType") != "home_run":
            continue

        seen_indices.add(idx)

        batter = play.get("matchup", {}).get("batter", {})
        pitcher = play.get("matchup", {}).get("pitcher", {})
        about = play.get("about", {})

        home_runs.append({
            "batter_name": batter.get("fullName", "Unknown"),
            "pitcher_name": pitcher.get("fullName", "Unknown"),
            "description": result.get("description", ""),
            "inning": about.get("inning"),
            "half": "Top" if about.get("isTopInning") else "Bottom",
            "rbi": result.get("rbi", 1),
            "away_score": result.get("awayScore", 0),
            "home_score": result.get("homeScore", 0),
        })

    return home_runs


def format_linescore(linescore: dict, away_name: str, home_name: str) -> str:
    """Format a linescore into a text box score table."""
    innings = linescore.get("innings", [])
    totals = linescore.get("teams", {})

    # Header row
    inning_nums = [str(i.get("num", "")) for i in innings]
    header = "     " + " ".join(f"{n:>3}" for n in inning_nums) + "  |   R   H   E"

    # Away row
    away_runs = [str(i.get("away", {}).get("runs", "")) for i in innings]
    away_total = totals.get("away", {})
    away_line = (
        f"{away_name[:4]:>4} "
        + " ".join(f"{r:>3}" for r in away_runs)
        + f"  | {away_total.get('runs', 0):>3} {away_total.get('hits', 0):>3} {away_total.get('errors', 0):>3}"
    )

    # Home row
    home_runs = [str(i.get("home", {}).get("runs", "")) for i in innings]
    home_total = totals.get("home", {})
    home_line = (
        f"{home_name[:4]:>4} "
        + " ".join(f"{r:>3}" for r in home_runs)
        + f"  | {home_total.get('runs', 0):>3} {home_total.get('hits', 0):>3} {home_total.get('errors', 0):>3}"
    )

    return f"```\n{header}\n{away_line}\n{home_line}\n```"
