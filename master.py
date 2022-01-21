import os
import logging
import discord
from discord.commands import Option

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger('discord').setLevel(level=logging.WARNING)
logger = logging.getLogger(__name__)

bot = discord.Bot()
@bot.slash_command(guild_ids=[692113197205028984])  # create a slash command for the supplied guilds
async def post(ctx, thread_number: int, post_text: str):
    """Отправить пост в тред"""  # the command description can be supplied as the docstring
    interaction = await ctx.respond(f"thread {thread_number}: {post_text}")
    await interaction.delete_original_message()
    # Please note that you MUST respond with ctx.respond(), ctx.defer(), or any other
    # interaction response within 3 seconds in your slash command code, otherwise the
    # interaction will fail.

@bot.slash_command(guild_ids=[692113197205028984])
async def oppos(
    ctx,
    name: Option(str, "Enter your name"),
    gender: Option(str, "Choose your gender", choices=["Male", "Female", "Other"]),
    age: Option(int, "Enter your age", required=False, default=18),
):
    await ctx.respond(f"Hello {name}")


@bot.slash_command(name="hi")  # Not passing in guild_ids creates a global slash command (might take an hour to register)
async def global_command(ctx, num: int):  # Takes one integer parameter
    await ctx.respond(f"This is a global command, {num}!")

@bot.event
async def on_ready():
    logging.info(f"Discord Bot is ready!")

bot.run(os.getenv("DISCORD_TOKEN"))
