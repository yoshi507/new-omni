"""Music — SoundCloud only via yt-dlp + FFmpeg."""
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

SC_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "scsearch",
    "noplaylist": True,
    "source_address": "0.0.0.0",
    "skip_download": True,
}


def _pick_stream(info: dict) -> str | None:
    url = info.get("url")
    if url:
        return url
    for f in reversed(info.get("formats") or []):
        if f.get("url") and (f.get("acodec") or "none") != "none":
            return f["url"]
    return info.get("webpage_url")


def _extract(query: str) -> dict:
    import yt_dlp

    q = query.strip()
    low = q.lower()

    # Reject YouTube links explicitly
    if any(x in low for x in ("youtube.com", "youtu.be", "youtube")):
        raise RuntimeError(
            "YouTube is not supported. Paste a SoundCloud URL or search by song/artist name."
        )

    # Force SoundCloud search for plain text; keep direct SC URLs as-is
    if "soundcloud.com" not in low:
        # scsearch1: first result only
        q = f"scsearch1:{q}"

    with yt_dlp.YoutubeDL(SC_OPTS) as ydl:
        info = ydl.extract_info(q, download=False)
        if info is None:
            raise RuntimeError("No results on SoundCloud")
        if "entries" in info:
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("No SoundCloud results for that search")
            info = entries[0]
        stream = _pick_stream(info)
        if not stream:
            raise RuntimeError("No stream URL from SoundCloud")
        return {
            "title": info.get("title") or query,
            "url": stream,
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
            if item.get("webpage"):
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

    music = app_commands.Group(name="music", description="Music controls (SoundCloud only)")

    @music.command(name="play", description="Play from SoundCloud URL or search")
    @app_commands.describe(query="SoundCloud URL or search terms (no YouTube)")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Guild only.", ephemeral=True)
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "Join a voice channel first.", ephemeral=True
            )

        await interaction.response.defer()
        async with concurrency.guild_slot(interaction.guild.id):
            gp = self._gp(interaction.guild.id)
            channel = interaction.user.voice.channel

            try:
                if not gp.voice or not gp.voice.is_connected():
                    gp.voice = await channel.connect()
                elif gp.voice.channel and gp.voice.channel.id != channel.id:
                    await gp.voice.move_to(channel)
            except Exception as e:
                return await interaction.followup.send(f"Could not join voice: {e}")

            try:
                track = await self._resolve(query.strip())
            except Exception as e:
                log.exception("Resolve failed")
                return await interaction.followup.send(
                    f"❌ Could not find that track on SoundCloud.\n{e}\n"
                    f"Tip: paste a **soundcloud.com** link or search by song/artist name."
                )

            title = track["title"]
            entry = {
                "title": title,
                "url": track["url"],
                "webpage": track.get("webpage") or query,
            }

            if gp.voice.is_playing() or gp.voice.is_paused():
                gp.queue.append(entry)
                await interaction.followup.send(f"Queued **{title}**")
                return

            try:
                src = self._make_source(entry["url"])
                gp.current = entry
                gp.voice.play(src, after=self._after(interaction.guild.id))
                await interaction.followup.send(f"▶️ Playing **{title}**")
            except Exception as e:
                log.exception("Play failed")
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
