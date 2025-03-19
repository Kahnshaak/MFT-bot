from discord.ext import commands

class Admin(commands.Cog):
    """Admin-only commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(administrator=True)
    async def shutdown(self, ctx):
        """Just an example"""
        await ctx.send("Shutting down... ")
        await self.bot.close()

def setup(bot):
    bot.add_cog(Admin(bot))
