"""Translation commands — MyMemory API (no AI quota)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import httpx

LANG_HINT = "en, es, fr, de, it, pt, ru, ja, ko, zh, ar, hi, nl, pl, tr, sv, uk"


class Translate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _my_memory(self, text: str, source: str, target: str) -> tuple[str | None, str | None]:
        text = text[:500]
        target = target.lower().strip()[:8]
        source = (source or "autodetect").lower().strip()[:12]
        pairs = [
            f"{source}|{target}",
            f"autodetect|{target}",
            f"en|{target}",
        ]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                for pair in pairs:
                    r = await client.get(
                        "https://api.mymemory.translated.net/get",
                        params={"q": text, "langpair": pair},
                    )
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    translated = (data.get("responseData") or {}).get("translatedText")
                    if not translated:
                        continue
                    if translated.lower().startswith("query length"):
                        continue
                    detected = source
                    try:
                        matches = data.get("matches") or []
                        if matches and isinstance(matches[0], dict):
                            detected = matches[0].get("source") or source
                    except Exception:
                        pass
                    return translated, str(detected or source)
        except Exception as e:
            return None, str(e)
        return None, "No translation returned"

    @app_commands.command(name="translate", description="Translate text (does NOT use AI quota)")
    @app_commands.describe(
        text="Text to translate",
        target=f"Target language code ({LANG_HINT})",
        source="Source language code (default: auto-detect)",
    )
    async def translate(
        self,
        interaction: discord.Interaction,
        text: str,
        target: str = "en",
        source: str = "autodetect",
    ):
        await interaction.response.defer()
        translated, meta = await self._my_memory(text, source, target)
        if not translated:
            return await interaction.followup.send(f"Translation failed: {meta}")
        emb = discord.Embed(title="🌐 Translation", color=0x5B6CFF)
        emb.add_field(name="Original", value=text[:900], inline=False)
        emb.add_field(name=f"→ {target.upper()}", value=translated[:900], inline=False)
        if meta and meta not in ("autodetect",):
            emb.set_footer(text=f"Source: {meta}")
        await interaction.followup.send(embed=emb)

    @app_commands.command(name="detectlang", description="Detect language of text")
    async def detectlang(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": text[:300], "langpair": "autodetect|en"},
                )
                data = r.json() if r.status_code == 200 else {}
                matches = data.get("matches") or []
                lang = None
                if matches and isinstance(matches[0], dict):
                    lang = matches[0].get("source") or matches[0].get("source-language")
                translated = (data.get("responseData") or {}).get("translatedText")
                msg = f"**Detected:** `{lang or 'unknown'}`"
                if translated:
                    msg += f"\nSample EN: {translated[:400]}"
                await interaction.followup.send(msg)
        except Exception as e:
            await interaction.followup.send(f"Detection failed ({e}).")

    @app_commands.command(name="tr", description="Quick translate (alias of /translate)")
    @app_commands.describe(text="Text", target="Target language code")
    async def tr_alias(self, interaction: discord.Interaction, text: str, target: str = "en"):
        await self.translate.callback(self, interaction, text, target, "autodetect")


async def setup(bot: commands.Bot):
    await bot.add_cog(Translate(bot))
