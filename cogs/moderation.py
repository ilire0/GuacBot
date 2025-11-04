import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

@app_commands.command(name="purge", description="Delete a number of messages from a channel")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete", channel="Channel to purge (defaults to current)")
async def purge(interaction: discord.Interaction, amount: int, channel: Optional[discord.TextChannel] = None):
    if amount < 1:
        return await interaction.response.send_message("Amount must be at least 1.", ephemeral=True)
    target = channel or interaction.channel
    try:
        deleted = await target.purge(limit=amount)
        await interaction.response.send_message(f"Deleted {len(deleted)} messages from {target.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to purge messages: {e}", ephemeral=True)

@app_commands.command(name="grant_role", description="Grant a role to a member")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(member="Member to grant the role to", role="Role to grant")
async def grant_role(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await member.add_roles(role, reason=f"Granted by {interaction.user}")
        await interaction.response.send_message(f"Granted {role.mention} to {member.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to grant role: {e}", ephemeral=True)

@app_commands.command(name="revoke_role", description="Revoke a role from a member")
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(member="Member to revoke the role from", role="Role to revoke")
async def revoke_role(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await member.remove_roles(role, reason=f"Revoked by {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to remove role: {e}", ephemeral=True)

@app_commands.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(member="Member to ban", reason="Reason for ban", delete_days="Days of messages to delete (0-7)")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None, delete_days: int = 0):
    if delete_days < 0 or delete_days > 7:
        return await interaction.response.send_message("delete_days must be between 0 and 7.", ephemeral=True)
    try:
        await interaction.guild.ban(member, reason=reason or f"Banned by {interaction.user}", delete_message_days=delete_days)
        await interaction.response.send_message(f"Banned {member.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to ban member: {e}", ephemeral=True)

@app_commands.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
    try:
        await interaction.guild.kick(member, reason=reason or f"Kicked by {interaction.user}")
        await interaction.response.send_message(f"Kicked {member.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to kick member: {e}", ephemeral=True)

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = ModerationCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(purge)
    bot.tree.add_command(grant_role)
    bot.tree.add_command(revoke_role)
    bot.tree.add_command(ban)
    bot.tree.add_command(kick)