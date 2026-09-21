"""Games + virtual currency (non-AI)."""
from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

SHOP = {
    "cookie": {"price": 50, "name": "Cookie"},
    "trophy": {"price": 500, "name": "Trophy"},
    "shield": {"price": 250, "name": "Shield"},
}


def _bal(data, uid: str) -> int:
    return int((data.get("economy") or {}).get(uid, {}).get("coins", 0))


def _set_bal(data, uid: str, amount: int):
    eco = data.setdefault("economy", {}).setdefault(uid, {})
    eco["coins"] = max(0, int(amount))


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your coin balance")
    async def balance(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user  # type: ignore
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        await interaction.response.send_message(
            f"**{user.display_name}** has **{_bal(data, str(user.id))}** coins."
        )

    @app_commands.command(name="daily", description="Claim daily coins")
    async def daily(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        gid = interaction.guild.id  # type: ignore
        reward = random.randint(80, 150)

        def mut(data):
            eco = data.setdefault("economy", {}).setdefault(uid, {})
            last = float(eco.get("dailyAt") or 0)
            if time.time() - last < 86400:
                raise RuntimeError("already")
            eco["dailyAt"] = time.time()
            eco["coins"] = int(eco.get("coins") or 0) + reward

        try:
            storage.update_guild(gid, mut)
        except RuntimeError:
            return await interaction.response.send_message("You already claimed daily.", ephemeral=True)
        await interaction.response.send_message(f"Daily reward: **+{reward}** coins!")

    @app_commands.command(name="work", description="Work for coins")
    async def work(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        gid = interaction.guild.id  # type: ignore
        pay = random.randint(20, 60)

        def mut(data):
            eco = data.setdefault("economy", {}).setdefault(uid, {})
            last = float(eco.get("workAt") or 0)
            if time.time() - last < 3600:
                raise RuntimeError("cd")
            eco["workAt"] = time.time()
            eco["coins"] = int(eco.get("coins") or 0) + pay

        try:
            storage.update_guild(gid, mut)
        except RuntimeError:
            return await interaction.response.send_message("Work cooldown: try later.", ephemeral=True)
        await interaction.response.send_message(f"You earned **{pay}** coins.")

    @app_commands.command(name="pay", description="Pay another user")
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            return await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        if member.id == interaction.user.id:
            return await interaction.response.send_message("Can't pay yourself.", ephemeral=True)
        uid, tid = str(interaction.user.id), str(member.id)

        def mut(data):
            if _bal(data, uid) < amount:
                raise RuntimeError("funds")
            _set_bal(data, uid, _bal(data, uid) - amount)
            _set_bal(data, tid, _bal(data, tid) + amount)

        try:
            storage.update_guild(interaction.guild.id, mut)  # type: ignore
        except RuntimeError:
            return await interaction.response.send_message("Insufficient coins.", ephemeral=True)
        await interaction.response.send_message(f"Paid **{amount}** to {member.mention}.")

    @app_commands.command(name="shop", description="View the shop")
    async def shop(self, interaction: discord.Interaction):
        lines = [f"`{k}` — **{v['price']}** coins ({v['name']})" for k, v in SHOP.items()]
        await interaction.response.send_message("**Shop**\n" + "\n".join(lines))

    @app_commands.command(name="buy", description="Buy a shop item")
    async def buy(self, interaction: discord.Interaction, item: str):
        item = item.lower()
        if item not in SHOP:
            return await interaction.response.send_message("Unknown item.", ephemeral=True)
        price = SHOP[item]["price"]
        uid = str(interaction.user.id)

        def mut(data):
            if _bal(data, uid) < price:
                raise RuntimeError("funds")
            _set_bal(data, uid, _bal(data, uid) - price)
            inv = data.setdefault("economy", {}).setdefault(uid, {}).setdefault("inv", {})
            inv[item] = int(inv.get(item) or 0) + 1

        try:
            storage.update_guild(interaction.guild.id, mut)  # type: ignore
        except RuntimeError:
            return await interaction.response.send_message("Not enough coins.", ephemeral=True)
        await interaction.response.send_message(f"Bought **{SHOP[item]['name']}**!")

    @app_commands.command(name="inventory", description="View your items")
    async def inventory(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        inv = (data.get("economy") or {}).get(str(interaction.user.id), {}).get("inv") or {}
        if not inv:
            return await interaction.response.send_message("Inventory empty.")
        lines = [f"{k}: {v}" for k, v in inv.items()]
        await interaction.response.send_message("**Inventory**\n" + "\n".join(lines))

    @app_commands.command(name="coinflip", description="Flip a coin (optional bet)")
    async def coinflip(self, interaction: discord.Interaction, bet: int = 0):
        side = random.choice(["heads", "tails"])
        msg = f"🪙 **{side}**"
        if bet > 0:
            uid = str(interaction.user.id)

            def mut(data):
                if _bal(data, uid) < bet:
                    raise RuntimeError("funds")
                win = random.random() < 0.5
                _set_bal(data, uid, _bal(data, uid) + (bet if win else -bet))
                data["_cf"] = win

            try:
                data = storage.update_guild(interaction.guild.id, mut)  # type: ignore
            except RuntimeError:
                return await interaction.response.send_message("Not enough coins.", ephemeral=True)
            msg += " — You " + ("won" if data.get("_cf") else "lost") + f" **{bet}**!"
        await interaction.response.send_message(msg)

    @app_commands.command(name="dice", description="Roll dice")
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 2, 100] = 6):
        await interaction.response.send_message(f"🎲 You rolled **{random.randint(1, sides)}** (d{sides})")

    @app_commands.command(name="rps", description="Rock paper scissors")
    @app_commands.describe(choice="rock, paper, or scissors")
    async def rps(self, interaction: discord.Interaction, choice: str):
        choice = choice.lower()
        if choice not in ("rock", "paper", "scissors"):
            return await interaction.response.send_message("Pick rock, paper, or scissors.", ephemeral=True)
        bot = random.choice(["rock", "paper", "scissors"])
        wins = {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
        if choice == bot:
            result = "Tie!"
        elif (choice, bot) in wins:
            result = "You win!"
        else:
            result = "You lose!"
        await interaction.response.send_message(f"You: **{choice}** · Bot: **{bot}** — {result}")

    @app_commands.command(name="slots", description="Slot machine")
    async def slots(self, interaction: discord.Interaction, bet: int = 10):
        if bet <= 0:
            return await interaction.response.send_message("Bet must be positive.", ephemeral=True)
        uid = str(interaction.user.id)
        symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]

        def mut(data):
            if _bal(data, uid) < bet:
                raise RuntimeError("funds")
            roll = [random.choice(symbols) for _ in range(3)]
            data["_slots"] = roll
            if len(set(roll)) == 1:
                _set_bal(data, uid, _bal(data, uid) + bet * 5)
                data["_win"] = bet * 5
            else:
                _set_bal(data, uid, _bal(data, uid) - bet)
                data["_win"] = 0

        try:
            data = storage.update_guild(interaction.guild.id, mut)  # type: ignore
        except RuntimeError:
            return await interaction.response.send_message("Not enough coins.", ephemeral=True)
        roll = data.get("_slots", [])
        win = data.get("_win", 0)
        msg = " | ".join(roll)
        msg += f"\n{'Jackpot +' + str(win) if win else 'No win (−' + str(bet) + ')'}"
        await interaction.response.send_message(msg)

    @app_commands.command(name="trivia", description="Quick trivia question")
    async def trivia(self, interaction: discord.Interaction):
        qas = [
            ("Capital of France?", "paris"),
            ("2+2?", "4"),
            ("Largest planet in our solar system?", "jupiter"),
            ("Discord was founded in which year?", "2015"),
        ]
        q, a = random.choice(qas)
        await interaction.response.send_message(f"❓ {q}\n*(reply in chat — fun mode, no auto-score)*")

    @app_commands.command(name="guessnumber", description="Guess 1-10")
    async def guessnumber(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 10]):
        secret = random.randint(1, 10)
        if number == secret:
            await interaction.response.send_message(f"🎉 Correct! It was **{secret}**.")
        else:
            await interaction.response.send_message(f"Nope — it was **{secret}**.")

    @app_commands.command(name="higherlower", description="Higher or lower than 50?")
    async def higherlower(self, interaction: discord.Interaction, guess: str):
        n = random.randint(1, 100)
        g = guess.lower()
        if g not in ("higher", "lower"):
            return await interaction.response.send_message("Say higher or lower.", ephemeral=True)
        correct = (g == "higher" and n > 50) or (g == "lower" and n < 50) or n == 50
        await interaction.response.send_message(f"Number was **{n}**. {'Nice!' if correct else 'Miss.'}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
