"""Feature hub: polls, quotes, colour roles, booster roles, autoname, embed builder."""
from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from omnibot import storage


def _parse_color(s: str | None, default: int = 0x5B6CFF) -> int:
    if not s:
        return default
    s = str(s).strip().lstrip("#")
    try:
        return int(s, 16) & 0xFFFFFF
    except ValueError:
        return default


class FeaturesHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    poll = app_commands.Group(name="poll", description="Create polls")

    @poll.command(name="create", description="Create a reaction poll")
    @app_commands.describe(
        question="Poll question",
        option1="First option",
        option2="Second option",
        option3="Optional third",
        option4="Optional fourth",
        option5="Optional fifth",
    )
    async def poll_create(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str | None = None,
        option4: str | None = None,
        option5: str | None = None,
    ):
        opts = [o for o in [option1, option2, option3, option4, option5] if o]
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        lines = [f"{emojis[i]} {o}" for i, o in enumerate(opts)]
        emb = discord.Embed(
            title="📊 Poll",
            description=f"**{question}**\n\n" + "\n".join(lines),
            color=0x5B6CFF,
        )
        emb.set_footer(text=f"Asked by {interaction.user.display_name}")
        await interaction.response.send_message(embed=emb)
        msg = await interaction.original_response()
        for i in range(len(opts)):
            try:
                await msg.add_reaction(emojis[i])
            except Exception:
                pass

    quote_g = app_commands.Group(name="quote", description="Message quotes")

    @quote_g.command(name="make", description="Turn a message into a styled quote (message ID)")
    async def quote_make(
        self, interaction: discord.Interaction, message_id: str, channel: discord.TextChannel | None = None
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        try:
            msg = await ch.fetch_message(int(message_id))
        except Exception:
            return await interaction.response.send_message("Message not found.", ephemeral=True)
        emb = discord.Embed(
            description=f"\"{msg.content[:1900]}\"" if msg.content else "*(no text)*",
            color=0x9B59B6,
            timestamp=msg.created_at,
        )
        emb.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url)
        emb.set_footer(text=f"Quoted by {interaction.user.display_name}")
        await interaction.response.send_message(embed=emb)

    @quote_g.command(name="save", description="Save a quote to the server quote book")
    async def quote_save(self, interaction: discord.Interaction, text: str, author: str | None = None):
        def mut(d):
            quotes = d.setdefault("quotes", [])
            quotes.append({"text": text[:500], "author": author or str(interaction.user), "by": str(interaction.user.id)})
            d["quotes"] = quotes[-100:]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message("Quote saved.", ephemeral=True)

    @quote_g.command(name="random", description="Random saved quote")
    async def quote_random(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        quotes = data.get("quotes") or []
        if not quotes:
            return await interaction.response.send_message("No quotes saved yet. Use /quote save")
        q = random.choice(quotes)
        emb = discord.Embed(description=f"\"{q.get('text')}\"", color=0x9B59B6)
        emb.set_footer(text=f"— {q.get('author', 'unknown')}")
        await interaction.response.send_message(embed=emb)

    color_g = app_commands.Group(name="color", description="Self-assignable colour roles")

    @color_g.command(name="set", description="Create or assign a colour role (hex e.g. FF0000)")
    async def color_set(self, interaction: discord.Interaction, hex_color: str):
        guild = interaction.guild
        if not guild:
            return
        color = _parse_color(hex_color)
        name = f"color-{hex_color.strip().lstrip('#').lower()[:6]}"
        role = discord.utils.get(guild.roles, name=name)
        if not role:
            try:
                role = await guild.create_role(name=name, colour=discord.Colour(color), reason="Colour role")
            except Exception as e:
                return await interaction.response.send_message(f"Could not create role: {e}", ephemeral=True)
        me = interaction.user
        if not isinstance(me, discord.Member):
            return await interaction.response.send_message("Members only.", ephemeral=True)
        for r in list(me.roles):
            if r.name.startswith("color-"):
                try:
                    await me.remove_roles(r, reason="Colour role swap")
                except Exception:
                    pass
        try:
            await me.add_roles(role, reason="Colour role")
        except Exception as e:
            return await interaction.response.send_message(f"Could not assign: {e}", ephemeral=True)
        await interaction.response.send_message(f"Colour set to **#{hex_color.strip().lstrip('#')}**.", ephemeral=True)

    @color_g.command(name="clear", description="Remove your colour role")
    async def color_clear(self, interaction: discord.Interaction):
        me = interaction.user
        if not isinstance(me, discord.Member):
            return
        removed = 0
        for r in list(me.roles):
            if r.name.startswith("color-"):
                try:
                    await me.remove_roles(r, reason="Colour clear")
                    removed += 1
                except Exception:
                    pass
        await interaction.response.send_message(f"Cleared {removed} colour role(s).", ephemeral=True)

    boost = app_commands.Group(name="boostrole", description="Roles for server boosters")

    @boost.command(name="set", description="Role given to members while boosting")
    @app_commands.checks.has_permissions(administrator=True)
    async def boost_set(self, interaction: discord.Interaction, role: discord.Role, enabled: bool = True):
        def mut(d):
            d["boosterRoles"] = {"enabled": enabled, "roleId": str(role.id)}

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Booster role {'on' if enabled else 'off'}: {role.mention}", ephemeral=True
        )

    @commands.Cog.listener(name="on_member_update")
    async def on_member_update_boostrole(self, before: discord.Member, after: discord.Member):
        if before.premium_since == after.premium_since:
            return
        data = storage.load_guild(after.guild.id)
        br = data.get("boosterRoles") or {}
        if not br.get("enabled") or not br.get("roleId"):
            return
        role = after.guild.get_role(int(br["roleId"]))
        if not role:
            return
        try:
            if after.premium_since and not before.premium_since:
                await after.add_roles(role, reason="Server boost")
            elif before.premium_since and not after.premium_since:
                await after.remove_roles(role, reason="Boost ended")
        except Exception:
            pass

    autoname = app_commands.Group(name="autoname", description="Auto-nickname new members")

    @autoname.command(name="setup", description="Template e.g. 'User | {user}' — empty to disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def autoname_setup(
        self, interaction: discord.Interaction, template: str = "", enabled: bool = True
    ):
        def mut(d):
            d["autoName"] = {"enabled": enabled and bool(template.strip()), "template": template[:80]}

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Auto-name {'on' if enabled and template.strip() else 'off'}: `{template or '(none)'}`",
            ephemeral=True,
        )

    @commands.Cog.listener(name="on_member_join")
    async def on_member_join_autoname(self, member: discord.Member):
        data = storage.load_guild(member.guild.id)
        an = data.get("autoName") or {}
        if not an.get("enabled") or not an.get("template"):
            return
        nick = (
            str(an["template"])
            .replace("{user}", member.name)
            .replace("{username}", member.name)
            .replace("{tag}", str(member.discriminator) if member.discriminator != "0" else "")
            .replace("{id}", str(member.id))
        )[:32]
        try:
            await member.edit(nick=nick, reason="Auto-name")
        except Exception:
            pass

    embed_g = app_commands.Group(name="embed", description="Build and send embeds")

    @embed_g.command(name="send", description="Send a custom embed")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_send(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: str = "5B6CFF",
        channel: discord.TextChannel | None = None,
        footer: str | None = None,
        image_url: str | None = None,
    ):
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Text channel only.", ephemeral=True)
        emb = discord.Embed(title=title[:256], description=description[:4000], color=_parse_color(color))
        if footer:
            emb.set_footer(text=footer[:2048])
        if image_url:
            emb.set_image(url=image_url)
        try:
            await ch.send(embed=emb)
        except Exception as e:
            return await interaction.response.send_message(f"Failed: {e}", ephemeral=True)
        await interaction.response.send_message(f"Embed sent in {ch.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(FeaturesHub(bot))
