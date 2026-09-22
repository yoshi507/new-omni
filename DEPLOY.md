# Deploy OmniBot

## Important: Discord bot vs Vercel

A Discord bot needs a **persistent process** (WebSocket to Discord 24/7).

**Vercel cannot run the Discord bot.** Vercel is serverless (short-lived functions).
Use Vercel only for the **static dashboard UI** if you want a separate frontend URL.

| Piece | Where it runs |
|-------|----------------|
| Discord bot + API (`main.py`) | Pterodactyl, VPS, Railway, Render, Fly.io, etc. |
| Static dashboard HTML (optional) | Vercel / any static host |

---

## A) Pterodactyl (recommended for full bot)

1. Python egg, `PY_FILE=main.py` **or** startup: `bash start.sh`
2. Upload full repo. Nested `new-omni-main/` is OK — `main.py` and `start.sh` auto-detect it.
3. Env vars from `.env.example` (`DISCORD_TOKEN`, OAuth, `GROQ_API_KEY`, `PUBLIC_BASE_URL`, …)
4. Start

Required layout (either flat or nested is fine):

```text
…/main.py
…/omnibot/
…/public/
…/requirements.txt
```

---

## B) Vercel (dashboard static only)

1. Import GitHub repo `yoshi507/new-omni` on [vercel.com](https://vercel.com)
2. Framework: Other · Output: `public/dashboard` (see `vercel.json`)
3. Deploy → you get a URL for the UI only
4. Point the dashboard’s API base to your **bot host** `PUBLIC_BASE_URL` (bot must still run elsewhere)

OAuth redirect must still point at the **bot API** host (where FastAPI runs), not only the static Vercel URL, unless you reverse-proxy API routes.

---

## C) One-process (bot + dashboard together)

This is the default: `python main.py` serves Discord **and** the dashboard on `PORT`.
No Vercel required.

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in
python main.py
```
