"""Temp voice channels + AI character speech in VC."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage
from omnibot.services import ai_limits, concurrency, groq_client, tts

log = logging.getLogger("omnibot.voice")


class VoiceExtra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_channels: set[int] = set()
        self._vc: dict[int, discord.VoiceClient] = {}

    voice = app_commands.Group(name="voice", description="Voice utilities & AI speech")

    @voice.command(name="setup-join-to-create", description="Set a lobby channel that creates temp voice rooms")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_jtc(self, interaction: discord.Interaction, lobby: discord.VoiceChannel):
        def mut(d):
            d.setdefault("tempVoice", {})["lobbyChannelId"] = str(lobby.id)
            d["tempVoice"]["enabled"] = True

        storage.update_guild(interaction.guild.id, mut)
        await interaction.response.send_message(f"Join-to-create lobby: {lobby.mention}", ephemeral=True)

    @voice.command(name="join", description="Join your voice channel so Omni can talk")
    async def join(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        channel = interaction.user.voice.channel
        await interaction.response.defer(ephemeral=True)
        try:
            vc = self._vc.get(interaction.guild.id)
            if vc and vc.is_connected():
                if vc.channel and vc.channel.id != channel.id:
                    await vc.move_to(channel)
                await interaction.followup.send(f"Moved to **{channel.name}**.", ephemeral=True)
                return
            vc = await channel.connect()
            self._vc[interaction.guild.id] = vc
            await interaction.followup.send(f"Joined **{channel.name}**. Use `/voice talk` or `/voice say`.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Could not join: {e}", ephemeral=True)

    @voice.command(name="leave", description="Leave voice channel")
    async def leave(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        vc = self._vc.pop(interaction.guild.id, None)
        if vc and vc.is_connected():
            await vc.disconnect()
            await interaction.response.send_message("Left voice.", ephemeral=True)
        else:
            for client in list(interaction.guild.voice_clients):
                try:
                    await client.disconnect()
                except Exception:
                    pass
            await interaction.response.send_message("Not connected / disconnected.", ephemeral=True)

    @voice.command(name="say", description="Speak text in VC with your AI personality voice (uses 1 AI quota)")
    @app_commands.describe(text="What Omni should say out loud")
    async def say(self, interaction: discord.Interaction, text: str):
        await self._speak(interaction, text=text, use_ai=False)

    @voice.command(name="talk", description="AI replies in character and speaks it in VC (uses 1 AI quota)")
    @app_commands.describe(message="What you say to Omni; it answers out loud in character")
    async def talk(self, interaction: discord.Interaction, message: str):
        await self._speak(interaction, text=message, use_ai=True)

    async def _ensure_vc(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return None
        if not interaction.user.voice or not interaction.user.voice.channel:
            return None
        channel = interaction.user.voice.channel
        vc = self._vc.get(interaction.guild.id)
        if vc and vc.is_connected():
            if vc.channel and vc.channel.id != channel.id:
                await vc.move_to(channel)
            return vc
        for client in interaction.guild.voice_clients:
            if client.is_connected():
                if client.channel and client.channel.id != channel.id:
                    await client.move_to(channel)
                self._vc[interaction.guild.id] = client
                return client
        vc = await channel.connect()
        self._vc[interaction.guild.id] = vc
        return vc

    async def _speak(self, interaction: discord.Interaction, text: str, use_ai: bool):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        gid = interaction.guild.id

        await interaction.response.defer()
        audio_path: Path | None = None
        done = asyncio.Event()
        vc = None
        async with concurrency.guild_slot(gid):
            ok_lim, lim_msg = ai_limits.can_use(gid)
            if not ok_lim:
                return await interaction.followup.send(f"❌ {lim_msg}")

            spoken = text
            if use_ai:
                ok, reply = await groq_client.chat(
                    gid,
                    text,
                    consume_quota=False,
                )
                if not ok:
                    return await interaction.followup.send(f"❌ {reply}")
                spoken = reply

            spoken_clean = tts.clean_for_speech(spoken)
            if not spoken_clean:
                return await interaction.followup.send("Nothing to say.")

            voice_id, voice_label = tts.voice_for_guild(gid)
            try:
                audio_path = await tts.synthesize(spoken_clean, voice=voice_id, guild_id=gid)
            except Exception as e:
                log.exception("TTS failed")
                return await interaction.followup.send(
                    f"❌ Speech failed ({e}). Ensure **edge-tts** is installed and ffmpeg is available."
                )

            try:
                vc = await self._ensure_vc(interaction)
            except Exception as e:
                if audio_path:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                return await interaction.followup.send(f"❌ Could not join voice: {e}")
            if not vc:
                if audio_path:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                return await interaction.followup.send("Join a voice channel first.")

            if vc.is_playing() or vc.is_paused():
                vc.stop()
                await asyncio.sleep(0.3)

            source = discord.FFmpegPCMAudio(str(audio_path), options="-vn")

            def _after(err):
                if err:
                    log.error("TTS play error: %s", err)
                self.bot.loop.call_soon_threadsafe(done.set)
                try:
                    if audio_path:
                        audio_path.unlink(missing_ok=True)
                except Exception:
                    pass

            vc.play(source, after=_after)
            ai_limits.consume(gid)
            u = ai_limits.usage(gid)
            preview = spoken_clean[:200] + ("…" if len(spoken_clean) > 200 else "")
            await interaction.followup.send(
                f"🔊 **Speaking** ({voice_label}) · AI {u['count']}/{u['limit']}\n> {preview}"
            )

        try:
            await asyncio.wait_for(done.wait(), timeout=120)
        except asyncio.TimeoutError:
            if vc and vc.is_playing():
                vc.stop()

    @voice.command(name="voiceinfo", description="Show which TTS voice matches the server AI personality")
    async def voiceinfo(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        voice_id, label = tts.voice_for_guild(interaction.guild.id)
        data = storage.load_guild(interaction.guild.id)
        persona = ((data.get("persona") or {}).get("instructions") or "")[:300]
        await interaction.response.send_message(
            f"**TTS voice:** `{voice_id}` ({label})\n"
            f"**Personality snippet:** {persona or '(default)'}\n"
            f"Change personality in the dashboard → AI & Personality.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        data = storage.load_guild(member.guild.id)
        tv = data.get("tempVoice") or {}
        if not tv.get("enabled") or not tv.get("lobbyChannelId"):
            return
        lobby_id = int(tv["lobbyChannelId"])
        if after.channel and after.channel.id == lobby_id:
            try:
                ch = await member.guild.create_voice_channel(
                    name=f"{member.display_name}'s room",
                    category=after.channel.category,
                    reason="Join-to-create",
                )
                self.temp_channels.add(ch.id)
                await member.move_to(ch)
            except Exception:
                pass
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temp voice empty")
                except Exception:
                    pass
                self.temp_channels.discard(before.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceExtra(bot))
