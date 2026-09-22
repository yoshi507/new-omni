# OmniBot Feature Universe — Implementation Map

Discord limits **100 global slash commands**. OmniBot uses **command groups**, **prefix commands**, and the **dashboard** so hundreds of actions fit.

## Status legend
- ✅ Implemented
- 🟡 Partial / needs optional API key
- ❌ Explicitly out of scope (per request)

## Implemented
1. Core — slash, prefix, buttons, cooldowns, permissions, per-server JSON, help, dashboard, OAuth, presence ✅
2–4. Moderation / Logging / Security — kick ban timeout warn purge lock slowmode automod anti-spam anti-nuke logging honeypot ✅
5. Welcome / goodbye / autorole / verification button gate ✅
6. Tickets open/claim/close ✅
7. Staff notes & cases ✅
8. Roles — autorole, reaction roles, give/remove, **sticky roles** ✅
9. Announcements ✅
10–11. Stats `/info` + dashboard ✅
12. Giveaways start/reroll ✅
13–15. Economy, levels, profiles, rep ✅
16. Games — trivia, hangman, guess, rps, **tic-tac-toe**, counting, word-chain ✅
17. Music YouTube (yt-dlp + ffmpeg) ✅
18. Media memes/cats/dogs 🟡
19. AI chat summary moderate security image personality memory limits ✅
20. Translate (MyMemory, non-AI) ✅
21–23. Info search util weather calc poll remind hash ✅
24–28. Birthdays suggestions polls AFK ✅
29. **Starboard** ✅
30. **Invite tracking + leaderboard** ✅
31. **Booster celebration** ✅
32–33. Temp voice join-to-create ✅
34–36. Advertise board ✅
37. Fun suite ✅
38. Automation keyword triggers + custom prefix commands ✅
41. Config backup export snapshots ✅
43. Health `/health` `/version` ✅
44. Dashboard multi-section + AI personality ✅

## Explicitly excluded (user request)
- ❌ Global cross-server economy
- ❌ Self-hosted / local LLM
- ❌ Social notifications (Twitch/TikTok/YouTube live)
- ❌ Premium / Stripe billing
- ❌ Tebex shop integration
- ❌ Minecraft / FiveM status embeds

## Slash command strategy
Groups: `/game`, `/engage`, `/invite`, `/verify`, `/music`, `/roles`, `/util`, `/level`, `/auto`, `/backup`, …
Secondary actions use **prefix** (`!afk`, custom commands) or **dashboard toggles**.

## External APIs (when available)
NASA DEMO_KEY, CoinGecko, open-er-api, wttr.in, Wikipedia, Urban Dictionary, GitHub, dictionaryapi, MyMemory, meme-api, dog.ceo, thecatapi
