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

    async def get_team_abbrevs(self) -> dict[int, str]:
        """Return {team_id: abbreviation} for all MLB teams."""
        data = await self._get("/api/v1/teams", {"sportId": 1})
        return {t["id"]: t["abbreviation"] for t in data.get("teams", [])}


def extract_home_runs(all_plays: list[dict], seen_indices: set[int]) -> list[dict]:
    """Find new home run plays that haven't been seen yet.

    Returns list of dicts with HR details.
    """
    home_runs = []
    for play in all_plays:
        idx = play.get("about", {}).get("atBatIndex")
        if idx is None or idx in seen_indices:
            continue

        if not play.get("about", {}).get("isComplete"):
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


def render_linescore_image(linescore: dict, away_name: str, home_name: str) -> bytes:
    """Render a linescore as a PNG image. Returns PNG bytes."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    innings = linescore.get("innings", [])
    totals = linescore.get("teams", {})

    # Build table data
    header = [""] + [str(i.get("num", "")) for i in innings] + ["R", "H", "E"]
    away_row = [away_name[:4]] + [str(i.get("away", {}).get("runs", "")) for i in innings]
    away_t = totals.get("away", {})
    away_row += [str(away_t.get("runs", 0)), str(away_t.get("hits", 0)), str(away_t.get("errors", 0))]
    home_row = [home_name[:4]] + [str(i.get("home", {}).get("runs", "")) for i in innings]
    home_t = totals.get("home", {})
    home_row += [str(home_t.get("runs", 0)), str(home_t.get("hits", 0)), str(home_t.get("errors", 0))]

    rows = [header, away_row, home_row]

    # Drawing config
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    pad_x, pad_y = 12, 8
    cell_h = 30

    # Calculate column widths
    temp_img = Image.new("RGB", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    num_cols = len(header)
    col_widths = []
    for c in range(num_cols):
        max_w = 0
        for row in rows:
            if c < len(row):
                bbox = temp_draw.textbbox((0, 0), row[c], font=font)
                max_w = max(max_w, bbox[2] - bbox[0])
        col_widths.append(max_w + pad_x * 2)

    # Ensure minimum width for cells
    col_widths = [max(w, 36) for w in col_widths]
    col_widths[0] = max(col_widths[0], 60)  # team name column

    total_w = sum(col_widths)
    total_h = cell_h * len(rows) + cell_h  # +1 for header
    # Separator column index (before R H E)
    sep_col = len(header) - 3

    bg_color = (47, 49, 54)       # Discord dark theme
    header_bg = (32, 34, 37)
    text_color = (255, 255, 255)
    dim_color = (185, 187, 190)
    line_color = (64, 68, 75)

    img = Image.new("RGB", (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(img)

    for r, row in enumerate(rows):
        y = r * cell_h
        # Header row background
        if r == 0:
            draw.rectangle([0, y, total_w, y + cell_h], fill=header_bg)

        x = 0
        for c, cell in enumerate(row):
            color = dim_color if r == 0 else text_color
            bbox = draw.textbbox((0, 0), cell, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            cx = x + (col_widths[c] - tw) // 2
            cy = y + (cell_h - th) // 2
            draw.text((cx, cy), cell, fill=color, font=font)
            x += col_widths[c]

        # Horizontal line under header
        if r == 0:
            draw.line([0, y + cell_h - 1, total_w, y + cell_h - 1], fill=line_color)

    # Vertical separator before R H E
    sep_x = sum(col_widths[:sep_col])
    draw.line([sep_x, 0, sep_x, total_h], fill=line_color, width=2)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def get_team_logo_url(team_abbrev: str) -> str:
    """Return ESPN team logo URL for a given MLB team abbreviation."""
    # ESPN uses lowercase abbreviations
    abbrev = team_abbrev.lower()
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/{abbrev}.png&h=200&w=200"
