"""Guild events: welcome, goodbye, autorole, leveling, automod, natural AI, deadchat."""
from __future__ import annotations

import random
import re
import time
from collections import defaultdict

import discord
from discord.ext import commands, tasks

from omnibot import storage
from omnibot.services import groq_client

NATURAL = re.compile(r"^(?:omni(?:bot)?)(?:\s+|[,:]\s*)(.+)$", re.I)

DEAD_CHAT_PROMPTS = [
    "Anyone still around? Drop a 👋 if you're here!",
    "Chat's been quiet… what's everyone up to?",
    "Dead chat? Not on my watch. Say hi!",
    "Random question: coffee or tea?",
    "Bump! What's the best thing that happened today?",
    "Hey {server} — let's get this chat moving again 🔥",
]


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._spam: dict[str, list[float]] = defaultdict(list)
        self._xp_cd: dict[str, float] = {}
        self._dead_cd: dict[str, float] = {}
        self.deadchat_loop.start()

    def cog_unload(self):
        self.deadchat_loop.cancel()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        ar = data.get("autorole") or {}
        if ar.get("enabled") and ar.get("roleId"):
            role = member.guild.get_role(int(ar["roleId"]))
            if role:
                try:
                    await member.add_roles(role, reason="OmniBot autorole")
                except Exception:
                    pass
        ws = data.get("welcomeSettings") or {}
        if ws.get("enabled") and ws.get("channelId"):
            ch = member.guild.get_channel(int(ws["channelId"]))
            if isinstance(ch, discord.TextChannel):
                msg = (
                    (ws.get("message") or "Welcome {user}!")
                    .replace("{user}", member.mention)
                    .replace("{server}", member.guild.name)
                    .replace("{username}", member.name)
                )
                try:
                    await ch.send(msg)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        gs = data.get("goodbyeSettings") or {}
        if gs.get("enabled") and gs.get("channelId"):
            ch = member.guild.get_channel(int(gs["channelId"]))
            if isinstance(ch, discord.TextChannel):
                msg = (
                    (gs.get("message") or "{username} left.")
                    .replace("{username}", member.name)
                    .replace("{server}", member.guild.name)
                    .replace("{user}", member.name)
                )
                try:
                    await ch.send(msg)
                except Exception:
                    pass

    @tasks.loop(minutes=2)
    async def deadchat_loop(self):
        for guild in list(self.bot.guilds):
            try:
                data = storage.load_guild(guild.id)
                dc = data.get("deadChat") or {}
                if not dc.get("enabled"):
                    continue
                minutes = max(5, int(dc.get("minutes") or 60))
                threshold = minutes * 60
                now = time.time()
                last_map = dc.get("lastMessageAt") or {}
                channel_ids = []
                only = dc.get("channelId")
                if only:
                    channel_ids = [str(only)]
                else:
                    channel_ids = list(last_map.keys())
                for cid in channel_ids:
                    key = f"{guild.id}:{cid}"
                    if now - self._dead_cd.get(key, 0) < threshold:
                        continue
                    last = float(last_map.get(cid) or 0)
                    if last and (now - last) < threshold:
                        continue
                    # Never messaged in this channel since enable — skip until first human msg
                    if not last:
                        continue
                    ch = guild.get_channel(int(cid))
                    if not isinstance(ch, discord.TextChannel):
                        continue
                    prompt = random.choice(DEAD_CHAT_PROMPTS).replace("{server}", guild.name)
                    custom = (dc.get("message") or "").strip()
                    if custom:
                        prompt = custom.replace("{server}", guild.name)
                    try:
                        await ch.send(prompt)
                        self._dead_cd[key] = now

                        def mut(d):
                            d.setdefault("deadChat", {}).setdefault("lastMessageAt", {})[cid] = time.time()

                        storage.update_guild(guild.id, mut)
                    except Exception:
                        pass
            except Exception:
                continue

    @deadchat_loop.before_loop
    async def before_deadchat(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        data = storage.load_guild(message.guild.id)

        dc = data.get("deadChat") or {}
        if dc.get("enabled"):

            def mut_dc(d):
                d.setdefault("deadChat", {}).setdefault("lastMessageAt", {})[
                    str(message.channel.id)
                ] = time.time()

            storage.update_guild(message.guild.id, mut_dc)

        am = data.get("automod") or {}
        if am.get("enabled") and am.get("blockedWords") and message.content:
            words = [w.strip().lower() for w in str(am["blockedWords"]).split(",") if w.strip()]
            content_l = message.content.lower()
            if any(w and w in content_l for w in words):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} that message was blocked by automod.",
                        delete_after=8,
                    )
                except Exception:
                    pass
                return

        spam = data.get("spamConfig") or {}
        if spam.get("enabled", True):
            key = f"{message.guild.id}:{message.author.id}"
            now = time.time()
            bucket = self._spam.get(key) or []
            if not isinstance(bucket, list):
                bucket = []
            bucket.append(now)
            self._spam[key] = [t for t in bucket if now - t < 7]
            if len(self._spam[key]) >= 7:
                try:
                    await message.channel.send(
                        f"{message.author.mention} slow down (anti-spam).",
                        delete_after=6,
                    )
                except Exception:
                    pass
                self._spam[key] = []

        ls = data.get("levelSettings") or {}
        if ls.get("enabled", True) and message.content:
            cd_key = f"{message.guild.id}:{message.author.id}"
            cd = int(ls.get("cooldown") or 60)
            if time.time() - self._xp_cd.get(cd_key, 0) >= cd:
                self._xp_cd[cd_key] = time.time()
                xmin, xmax = int(ls.get("xpMin") or 15), int(ls.get("xpMax") or 25)
                gain = random.randint(min(xmin, xmax), max(xmin, xmax))
                leveled_to: int | None = None

                def mut_xp(d):
                    nonlocal leveled_to
                    lv = d.setdefault("levels", {}).setdefault(
                        str(message.author.id), {"xp": 0, "level": 0}
                    )
                    # scrub old bug flag if present
                    d.pop("_levelup", None)
                    lv["xp"] = int(lv.get("xp") or 0) + gain
                    need = 100 + int(lv.get("level") or 0) * 50
                    if lv["xp"] >= need:
                        lv["xp"] -= need
                        lv["level"] = int(lv.get("level") or 0) + 1
                        leveled_to = lv["level"]

                storage.update_guild(message.guild.id, mut_xp)
                if leveled_to is not None and ls.get("announce", True):
                    try:
                        await message.channel.send(
                            f"🎉 {message.author.mention} reached level **{leveled_to}**!"
                        )
                    except Exception:
                        pass

        if not message.content:
            return
        content = message.content.strip()
        prompt = None
        m = NATURAL.match(content)
        if m:
            prompt = m.group(1).strip()
        else:
            me = message.guild.me
            if me and me.nick:
                nick = me.nick.strip()
                low = content.lower()
                nlow = nick.lower()
                if low.startswith(nlow + " ") or low.startswith(nlow + ",") or low.startswith(nlow + ":"):
                    prompt = content[len(nick) :].lstrip(" ,:").strip()

        dash = data.get("dashboard") or {}
        ai_cfg = dash.get("ai") or {}
        if prompt and ai_cfg.get("naturalInvocation", True) and ai_cfg.get("enabled", True):
            first = prompt.split()[0].lower() if prompt.split() else ""
            if first in {"help", "ping", "balance", "daily", "play", "skip", "stop"}:
                return
            async with message.channel.typing():
                ok, text = await groq_client.chat(message.guild.id, prompt)
            try:
                await message.reply(
                    f"❌ {text}" if not ok else text[:1900], mention_author=False
                )
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
