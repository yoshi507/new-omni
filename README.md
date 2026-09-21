# OmniBot (Python) — `new-omni`

**Complete rebuild** of OmniBot: Discord bot + web dashboard + REST API in **one Python process**.

Repository: https://github.com/yoshi507/new-omni

## Feature parity

| Area | Included |
|------|----------|
| Slash + prefix + `omni` / nickname natural AI | Yes |
| AI chat, summary, moderate, security, imagine | Yes (20/guild/day) |
| Per-server personality | Yes |
| Economy & games | Yes |
| Moderation + automod + anti-spam | Yes |
| Anti-nuke monitor/alert | Yes |
| Welcome / goodbye / autorole / leveling | Yes |
| Dead Chat settings | Yes |
| Appeals (Discord + website) | Yes |
| Giveaways, reaction roles, quiz | Yes |
| Advertise board, partner, affiliate | Yes |
| Music (SoundCloud-first, no YouTube) | Yes |
| Captcha toggle, userphone | Yes |
| Translate (non-AI) | Yes |
| Dashboard OAuth + settings toggles | Yes |
| ToS / Privacy routes | Yes |

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill secrets
python main.py
```

- Dashboard: `http://HOST:PORT/`
- Health: `/health`
- Version: `/version`

System packages: **ffmpeg** recommended for music.

## Environment variables

See `.env.example`. Full list is in the response / docs below after deploy.

## Discord Developer Portal

1. Redirect URL: `{PUBLIC_BASE_URL}/auth/discord/callback`
2. Scopes: `identify`, `guilds`
3. Bot intents: Message Content, Server Members, presence optional

## Wispbyte

Start command: `python main.py`  
Set `PORT` (injected) and all env vars from `.env.example`.
