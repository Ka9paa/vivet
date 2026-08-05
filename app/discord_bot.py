from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Application, AuditLog, License, Owner, PanelMember

ROLE_CHOICES = (
    ("Owner", "owner"),
    ("Developer", "developer"),
    ("Admin", "admin"),
    ("Auth Access", "auth_access"),
)
ROLE_ORDER = {"owner": 4, "admin": 3, "developer": 2, "auth_access": 1}
LEGACY_ROLE_MAP = {"viewer": "auth_access", "support": "auth_access", "reseller": "auth_access"}
DURATION_CHOICES = (
    ("1 Day", "day"),
    ("1 Week", "week"),
    ("1 Month", "month"),
    ("Lifetime", "lifetime"),
)


def normalized_role(role: str | None) -> str:
    value = (role or "auth_access").lower()
    return LEGACY_ROLE_MAP.get(value, value)


def actor_role(interaction: discord.Interaction) -> str | None:
    if str(interaction.user.id) == settings.discord_owner_user_id:
        return "owner"
    with SessionLocal() as db:
        row = db.scalar(
            select(PanelMember).where(
                PanelMember.discord_id == str(interaction.user.id),
                PanelMember.enabled == True,
            )
        )
        if row:
            return normalized_role(row.role)
    member = interaction.user
    if isinstance(member, discord.Member) and settings.discord_auth_staff_role_id:
        if any(str(role.id) == settings.discord_auth_staff_role_id for role in member.roles):
            return "admin"
    return None


def has_level(interaction: discord.Interaction, minimum: str) -> bool:
    role = actor_role(interaction)
    return bool(role and ROLE_ORDER.get(role, 0) >= ROLE_ORDER[minimum])


def can_assign(interaction: discord.Interaction, target_role: str) -> bool:
    current = actor_role(interaction)
    if current == "owner":
        return True
    if current == "admin":
        return target_role in {"developer", "auth_access"}
    return False


def owner_record(db):
    return db.scalar(select(Owner).order_by(Owner.created_at))


def role_label(role: str) -> str:
    return dict((value, name) for name, value in ROLE_CHOICES).get(normalized_role(role), role.title())


async def resolve_log_channel(guild: discord.Guild | None):
    if guild is None:
        return None
    if settings.discord_log_channel_id:
        channel = guild.get_channel(int(settings.discord_log_channel_id))
        if isinstance(channel, discord.TextChannel):
            return channel
    for name in ("vivet-logs", "auth-logs", "logs"):
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            return channel
    return None


async def log_action(
    interaction: discord.Interaction,
    title: str,
    description: str,
    *,
    target: discord.abc.User | None = None,
    color: int = 0x685F9C,
):
    channel = await resolve_log_channel(interaction.guild)
    if channel is None:
        print("[Vivet] No Discord log channel configured. Add DISCORD_LOG_CHANNEL_ID or create #vivet-logs.")
        return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Actioned by", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
    if target:
        embed.add_field(name="Member", value=f"{target.mention}\n`{target.id}`", inline=True)
    embed.add_field(name="Command", value=f"`/{interaction.command.qualified_name if interaction.command else 'unknown'}`", inline=True)
    embed.set_footer(text="Vivet Access & Licensing Logs")
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"[Vivet] Missing Send Messages/Embed Links permission in #{channel.name}.")


async def deny(interaction: discord.Interaction):
    await interaction.response.send_message(
        "You do not have permission to use this command.", ephemeral=True
    )


class AuthGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="auth", description="Manage Vivet dashboard access")

    @app_commands.command(name="add", description="Give a Discord member Vivet dashboard access")
    @app_commands.describe(user="Member to authorize", role="Permission level")
    @app_commands.choices(role=[app_commands.Choice(name=name, value=value) for name, value in ROLE_CHOICES])
    async def add(self, interaction: discord.Interaction, user: discord.Member, role: app_commands.Choice[str]):
        if not can_assign(interaction, role.value):
            return await deny(interaction)
        with SessionLocal() as db:
            owner = owner_record(db)
            if not owner:
                return await interaction.response.send_message("No Vivet owner account exists yet.", ephemeral=True)
            row = db.scalar(select(PanelMember).where(PanelMember.discord_id == str(user.id)))
            if row:
                row.discord_username, row.role, row.enabled = str(user), role.value, True
            else:
                row = PanelMember(
                    owner_id=owner.id,
                    discord_id=str(user.id),
                    discord_username=str(user),
                    role=role.value,
                )
                db.add(row)
            db.add(AuditLog(owner_id=owner.id, event="discord.auth.add", detail=f"{interaction.user} gave {user} {role.value}"))
            db.commit()
        embed = discord.Embed(title="Access granted", color=0x685F9C)
        embed.description = f"{user.mention} can now access Vivet as **{role.name}**."
        embed.add_field(name="Discord user", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Permission", value=role.name, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_action(interaction, "Dashboard access granted", f"Permission: **{role.name}**", target=user)

    @app_commands.command(name="remove", description="Remove Vivet dashboard access")
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        if not has_level(interaction, "admin"):
            return await deny(interaction)
        with SessionLocal() as db:
            row = db.scalar(select(PanelMember).where(PanelMember.discord_id == str(user.id)))
            if row:
                if normalized_role(row.role) == "owner" and actor_role(interaction) != "owner":
                    return await deny(interaction)
                row.enabled = False
                owner = owner_record(db)
                db.add(AuditLog(owner_id=owner.id if owner else None, event="discord.auth.remove", detail=f"{interaction.user} removed {user}"))
                db.commit()
        await interaction.response.send_message(f"Removed Vivet access from {user.mention}.", ephemeral=True)
        await log_action(interaction, "Dashboard access removed", "The member can no longer sign in with Discord.", target=user, color=0xD35B70)

    @app_commands.command(name="permissions", description="View a member's Vivet permission")
    async def permissions(self, interaction: discord.Interaction, user: discord.Member):
        if not has_level(interaction, "auth_access"):
            return await deny(interaction)
        with SessionLocal() as db:
            row = db.scalar(select(PanelMember).where(PanelMember.discord_id == str(user.id), PanelMember.enabled == True))
        value = role_label(row.role) if row else "No access"
        embed = discord.Embed(title="Vivet permissions", color=0x685F9C)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Member", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Access", value=f"**{value}**", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="List everyone authorized for Vivet")
    async def list_members(self, interaction: discord.Interaction):
        if not has_level(interaction, "auth_access"):
            return await deny(interaction)
        with SessionLocal() as db:
            rows = db.scalars(select(PanelMember).where(PanelMember.enabled == True).order_by(PanelMember.created_at)).all()
        embed = discord.Embed(title="Vivet access list", description="Authorized dashboard members", color=0x685F9C)
        grouped: dict[str, list[str]] = {value: [] for _, value in ROLE_CHOICES}
        for row in rows:
            role = normalized_role(row.role)
            grouped.setdefault(role, []).append(f"<@{row.discord_id}> (`{row.discord_id}`)")
        if settings.discord_owner_user_id and not any(row.discord_id == settings.discord_owner_user_id for row in rows):
            grouped["owner"].insert(0, f"<@{settings.discord_owner_user_id}> (`{settings.discord_owner_user_id}`)")
        for name, value in ROLE_CHOICES:
            members = grouped.get(value) or []
            embed.add_field(name=name, value="\n".join(members) if members else "*None*", inline=False)
        embed.set_footer(text=f"{sum(len(v) for v in grouped.values())} authorized account(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_action(interaction, "Access list viewed", f"{interaction.user.mention} viewed the authorized member list.")


async def app_autocomplete(interaction: discord.Interaction, current: str):
    with SessionLocal() as db:
        apps = db.scalars(select(Application).order_by(Application.name)).all()
    current = current.lower()
    return [
        app_commands.Choice(name=f"{app.name} • {app.version}", value=app.public_id)
        for app in apps
        if current in app.name.lower() or current in app.public_id.lower()
    ][:25]


def expiry_for(duration: str):
    now = datetime.now(timezone.utc)
    return {
        "day": now + timedelta(days=1),
        "week": now + timedelta(days=7),
        "month": now + timedelta(days=30),
        "lifetime": None,
    }[duration]


def make_key() -> str:
    return "VVT-" + "-".join(secrets.token_hex(2).upper() for _ in range(4))


class VivetBot(commands.Bot):
    async def setup_hook(self):
        self.tree.add_command(AuthGroup())
        if settings.discord_guild_id:
            guild = discord.Object(id=int(settings.discord_guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


intents = discord.Intents.default()
intents.members = True
bot = VivetBot(command_prefix="!", intents=intents)


@bot.tree.command(name="generate", description="Generate Vivet license keys")
@app_commands.describe(application="Application", duration="License duration", quantity="Number of keys", note="Optional note")
@app_commands.choices(duration=[app_commands.Choice(name=name, value=value) for name, value in DURATION_CHOICES])
@app_commands.autocomplete(application=app_autocomplete)
async def generate(
    interaction: discord.Interaction,
    application: str,
    duration: app_commands.Choice[str],
    quantity: app_commands.Range[int, 1, 25] = 1,
    note: str | None = None,
):
    if not has_level(interaction, "auth_access"):
        return await deny(interaction)
    with SessionLocal() as db:
        app_row = db.scalar(select(Application).where(Application.public_id == application))
        if not app_row:
            return await interaction.response.send_message("Application not found.", ephemeral=True)
        keys = [make_key() for _ in range(quantity)]
        expires = expiry_for(duration.value)
        for key in keys:
            db.add(License(application_id=app_row.id, key=key, expires_at=expires, note=(note or "").strip() or None))
        db.add(AuditLog(owner_id=app_row.owner_id, application_id=app_row.id, event="discord.license.generated", detail=f"{interaction.user} generated {quantity} {duration.value} key(s)"))
        db.commit()
        app_name = app_row.name
    embed = discord.Embed(title="License key generated" if quantity == 1 else "License keys generated", color=0x685F9C)
    embed.add_field(name="Application", value=app_name, inline=True)
    embed.add_field(name="Duration", value=duration.name, inline=True)
    embed.add_field(name="Generated by", value=interaction.user.mention, inline=True)
    embed.add_field(name="Key" if quantity == 1 else "Keys", value="\n".join(f"`{key}`" for key in keys), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_action(interaction, "License generated", f"**{quantity}× {duration.name}** for **{app_name}**")


@bot.tree.command(name="delete_key", description="Permanently delete a Vivet license key")
@app_commands.describe(key="License key to delete")
async def delete_key(interaction: discord.Interaction, key: str):
    if not has_level(interaction, "auth_access"):
        return await deny(interaction)
    clean = key.strip().upper()
    with SessionLocal() as db:
        license_row = db.scalar(select(License).where(License.key == clean))
        if not license_row:
            return await interaction.response.send_message("That license key does not exist.", ephemeral=True)
        app_row = db.get(Application, license_row.application_id)
        owner_id = app_row.owner_id if app_row else None
        app_name = app_row.name if app_row else "Unknown application"
        db.delete(license_row)
        db.add(AuditLog(owner_id=owner_id, application_id=app_row.id if app_row else None, event="discord.license.deleted", detail=f"{interaction.user} deleted {clean}"))
        db.commit()
    await interaction.response.send_message(f"Deleted `{clean}` from **{app_name}**.", ephemeral=True)
    await log_action(interaction, "License deleted", f"`{clean}` from **{app_name}**", color=0xD35B70)


@bot.tree.command(name="key_info", description="View information about a Vivet license key")
@app_commands.describe(key="License key")
async def key_info(interaction: discord.Interaction, key: str):
    if not has_level(interaction, "auth_access"):
        return await deny(interaction)
    clean = key.strip().upper()
    with SessionLocal() as db:
        row = db.scalar(select(License).where(License.key == clean))
        if not row:
            return await interaction.response.send_message("That license key does not exist.", ephemeral=True)
        app_row = db.get(Application, row.application_id)
        status = "Banned" if row.banned else "Active"
        expires = "Lifetime" if row.expires_at is None else discord.utils.format_dt(row.expires_at, style="R")
        embed = discord.Embed(title="License information", color=0x685F9C)
        embed.add_field(name="Key", value=f"`{row.key}`", inline=False)
        embed.add_field(name="Application", value=app_row.name if app_row else "Unknown", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Expires", value=expires, inline=True)
        embed.add_field(name="HWID", value=f"`{row.hwid}`" if row.hwid else "Not bound", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="reset_hwid", description="Reset the HWID attached to a license key")
@app_commands.describe(key="License key")
async def reset_hwid(interaction: discord.Interaction, key: str):
    if not has_level(interaction, "auth_access"):
        return await deny(interaction)
    clean = key.strip().upper()
    with SessionLocal() as db:
        row = db.scalar(select(License).where(License.key == clean))
        if not row:
            return await interaction.response.send_message("That license key does not exist.", ephemeral=True)
        row.hwid = None
        app_row = db.get(Application, row.application_id)
        db.add(AuditLog(owner_id=app_row.owner_id if app_row else None, application_id=row.application_id, event="discord.license.hwid_reset", detail=f"{interaction.user} reset {clean}"))
        db.commit()
    await interaction.response.send_message(f"Reset the HWID for `{clean}`.", ephemeral=True)
    await log_action(interaction, "HWID reset", f"`{clean}`")


@bot.tree.command(name="ban_key", description="Ban or unban a Vivet license key")
@app_commands.describe(key="License key", banned="True to ban, false to unban")
async def ban_key(interaction: discord.Interaction, key: str, banned: bool = True):
    if not has_level(interaction, "developer"):
        return await deny(interaction)
    clean = key.strip().upper()
    with SessionLocal() as db:
        row = db.scalar(select(License).where(License.key == clean))
        if not row:
            return await interaction.response.send_message("That license key does not exist.", ephemeral=True)
        row.banned = banned
        app_row = db.get(Application, row.application_id)
        db.add(AuditLog(owner_id=app_row.owner_id if app_row else None, application_id=row.application_id, event="discord.license.ban_changed", detail=f"{interaction.user} set {clean} banned={banned}"))
        db.commit()
    state = "banned" if banned else "unbanned"
    await interaction.response.send_message(f"`{clean}` has been **{state}**.", ephemeral=True)
    await log_action(interaction, f"License {state}", f"`{clean}`", color=0xD35B70 if banned else 0x52B788)


@bot.event
async def on_ready():
    print(f"Vivet Discord bot ready as {bot.user} ({bot.user.id})")
    if bot.guilds:
        for guild in bot.guilds:
            channel = await resolve_log_channel(guild)
            print(f"[Vivet] {guild.name}: log channel = #{channel.name}" if channel else f"[Vivet] {guild.name}: no log channel configured")


def main():
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing from .env")
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
