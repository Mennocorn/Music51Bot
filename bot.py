import asyncio
import traceback
from Cache.Cache import Cache
import atexit
import signal
import sys

import discord
from discord.ext import commands

import config

intents = discord.Intents.default()
intents.members = True

initial_extensions = (
    f"cogs.{'Base'}",

)


class MusicCache(Cache):
    def get_loop_string(self, guild_id: str) -> str:
        if self.cache[guild_id]['loop']:
            return ":white_check_mark: Looping"
        else:
            return ":x: Not Looping"

    def save(self):
        keys = list(bot.cache.cache.keys())
        for i in range(2, len(keys) - 1):
            self.cache[keys[i]]['message'] = None
        await super().save()

    async def get_message(self, guild: discord.Guild):
        channel = guild.get_channel(self._cache[str(guild.id)]['message_id'][1])
        msg = await channel.fetch_message(self._cache[str(guild.id)]['message_id'][0])
        return msg


class DJ(commands.Bot):

    def __init__(self):
        self.cache = MusicCache("./data.json")
        self.cache.load()
        self.custom_queues = Cache("./queues.json")
        self.custom_queues.load()
        super().__init__(command_prefix='!', intents=intents, case_insensitive=True, application_id=config.app_id)
        self.files_cleaned = False

    async def setup_hook(self) -> None:
        print('setup hook')
        for extension in initial_extensions:
            print(extension)
            try:
                await self.load_extension(extension)
            except Exception as exc:
                print(f"Failed to load {extension}, with {exc}")
                traceback.print_exc()
        await self.tree.sync(guild=config.guilds[0])
        self.loop.create_task(self.cache.automatic_save())

    async def on_ready(self) -> None:
        print("We have gone online")
        if not self.files_cleaned:
            for guild in self.guilds:
                if str(guild.id) not in list(self.cache.cache.keys()):
                    self.cache.cache[str(guild.id)] = {
                        "loop": False,
                        "message_id": 0,
                        "known_songs": [],
                    }
                if str(guild.id) not in self.custom_queues.cache.keys():
                    self.custom_queues.cache[str(guild.id)] = {}
            await self.cache.save()

    async def on_guild_join(self, guild):
        if str(guild.id) not in list(self.cache.cache.keys()):
            self.cache.cache[str(guild.id)] = {
                "loop": False,
                "message": None,
            }
            if str(guild.id) not in self.custom_queues.cache.keys():
                self.custom_queues.cache[str(guild.id)] = {}

    def run(self) -> None:
        try:
            super().run(token=config.token, reconnect=True)
        except Exception as e:
            print(f'Failed to start bot with {e}')
            traceback.print_exc()

    async def close(self) -> None:
        try:
            await super().close()
        except:
            pass


bot = DJ()


# this is called when the program is terminated
@atexit.register
def exited():
    # run the async exit_function
    bot.custom_queues.save()
    bot.cache.save()


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    # sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
bot.run()
