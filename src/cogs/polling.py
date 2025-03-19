import discord
from discord.ext import commands

class Polling(commands.Cog): # create a class for our cog that inherits from commands.Cog
    # this class is used to create a cog, which is a module that can be added to the bot

    def __init__(self, bot): # this is a special method that is called when the cog is loaded
        self.bot = bot

    @commands.command() # creates a prefixed command
    async def hello(self, ctx): # all methods now must have both self and ctx parameters
        await ctx.send('Hello!')

    @commands.slash_command(name="poll_create", description="Create a poll")
    async def poll_create(self, ctx, question: str, options: str):
        options_list = [opt.strip() for opt in options.split(",")]
        if len(options_list) < 2:
            await ctx.respond("You need at least 2 options!", ephemeral=True)
            return
        poll_id = str(ctx.channel.id)
        redis_client.hset(f"poll:{poll_id}", mapping={opt: 0 for opt in options_list})
        redis_client.expire(f"poll:{poll_id}", 3600)



    @discord.slash_command() # we can also add application commands
    async def goodbye(self, ctx):
        await ctx.respond('Goodbye!')

    @discord.user_command()
    async def greet(self, ctx, member: discord.Member):
        await ctx.respond(f'{ctx.author.mention} says hello to {member.mention}!')

    math = discord.SlashCommandGroup("math", "Spooky math stuff") # create a Slash Command Group called "math"
    advanced_math = math.create_subgroup(
        "advanced",
        "super hard math commands!"
    )

    @math.command()
    async def add(self, a: int, b: int):
        c = a + b
        await ctx.respond(f"{a} + {b} is {c}.")
    
    @advanced_math.command()
    async def midpoint(self, x1: float, y1: float, x2: float, y2: float):
        mid_x = (x1 + x2)/2
        mid_y = (y1 + y2)/2
        await ctx.respond(f"The midpoint between those coordinates is ({mid_x}, {mid_y}).")

    @commands.Cog.listener() # we can add event listeners to our cog
    async def on_member_join(self, member): # this is called when a member joins the server
    # you must enable the proper intents
    # to access this event.
    # See the Popular-Topics/Intents page for more info
        await member.send('Welcome to the server!')

def setup(bot): # this is called by Pycord to setup the cog
    bot.add_cog(Greetings(bot)) # add the cog to the bot
