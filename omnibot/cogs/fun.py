"""Fun commands — 8ball, ship, jokes, animals, etc."""
from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands
import httpx


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    fun = app_commands.Group(name="fun", description="Fun commands")

    @fun.command(name="eightball", description="Magic 8-ball")
    async def eightball(self, interaction: discord.Interaction, question: str):
        answers = [
            "Yes.", "No.", "Maybe.", "Ask again later.", "Definitely.",
            "I wouldn't count on it.", "Absolutely!", "Sources say no.",
            "Without a doubt.", "Very doubtful.",
        ]
        await interaction.response.send_message(f"🎱 **{question}**\n{random.choice(answers)}")

    @fun.command(name="ship", description="Ship two users")
    async def ship(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
        score = (user1.id + user2.id) % 101
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        await interaction.response.send_message(f"💕 {user1.display_name} × {user2.display_name}\n`{bar}` **{score}%**")

    @fun.command(name="joke", description="Random joke")
    async def joke(self, interaction: discord.Interaction):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://official-joke-api.appspot.com/random_joke")
                data = r.json()
                await interaction.response.send_message(f"{data.get('setup')}\n||{data.get('punchline')}||")
        except Exception:
            await interaction.response.send_message("Why did the bot go to therapy? Too many issues.")

    @fun.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🪙 **{random.choice(['Heads', 'Tails'])}**")

    @fun.command(name="dice", description="Roll dice")
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 2, 100] = 6, count: app_commands.Range[int, 1, 10] = 1):
        rolls = [random.randint(1, sides) for _ in range(count)]
        await interaction.response.send_message(f"🎲 {rolls} (sum={sum(rolls)})")

    @fun.command(name="choose", description="Pick randomly from options (comma-separated)")
    async def choose(self, interaction: discord.Interaction, options: str):
        parts = [p.strip() for p in options.split(",") if p.strip()]
        if len(parts) < 2:
            return await interaction.response.send_message("Provide at least two options separated by commas.", ephemeral=True)
        await interaction.response.send_message(f"I pick **{random.choice(parts)}**")

    @fun.command(name="rps", description="Rock paper scissors")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        bot_c = random.choice(["rock", "paper", "scissors"])
        wins = {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
        if choice.value == bot_c:
            result = "Tie!"
        elif (choice.value, bot_c) in wins:
            result = "You win!"
        else:
            result = "You lose!"
        await interaction.response.send_message(f"You: **{choice.value}** · Bot: **{bot_c}** → {result}")

    @fun.command(name="rate", description="Rate something 0–100")
    async def rate(self, interaction: discord.Interaction, thing: str):
        score = sum(ord(c) for c in thing.lower()) % 101
        await interaction.response.send_message(f"I rate **{thing}** a **{score}/100**")

    @fun.command(name="hug", description="Hug someone")
    async def hug(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"🤗 {interaction.user.mention} hugs {member.mention}!")

    @fun.command(name="pat", description="Pat someone")
    async def pat(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"🥰 {interaction.user.mention} pats {member.mention}!")

    @fun.command(name="cat", description="Random cat image")
    async def cat(self, interaction: discord.Interaction):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://api.thecatapi.com/v1/images/search")
                url = r.json()[0]["url"]
                await interaction.response.send_message(url)
        except Exception:
            await interaction.response.send_message("Could not fetch a cat right now.")

    @fun.command(name="dog", description="Random dog image")
    async def dog(self, interaction: discord.Interaction):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://dog.ceo/api/breeds/image/random")
                url = r.json()["message"]
                await interaction.response.send_message(url)
        except Exception:
            await interaction.response.send_message("Could not fetch a dog right now.")

    @fun.command(name="meme", description="Random meme")
    async def meme(self, interaction: discord.Interaction):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://meme-api.com/gimme")
                data = r.json()
                emb = discord.Embed(title=data.get("title", "Meme"), color=0x5B6CFF)
                emb.set_image(url=data.get("url"))
                await interaction.response.send_message(embed=emb)
        except Exception:
            await interaction.response.send_message("Meme service unavailable.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
