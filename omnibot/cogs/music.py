"""Music — SoundCloud-first via yt-dlp / FFmpeg (no YouTube)."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("omnibot.music")


class GuildPlayer:
    def __init__(self):
        self.queue: list[dict] = []
        self.voice: discord.VoiceClient | None = None
        self.current: dict | None = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def _gp(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    music = app_commands.Group(name="music", description="Music controls")

    @music.command(name="play", description="Play a SoundCloud track URL or search")
    @app_commands.describe(query="SoundCloud URL or search terms")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        if "youtube.com" in query.lower() or "youtu.be" in query.lower():
            return await interaction.response.send_message("YouTube is disabled. Use SoundCloud.", ephemeral=True)

        await interaction.response.defer()
        gp = self._gp(interaction.guild.id)
        channel = interaction.user.voice.channel

        try:
            if not gp.voice or not gp.voice.is_connected():
                gp.voice = await channel.connect()
            elif gp.voice.channel.id != channel.id:
                await gp.voice.move_to(channel)
        except Exception as e:
            return await interaction.followup.send(f"Could not join voice: {e}")

        # Prefer soundcloud URL; otherwise treat as search (yt-dlp scsearch)
        source_url = query
        title = query
        if "soundcloud.com" not in query.lower():
            source_url = f"scsearch1:{query}"

        try:
            source = await discord.FFmpegPCMAudio.from_probe  # type: ignore
        except Exception:
            source = None

        # Use yt-dlp extract via discord.PCMVolumeTransformer + FFmpegPCMAudio
        try:
            import yt_dlp

            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "default_search": "scsearch",
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                stream_url = info["url"]
                title = info.get("title") or title

            ffmpeg_opts = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn",
            }
            audio = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
            transformed = discord.PCMVolumeTransformer(audio, volume=0.8)

            def after_play(err):
                if err:
                    log.error("Player error: %s", err)
                fut = asyncio.run_coroutine_threadsafe(self._play_next(interaction.guild.id), self.bot.loop)
                try:
                    fut.result()
                except Exception:
                    pass

            if gp.voice.is_playing():
                gp.queue.append({"title": title, "url": stream_url})
                await interaction.followup.send(f"Queued **{title}**")
            else:
                gp.current = {"title": title}
                gp.voice.play(transformed, after=after_play)
                await interaction.followup.send(f"▶️ Playing **{title}**")
        except Exception as e:
            log.exception("Music play failed")
            await interaction.followup.send(
                f"❌ Could not play audio ({e}). Install ffmpeg + `pip install yt-dlp` and try a SoundCloud URL."
            )

    async def _play_next(self, guild_id: int):
        gp = self._gp(guild_id)
        if not gp.queue or not gp.voice:
            gp.current = None
            return
        item = gp.queue.pop(0)
        try:
            audio = discord.FFmpegPCMAudio(
                item["url"],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )
            gp.current = item
            gp.voice.play(discord.PCMVolumeTransformer(audio, volume=0.8))
        except Exception as e:
            log.error("Next track failed: %s", e)

    @music.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        if gp.voice and gp.voice.is_playing():
            gp.voice.stop()
            await interaction.response.send_message("Skipped.")
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)

    @music.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        gp.queue.clear()
        if gp.voice:
            if gp.voice.is_playing():
                gp.voice.stop()
            await gp.voice.disconnect()
            gp.voice = None
        await interaction.response.send_message("Stopped.")

    @music.command(name="queue", description="Show queue")
    async def queue(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        if not gp.queue and not gp.current:
            return await interaction.response.send_message("Queue empty.")
        lines = []
        if gp.current:
            lines.append(f"Now: **{gp.current.get('title')}**")
        for i, t in enumerate(gp.queue[:15], 1):
            lines.append(f"{i}. {t.get('title')}")
        await interaction.response.send_message("\n".join(lines))

    @music.command(name="pause", description="Pause")
    async def pause(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        if gp.voice and gp.voice.is_playing():
            gp.voice.pause()
            await interaction.response.send_message("Paused.")
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)

    @music.command(name="resume", description="Resume")
    async def resume(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        if gp.voice and gp.voice.is_paused():
            gp.voice.resume()
            await interaction.response.send_message("Resumed.")
        else:
            await interaction.response.send_message("Nothing paused.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
