"""Non-AI translation via libretranslate-style public APIs with fallback."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import httpx


class Translate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="translate", description="Translate text (does NOT use AI quota)")
    @app_commands.describe(text="Text to translate", target="Target language code e.g. en, es, fr, de, ja")
    async def translate(self, interaction: discord.Interaction, text: str, target: str = "en"):
        await interaction.response.defer()
        target = target.lower().strip()[:8]
        # MyMemory free API
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": text[:500], "langpair": f"|{target}" if "|" not in target else target},
                )
                # langpair needs source|target — auto detect with unknown source
                r = await client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": text[:500], "langpair": f"autodetect|{target}"},
                )
                if r.status_code != 200:
                    # retry with en|target if auto fails
                    r = await client.get(
                        "https://api.mymemory.translated.net/get",
                        params={"q": text[:500], "langpair": f"en|{target}"},
                    )
                data = r.json()
                translated = (data.get("responseData") or {}).get("translatedText")
                if not translated:
                    return await interaction.followup.send("Translation failed for that language.")
                await interaction.followup.send(f"**→ {target}:** {translated[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Translation service unavailable ({e}).")

    @app_commands.command(name="detectlang", description="Detect language of text")
    async def detectlang(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": text[:300], "langpair": "autodetect|en"},
                )
                data = r.json()
                matches = data.get("matches") or []
                lang = "unknown"
                if matches:
                    lang = matches[0].get("source") or lang
                await interaction.followup.send(f"Detected language: **{lang}**")
        except Exception:
            await interaction.followup.send("Could not detect language.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Translate(bot))
