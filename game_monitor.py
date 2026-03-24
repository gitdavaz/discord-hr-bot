"""Monitors live MLB games and detects home runs."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timezone, datetime
from typing import Callable, Awaitable

import aiohttp

from mlb_api import MLBApi, extract_home_runs

logger = logging.getLogger(__name__)

# Callback type: called with (home_run_info, game_info, linescore)
HRCallback = Callable[[dict, dict, dict], Awaitable[None]]


class GameMonitor:
    def __init__(self, poll_interval: int = 15):
        self.poll_interval = poll_interval
        # {game_pk: set of seen atBatIndex}
        self._seen_plays: dict[int, set[int]] = {}
        self._running = False
        self._on_home_run: HRCallback | None = None

    def on_home_run(self, callback: HRCallback):
        self._on_home_run = callback

    async def run(self, session: aiohttp.ClientSession):
        """Main polling loop."""
        self._running = True
        api = MLBApi(session)

        while self._running:
            try:
                await self._poll(api)
            except Exception:
                logger.exception("Error during poll cycle")
            await asyncio.sleep(self.poll_interval)

    async def _poll(self, api: MLBApi):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        games = await api.get_todays_games(today)

        live_games = [
            g for g in games
            if g.get("status", {}).get("abstractGameState") == "Live"
        ]

        if not live_games:
            logger.debug("No live games right now")
            return

        logger.debug("Monitoring %d live game(s)", len(live_games))

        for game in live_games:
            game_pk = game["gamePk"]
            if game_pk not in self._seen_plays:
                # New game — backfill seen plays so we don't spam old HRs
                self._seen_plays[game_pk] = set()
                feed = await api.get_live_feed(game_pk)
                all_plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
                for play in all_plays:
                    idx = play.get("about", {}).get("atBatIndex")
                    if idx is not None:
                        self._seen_plays[game_pk].add(idx)
                logger.info(
                    "Joined game %d with %d existing plays",
                    game_pk, len(self._seen_plays[game_pk])
                )
                continue

            feed = await api.get_live_feed(game_pk)
            all_plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])

            home_runs = extract_home_runs(all_plays, self._seen_plays[game_pk])

            # Mark all new plays as seen (not just HRs)
            for play in all_plays:
                idx = play.get("about", {}).get("atBatIndex")
                if idx is not None:
                    self._seen_plays[game_pk].add(idx)

            if not home_runs or not self._on_home_run:
                continue

            game_info = {
                "game_pk": game_pk,
                "away_team": game["teams"]["away"]["team"]["name"],
                "home_team": game["teams"]["home"]["team"]["name"],
            }

            linescore = await api.get_linescore(game_pk)

            for hr in home_runs:
                logger.info("HR detected: %s", hr["description"])
                await self._on_home_run(hr, game_info, linescore)

        # Clean up finished games
        live_pks = {g["gamePk"] for g in live_games}
        finished = [pk for pk in self._seen_plays if pk not in live_pks]
        for pk in finished:
            # Keep for a bit in case the game just ended but keep memory bounded
            pass

    def stop(self):
        self._running = False
