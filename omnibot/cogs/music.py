"""Music — YouTube (and SoundCloud) via yt-dlp + FFmpeg."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import discord
from discord import app_commands
from discord.ext import commands

from omnibot.services import concurrency

log = logging.getLogger("omnibot.music")
_executor = ThreadPoolExecutor(max_workers=2)

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}


def _extract(query: str) -> dict:
    import yt_dlp

    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if info is None:
            raise RuntimeError("No results")
        if "entries" in info:
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("No search results")
            info = entries[0]
        url = info.get("url") or info.get("webpage_url")
        if not url:
            raise RuntimeError("No stream URL")
        if not info.get("url") and info.get("formats"):
            for f in reversed(info["formats"]):
                if f.get("url") and (f.get("acodec") or "none") != "none":
                    url = f["url"]
                    break
        return {
            "title": info.get("title") or query,
            "url": info.get("url") or url,
            "webpage": info.get("webpage_url") or query,
            "duration": info.get("duration"),
        }


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

    async def _resolve(self, query: str) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _extract, query)

    def _make_source(self, stream_url: str) -> discord.AudioSource:
        before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        audio = discord.FFmpegPCMAudio(stream_url, before_options=before, options="-vn")
        return discord.PCMVolumeTransformer(audio, volume=0.85)

    def _after(self, guild_id: int):
        def _cb(err):
            if err:
                log.error("Player error: %s", err)
            fut = asyncio.run_coroutine_threadsafe(self._play_next(guild_id), self.bot.loop)
            try:
                fut.result(timeout=5)
            except Exception:
                pass

        return _cb

    async def _play_next(self, guild_id: int):
        gp = self._gp(guild_id)
        if not gp.queue or not gp.voice or not gp.voice.is_connected():
            gp.current = None
            return
        item = gp.queue.pop(0)
        try:
            if item.get("webpage") and (
                "youtube" in str(item.get("webpage", "")).lower()
                or "youtu.be" in str(item.get("webpage", "")).lower()
            ):
                try:
                    fresh = await self._resolve(item["webpage"])
                    item["url"] = fresh["url"]
                    item["title"] = fresh.get("title") or item.get("title")
                except Exception as e:
                    log.warning("Re-resolve failed: %s", e)
            src = self._make_source(item["url"])
            gp.current = item
            gp.voice.play(src, after=self._after(guild_id))
        except Exception as e:
            log.error("Next track failed: %s", e)
            await self._play_next(guild_id)

    music = app_commands.Group(name="music", description="Music controls (YouTube + SoundCloud)")

    @music.command(name="play", description="Play from YouTube URL or search")
    @app_commands.describe(query="YouTube URL, SoundCloud URL, or search terms")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Join a voice channel first.", ephemeral=True
            )

        await interaction.response.defer()
        if not await concurrency.try_acquire(interaction.guild.id, timeout=0.1):
            return await interaction.followup.send(
                "⏳ This server is already handling 4 tasks. Try again in a moment."
            )
        gp = self._gp(interaction.guild.id)
        channel = interaction.user.voice.channel

        try:
            if not gp.voice or not gp.voice.is_connected():
                gp.voice = await channel.connect()
            elif gp.voice.channel and gp.voice.channel.id != channel.id:
                await gp.voice.move_to(channel)
        except Exception as e:
            concurrency.release(interaction.guild.id)
            return await interaction.followup.send(f"Could not join voice: {e}")

        try:
            track = await self._resolve(query.strip())
        except Exception as e:
            log.exception("Resolve failed")
            concurrency.release(interaction.guild.id)
            return await interaction.followup.send(
                f"❌ Could not find that track ({e}). Try a YouTube URL or different search."
            )

        title = track["title"]
        entry = {
            "title": title,
            "url": track["url"],
            "webpage": track.get("webpage") or query,
        }

        if gp.voice.is_playing() or gp.voice.is_paused():
            gp.queue.append(entry)
            concurrency.release(interaction.guild.id)
            await interaction.followup.send(f"Queued **{title}**")
            return

        try:
            src = self._make_source(entry["url"])
            gp.current = entry
            gp.voice.play(src, after=self._after(interaction.guild.id))
            concurrency.release(interaction.guild.id)
            await interaction.followup.send(f"▶️ Playing **{title}**")
        except Exception as e:
            log.exception("Play failed")
            concurrency.release(interaction.guild.id)
            await interaction.followup.send(
                f"❌ Could not play audio ({e}). Ensure **ffmpeg** is installed on the server."
            )

    @music.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        if gp.voice and (gp.voice.is_playing() or gp.voice.is_paused()):
            gp.voice.stop()
            await interaction.response.send_message("Skipped.")
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)

    @music.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction):
        gp = self._gp(interaction.guild.id)  # type: ignore
        gp.queue.clear()
        if gp.voice:
            if gp.voice.is_playing() or gp.voice.is_paused():
                gp.voice.stop()
            try:
                await gp.voice.disconnect()
            except Exception:
                pass
            gp.voice = None
        gp.current = None
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
