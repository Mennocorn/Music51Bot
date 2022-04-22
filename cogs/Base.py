
import discord
from discord.ext import commands
from discord import app_commands
import wavelink

import config


async def handle_skip(player):
    if not player.queue.is_empty:
        new = await player.queue.get_wait()
        await player.play(new)
    else:
        await player.stop()


async def get_player(guild, user) -> wavelink.Player:
    if not guild.voice_client:
        player: wavelink.Player = await user.voice.channel.connect(cls=wavelink.Player)
    else:
        player: wavelink.Player = guild.voice_client
    return player


def format_length(time: float):
    str_time: str = str(round(time/60, 2))
    return str_time.replace('.', ':')


def create_embed(bot, player: wavelink.Player, track):
    if track is not None:
        embed = discord.Embed(title=track.title, description=track.author, url=track.uri)
        embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(name='Length', value=format_length(track.duration), inline=True)
        embed.add_field(name='Loop', value=bot.cache.get_loop_string(str(player.guild.id)), inline=True)
        embed.add_field(name='State', value=':white_check_mark: Playing', inline=True)
        embed.set_footer(text=f'Volume: {player.volume}%')
        x = 1
        for item in player.queue:
            if x == 21:
                embed.add_field(name='\u200b', value=f'...{len(player.queue)-21} more tracks in queue', inline=False)
                break
            embed.add_field(name=x, value=f'{item.title} - {item.author}', inline=False)
            x += 1
        return embed
    else:
        return discord.Embed(title='Queue is empty')


def add_song_to_song_list(bot, guild: discord.Guild, song: wavelink.YouTubeTrack):
    if song.title not in bot.cache.cache['known_songs']:
        bot.cache.cache['known_songs'].append(song.title)


def get_time(arg):
    if ':' not in arg:
        raise discord.ext.commands.ConversionError
    skip = arg.split(':')
    try:
        skip[0] = int(skip[0])
        skip[1] = int(skip[1])
    except Exception as e:
        raise discord.ext.commands.ConversionError
    return skip[0], skip[1]


class AddSongModal(discord.ui.Modal, title='Add a song'):
    def __init__(self, bot, queue=None):
        self.bot = bot
        self.queue = queue
        super().__init__(timeout=None)
    song = discord.ui.TextInput(required=True,
                                label='Song title')

    async def on_submit(self, interaction: discord.Interaction):
        song = await wavelink.YouTubeTrack.search(self.song.value, return_first=True)
        if self.queue is None:
            add_song_to_song_list(self.bot, interaction.guild, song)
            try:
                player: wavelink.Player = await get_player(guild=interaction.guild, user=interaction.user)
                if player.track is not None:
                    player.queue.put(song)
                else:
                    await player.play(song)
                msg = self.bot.cache.cache[str(interaction.guild.id)]['message']
                await msg.edit(embed=create_embed(bot=self.bot, player=player, track=player.track or song))
                await interaction.response.send_message(f'Added {song.title} to queue.', ephemeral=True)
            except Exception as e:
                print(e)
                await interaction.response.send_message("No song could be found.", ephemeral=True)
        else:
            self.bot.custom_queues[str(interaction.guild_id)][self.queue].append(song.title)
            await interaction.response.send_message(f'Added {song.title} to {self.queue}')


class PlayerView(discord.ui.View):

    def __init__(self, client, guild):
        self.bot = client
        super().__init__(timeout=None)
        self.add_item(CustomQueueSelect(self.bot, guild, "play"))

    @discord.ui.button(label='Pause', style=discord.ButtonStyle.red)
    async def toggle_play_state(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        embed = interaction.message.embeds[0]
        if player is not None:
            if button.label == "Pause":
                if not player.is_paused():
                    await player.pause()
                else:
                    pass
                button.label = "Resume"
                button.style = discord.ButtonStyle.green
                embed.set_field_at(2, name='State', value=':clock1: Not Playing')
            else:
                if player.is_paused():
                    await player.resume()
                else:
                    pass
                button.label = "Pause"
                button.style = discord.ButtonStyle.red
                embed.set_field_at(2, name='State', value=':white_check_mark: Playing')

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Add Song', style=discord.ButtonStyle.blurple)
    async def add_song_to_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        return await interaction.response.send_modal(AddSongModal(self.bot))

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.blurple)
    async def skip_a_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if player is not None:
            if not player.queue.is_empty:
                track = await player.queue.get_wait()
                await player.play(track)
            else:
                track = None
                await player.stop()

            await interaction.response.edit_message(embed=create_embed(bot=self.bot, player=player, track=track))

    @discord.ui.button(label='Loop', style=discord.ButtonStyle.red)
    async def loop_current_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        embed = interaction.message.embeds[0]
        if player is not None:
            if self.bot.cache.cache[str(interaction.guild_id)]['loop']:
                self.bot.cache.cache[str(interaction.guild_id)]['loop'] = False
                button.style = discord.ButtonStyle.red
                embed.set_field_at(1, name='Loop', value=':x: Not Looping')
            else:
                self.bot.cache.cache[str(interaction.guild_id)]['loop'] = True
                button.style = discord.ButtonStyle.green
                embed.set_field_at(1, name='Loop', value=':white_check_mark: Looping')

        await interaction.response.edit_message(view=self, embed=embed)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.red)
    async def stop_bot_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if player is not None:
            await player.stop()
            await player.disconnect()
            player.queue.clear()
        await interaction.message.delete()

    @discord.ui.select(placeholder='Select Volume', options=[discord.SelectOption(label=f'{item}%') for item in ([item for item in range(10, 110, 10)] + [number for number in range(200, 1100, 100)])])
    async def volume_select(self, interaction: discord.Interaction, select):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if player is not None:
            percentage = select.values[0].split('%')[0]
            await player.set_volume(int(percentage))
        await interaction.response.edit_message(embed=create_embed(self.bot, player, player.track))



class CustomQueueSelect(discord.ui.Select):
    def __init__(self, bot, guild, reason):
        options = []
        self.bot = bot
        self.reason = reason
        if len(bot.custom_queues.cache[str(guild.id)].keys()) > 0:
            for queue in list(bot.custom_queues.cache[str(guild.id)].keys()):
                options.append(discord.SelectOption(label=queue))
            super().__init__(options=options, placeholder="Select a custom Queue")
        else:
            super().__init__(disabled=True, placeholder='You have not yet set custom queues', options=[discord.SelectOption(label='None')])

    async def callback(self, interaction: discord.Interaction):

        if self.reason == "play":
            try:
                if interaction.guild.voice_client is None:
                    player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                    just_connected = True
                else:

                    player: wavelink.Player = interaction.guild.voice_client
                    just_connected = False
                song_list = []
                for song in self.bot.custom_queues.cache[str(interaction.guild.id)][self.values[0]]:
                    song_list.append(await wavelink.YouTubeTrack.search(song, return_first=True))
                player.queue.extend(song_list)
                if just_connected:
                    await player.play(await player.queue.get_wait())
                    await interaction.response.send_message(content=None, embed=create_embed(self.bot, player, track=player.track or player.queue[0]),
                                                            view=PlayerView(client=self.bot, guild=interaction.guild))
                    msg = await interaction.original_message()
                    self.bot.cache.cache[str(interaction.guild_id)]['loop'] = False
                    self.bot.cache.cache[str(interaction.guild.id)]['message'] = msg
                    return
                else:
                    if not player.is_playing():
                        await player.play(await player.queue.get_wait())
                    msg = self.bot.cache.cache[str(interaction.guild.id)]['message']
                    embed = create_embed(self.bot, player, track=player.track)
                    await msg.edit(embed=embed)
                return await interaction.response.send_message(f"Added {self.values[0]} to queue", ephemeral=True)
            except KeyError:
                return await interaction.response.send_message(f"Queue could not be found", ephemeral=True)
        else:
            await interaction.response.send_modal(AddSongModal( bot=self.bot, queue=self.values[0],))



class MusicalBase(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()

        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=2333,
                                            password='12345')

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node):
        print(f'Node: {node.identifier} is ready')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is None:
            return

        if member == self.bot.user and after.channel is None:
            player: wavelink.Player = await get_player(member.guild, member)
            if player is not None:
                await player.stop()
                await player.disconnect()
                player.queue.clear()

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.YouTubeTrack, reason):
        if not reason == 'REPLACED':
            if self.bot.cache.cache[str(player.guild.id)]['loop']:
                return await player.play(track)
            if not player.queue.is_empty:
                new = await player.queue.get_wait()
                await player.play(new)
            else:
                new = None
                await player.stop()
            msg = self.bot.cache.cache[str(player.guild.id)]['message']
            await msg.edit(embed=create_embed(bot=self.bot, player=player, track=new))

    async def search_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        songs = [app_commands.Choice(name=song, value=song) for song in self.bot.cache.cache['known_songs'] if current.lower() in song.lower()]
        if len(songs) >= 25:
            return songs[:25]
        return songs

    @app_commands.command(name='play', description='Starts a music session in your current voice chat.')
    @app_commands.autocomplete(search=search_autocomplete)
    async def _play(self, interaction: discord.Interaction, search: str):
        search = await wavelink.YouTubeTrack.search(search, return_first=True)
        add_song_to_song_list(self.bot, interaction.guild, search)
        if interaction.user.voice.channel is None:
            return interaction.response.send_message(content='You are not in a voice channel', ephemeral=True)

        if not interaction.guild.voice_client:
            player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
        else:
            player: wavelink.Player = interaction.guild.voice_client
            if not player.is_playing():
                await player.play(search)
                msg = self.bot.cache.cache[str(interaction.guild.id)]['message']
                await msg.edit(embed=create_embed(self.bot, player, player.track or search))
                return await interaction.response.send_message(f"Resumed Playback with {search.title}", ephemeral=True)
        if not player.is_playing():
            await player.play(search)
            await interaction.response.send_message(content=None,
                                                    embed=create_embed(bot=self.bot, player=player, track=player.track or search),
                                                    view=PlayerView(client=self.bot, guild=interaction.guild))
            msg = await interaction.original_message()
            self.bot.cache.cache[str(interaction.guild_id)]['loop'] = False
            self.bot.cache.cache[str(interaction.guild.id)]['message'] = msg
            print(self.bot.cache.cache[str(interaction.guild.id)])
            return
        else:
            msg = self.bot.cache.cache[str(interaction.guild.id)]['message']
            if player.track is not None:
                player.queue.put(search)
            else:
                await player.play(search)
            await msg.edit(embed=create_embed(self.bot, player, track=player.track or search))
            return await interaction.response.send_message(f"Added {search.title} to queue", ephemeral=True)

    @app_commands.command()
    async def self_sync(self, interaction):
        await self.bot.tree.sync()
        return await interaction.response.send_message(':white_check_mark:')

    @app_commands.command(name="skip_to", description="Skip to a defined position in the song, use a MINUTE:SECOND format.")
    async def _skip_to(self, interaction, place: str):
        place = get_time(place)
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if not player.is_connected() or not player.is_playing():
            return interaction.response.send_message('You are not in a voice channel or the bot is not playing a song.')
        await player.seek((int(place[0]) * 60 * 1000) + (int(place[1]) * 1000))
        await interaction.response.send_message(f'Skipped to {place[0]}:{place[1]}', ephemeral=True)

    @app_commands.command(name='forward', description='Skip forwards 10 seconds by default or a custom amount of seconds')
    async def _forward(self, interaction, time: int = 10):
        player: wavelink.Player = interaction.guild.voice_client
        if not player.is_connected() or not player.is_playing():
            return interaction.response.send_message('You are not in a voice channel or the bot is not playing a song.')
        if time > (player.track.duration - player.position):
            return interaction.response.send_message('You cant skip this far.')
        await player.seek(int(player.position + time))
        await interaction.response.send_message(f'Skipped {time} seconds', ephemeral=True)

    @app_commands.command(name='volume', description='Set the players\' Volume.')
    async def _volume(self, interaction, volume: int):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if not player.is_connected():
            return interaction.response.send_message('You are not in a voice channel.')
        await player.set_volume(volume * 10)
        await interaction.response.send_message(f'Set volume to {volume}%.', ephemeral=True)

    @app_commands.command(name='position', description='Get the current song position.')
    async def _position(self, interaction):
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        if player is not None:
            time = format_length(player.position)
            return await interaction.response.send_message(f'The current position is {time}')

    @app_commands.command(name='queue', description='Retrieve the current active queue')
    async def _queue(self, interaction: discord.Interaction):
        pass  # TODO add a queue retrieval

    @app_commands.command(name='custom_queue', description='Make a custom saved queue of the current player queue.')
    async def _custom_queue_maker(self, interaction: discord.Interaction, name: str):
        queue = []
        player: wavelink.Player = await get_player(interaction.guild, interaction.user)
        for song in player.queue:
            queue.append(song.title)
        self.bot.custom_queues.cache[str(interaction.guild.id)][name] = queue

    @app_commands.command(name='play_queue', description='Play a saved custom queue.')
    async def _play_queue(self, interaction):
        view = discord.ui.View(timeout=None)
        view.add_item(CustomQueueSelect(self.bot, interaction.guild, "play"))
        print(view.children)
        return await interaction.response.send_message(content='Select a queue to add to the current queue', view=view, ephemeral=True)

   # @app_commands.command(name='manage_queues'
    @app_commands.command()
    async def save(self, interaction):
        self.bot.cache.save()
        self.bot.custom_queues.save()
        print('reached')
        await self.bot.tree.sync()
        print('second reach')
        await interaction.response.send_message('Saved', ephemeral=True)

class ManageQueue(app_commands.Group):

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name='add', description='Add a song to a custom Queue')
    @app_commands.describe(song='The song you want to add to the queue')
    async def add_song_to_queue(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=None)
        view.add_item(CustomQueueSelect(self.bot, interaction.guild, "add"))
        return await interaction.response.send_message(content='Select a queue to add to the current queue', view=view, ephemeral=True)
async def setup(bot):
    await bot.add_cog(MusicalBase(bot), guilds=config.guilds)
    bot.tree.add_command(ManageQueue(bot))