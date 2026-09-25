"""Roleplay actions + relationship (marry / ship / status) system."""
from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

RP_ACTIONS: dict[str, tuple[str, str]] = {
    "hug": ("{a} gives {b} a warm hug!", "🤗"),
    "kiss": ("{a} kisses {b}!", "💋"),
    "pat": ("{a} gently pats {b}'s head.", "🥰"),
    "cuddle": ("{a} cuddles up with {b}.", "🧸"),
    "highfive": ("{a} high-fives {b}!", "🙌"),
    "poke": ("{a} pokes {b}.", "👉"),
    "boop": ("{a} boops {b}'s nose!", "👃"),
    "wave": ("{a} waves at {b}!", "👋"),
    "slap": ("{a} playfully slaps {b}.", "👋"),
    "punch": ("{a} playfully punches {b}'s arm.", "👊"),
    "kick": ("{a} playfully kicks {b}.", "🦵"),
    "bite": ("{a} playfully bites {b}!", "😈"),
    "stare": ("{a} stares at {b} intensely…", "👀"),
    "blush": ("{a} blushes looking at {b}.", "😳"),
    "holdhands": ("{a} holds hands with {b}.", "🤝"),
    "dance": ("{a} dances with {b}!", "💃"),
    "tickle": ("{a} tickles {b}!", "🤭"),
    "comfort": ("{a} comforts {b}.", "💗"),
    "yell": ("{a} yells at {b}!", "📢"),
    "thank": ("{a} thanks {b}!", "🙏"),
    "greet": ("{a} greets {b}!", "✨"),
    "cry": ("{a} cries on {b}'s shoulder.", "😢"),
    "laugh": ("{a} laughs with {b}!", "😂"),
    "nom": ("{a} noms {b}!", "🍪"),
    "snuggle": ("{a} snuggles with {b}.", "🛏️"),
}


def _pair_key(a: int, b: int) -> str:
    x, y = sorted((int(a), int(b)))
    return f"{x}:{y}"


def _rel(data: dict, a: int, b: int) -> dict:
    rels = data.setdefault("relationships", {})
    k = _pair_key(a, b)
    return rels.setdefault(k, {"xp": 0, "married": False, "marriedAt": 0, "ship": None})


class SocialSystems(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    rp = app_commands.Group(name="rp", description="Roleplay actions")

    @rp.command(name="do", description="Perform a roleplay action on someone")
    @app_commands.describe(action="Action name (hug, kiss, pat, …)", member="Target member", note="Optional flavour text")
    async def rp_do(
        self,
        interaction: discord.Interaction,
        action: str,
        member: discord.Member,
        note: str | None = None,
    ):
        key = action.lower().strip().replace(" ", "").replace("_", "")
        aliases = {"high-five": "highfive", "holdhand": "holdhands", "handhold": "holdhands"}
        key = aliases.get(key, key)
        if key not in RP_ACTIONS:
            opts = ", ".join(sorted(RP_ACTIONS)[:12]) + "…"
            return await interaction.response.send_message(
                f"Unknown action `{action}`. Try: {opts}\nOr `/rp list`",
                ephemeral=True,
            )
        if member.id == interaction.user.id and key not in ("wave", "blush", "cry", "laugh"):
            return await interaction.response.send_message("Pick someone else for that action!", ephemeral=True)

        template, emoji = RP_ACTIONS[key]
        text = template.format(a=interaction.user.mention, b=member.mention)
        if note:
            text += f"\n*{note[:200]}*"
        emb = discord.Embed(description=f"{emoji} {text}", color=0xE91E8C)
        emb.set_footer(text=f"RP · {action}")
        await interaction.response.send_message(embed=emb)

        if interaction.guild and member.id != interaction.user.id:
            def mut(d):
                r = _rel(d, interaction.user.id, member.id)
                r["xp"] = int(r.get("xp") or 0) + random.randint(1, 3)

            try:
                storage.update_guild(interaction.guild.id, mut)
            except Exception:
                pass

    @rp.command(name="list", description="List available RP actions")
    async def rp_list(self, interaction: discord.Interaction):
        lines = [f"`{k}` {v[1]}" for k, v in sorted(RP_ACTIONS.items())]
        emb = discord.Embed(
            title="🎭 RP actions",
            description="Use `/rp do action:<name> member:@user`\n\n" + " · ".join(lines),
            color=0xE91E8C,
        )
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @rp.command(name="say", description="Speak in-character (roleplay line)")
    async def rp_say(self, interaction: discord.Interaction, character: str, line: str):
        emb = discord.Embed(description=line[:2000], color=0x9B59B6)
        emb.set_author(name=f"🎭 {character[:64]}")
        emb.set_footer(text=f"RP by {interaction.user.display_name}")
        await interaction.response.send_message(embed=emb)

    rel = app_commands.Group(name="relationship", description="Relationships, marriage & ship")

    @rel.command(name="ship", description="Ship two members (compatibility %)")
    async def rel_ship(
        self,
        interaction: discord.Interaction,
        member1: discord.Member,
        member2: discord.Member | None = None,
    ):
        a = member1
        b = member2 or interaction.user  # type: ignore
        if a.id == b.id:
            return await interaction.response.send_message("Ship two different people!", ephemeral=True)
        seed = (a.id ^ b.id) % 101
        bars = "❤️" * (seed // 10) + "🖤" * (10 - seed // 10)
        emb = discord.Embed(
            title="💘 Ship",
            description=f"{a.mention} × {b.mention}\n**{seed}%**\n{bars}",
            color=0xFF69B4,
        )
        if interaction.guild:
            def mut(d):
                r = _rel(d, a.id, b.id)
                r["ship"] = seed

            storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(embed=emb)

    @rel.command(name="marry", description="Propose marriage to someone")
    async def rel_marry(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if member.id == interaction.user.id:
            return await interaction.response.send_message("You can't marry yourself.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("You can't marry a bot.", ephemeral=True)

        data = storage.load_guild(interaction.guild.id)
        for k, v in (data.get("relationships") or {}).items():
            if not v.get("married"):
                continue
            if str(interaction.user.id) in k.split(":") or str(member.id) in k.split(":"):
                return await interaction.response.send_message(
                    "One of you is already married. Use `/relationship divorce` first.",
                    ephemeral=True,
                )

        view = MarryView(interaction.user.id, member.id, interaction.guild.id)
        emb = discord.Embed(
            title="💍 Marriage proposal",
            description=f"{interaction.user.mention} proposed to {member.mention}!\n{member.mention}, will you accept?",
            color=0xFFD700,
        )
        await interaction.response.send_message(embed=emb, view=view)

    @rel.command(name="divorce", description="End your marriage")
    async def rel_divorce(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        uid = str(interaction.user.id)
        found = [None]

        def mut(d):
            rels = d.get("relationships") or {}
            for k, v in list(rels.items()):
                if uid in k.split(":") and v.get("married"):
                    v["married"] = False
                    v["marriedAt"] = 0
                    found[0] = k
                    break

        storage.update_guild(interaction.guild.id, mut)
        if not found[0]:
            return await interaction.response.send_message("You're not married.", ephemeral=True)
        other = [x for x in found[0].split(":") if x != uid][0]
        await interaction.response.send_message(f"Marriage with <@{other}> has ended.")

    @rel.command(name="status", description="Show relationship status with someone")
    async def rel_status(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        data = storage.load_guild(interaction.guild.id)
        r = _rel(data, interaction.user.id, member.id)
        xp = int(r.get("xp") or 0)
        level = 0
        need = 10
        rem = xp
        while rem >= need:
            rem -= need
            level += 1
            need = 10 + level * 5
        married = r.get("married")
        ship = r.get("ship")
        emb = discord.Embed(title="💞 Relationship status", color=0xFF69B4)
        emb.add_field(name="Pair", value=f"{interaction.user.mention} & {member.mention}", inline=False)
        emb.add_field(name="Bond level", value=f"**{level}** ({xp} XP)")
        emb.add_field(name="Married", value="💍 Yes" if married else "No")
        if ship is not None:
            emb.add_field(name="Last ship %", value=f"{ship}%")
        if married and r.get("marriedAt"):
            emb.add_field(name="Married since", value=f"<t:{int(r['marriedAt'])}:R>")
        await interaction.response.send_message(embed=emb)

    @rel.command(name="leaderboard", description="Top relationship bonds in this server")
    async def rel_lb(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        data = storage.load_guild(interaction.guild.id)
        rels = data.get("relationships") or {}
        ranked = sorted(rels.items(), key=lambda kv: int(kv[1].get("xp") or 0), reverse=True)[:10]
        if not ranked:
            return await interaction.response.send_message(
                "No relationships tracked yet. Try `/rp do` or `/relationship ship`!"
            )
        lines = []
        for i, (k, v) in enumerate(ranked, 1):
            a, b = k.split(":")
            tag = " 💍" if v.get("married") else ""
            lines.append(f"**{i}.** <@{a}> & <@{b}> — {v.get('xp', 0)} XP{tag}")
        emb = discord.Embed(title="💞 Bond leaderboard", description="\n".join(lines), color=0xFF69B4)
        await interaction.response.send_message(embed=emb)


class MarryView(discord.ui.View):
    def __init__(self, proposer_id: int, target_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.guild_id = guild_id

    @discord.ui.button(label="Accept 💍", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message("Only the proposed member can accept.", ephemeral=True)

        def mut(d):
            uid_a, uid_b = str(self.proposer_id), str(self.target_id)
            for k, v in list((d.get("relationships") or {}).items()):
                parts = k.split(":")
                if uid_a in parts or uid_b in parts:
                    v["married"] = False
            r = _rel(d, self.proposer_id, self.target_id)
            r["married"] = True
            r["marriedAt"] = time.time()
            r["xp"] = int(r.get("xp") or 0) + 50

        storage.update_guild(self.guild_id, mut)
        for child in self.children:
            child.disabled = True  # type: ignore
        await interaction.response.edit_message(
            content=f"💍 <@{self.proposer_id}> and <@{self.target_id}> are now married!",
            embed=None,
            view=self,
        )
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.target_id, self.proposer_id):
            return await interaction.response.send_message("Not your proposal.", ephemeral=True)
        for child in self.children:
            child.disabled = True  # type: ignore
        await interaction.response.edit_message(content="Proposal declined.", embed=None, view=self)
        self.stop()


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialSystems(bot))
