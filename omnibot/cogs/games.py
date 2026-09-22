"""Games — trivia, hangman, number guess, tic-tac-toe simple."""
from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands


TRIVIA = [
    ("What is the capital of France?", "paris"),
    ("How many continents are there?", "7"),
    ("What planet is known as the Red Planet?", "mars"),
    ("What is 12 × 12?", "144"),
    ("What gas do plants absorb?", "carbon dioxide"),
]


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hangman: dict[int, dict] = {}
        self.guess: dict[int, dict] = {}

    game = app_commands.Group(name="game", description="Mini-games")

    @game.command(name="trivia", description="Answer a trivia question")
    async def trivia(self, interaction: discord.Interaction):
        q, a = random.choice(TRIVIA)
        await interaction.response.send_message(f"🧠 **Trivia:** {q}\nReply with your answer in chat within 30s.")
        channel = interaction.channel

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except Exception:
            return await interaction.followup.send(f"Time's up! Answer was **{a}**.")
        if msg.content.strip().lower() == a.lower():
            await interaction.followup.send("✅ Correct!")
        else:
            await interaction.followup.send(f"❌ Nope — answer was **{a}**.")

    @game.command(name="guess", description="Guess a number 1–100")
    async def guess_start(self, interaction: discord.Interaction):
        n = random.randint(1, 100)
        self.guess[interaction.user.id] = {"n": n, "tries": 0}
        await interaction.response.send_message("I'm thinking of a number 1–100. Use `/game guessnumber <n>`.")

    @game.command(name="guessnumber", description="Submit a guess")
    async def guess_num(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 100]):
        state = self.guess.get(interaction.user.id)
        if not state:
            return await interaction.response.send_message("Start with `/game guess` first.", ephemeral=True)
        state["tries"] += 1
        if number == state["n"]:
            self.guess.pop(interaction.user.id, None)
            return await interaction.response.send_message(f"🎉 Correct in {state['tries']} tries!")
        hint = "higher" if number < state["n"] else "lower"
        await interaction.response.send_message(f"Try **{hint}**.")

    @game.command(name="hangman", description="Start hangman")
    async def hangman(self, interaction: discord.Interaction):
        words = ["python", "discord", "omnibot", "galaxy", "keyboard", "music"]
        word = random.choice(words)
        self.hangman[interaction.user.id] = {"word": word, "guessed": set(), "lives": 6}
        await interaction.response.send_message(self._hang_view(interaction.user.id) + "\nUse `/game hangletter <letter>`.")

    def _hang_view(self, uid: int) -> str:
        s = self.hangman[uid]
        shown = " ".join(c if c in s["guessed"] else "_" for c in s["word"])
        return f"Lives: {s['lives']} | {shown}"

    @game.command(name="hangletter", description="Guess a letter in hangman")
    async def hangletter(self, interaction: discord.Interaction, letter: str):
        letter = letter.lower().strip()[:1]
        s = self.hangman.get(interaction.user.id)
        if not s:
            return await interaction.response.send_message("Start with `/game hangman`.", ephemeral=True)
        if not letter.isalpha():
            return await interaction.response.send_message("A letter please.", ephemeral=True)
        if letter in s["guessed"]:
            return await interaction.response.send_message("Already guessed.", ephemeral=True)
        s["guessed"].add(letter)
        if letter not in s["word"]:
            s["lives"] -= 1
        if all(c in s["guessed"] for c in s["word"]):
            self.hangman.pop(interaction.user.id, None)
            return await interaction.response.send_message(f"🎉 You won! Word was **{s['word']}**.")
        if s["lives"] <= 0:
            self.hangman.pop(interaction.user.id, None)
            return await interaction.response.send_message(f"💀 Game over. Word was **{s['word']}**.")
        await interaction.response.send_message(self._hang_view(interaction.user.id))

    @game.command(name="rps", description="Rock paper scissors")
    async def rps(self, interaction: discord.Interaction, choice: str):
        choice = choice.lower()
        if choice not in {"rock", "paper", "scissors"}:
            return await interaction.response.send_message("Pick rock, paper, or scissors.", ephemeral=True)
        bot_c = random.choice(["rock", "paper", "scissors"])
        wins = {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
        if choice == bot_c:
            result = "Tie"
        elif (choice, bot_c) in wins:
            result = "You win"
        else:
            result = "You lose"
        await interaction.response.send_message(f"You **{choice}** vs **{bot_c}** → {result}")

    @game.command(name="tictactoe", description="Challenge someone to tic-tac-toe")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot or opponent.id == interaction.user.id:
            return await interaction.response.send_message("Pick a real opponent.", ephemeral=True)
        board = [" "] * 9
        turn = interaction.user.id
        players = {interaction.user.id: "X", opponent.id: "O"}

        def render():
            rows = []
            for i in range(0, 9, 3):
                rows.append(" | ".join(board[i:i+3]))
            return "```\n" + "\n---------\n".join(rows) + "\n```"

        view = discord.ui.View(timeout=120)
        labels = [str(i+1) for i in range(9)]

        async def make_cb(idx: int):
            async def cb(inter: discord.Interaction):
                nonlocal turn
                if inter.user.id != turn:
                    return await inter.response.send_message("Not your turn.", ephemeral=True)
                if board[idx] != " ":
                    return await inter.response.send_message("Taken.", ephemeral=True)
                board[idx] = players[inter.user.id]
                wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
                mark = players[inter.user.id]
                if any(board[a]==board[b]==board[c]==mark for a,b,c in wins):
                    for c in view.children:
                        c.disabled = True
                    return await inter.response.edit_message(content=f"{render()}\n🎉 {inter.user.mention} wins!", view=view)
                if all(c != " " for c in board):
                    for c in view.children:
                        c.disabled = True
                    return await inter.response.edit_message(content=f"{render()}\nTie!", view=view)
                turn = opponent.id if turn == interaction.user.id else interaction.user.id
                await inter.response.edit_message(content=f"{render()}\nTurn: <@{turn}>", view=view)
            return cb

        for i in range(9):
            btn = discord.ui.Button(label=labels[i], style=discord.ButtonStyle.secondary, row=i//3)
            btn.callback = await make_cb(i)
            view.add_item(btn)

        await interaction.response.send_message(
            f"Tic-Tac-Toe: {interaction.user.mention} (X) vs {opponent.mention} (O)\n{render()}\nTurn: {interaction.user.mention}",
            view=view,
        )

    @game.command(name="count", description="Info about counting channel (setup with /engage counting-setup)")
    async def count_info(self, interaction: discord.Interaction):
        from omnibot import storage
        data = storage.load_guild(interaction.guild.id)
        c = data.get("counting") or {}
        if not c.get("enabled"):
            return await interaction.response.send_message("Counting not set up. Admins: `/engage counting-setup`.")
        await interaction.response.send_message(f"Next number: **{c.get('next', 1)}** in <#{c.get('channelId')}>")


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
