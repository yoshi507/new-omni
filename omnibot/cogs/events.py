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
from omnibot.services.question_packs import pick_question

NATURAL_TRIGGER = re.compile(r"\b(?:omni(?:bot)?)\b", re.I)


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
                minutes = int(dc.get("minutes") or 60)
                ch_id = dc.get("channelId")
                channels = []
                if ch_id:
                    ch = guild.get_channel(int(ch_id))
                    if isinstance(ch, discord.TextChannel):
                        channels = [ch]
                else:
                    channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages][:5]
                now = time.time()
                last_map = dc.get("lastMessageAt") or {}
                for ch in channels:
                    key = str(ch.id)
                    last = float(last_map.get(key) or 0)
                    if last <= 0:
                        def mut_seed(d, k=key):
                            d.setdefault("deadChat", {}).setdefault("lastMessageAt", {})[k] = now
                        storage.update_guild(guild.id, mut_seed)
                        continue
                    if now - last < minutes * 60:
                        continue
                    cd_key = f"{guild.id}:{ch.id}"
                    if now - float(self._dead_cd.get(cd_key) or 0) < 120:
                        continue
                    self._dead_cd[cd_key] = now
                    q = pick_question(data)
                    try:
                        await ch.send(f"💬 **Dead chat reviver**\n{q}")
                    except Exception:
                        pass
                    def mut_reset(d, k=key):
                        d.setdefault("deadChat", {}).setdefault("lastMessageAt", {})[k] = time.time()
                    storage.update_guild(guild.id, mut_reset)
            except Exception:
                continue

    @deadchat_loop.before_loop
    async def before_deadchat(self):
        await self.bot.wait_until_ready()

    def _extract_natural_prompt(self, content: str, guild: discord.Guild) -> str | None:
        text = content.strip()
        if not text:
            return None
        if NATURAL_TRIGGER.search(text):
            cleaned = NATURAL_TRIGGER.sub(" ", text)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,:;-").strip()
            return cleaned or "hi"
        me = guild.me
        if me and me.nick:
            nick = me.nick.strip()
            low = text.lower()
            nlow = nick.lower()
            if low.startswith(nlow + " ") or low.startswith(nlow + ",") or low.startswith(nlow + ":"):
                return text[len(nick) :].lstrip(" ,:").strip() or "hi"
        if me and (f"<@{me.id}>" in text or f"<@!{me.id}>" in text):
            cleaned = text.replace(f"<@{me.id}>", " ").replace(f"<@!{me.id}>", " ")
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,:;-").strip()
            return cleaned or "hi"
        return None

    def _smart_automod_hit(self, content: str, data: dict) -> str | None:
        """Rule-based smart automod — no external API / no Groq key."""
        sm = data.get("smartAutomod") or {}
        if not sm.get("enabled"):
            return None
        text = content or ""
        low = text.lower()
        if sm.get("blockInvites", True):
            if re.search(r"(discord(?:\.gg|app\.com/invite)/[a-z0-9-]+)", low):
                return "Discord invite links are not allowed"
        if sm.get("blockLinks", False):
            if re.search(r"https?://\S+", low) and "discord.com" not in low:
                return "Links are not allowed"
        max_m = int(sm.get("maxMentions") or 5)
        if len(re.findall(r"<@!?\d+>", text)) > max_m:
            return f"Too many mentions (max {max_m})"
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= 12:
            if sum(1 for c in letters if c.isupper()) / len(letters) >= 0.75:
                return "Excessive caps"
        if re.search(r"(.)\1{6,}", text):
            return "Repeated character spam"
        if sum(1 for c in text if "\u0300" <= c <= "\u036f") > 8:
            return "Obfuscated text"
        scam = ["free nitro", "steam gift", "airdrop", "claim your", "wallet connect",
                "double your", "crypto giveaway", "click here to claim", "discord nitro free"]
        if any(p in low for p in scam):
            return "Possible scam/phishing content"
        for w in ["kys", "kill yourself"]:
            if re.search(rf"\b{re.escape(w)}\b", low):
                return "Prohibited language"
        return None

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

        # Smart automod (local rules — does NOT use AI API key)
        try:
            reason = self._smart_automod_hit(message.content or "", data)
        except Exception:
            reason = None
        if reason:
            sm = data.get("smartAutomod") or {}
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(
                    f"{message.author.mention} message removed (**smart automod**): {reason}",
                    delete_after=10,
                )
            except Exception:
                pass
            action = str(sm.get("action") or "delete")
            if action == "timeout" and isinstance(message.author, discord.Member):
                try:
                    from datetime import timedelta
                    mins = int(sm.get("timeoutMinutes") or 5)
                    await message.author.timeout(timedelta(minutes=mins), reason=f"Smart automod: {reason}")
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
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} slow down (anti-spam).",
                        delete_after=6,
                    )
                except Exception:
                    pass
                self._spam[key] = []
                return

        ls = data.get("levelSettings") or {}
        if ls.get("enabled", True):
            xp_key = f"{message.guild.id}:{message.author.id}"
            now = time.time()
            if now - float(self._xp_cd.get(xp_key) or 0) >= 60:
                self._xp_cd[xp_key] = now
                xmin, xmax = int(ls.get("xpMin") or 15), int(ls.get("xpMax") or 25)
                gain = random.randint(min(xmin, xmax), max(xmin, xmax))
                leveled_to: int | None = None

                def mut_xp(d):
                    nonlocal leveled_to
                    lv = d.setdefault("levels", {}).setdefault(
                        str(message.author.id), {"xp": 0, "level": 0}
                    )
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

        prompt = None
        me = message.guild.me
        if me and me in message.mentions:
            cleaned = message.content
            for u in message.mentions:
                cleaned = cleaned.replace(f"<@{u.id}>", " ").replace(f"<@!{u.id}>", " ")
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,:;-").strip()
            prompt = cleaned or "hi"
        else:
            prompt = self._extract_natural_prompt(message.content, message.guild)

        dash = data.get("dashboard") or {}
        ai_cfg = dash.get("ai") or {}
        if prompt and ai_cfg.get("naturalInvocation", True) and ai_cfg.get("enabled", True):
            first = prompt.split()[0].lower() if prompt.split() else ""
            if first in {"help", "ping", "balance", "daily", "play", "skip", "stop"}:
                return
            async with message.channel.typing():
                ok, text = await groq_client.chat(message.guild.id, prompt, user_id=message.author.id)
            try:
                await message.reply(
                    f"❌ {text}" if not ok else text[:1900], mention_author=False
                )
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
