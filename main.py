import asyncio
import time
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

import config as cfg
from utils.api import BypassAPI
from utils.config_manager import config_manager
from utils.embeds import (
    confirmation_embed,
    custom_embed,
    error_embed,
    help_embed,
    panel_embed,
    success_embed,
    supported_embed,
)
from utils.helpers import (
    extract_urls,
    get_hostname,
    is_valid_url,
)
from utils.logger import logger

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix=".",
    intents=intents,
    help_command=None,
)

api_client = BypassAPI()

_processed_messages: set[int] = set()
_last_auto: dict[int, float] = {}


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


class ResultView(discord.ui.View):

    def __init__(self, requester: discord.User | discord.Member, result: str) -> None:
        super().__init__(timeout=300)
        self.requester = requester
        self.result = result

    @discord.ui.button(label="Result", style=discord.ButtonStyle.primary, emoji="\U0001F511")
    async def result_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message(
                "Only the user who requested this bypass can view the result.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            content=f"```{self.result[:1900]}```",
            ephemeral=True,
        )

    def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True


def make_result_view(requester: discord.User | discord.Member, result: str) -> discord.ui.View:
    view = ResultView(requester, result)
    join_button = discord.ui.Button(
        label="JOIN",
        style=discord.ButtonStyle.link,
        url=cfg.DISCORD_INVITE_URL,
    )
    view.add_item(join_button)
    return view


class ConfirmationView(discord.ui.View):

    def __init__(self, requester: discord.User | discord.Member, on_continue: Any, on_cancel: Any) -> None:
        super().__init__(timeout=cfg.CONFIRMATION_TIMEOUT)
        self.requester = requester
        self._on_continue = on_continue
        self._on_cancel = on_cancel
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message(
                "These buttons are not for you.",
                ephemeral=True,
            )
            return False
        return True

    def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def on_timeout(self) -> None:
        if not self.finished:
            self.disable_all()
            self.finished = True

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.success, emoji="\u2705")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finished:
            return
        self.finished = True
        self.disable_all()
        await interaction.response.edit_message(view=self)
        if self._on_continue is not None:
            await self._on_continue(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="\u274C")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.finished:
            return
        self.finished = True
        self.disable_all()
        await interaction.response.edit_message(view=self)
        if self._on_cancel is not None:
            await self._on_cancel(interaction)


async def process_bypass(
    link: str,
    user: discord.User | discord.Member,
    send_func: Any,
) -> None:
    start = time.perf_counter()
    if not is_valid_url(link):
        elapsed = time.perf_counter() - start
        await send_func(embed=error_embed("Invalid URL provided.", elapsed))
        return

    result = await api_client.bypass(link)
    elapsed = time.perf_counter() - start

    if not result["success"]:
        await send_func(embed=error_embed(result["error"] or "Bypass failed.", elapsed))
        return

    embed = success_embed(
        result=result["result"],
        service=result["service"],
        user=user,
        elapsed=elapsed,
    )
    view = make_result_view(user, result["result"])
    await send_func(embed=embed, view=view)


def is_platorelay(link: str) -> bool:
    return "auth.platorelay.com" in get_hostname(link)


async def handle_bypass_command(
    interaction: discord.Interaction,
    link: str,
) -> None:
    if not is_valid_url(link):
        await interaction.response.send_message(
            embed=error_embed("Invalid URL provided."),
            ephemeral=True,
        )
        return

    async def _send_public(content: Any = None, *, embed: Any = None, view: Any = None) -> None:
        await interaction.followup.send(content=content, embed=embed, view=view)

    if is_platorelay(link):
        await interaction.response.send_message(
            embed=confirmation_embed(),
            view=ConfirmationView(
                requester=interaction.user,
                on_continue=_make_continue_handler(interaction, link),
                on_cancel=_make_cancel_handler(interaction),
            ),
            ephemeral=True,
        )
        return

    await interaction.response.defer()
    await process_bypass(link, interaction.user, _send_public)


def _make_continue_handler(interaction: discord.Interaction, link: str) -> Any:
    async def _continue(btn_interaction: discord.Interaction) -> None:
        async def _send(content: Any = None, *, embed: Any = None, view: Any = None) -> None:
            await btn_interaction.followup.send(content=content, embed=embed, view=view)

        await process_bypass(link, interaction.user, _send)

    return _continue


def _make_cancel_handler(interaction: discord.Interaction) -> Any:
    async def _cancel(btn_interaction: discord.Interaction) -> None:
        await btn_interaction.followup.send(
            content="Bypass request cancelled.",
            ephemeral=True,
        )

    return _cancel


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

    if message.author.bot:
        return
    if message.guild is None:
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
    if not urls:
        return

    _processed_messages.add(message.id)

    slowdown = config_manager.get_slowdown(guild_id)
    now = time.time()
    last = _last_auto.get(guild_id, 0.0)
    if slowdown > 0 and now - last < slowdown:
        return
    _last_auto[guild_id] = now

    supported = await api_client.get_supported()
    supported_hosts: list[str] = []
    if supported["success"]:
        supported_hosts = [get_hostname(s) for s in supported["services"] if get_hostname(s)]

    for url in urls:
        hostname = get_hostname(url)
        if supported["success"]:
            if hostname not in supported_hosts:
                continue
        logger.info("Auto-bypass for guild %s, url: %s", guild_id, hostname or url)
        await process_bypass(url, message.author, message.channel.send)

    delete_time = config_manager.get_delete_time(guild_id)
    if delete_time > 0:
        try:
            await asyncio.sleep(delete_time)
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            logger.warning("Missing Manage Messages permission in channel %s", message.channel.id)
        except Exception as exc:
            logger.warning("Failed to delete message %s: %s", message.id, exc)


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
    delete_time="Seconds before the original message is deleted (25-250).",
)
@app_commands.choices(delete_time=[app_commands.Choice(name=str(n), value=str(n)) for n in [25, 30, 45, 60, 90, 120, 150, 180, 250]])
async def setupbypass_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    delete_time: app_commands.Choice[str],
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "You need the Manage Channels permission to use this command.",
            ephemeral=True,
        )
        return

    try:
        dt_value = int(delete_time.value)
    except (TypeError, ValueError):
        await interaction.response.send_message("Invalid delete time.", ephemeral=True)
        return

    if dt_value < cfg.MIN_DELETE_TIME or dt_value > cfg.MAX_DELETE_TIME:
        await interaction.response.send_message(
            f"Delete time must be between {cfg.MIN_DELETE_TIME} and {cfg.MAX_DELETE_TIME} seconds.",
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
    logger.info("Guild %s configured auto-bypass in channel %s, delete_time=%s", interaction.guild.id, channel.id, dt_value)
    embed = discord.Embed(
        title="Auto-Bypass Configured",
        color=cfg.EMBED_COLOR,
        description=(
            f"Channel: {channel.mention}\n"
            f"Delete time: {dt_value} seconds\n"
            f"Status: Enabled"
        ),
    )
    embed.set_thumbnail(url=cfg.EMOJI_CHECKMARK)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slowdown", description="Set cooldown between auto-bypasses.")
@app_commands.describe(seconds="Cooldown in seconds (0-60).")
async def slowdown_command(interaction: discord.Interaction, seconds: int) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "You need the Manage Channels permission to use this command.",
            ephemeral=True,
        )
        return
    if seconds < cfg.MIN_SLOWDOWN or seconds > cfg.MAX_SLOWDOWN:
        await interaction.response.send_message(
            f"Slowdown must be between {cfg.MIN_SLOWDOWN} and {cfg.MAX_SLOWDOWN} seconds.",
            ephemeral=True,
        )
        return
    config_manager.set_guild_config(interaction.guild.id, {"slowdown": seconds})
    logger.info("Guild %s set slowdown to %s seconds", interaction.guild.id, seconds)
    embed = discord.Embed(
        title="Slowdown Updated",
        color=cfg.EMBED_COLOR,
        description=f"Slowdown set to {seconds} seconds.",
    )
    embed.set_thumbnail(url=cfg.EMOJI_TIMER)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="bypasspanel", description="Show the current auto-bypass configuration.")
async def bypasspanel_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    data = config_manager.get_guild_config(interaction.guild.id)
    await interaction.response.send_message(embed=panel_embed(data))


@bot.tree.command(name="embed", description="Build a custom embed.")
@app_commands.describe(
    title="Embed title.",
    description="Embed description.",
    url="Embed URL.",
    color="Embed color.",
    image="Image URL.",
    thumbnail="Thumbnail URL.",
    tumbanair="Select a user to use their avatar as the thumbnail.",
    footer="Footer text.",
    timestamp="Add current timestamp.",
)
@app_commands.choices(
    color=[app_commands.Choice(name=name, value=str(value)) for name, value in cfg.COLOR_CHOICES.items()],
)
async def embed_command(
    interaction: discord.Interaction,
    title: str | None = None,
    description: str | None = None,
    url: str | None = None,
    color: app_commands.Choice[str] | None = None,
    image: str | None = None,
    thumbnail: str | None = None,
    tumbanair: discord.User | None = None,
    footer: str | None = None,
    timestamp: bool = False,
) -> None:
    color_value = cfg.EMBED_COLOR
    if color is not None:
        try:
            color_value = int(color.value)
        except (TypeError, ValueError):
            color_value = cfg.EMBED_COLOR

    thumb_url = thumbnail
    if tumbanair is not None:
        thumb_url = tumbanair.display_avatar.url

    if url is not None and not is_valid_url(url):
        await interaction.response.send_message("Invalid URL provided.", ephemeral=True)
        return
    if image is not None and not is_valid_url(image):
        await interaction.response.send_message("Invalid image URL.", ephemeral=True)
        return
    if thumb_url is not None and not is_valid_url(thumb_url):
        await interaction.response.send_message("Invalid thumbnail URL.", ephemeral=True)
        return

    embed = custom_embed(
        title=title,
        description=description,
        url=url,
        color=color_value,
        image=image,
        thumbnail=thumb_url,
        footer=footer,
        timestamp=timestamp,
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show all available commands.")
async def help_slash_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=help_embed())


@bot.command(name="help")
async def help_prefix_command(ctx: commands.Context) -> None:
    await ctx.send(embed=help_embed())


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
