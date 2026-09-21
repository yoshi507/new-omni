# OmniBot (Python) — `new-omni`

Full rebuild of OmniBot: **Discord bot + web dashboard + REST API in one Python process**.

## Features (parity with Node OmniBot)

- Slash + prefix + natural `omni` / nickname invocation
- AI chat, summarise, moderate, security, persona (20 AI requests/guild/day)
- Image generation via Home Mode API
- Economy & games (coins, daily, shop, slots, rps, dice, trivia, …)
- Moderation, automod, anti-spam, anti-nuke (safe monitor/alert/lockdown)
- Welcome / goodbye / autorole / leveling / logging
- Appeals, quizzes, giveaways, reaction roles, tickets
- Dead Chat Reviver, partnerships, affiliate, server advertise
- Music (SoundCloud-first; Spotify metadata optional)
- Captcha verification, userphone, automations, swear jar, forum AI help
- Dashboard with Discord OAuth, per-guild settings, appeals portal

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in secrets
python main.py
```

Open `http://HOST:PORT/` for the dashboard. Health: `/health`  Version: `/version`

## Environment variables

See `.env.example` and the **Environment variables** section at the bottom of this README after deploy notes.

## Architecture

```
main.py                 # starts FastAPI (uvicorn) + discord.py bot together
omnibot/
  config.py             # env loading
  storage.py            # per-guild JSON storage
  bot.py                # discord client + cog loader
  cogs/                 # feature modules (commands + events)
  services/             # AI, music, economy, security helpers
  web/                  # FastAPI app, OAuth, settings API
public/dashboard/       # static dashboard UI
data/                   # runtime guild data (not committed)
```
