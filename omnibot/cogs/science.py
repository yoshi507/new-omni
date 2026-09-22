"""Science, space, finance light utilities."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import httpx


class Science(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    science = app_commands.Group(name="science", description="Space & science")

    @science.command(name="apod", description="NASA Astronomy Picture of the Day")
    async def apod(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get("https://api.nasa.gov/planetary/apod", params={"api_key": "DEMO_KEY"})
                data = r.json()
                emb = discord.Embed(title=data.get("title"), description=(data.get("explanation") or "")[:2000], color=0x5B6CFF)
                if data.get("url") and data.get("media_type") == "image":
                    emb.set_image(url=data["url"])
                await interaction.followup.send(embed=emb)
        except Exception:
            await interaction.followup.send("NASA APOD unavailable (rate limit or network).")

    @science.command(name="iss", description="Current ISS location")
    async def iss(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get("http://api.open-notify.org/iss-now.json")
                pos = r.json()["iss_position"]
                await interaction.followup.send(f"🛰 ISS at lat **{pos['latitude']}**, lon **{pos['longitude']}**")
        except Exception:
            await interaction.followup.send("ISS API unavailable.")

    @science.command(name="peopleinspace", description="People currently in space")
    async def people(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get("http://api.open-notify.org/astros.json")
                data = r.json()
                names = ", ".join(p["name"] for p in data.get("people", []))
                await interaction.followup.send(f"**{data.get('number')}** people in space:\n{names}")
        except Exception:
            await interaction.followup.send("API unavailable.")


class Finance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    finance = app_commands.Group(name="finance", description="Currency & crypto prices")

    @finance.command(name="crypto", description="Crypto price (CoinGecko)")
    async def crypto(self, interaction: discord.Interaction, coin: str = "bitcoin"):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": coin.lower(), "vs_currencies": "usd,eur"},
                )
                data = r.json().get(coin.lower())
                if not data:
                    return await interaction.followup.send("Coin not found. Try `bitcoin`, `ethereum`, etc.")
                await interaction.followup.send(f"**{coin}**: ${data.get('usd')} · €{data.get('eur')}")
        except Exception:
            await interaction.followup.send("CoinGecko unavailable.")

    @finance.command(name="fx", description="Currency conversion rates (USD base sample)")
    async def fx(self, interaction: discord.Interaction, amount: float = 1.0, base: str = "usd", target: str = "eur"):
        await interaction.response.defer()
        base, target = base.lower(), target.lower()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://open.er-api.com/v6/latest/{base.upper()}")
                data = r.json()
                rates = data.get("rates") or {}
                if target.upper() not in rates:
                    return await interaction.followup.send("Unknown currency code.")
                converted = amount * rates[target.upper()]
                await interaction.followup.send(f"**{amount} {base.upper()}** = **{converted:.4f} {target.upper()}**")
        except Exception:
            await interaction.followup.send("FX API unavailable.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Science(bot))
    await bot.add_cog(Finance(bot))
