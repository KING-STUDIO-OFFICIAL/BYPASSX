from datetime import datetime, timezone
from typing import Any

import discord

import config as cfg
from utils.helpers import format_datetime, truncate


def _black_embed(title: str | None = None, description: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=cfg.EMBED_COLOR,
    )
    return embed


def success_embed(
    result: str,
    service: str,
    user: discord.User | discord.Member,
    elapsed: float,
) -> discord.Embed:
    embed = _black_embed()
    embed.set_author(name="Bypass Successful", icon_url=cfg.EMOJI_CHECKMARK)
    embed.description = f"{cfg.EMOJI_KEY} Result processed successfully."
    embed.add_field(
        name="Result",
        value=f"```{truncate(result, 1000)}```",
        inline=False,
    )
    embed.add_field(
        name="\u200b",
        value=(
            f"\U0001F517 **{service or 'Unknown'}** \u2022 "
            f"Requested by **{user.display_name}** \u2022 "
            f"\u23F1\uFE0F {elapsed:.2f}s | {format_datetime()}"
        ),
        inline=False,
    )
    embed.set_thumbnail(url=cfg.EMOJI_CONFETTI)
    return embed


def error_embed(reason: str, elapsed: float = 0.0) -> discord.Embed:
    embed = _black_embed()
    embed.set_author(name="Bypass Failed", icon_url=cfg.EMOJI_ERROR)
    embed.add_field(name="Reason:", value=truncate(reason, 1000), inline=False)
    embed.add_field(name="TIME:", value=f"{elapsed:.2f}s", inline=False)
    embed.set_thumbnail(url=cfg.EMOJI_ERROR)
    return embed


def supported_embed(services: list[str]) -> discord.Embed:
    embed = _black_embed(title="Supported Services")
    embed.set_thumbnail(url=cfg.EMOJI_KEY)
    if not services:
        embed.description = "No supported services returned by the API."
        return embed
    chunks: list[str] = []
    current = ""
    for service in services:
        line = f"\u2022 {service}\n"
        if len(current) + len(line) > 1000:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    for i, chunk in enumerate(chunks, start=1):
        embed.add_field(
            name=f"Services {i}" if len(chunks) > 1 else "Services",
            value=chunk,
            inline=False,
        )
    embed.set_footer(text=f"Total: {len(services)} services")
    return embed


def panel_embed(config_data: dict[str, Any]) -> discord.Embed:
    embed = _black_embed(title="Automatic Bypass Configuration")
    embed.set_thumbnail(url=cfg.EMOJI_TIMER)
    status = "\u2705 Enabled" if config_data.get("enabled") else "\u26D4\uFE0F Disabled"
    channel_id = config_data.get("auto_channel")
    channel_str = f"<#{channel_id}>" if channel_id else "Not configured"
    embed.add_field(name="Auto-Bypass Status", value=status, inline=False)
    embed.add_field(name="Channel", value=channel_str, inline=False)
    embed.add_field(name="Delete Time", value=f"{config_data.get('delete_time', 60)} seconds", inline=False)
    embed.add_field(name="Slowdown", value=f"{config_data.get('slowdown', 0)} seconds", inline=False)
    return embed


def help_embed() -> discord.Embed:
    embed = _black_embed(title="Bypass Bot - Help")
    embed.set_thumbnail(url=cfg.EMOJI_KEY)
    commands = [
        ("/bypass `<link>`", "Process a URL through the bypass API."),
        ("/supported", "Show all services supported by the API."),
        ("/setupbypass `<channel>` `<delete_time>`", "Enable automatic bypass in a channel (Manage Channels)."),
        ("/embed", "Build a custom embed with various options."),
        ("/slowdown `<seconds>`", "Set cooldown between auto-bypasses (Manage Channels)."),
        ("/bypasspanel", "Show the current auto-bypass configuration."),
        ("/help", "Show this help message."),
        (".help", "Show this help message using the dot prefix."),
    ]
    for name, desc in commands:
        embed.add_field(name=name, value=desc, inline=False)
    embed.set_footer(text="Bypass Bot")
    return embed


def custom_embed(
    title: str | None,
    description: str | None,
    url: str | None,
    color: int,
    image: str | None,
    thumbnail: str | None,
    footer: str | None,
    timestamp: bool,
) -> discord.Embed:
    embed = discord.Embed(color=color)
    if title:
        embed.title = title
    if description:
        embed.description = description
    if url:
        embed.url = url
    if image:
        embed.set_image(url=image)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if footer:
        embed.set_footer(text=footer)
    if timestamp:
        embed.timestamp = datetime.now(timezone.utc)
    return embed


def confirmation_embed() -> discord.Embed:
    embed = _black_embed()
    embed.set_author(name="Confirmation Required", icon_url=cfg.EMOJI_TIMER)
    embed.description = (
        "\u26A0\uFE0F Bypassing this link may put you at risk of getting blacklisted "
        "from using Delta, should you continue or not?"
    )
    return embed
