"""Send an announcement to all subscribed channels as the bot."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import discord

# Load .env file if present
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

DATA_DIR = Path(__file__).resolve().parent / "data"
SUBSCRIPTIONS_FILE = DATA_DIR / "subscriptions.json"


def load_subscriptions() -> dict[str, list[int]]:
    if SUBSCRIPTIONS_FILE.exists():
        with open(SUBSCRIPTIONS_FILE) as f:
            return json.load(f)
    return {}


async def send_announcement(message: str):
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN not set")
        sys.exit(1)

    subs = load_subscriptions()
    if not subs:
        print("No subscribed channels found.")
        sys.exit(0)

    all_channels = [cid for ids in subs.values() for cid in ids]
    print(f"Sending to {len(all_channels)} channel(s)...")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        sent = 0
        for channel_id in all_channels:
            channel = client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await client.fetch_channel(channel_id)
                except Exception as e:
                    print(f"  Failed to fetch channel {channel_id}: {e}")
                    continue
            try:
                await channel.send(message)
                print(f"  Sent to #{channel.name} ({channel_id})")
                sent += 1
            except discord.Forbidden:
                print(f"  Missing permissions for #{channel.name} ({channel_id})")
            except Exception as e:
                print(f"  Error sending to {channel_id}: {e}")

        print(f"Done. Sent to {sent}/{len(all_channels)} channel(s).")
        await client.close()

    await client.start(token)


def main():
    if len(sys.argv) < 2:
        print('Usage: python announce.py "Your message here"')
        print('  Mention users with <@USER_ID>')
        print('  Use @everyone or @here for broad mentions')
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    message = message.replace("\\n", "\n")
    asyncio.run(send_announcement(message))


if __name__ == "__main__":
    main()
