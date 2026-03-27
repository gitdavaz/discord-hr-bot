"""Monitors live MLB games and detects home runs."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timezone, datetime, timedelta
from typing import Callable, Awaitable

import aiohttp

from mlb_api import MLBApi, extract_home_runs

logger = logging.getLogger(__name__)

# Callback type: called with (home_run_info, game_info)
HRCallback = Callable[[dict, dict], Awaitable[None]]


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
        self._team_abbrevs = await api.get_team_abbrevs()
        logger.info("Loaded %d team abbreviations", len(self._team_abbrevs))

        while self._running:
            try:
                await self._poll(api)
            except Exception:
                logger.exception("Error during poll cycle")
            await asyncio.sleep(self.poll_interval)

    async def _poll(self, api: MLBApi):
        now_utc = datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        yesterday = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")

        # Check both today and yesterday to catch late-night games
        # that started on the previous calendar day (UTC)
        games = await api.get_todays_games(today)
        if yesterday != today:
            yesterday_games = await api.get_todays_games(yesterday)
            # Deduplicate by gamePk
            seen_pks = {g["gamePk"] for g in games}
            for g in yesterday_games:
                if g["gamePk"] not in seen_pks:
                    games.append(g)

        live_games = [
            g for g in games
            if g.get("status", {}).get("abstractGameState") == "Live"
            and g.get("gameType") != "E"
        ]

        if not live_games:
            logger.info("No live games right now")
            return

        logger.info("Polling %d live game(s)", len(live_games))

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

            new_play_count = len(all_plays) - len(self._seen_plays[game_pk])
            home_runs = extract_home_runs(all_plays, self._seen_plays[game_pk])

            # Only mark completed plays as seen — in-progress plays
            # may not have eventType populated yet
            for play in all_plays:
                idx = play.get("about", {}).get("atBatIndex")
                if idx is not None and play.get("about", {}).get("isComplete"):
                    self._seen_plays[game_pk].add(idx)

            if new_play_count > 0:
                logger.info(
                    "Game %d: %d new play(s), %d HR(s) found",
                    game_pk, new_play_count, len(home_runs)
                )

            if not home_runs or not self._on_home_run:
                continue

            away_id = game["teams"]["away"]["team"]["id"]
            home_id = game["teams"]["home"]["team"]["id"]
            game_info = {
                "game_pk": game_pk,
                "away_team": game["teams"]["away"]["team"]["name"],
                "home_team": game["teams"]["home"]["team"]["name"],
                "away_abbrev": self._team_abbrevs.get(away_id, "???"),
                "home_abbrev": self._team_abbrevs.get(home_id, "???"),
            }

            for hr in home_runs:
                logger.info("HR detected: %s", hr["description"])
                await self._on_home_run(hr, game_info)

        # Clean up finished games
        live_pks = {g["gamePk"] for g in live_games}
        finished = [pk for pk in self._seen_plays if pk not in live_pks]
        for pk in finished:
            # Keep for a bit in case the game just ended but keep memory bounded
            pass

    def stop(self):
        self._running = False
