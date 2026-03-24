"""Discord bot that sends home run notifications."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord import app_commands

from game_monitor import GameMonitor
from mlb_api import format_linescore

# Load .env file if present
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
SUBSCRIPTIONS_FILE = DATA_DIR / "subscriptions.json"


# --- Subscription persistence ---

def load_subscriptions() -> dict[str, list[int]]:
    """Load {guild_id: [channel_id, ...]} from disk."""
    if SUBSCRIPTIONS_FILE.exists():
        with open(SUBSCRIPTIONS_FILE) as f:
            return json.load(f)
    return {}


def save_subscriptions(subs: dict[str, list[int]]):
    DATA_DIR.mkdir(exist_ok=True)
    with open(SUBSCRIPTIONS_FILE, "w") as f:
        json.dump(subs, f, indent=2)


# --- Bot setup ---

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
subscriptions = load_subscriptions()


@tree.command(name="subscribe", description="Subscribe this channel to home run notifications")
@app_commands.describe(channel="Channel to send HR notifications to (defaults to current)")
@app_commands.checks.has_permissions(manage_channels=True)
async def subscribe(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    target = channel or interaction.channel
    guild_id = str(interaction.guild_id)

    if guild_id not in subscriptions:
        subscriptions[guild_id] = []

    if target.id in subscriptions[guild_id]:
        await interaction.response.send_message(
            f"{target.mention} is already subscribed to HR notifications.", ephemeral=True
        )
        return

    subscriptions[guild_id].append(target.id)
    save_subscriptions(subscriptions)
    await interaction.response.send_message(
        f"{target.mention} will now receive home run notifications!"
    )


@tree.command(name="unsubscribe", description="Unsubscribe a channel from home run notifications")
@app_commands.describe(channel="Channel to unsubscribe (defaults to current)")
@app_commands.checks.has_permissions(manage_channels=True)
async def unsubscribe(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    target = channel or interaction.channel
    guild_id = str(interaction.guild_id)

    if guild_id in subscriptions and target.id in subscriptions[guild_id]:
        subscriptions[guild_id].remove(target.id)
        if not subscriptions[guild_id]:
            del subscriptions[guild_id]
        save_subscriptions(subscriptions)
        await interaction.response.send_message(
            f"{target.mention} unsubscribed from HR notifications."
        )
    else:
        await interaction.response.send_message(
            f"{target.mention} is not subscribed.", ephemeral=True
        )


@tree.command(name="test", description="Send a fake home run notification to this channel")
async def test(interaction: discord.Interaction):
    hr = {
        "batter_name": "Shohei Ohtani",
        "pitcher_name": "Gerrit Cole",
        "description": "Shohei Ohtani homers (1) on a fly ball to center field. Mookie Betts scores.",
        "half": "Bottom",
        "inning": 5,
        "rbi": 2,
        "away_score": 3,
        "home_score": 4,
    }
    game_info = {
        "game_pk": 0,
        "away_team": "New York Yankees",
        "home_team": "Los Angeles Dodgers",
    }
    linescore = {
        "innings": [
            {"num": i, "away": {"runs": r[0]}, "home": {"runs": r[1]}}
            for i, r in enumerate(
                [(0, 1), (2, 0), (0, 0), (1, 1), (0, 2)], start=1
            )
        ],
        "teams": {
            "away": {"runs": 3, "hits": 7, "errors": 0},
            "home": {"runs": 4, "hits": 6, "errors": 1},
        },
    }
    embed = discord.Embed(
        title="HOME RUN!",
        description=hr["description"],
        color=discord.Color.red(),
    )
    embed.add_field(name="Batter", value=hr["batter_name"], inline=True)
    embed.add_field(name="Pitcher", value=hr["pitcher_name"], inline=True)
    embed.add_field(name="Inning", value=f"{hr['half']} {hr['inning']}", inline=True)
    embed.add_field(name="RBI", value=str(hr["rbi"]), inline=True)
    embed.add_field(
        name="Score",
        value=f"{game_info['away_team']} {hr['away_score']} - {hr['home_score']} {game_info['home_team']}",
        inline=False,
    )
    box = format_linescore(linescore, game_info["away_team"], game_info["home_team"])
    embed.add_field(name="Box Score", value=box, inline=False)
    embed.set_footer(text="Test notification")
    await interaction.response.send_message(embed=embed)


@tree.command(name="status", description="Show which channels are subscribed to HR notifications")
async def status(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    channel_ids = subscriptions.get(guild_id, [])

    if not channel_ids:
        await interaction.response.send_message("No channels are subscribed in this server.", ephemeral=True)
        return

    mentions = [f"<#{cid}>" for cid in channel_ids]
    await interaction.response.send_message(
        f"HR notifications go to: {', '.join(mentions)}", ephemeral=True
    )


# --- Home run notification ---

async def send_hr_notification(hr: dict, game_info: dict, linescore: dict):
    """Send an embed to all subscribed channels."""
    embed = discord.Embed(
        title="HOME RUN!",
        description=hr["description"],
        color=discord.Color.red(),
    )
    embed.add_field(
        name="Batter", value=hr["batter_name"], inline=True
    )
    embed.add_field(
        name="Pitcher", value=hr["pitcher_name"], inline=True
    )
    embed.add_field(
        name="Inning", value=f"{hr['half']} {hr['inning']}", inline=True
    )
    embed.add_field(
        name="RBI", value=str(hr["rbi"]), inline=True
    )
    embed.add_field(
        name="Score",
        value=f"{game_info['away_team']} {hr['away_score']} - {hr['home_score']} {game_info['home_team']}",
        inline=False,
    )

    box = format_linescore(linescore, game_info["away_team"], game_info["home_team"])
    embed.add_field(name="Box Score", value=box, inline=False)

    embed.set_footer(text=f"Game {game_info['game_pk']}")

    for guild_id, channel_ids in subscriptions.items():
        for channel_id in channel_ids:
            channel = bot.get_channel(channel_id)
            if channel is None:
                continue
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                logger.warning("Cannot send to channel %d - missing permissions", channel_id)
            except Exception:
                logger.exception("Failed to send HR notification to %d", channel_id)


# --- Lifecycle ---

_monitor_started = False


@bot.event
async def on_ready():
    global _monitor_started
    await tree.sync()
    logger.info("Logged in as %s (commands synced)", bot.user)

    if not _monitor_started:
        _monitor_started = True
        poll_interval = int(os.environ.get("POLL_INTERVAL", "15"))
        monitor = GameMonitor(poll_interval=poll_interval)
        monitor.on_home_run(send_hr_notification)
        bot.loop.create_task(_run_monitor(monitor))


async def _run_monitor(monitor: GameMonitor):
    """Run the monitor with a persistent session, restarting on failure."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await monitor.run(session)
        except Exception:
            logger.exception("Monitor crashed, restarting in 10s")
            await asyncio.sleep(10)


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN environment variable is required")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
