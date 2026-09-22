"""Search utilities — wiki, urban, github, define."""
from __future__ import annotations

from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands
import httpx


class Search(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    search = app_commands.Group(name="search", description="Search the web & knowledge bases")

    @search.command(name="wiki", description="Wikipedia summary")
    async def wiki(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(query)}",
                    headers={"User-Agent": "OmniBot/1.0"},
                )
                if r.status_code != 200:
                    return await interaction.followup.send("No Wikipedia page found.")
                data = r.json()
                emb = discord.Embed(
                    title=data.get("title"),
                    description=(data.get("extract") or "")[:2000],
                    url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                    color=0x5B6CFF,
                )
                thumb = (data.get("thumbnail") or {}).get("source")
                if thumb:
                    emb.set_thumbnail(url=thumb)
                await interaction.followup.send(embed=emb)
        except Exception:
            await interaction.followup.send("Wikipedia unavailable.")

    @search.command(name="urban", description="Urban Dictionary")
    async def urban(self, interaction: discord.Interaction, term: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://api.urbandictionary.com/v0/define", params={"term": term})
                data = r.json()
                defs = data.get("list") or []
                if not defs:
                    return await interaction.followup.send("No definition.")
                d = defs[0]
                emb = discord.Embed(title=d.get("word"), description=(d.get("definition") or "")[:2000], color=0x5B6CFF)
                if d.get("example"):
                    emb.add_field(name="Example", value=d["example"][:1000], inline=False)
                await interaction.followup.send(embed=emb)
        except Exception:
            await interaction.followup.send("Urban Dictionary unavailable.")

    @search.command(name="github", description="Search GitHub repositories")
    async def github(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "per_page": 5},
                    headers={"User-Agent": "OmniBot", "Accept": "application/vnd.github+json"},
                )
                items = (r.json() or {}).get("items") or []
                if not items:
                    return await interaction.followup.send("No repos found.")
                lines = [f"**[{i['full_name']}]({i['html_url']})** ⭐ {i['stargazers_count']}" for i in items]
                await interaction.followup.send("\n".join(lines))
        except Exception:
            await interaction.followup.send("GitHub search failed.")

    @search.command(name="define", description="Dictionary definition")
    async def define(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
                if r.status_code != 200:
                    return await interaction.followup.send("No definition found.")
                data = r.json()[0]
                meanings = data.get("meanings") or []
                defs = []
                for m in meanings[:3]:
                    for d in (m.get("definitions") or [])[:2]:
                        defs.append(f"• ({m.get('partOfSpeech')}) {d.get('definition')}")
                await interaction.followup.send(f"**{data.get('word')}**\n" + "\n".join(defs)[:1900])
        except Exception:
            await interaction.followup.send("Dictionary unavailable.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Search(bot))
