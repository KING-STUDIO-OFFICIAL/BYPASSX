import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

import config as cfg
from utils.api import BypassAPI
from utils.config_manager import config_manager
from utils.embeds import (
    about_embed,
    bypasscount_embed,
    confirmation_embed,
    custom_embed,
    error_embed,
    help_embed_en,
    help_embed_es,
    leaderboard_embed,
    panel_embed,
    ping_embed,
    platorelay_warning_embed,
    profile_embed,
    progress_embed,
    stats_embed,
    status_embed,
    success_embed,
    supported_embed,
    uptime_embed,
)
from utils.helpers import (
    extract_urls,
    get_hostname,
    is_valid_url,
)
from utils.logger import logger

bot = commands.Bot(
    command_prefix="!",
    intents=discord.Intents.all(),
    help_command=None,
)

api_client = BypassAPI()

BOT_START_TIME = time.time()
BOT_START_DATETIME = datetime.now(timezone.utc)

PLATORELAY_HOSTS = {"auth.platorelay.com", "platorelay.com"}

EMOJI_COPY_BTN = "<:CopyPaste:1525379105111932958>"
EMOJI_ADD_BTN = "<:add_symbol:1527235736116527179>"
EMOJI_HOME_BTN = "<:Home:1527235583460773909>"

MAX_AUTO_MSG_DELETE = 500
MIN_AUTO_MSG_DELETE = 5


def _normalize_host(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        return get_hostname(value)
    host = value.split("/")[0].split(":")[0].split("?")[0].split(" ")[0]
    return host


def _format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _is_platorelay(url: str) -> bool:
    hostname = _normalize_host(url)
    return hostname in PLATORELAY_HOSTS


class KeepAliveServer:

    def __init__(self, port: int) -> None:
        self.port = port
        self._runner: Any = None
        self._site: Any = None

    async def _handler(self, request: Any) -> Any:
        from aiohttp.web import Response
        if request.path == "/health":
            return Response(
                text='{"status": "online"}',
                status=200,
                content_type="application/json",
            )
        return Response(text="OK", status=200)

    async def start(self) -> None:
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", self._handler)
        app.router.add_get("/health", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await self._site.start()
        logger.info("Keep-alive server listening on port %s", self.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()


keep_alive = KeepAliveServer(cfg.PORT)

_processed_messages: OrderedDict[int, float] = OrderedDict()
MAX_PROCESSED_CACHE = 1000

_supported_cache: dict[str, Any] = {"services": [], "timestamp": 0}
SUPPORTED_CACHE_TTL = 300

_last_auto: dict[int, float] = {}


class ResultView(discord.ui.View):
    def __init__(self, user: discord.User | discord.Member, result: str) -> None:
        super().__init__(timeout=300)
        self.user = user
        self.result = result
        self.add_item(discord.ui.Button(
            label="Invite",
            style=discord.ButtonStyle.link,
            url=cfg.DISCORD_INVITE_URL,
            emoji=EMOJI_ADD_BTN,
        ))
        self.add_item(discord.ui.Button(
            label="Server",
            style=discord.ButtonStyle.link,
            url=cfg.DISCORD_INVITE_URL,
            emoji=EMOJI_HOME_BTN,
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ You cannot interact with this message.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Copy", style=discord.ButtonStyle.success, emoji=EMOJI_COPY_BTN)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        content = self.result
        if len(content) > 1990:
            content = self.result[:1990] + "..."
        await interaction.response.send_message(
            content=content,
            ephemeral=True,
        )


class PlatorelayConfirmView(discord.ui.View):
    def __init__(self, user: discord.User | discord.Member) -> None:
        super().__init__(timeout=120)
        self.user = user
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the user who started this bypass can interact.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.success, emoji="✅")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        await interaction.response.edit_message(content="# ✅ **`CONTINUING BYPASS...`**", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        await interaction.response.edit_message(content="# ❌ **`BYPASS CANCELLED`**", embed=None, view=None)
        self.stop()


class HelpView(discord.ui.View):
    def __init__(self, user: discord.User | discord.Member) -> None:
        super().__init__(timeout=300)
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Only the user who opened the help can interact.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Español", style=discord.ButtonStyle.primary, emoji="🇪🇸")
    async def spanish_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=help_embed_es(), view=self)

    @discord.ui.button(label="English", style=discord.ButtonStyle.primary, emoji="🇺🇸")
    async def english_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=help_embed_en(), view=self)


def make_result_view(user: discord.User | discord.Member, result: str) -> discord.ui.View:
    return ResultView(user, result)


async def _delete_message_later(msg: discord.Message, seconds: int) -> None:
    if seconds <= 0:
        return
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except discord.NotFound:
        pass
    except discord.Forbidden:
        logger.warning("Missing Manage Messages permission in channel %s", msg.channel.id)
    except Exception as exc:
        logger.warning("Failed to delete message %s: %s", msg.id, exc)


async def process_bypass(
    link: str,
    user: discord.User | discord.Member,
    send_func: Any,
    progress_msg: discord.Message | None = None,
    track_count: bool = True,
) -> discord.Message | None:
    start = time.perf_counter()

    if not is_valid_url(link):
        elapsed = time.perf_counter() - start
        if progress_msg:
            await progress_msg.edit(embed=error_embed("Invalid URL provided.", elapsed), view=None)
            return progress_msg
        return await send_func(embed=error_embed("Invalid URL provided.", elapsed))

    if not progress_msg:
        try:
            progress_msg = await send_func(embed=progress_embed())
        except Exception as exc:
            logger.warning("Failed to send progress embed: %s", exc)
            progress_msg = None

    try:
        result = await api_client.bypass(link)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error("Bypass exception: %s", exc)
        err = error_embed(str(exc), elapsed)
        if progress_msg:
            await progress_msg.edit(embed=err, view=None)
            return progress_msg
        return await send_func(embed=err)

    elapsed = time.perf_counter() - start

    if not result["success"]:
        err = error_embed(result["error"] or "Bypass failed.", elapsed)
        if progress_msg:
            await progress_msg.edit(embed=err, view=None)
            return progress_msg
        return await send_func(embed=err)

    if track_count:
        try:
            config_manager.increment_bypass_count(user.id)
        except Exception as exc:
            logger.warning("Failed to track bypass count: %s", exc)

    embed = success_embed(
        result=result["result"],
        service=result["service"],
        user=user,
        elapsed=elapsed,
    )
    view = make_result_view(user, result["result"])

    if progress_msg:
        await progress_msg.edit(embed=embed, view=view)
        return progress_msg
    return await send_func(embed=embed, view=view)


async def handle_bypass_command(interaction: discord.Interaction, link: str) -> None:
    await interaction.response.defer()

    async def send_func(**kwargs):
        return await interaction.followup.send(**kwargs)

    if _is_platorelay(link):
        warning_embed = platorelay_warning_embed()
        view = PlatorelayConfirmView(interaction.user)
        msg = await interaction.followup.send(embed=warning_embed, view=view)
        await view.wait()
        if view.value is not True:
            try:
                await msg.edit(content="# ❌ **`BYPASS CANCELLED`**", embed=None, view=None)
            except Exception:
                pass
            return
        try:
            await msg.delete()
        except Exception:
            pass

    await process_bypass(link, interaction.user, send_func)


async def handle_auto_bypass(
    url: str,
    user: discord.User | discord.Member,
    channel: discord.TextChannel,
) -> None:
    if _is_platorelay(url):
        try:
            notice = await channel.send(
                content=(
                    f"# ⚠️ **`DELTA BYPASS DISABLED`**\n"
                    f"> {user.mention} — Auto-bypass for `auth.platorelay.com` links\n"
                    f"> is disabled because it requires manual confirmation."
                ),
            )
            asyncio.create_task(_delete_message_later(notice, 15))
        except Exception as exc:
            logger.warning("Failed to send platorelay auto-bypass notice: %s", exc)
        return

    progress_msg = None
    try:
        progress_msg = await channel.send(embed=progress_embed())
    except Exception as exc:
        logger.warning("Failed to send progress message: %s", exc)

    result_msg = await process_bypass(url, user, channel.send, progress_msg, track_count=True)

    guild_id = channel.guild.id
    bot_delete_time = config_manager.get_auto_msg_delete_time(guild_id)
    if bot_delete_time > 0 and result_msg is not None:
        asyncio.create_task(_delete_message_later(result_msg, bot_delete_time))


@bot.event
async def on_ready() -> None:
    logger.info("Bot logged in as %s (ID: %s)", bot.user, bot.user.id if bot.user else "unknown")
    try:
        synced = await bot.tree.sync()
        logger.info("Synchronized %s slash commands", len(synced))
    except Exception as exc:
        logger.error("Failed to synchronize slash commands: %s", exc)
    if keep_alive._site is None:
        await keep_alive.start()


@bot.event
async def on_message(message: discord.Message) -> None:
    await bot.process_commands(message)

    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id

    if not config_manager.is_auto_enabled(guild_id):
        return

    auto_channel = config_manager.get_auto_channel(guild_id)
    if auto_channel is None or message.channel.id != auto_channel:
        return

    if message.id in _processed_messages:
        return

    urls = extract_urls(message.content)

    instant_delete = config_manager.is_instant_delete(guild_id)
    delete_time = config_manager.get_delete_time(guild_id)

    if instant_delete:
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            logger.warning("Missing Manage Messages permission in channel %s", message.channel.id)
        except Exception as exc:
            logger.warning("Failed to delete user message %s: %s", message.id, exc)
    else:
        asyncio.create_task(_delete_message_later(message, delete_time))

    if not urls:
        return

    current_time = time.time()

    while _processed_messages:
        oldest_key = next(iter(_processed_messages))
        if current_time - _processed_messages[oldest_key] > 3600:
            _processed_messages.popitem(last=False)
        else:
            break

    _processed_messages[message.id] = current_time
    if len(_processed_messages) > MAX_PROCESSED_CACHE:
        _processed_messages.popitem(last=False)

    if current_time - _supported_cache["timestamp"] > SUPPORTED_CACHE_TTL:
        try:
            supported = await api_client.get_supported()
            if supported["success"]:
                _supported_cache["services"] = [
                    _normalize_host(s) for s in supported["services"] if _normalize_host(s)
                ]
                _supported_cache["timestamp"] = current_time
                logger.info("Updated supported services cache: %s services", len(_supported_cache["services"]))
        except Exception as exc:
            logger.warning("Failed to fetch supported services: %s", exc)

    supported_hosts = _supported_cache["services"]
    slowdown = config_manager.get_slowdown(guild_id)

    for url in urls:
        hostname = get_hostname(url)

        if supported_hosts and hostname not in supported_hosts:
            continue

        now = time.time()
        last = _last_auto.get(guild_id, 0.0)
        if slowdown > 0 and now - last < slowdown:
            logger.info("Slowdown active for guild %s, skipping URL: %s", guild_id, hostname or url)
            continue

        _last_auto[guild_id] = now
        logger.info("Auto-bypass for guild %s, url: %s", guild_id, hostname or url)

        await handle_auto_bypass(url, message.author, message.channel)


@bot.tree.command(name="bypass", description="Process a URL through the bypass API.")
@app_commands.describe(link="The URL to bypass.")
async def bypass_command(interaction: discord.Interaction, link: str) -> None:
    await handle_bypass_command(interaction, link)


@bot.tree.command(name="supported", description="Show all services supported by the API.")
async def supported_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    result = await api_client.get_supported()
    if not result["success"]:
        await interaction.followup.send(
            embed=error_embed(result["error"] or "Could not retrieve supported services."),
        )
        return
    await interaction.followup.send(embed=supported_embed(result["services"]))


@bot.tree.command(name="setupbypass", description="Enable automatic bypass in a channel.")
@app_commands.describe(
    channel="The channel to enable auto-bypass in.",
    delete_time="Seconds before user messages are deleted (25-250).",
)
@app_commands.choices(delete_time=[app_commands.Choice(name=str(n), value=str(n)) for n in [25, 30, 45, 60, 90, 120, 150, 180, 250]])
async def setupbypass_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    delete_time: app_commands.Choice[str],
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )
        return

    try:
        dt_value = int(delete_time.value)
    except (TypeError, ValueError):
        await interaction.response.send_message("# ❌ **`INVALID INPUT`**\n> Invalid delete time.", ephemeral=True)
        return

    if dt_value < cfg.MIN_DELETE_TIME or dt_value > cfg.MAX_DELETE_TIME:
        await interaction.response.send_message(
            f"# ❌ **`OUT OF RANGE`**\n> Delete time must be between `{cfg.MIN_DELETE_TIME}` and `{cfg.MAX_DELETE_TIME}` seconds.",
            ephemeral=True,
        )
        return

    config_manager.set_guild_config(
        interaction.guild.id,
        {
            "auto_channel": channel.id,
            "delete_time": dt_value,
            "enabled": True,
        },
    )

    embed = discord.Embed(
        color=0x000000,
        description=(
            f"# ✅ **`AUTO-BYPASS ENABLED`**\n"
            f"> Automatic bypass has been enabled in {channel.mention}\n"
            f"> Delete Time: `{dt_value} seconds`"
        ),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="disablebypass", description="Disable automatic bypass.")
async def disablebypass_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"enabled": False})
    embed = discord.Embed(
        color=0x000000,
        description="# ⛔ **`AUTO-BYPASS DISABLED`**\n> Automatic bypass has been disabled.",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="autodelete", description="Instantly delete user messages in the auto-bypass channel.")
@app_commands.describe(enabled="True = user messages deleted instantly.")
async def autodelete_command(interaction: discord.Interaction, enabled: bool) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"instant_delete": enabled})
    delete_time = config_manager.get_delete_time(interaction.guild.id)
    if enabled:
        description = (
            "# 🗑️ Auto Delete Enabled\n"
            "> User messages will be deleted **instantly** in the auto-bypass channel.\n"
            f"> Bot bypass messages will last based on `/autodeltime` setting."
        )
    else:
        description = (
            "# 🗑️ Auto Delete Disabled\n"
            f"> User messages will last `{delete_time}s` before deletion."
        )
    embed = discord.Embed(color=0x000000, description=description)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="autodeltime", description="Set how long bot bypass messages last before being deleted.")
@app_commands.describe(seconds="Seconds before bot messages are deleted (5-500).")
async def autodeltime_command(interaction: discord.Interaction, seconds: int) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission.",
            ephemeral=True,
        )
        return
    if seconds < MIN_AUTO_MSG_DELETE or seconds > MAX_AUTO_MSG_DELETE:
        await interaction.response.send_message(
            f"# ❌ **`OUT OF RANGE`**\n> Time must be between `{MIN_AUTO_MSG_DELETE}` and `{MAX_AUTO_MSG_DELETE}` seconds.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"auto_msg_delete_time": seconds})
    embed = discord.Embed(
        color=0x000000,
        description=(
            "# ⏱️ **`BOT MESSAGE DELETE TIME SET`**\n"
            f"> Bot bypass messages will now last **`{seconds} seconds`** before being deleted."
        ),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="slowdown", description="Set cooldown between auto-bypasses.")
@app_commands.describe(seconds="Cooldown in seconds (0-60).")
async def slowdown_command(interaction: discord.Interaction, seconds: int) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission.",
            ephemeral=True,
        )
        return
    if seconds < cfg.MIN_SLOWDOWN or seconds > cfg.MAX_SLOWDOWN:
        await interaction.response.send_message(
            f"# ❌ **`OUT OF RANGE`**\n> Slowdown must be between `{cfg.MIN_SLOWDOWN}` and `{cfg.MAX_SLOWDOWN}` seconds.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"slowdown": seconds})
    embed = discord.Embed(
        color=0x000000,
        description=f"# ⏱️ **`SLOWDOWN SET`**\n> Cooldown between auto-bypasses set to `{seconds} seconds`.",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="delete-time", description="Set how long user messages last in auto-bypass channel.")
@app_commands.describe(seconds="Seconds before user messages are deleted (25-250).")
async def delete_time_command(interaction: discord.Interaction, seconds: int) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "# ❌ **`PERMISSION DENIED`**\n> You need the **Manage Channels** permission.",
            ephemeral=True,
        )
        return
    if seconds < cfg.MIN_DELETE_TIME or seconds > cfg.MAX_DELETE_TIME:
        await interaction.response.send_message(
            f"# ❌ **`OUT OF RANGE`**\n> Delete time must be between `{cfg.MIN_DELETE_TIME}` and `{cfg.MAX_DELETE_TIME}` seconds.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"delete_time": seconds})
    embed = discord.Embed(
        color=0x000000,
        description=f"# ⏱️ **`DELETE TIME SET`**\n> User messages will now last **`{seconds} seconds`** before being deleted.",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="bypasspanel", description="Show the current auto-bypass configuration.")
async def bypasspanel_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("# ❌ **`ERROR`**\n> This command can only be used in a server.", ephemeral=True)
        return
    data = config_manager.get_guild_config(interaction.guild.id)
    await interaction.response.send_message(embed=panel_embed(data))


@bot.tree.command(name="profile", description="Show your user statistics.")
async def profile_command(interaction: discord.Interaction) -> None:
    count = config_manager.get_user_bypass_count(interaction.user.id)
    await interaction.response.send_message(embed=profile_embed(interaction.user, count), ephemeral=True)


@bot.tree.command(name="bypasscount", description="Show bypass count for a user.")
@app_commands.describe(user="The user to check (defaults to yourself).")
async def bypasscount_command(
    interaction: discord.Interaction,
    user: discord.User | None = None,
) -> None:
    target = user or interaction.user
    count = config_manager.get_user_bypass_count(target.id)
    await interaction.response.send_message(embed=bypasscount_embed(target, count), ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show top users by bypass count.")
async def leaderboard_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    raw_entries = config_manager.get_leaderboard(limit=10)
    resolved: list[tuple[discord.User | None, int]] = []
    for user_id, count in raw_entries:
        try:
            user = await bot.fetch_user(user_id)
        except Exception:
            user = None
        resolved.append((user, count))
    await interaction.followup.send(embed=leaderboard_embed(resolved))


@bot.tree.command(name="status", description="Show API status.")
async def status_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    start = time.perf_counter()
    try:
        result = await api_client.get_supported()
        api_latency = (time.perf_counter() - start) * 1000
        services_count = len(result.get("services", []))
        api_ok = result["success"]
        api_message = "OK" if api_ok else (result.get("error") or "Unknown error")
    except Exception as exc:
        api_latency = (time.perf_counter() - start) * 1000
        services_count = 0
        api_ok = False
        api_message = str(exc)
    await interaction.followup.send(
        embed=status_embed(api_ok, api_message, services_count)
    )


@bot.tree.command(name="ping", description="Show bot latency.")
async def ping_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    ws_latency = bot.latency * 1000
    start = time.perf_counter()
    try:
        await api_client.get_supported()
        api_latency = (time.perf_counter() - start) * 1000
    except Exception:
        api_latency = (time.perf_counter() - start) * 1000
    await interaction.followup.send(embed=ping_embed(ws_latency, api_latency))


@bot.tree.command(name="stats", description="Show bot statistics.")
async def stats_command(interaction: discord.Interaction) -> None:
    guild_count = len(bot.guilds)
    user_count = sum(g.member_count or 0 for g in bot.guilds)
    channel_count = sum(len(g.channels) for g in bot.guilds)
    global_bypass = config_manager.get_global_bypass_count()
    auto_enabled_guilds = sum(
        1 for cfg_data in config_manager.all_configs().values()
        if isinstance(cfg_data, dict) and cfg_data.get("enabled")
    )
    await interaction.response.send_message(
        embed=stats_embed(guild_count, user_count, channel_count, global_bypass, auto_enabled_guilds)
    )


@bot.tree.command(name="uptime", description="Show bot uptime.")
async def uptime_command(interaction: discord.Interaction) -> None:
    uptime_seconds = time.time() - BOT_START_TIME
    start_str = discord.utils.format_dt(BOT_START_DATETIME, "F")
    uptime_str = _format_uptime(uptime_seconds)
    await interaction.response.send_message(embed=uptime_embed(start_str, uptime_str))


@bot.tree.command(name="about", description="Show bot information.")
async def about_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=about_embed())


@bot.tree.command(name="embed", description="Create a custom embed.")
@app_commands.describe(
    title="Embed title.",
    description="Embed description.",
    color="Hex color (e.g. 000000 for black, ff0000 for red).",
)
async def embed_command(
    interaction: discord.Interaction,
    title: str,
    description: str,
    color: str = "000000",
) -> None:
    try:
        color_hex = color.lstrip("#")
        color_int = int(color_hex, 16)
        if not (0 <= color_int <= 0xFFFFFF):
            raise ValueError
    except ValueError:
        await interaction.response.send_message(
            "# ❌ **`INVALID COLOR`**\n> Use a hex value like `000000` or `ff0000`.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(title=title, description=description, color=color_int)
    embed.set_footer(text=f"Created by {interaction.user.display_name}")
    try:
        await interaction.response.send_message(embed=embed)
    except Exception as exc:
        await interaction.response.send_message(
            f"# ❌ **`ERROR`**\n> Failed to send embed: `{exc}`", ephemeral=True
        )


@bot.tree.command(name="invite", description="Get bot invite link.")
async def invite_command(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        color=0x000000,
        description=(
            f"# 🔗 **`INVITE BYPASSX`**\n"
            f"> [Click here to invite the bot]({cfg.DISCORD_INVITE_URL})"
        ),
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Invite",
        style=discord.ButtonStyle.link,
        url=cfg.DISCORD_INVITE_URL,
        emoji=EMOJI_ADD_BTN,
    ))
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="support", description="Get support server link.")
async def support_command(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        color=0x000000,
        description=(
            f"# 🏠 **`SUPPORT SERVER`**\n"
            f"> [Click here to join the support server]({cfg.DISCORD_INVITE_URL})"
        ),
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Join Support Server",
        style=discord.ButtonStyle.link,
        url=cfg.DISCORD_INVITE_URL,
        emoji=EMOJI_HOME_BTN,
    ))
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="help", description="Show all available commands.")
async def help_slash_command(interaction: discord.Interaction) -> None:
    view = HelpView(interaction.user)
    await interaction.response.send_message(embed=help_embed_es(), view=view)


@bot.command(name="help")
async def help_prefix_command(ctx: commands.Context) -> None:
    view = HelpView(ctx.author)
    await ctx.send(embed=help_embed_es(), view=view)


async def main() -> None:
    if not cfg.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN is not set. Add it to your .env file.")
        return

    async with bot:
        await keep_alive.start()
        await bot.start(cfg.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by keyboard interrupt.")
    except Exception as exc:
        logger.error("Fatal error during bot startup: %s", exc)
