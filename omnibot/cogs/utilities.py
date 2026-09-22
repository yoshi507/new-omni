"""Utilities — weather, calc, reminders, polls, timers, convert."""
from __future__ import annotations

import asyncio
import hashlib
import random
import time
from datetime import datetime, timezone
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands
import httpx


class Utilities(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    util = app_commands.Group(name="util", description="Utility commands")

    @util.command(name="ping", description="Bot latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong · `{round(self.bot.latency * 1000)}ms`")

    @util.command(name="calc", description="Simple calculator (+ - * /)")
    async def calc(self, interaction: discord.Interaction, expression: str):
        allowed = set("0123456789+-*/().% ")
        if not set(expression) <= allowed:
            return await interaction.response.send_message("Only numbers and + - * / ( ) allowed.", ephemeral=True)
        try:
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307 — restricted
            await interaction.response.send_message(f"`{expression}` = **{result}**")
        except Exception:
            await interaction.response.send_message("Could not evaluate.", ephemeral=True)

    @util.command(name="weather", description="Weather by city (wttr.in)")
    async def weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://wttr.in/{quote(city)}?format=j1")
                data = r.json()
                cur = data["current_condition"][0]
                area = data["nearest_area"][0]["areaName"][0]["value"]
                text = (
                    f"**{area}**\n"
                    f"{cur['weatherDesc'][0]['value']} · {cur['temp_C']}°C (feels {cur['FeelsLikeC']}°C)\n"
                    f"Humidity {cur['humidity']}% · Wind {cur['windspeedKmph']} km/h"
                )
                await interaction.followup.send(text)
        except Exception:
            await interaction.followup.send("Could not fetch weather.")

    @util.command(name="remind", description="Remind you after N minutes")
    async def remind(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 10080], text: str):
        await interaction.response.send_message(f"Okay — I'll remind you in {minutes}m.")
        await asyncio.sleep(minutes * 60)
        try:
            await interaction.followup.send(f"⏰ {interaction.user.mention} Reminder: {text[:500]}")
        except Exception:
            try:
                await interaction.user.send(f"⏰ Reminder: {text[:500]}")
            except Exception:
                pass

    @util.command(name="poll", description="Create a quick yes/no or multi poll")
    async def poll(self, interaction: discord.Interaction, question: str, option_a: str = "Yes", option_b: str = "No", option_c: str | None = None):
        emb = discord.Embed(title="📊 Poll", description=question, color=0x5B6CFF)
        emb.add_field(name="🇦", value=option_a)
        emb.add_field(name="🇧", value=option_b)
        if option_c:
            emb.add_field(name="🇨", value=option_c)
        await interaction.response.send_message(embed=emb)
        msg = await interaction.original_response()
        await msg.add_reaction("🇦")
        await msg.add_reaction("🇧")
        if option_c:
            await msg.add_reaction("🇨")

    @util.command(name="timestamp", description="Discord timestamp for a unix time")
    async def timestamp(self, interaction: discord.Interaction, unix: int | None = None):
        t = unix or int(time.time())
        await interaction.response.send_message(f"`{t}` → <t:{t}:F> · <t:{t}:R>")

    @util.command(name="hash", description="SHA256 hash of text")
    async def hash_text(self, interaction: discord.Interaction, text: str):
        h = hashlib.sha256(text.encode()).hexdigest()
        await interaction.response.send_message(f"`{h}`")

    @util.command(name="password", description="Generate a random password")
    async def password(self, interaction: discord.Interaction, length: app_commands.Range[int, 8, 64] = 16):
        import string
        chars = string.ascii_letters + string.digits + "!@#$%"
        pw = "".join(random.choice(chars) for _ in range(length))
        await interaction.response.send_message(f"||`{pw}`||", ephemeral=True)

    @util.command(name="color", description="Preview a hex color")
    async def color(self, interaction: discord.Interaction, hex_code: str):
        hex_code = hex_code.lstrip("#")
        try:
            value = int(hex_code, 16)
            emb = discord.Embed(title=f"#{hex_code}", color=value)
            await interaction.response.send_message(embed=emb)
        except Exception:
            await interaction.response.send_message("Invalid hex.", ephemeral=True)

    @util.command(name="base64", description="Encode or decode base64")
    @app_commands.choices(mode=[
        app_commands.Choice(name="encode", value="encode"),
        app_commands.Choice(name="decode", value="decode"),
    ])
    async def base64_cmd(self, interaction: discord.Interaction, mode: app_commands.Choice[str], text: str):
        import base64
        try:
            if mode.value == "encode":
                out = base64.b64encode(text.encode()).decode()
            else:
                out = base64.b64decode(text.encode()).decode()
            await interaction.response.send_message(f"`{out[:1900]}`")
        except Exception:
            await interaction.response.send_message("Failed.", ephemeral=True)

    @util.command(name="servertime", description="Current UTC time")
    async def servertime(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await interaction.response.send_message(f"UTC: `{now.isoformat()}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
