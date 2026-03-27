# MLB Home Run Discord Bot

A Discord bot that monitors live MLB games and sends notifications to subscribed channels when a home run is hit. Notifications include the batter, pitcher, exit velocity, distance, current score, and a rendered box score image.

## Setup

### 1. Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** and name it
3. Go to **Bot** in the sidebar, click **Add Bot**
4. Copy the bot **Token** — you'll need this for the `.env` file
5. Go to **OAuth2 > URL Generator**
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: **Send Messages**, **Embed Links**, **Read Message History**
6. Copy the generated URL and open it to invite the bot to your server

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```
DISCORD_BOT_TOKEN=your-bot-token-here
POLL_INTERVAL=15
```

### 3. Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 4. Deploy on DigitalOcean (Droplet)

```bash
# On the Droplet
git clone https://github.com/YOUR_USERNAME/discord-hr-bot.git
cd discord-hr-bot
cp .env.example .env   # add your bot token
docker compose up -d --build
```

## Discord Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/subscribe [#channel]` | Subscribe a channel to HR notifications (defaults to current channel) | Manage Channels |
| `/unsubscribe [#channel]` | Unsubscribe a channel | Manage Channels |
| `/status` | Show which channels are subscribed | None |
| `/test` | Send a fake HR notification to preview the format | None |

## Announcement Script

Send messages as the bot to all subscribed channels from the Droplet CLI:

```bash
# Simple message
docker compose exec bot python announce.py "Your message here"

# With newlines
docker compose exec bot python announce.py "First line\nSecond line"

# Mention @everyone
docker compose exec bot python announce.py "Hey @everyone — games delayed due to weather!"

# Mention a specific user (right-click user in Discord > Copy User ID)
docker compose exec bot python announce.py "Thanks <@123456789012345678> for the feedback!"
```

## Updating

Push changes from your local machine:

```bash
git add -A && git commit -m "your message"
git push
```

Then on the Droplet:

```bash
cd ~/discord-hr-bot
git pull
docker compose up -d --build
```

## Useful Droplet Commands

```bash
docker compose logs -f          # Live logs
docker compose logs --tail 50   # Last 50 lines
docker compose ps               # Check if container is running
docker compose restart           # Restart the bot
docker compose down              # Stop the bot
```

## How It Works

- Polls the MLB Stats API every 15 seconds for live games
- Skips exhibition games
- Detects home runs by watching for new completed plays with `eventType: home_run`
- Checks both today and yesterday's schedule (UTC) to catch late-night West Coast games
- Sends a Discord embed with batter, pitcher, exit velocity, distance, score, team logo, and a rendered box score image
- Subscriptions are persisted to `data/subscriptions.json`
