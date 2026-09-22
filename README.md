# OmniBot (Python) — `new-omni`

Discord bot + web dashboard + REST API in **one Python process**.

Repository: https://github.com/yoshi507/new-omni

## Quick start (VPS / local)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill secrets
python main.py
```

- Dashboard: `http://HOST:PORT/`
- Health: `/health`
- Version: `/version`

System package **ffmpeg** is recommended for music and voice TTS.

## Pterodactyl / panel hosts

### 1. Egg
Use a **Python** egg (not Node). Python 3.10+ (3.12 / 3.13 OK).

### 2. Files
Upload the **full** repo into `/home/container` so you have:

```text
/home/container/
  main.py
  requirements.txt
  start.sh
  omnibot/
  public/
  .env          (or set vars in the panel)
```

**GitHub zip note:** downloading the ZIP creates a nested folder (`new-omni-main/`).  
Either:

- Move everything *out* of that folder into `/home/container`, **or**
- Set startup to `bash start.sh` — it auto-detects the nested folder.

### 3. Startup command

**Option A (recommended):**
```bash
bash start.sh
```

**Option B (panel Python egg variables):**
- `PY_FILE` = `main.py`
- `REQUIREMENTS_FILE` = `requirements.txt`

If you use Option B, files must already be flattened (no nested `new-omni-main`).

### 4. Environment variables
Set at least (panel Variables or `.env`):

| Variable | Required |
|----------|----------|
| `DISCORD_TOKEN` | Yes |
| `DISCORD_CLIENT_ID` | Dashboard |
| `DISCORD_CLIENT_SECRET` | Dashboard |
| `PUBLIC_BASE_URL` | Dashboard OAuth |
| `SESSION_SECRET` | Dashboard sessions |
| `GROQ_API_KEY` | AI features |
| `PORT` | Usually injected by panel |

See `.env.example` for the full list.

### 5. Discord Developer Portal
1. Redirect: `{PUBLIC_BASE_URL}/auth/discord/callback`
2. Scopes: `identify`, `guilds`
3. Intents: Message Content, Server Members

## Concurrency

- **Global pool:** 10 heavy tasks at once (AI, music resolve, TTS, etc.) shared by all servers
- **Per guild:** max 1 concurrent heavy task
- Extra work **queues** (does not reject)

## Feature overview

Slash groups + prefix + natural AI · moderation · tickets · economy · games · music (yt-dlp) · voice TTS with character voices · dashboard toggles · and more. See `FEATURES.md`.
