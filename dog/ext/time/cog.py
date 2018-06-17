import datetime
import logging

import discord
import pycountry
import pytz
from discord.ext import commands
from discord.ext.commands import BucketType, cooldown
from lifesaver.bot import Cog, Context, command, group
from lifesaver.bot.storage import AsyncJSONStorage

from .converters import hour_minute
from .map import Map

log = logging.getLogger(__name__)


def timezone_is_concrete(timezone: str) -> bool:
    tz = pytz.timezone(timezone)
    return isinstance(tz, pytz.tzinfo.StaticTzInfo)


TWELVEHOUR_COUNTRIES = ['US', 'AU', 'CA', 'PH']


class Time(Cog):
    def __init__(self, bot):
        super().__init__(bot)
        self.timezones = AsyncJSONStorage('timezones.json', loop=bot.loop)

    def get_time_for(self, user: discord.User):
        timezone = self.timezones.get(user.id)
        if not timezone:
            return None
        their_time = datetime.datetime.now(pytz.timezone(timezone))
        time_format = '%H:%M:%S' if their_time.hour < 12 else '%H:%M:%S (%I:%M:%S %p)'
        return their_time.strftime('%B %d, %Y  ' + time_format)

    @command(aliases=['st'])
    async def sleepytime(self, ctx: Context, *, awaken_time: hour_minute):
        """Calculates the time you should go to sleep at night."""

        cycle_length = datetime.timedelta(seconds=90 * 60)

        most_late = awaken_time - datetime.timedelta(seconds=270 * 60)
        second_time = most_late - cycle_length
        third_time = second_time - cycle_length
        fourth_time = third_time - cycle_length

        times = [fourth_time, third_time, second_time, most_late]
        time_format = '%I:%M %p'
        formatted = [f'**{time.strftime(time_format)}**' for time in times]
        await ctx.send(
            f'To wake up at {awaken_time.strftime(time_format)} feeling great, '
            f'try falling sleep at these times: {", ".join(formatted)}'
        )

    @group(invoke_without_command=True, aliases=['t'])
    async def time(self, ctx: Context, *, who: discord.Member = None):
        """Views the time for another user."""
        who = who or ctx.author

        if self.bot.is_blacklisted(who):
            await ctx.send(f"{who} can't use this bot.")
            return

        formatted_time = self.get_time_for(who)
        if not formatted_time:
            await ctx.send(
                f"You haven't set your timezone yet. Send `{ctx.prefix}time set` to do so in a DM."
                if who == ctx.author else
                (f'{who.display_name} has not set their timezone. They can set their timezone with '
                 f'`{ctx.prefix}time set`.')
            )
            return

        await ctx.send(f'{who.display_name}: {formatted_time}')

    @time.command(typing=True)
    @cooldown(1, 5, BucketType.guild)
    async def map(self, ctx: Context):
        """Views a timezone map."""

        twelve_hour = False
        try:
            invoker_timezone = self.timezones.get(ctx.author.id)
            country = next(
                country for (country, timezones) in pytz.country_timezones.items() if invoker_timezone in timezones
            )
            twelve_hour = country in TWELVEHOUR_COUNTRIES
        except StopIteration:
            pass

        map = Map(session=self.bot.session, twelve_hour=twelve_hour, loop=self.bot.loop)

        for member in ctx.guild.members:
            tz = self.timezones.get(member.id)
            if not tz:
                continue
            map.add_member(member, tz)

        await map.draw()
        buffer = await map.render()

        file = discord.File(fp=buffer, filename=f'map_{ctx.guild.id}.png')
        await ctx.send(file=file)

        map.close()

    @time.command(name='reset')
    async def time_reset(self, ctx: Context):
        """Resets your timezone."""
        if await ctx.confirm(title='Are you sure?', message='Your timezone will be removed.'):
            try:
                await self.timezones.delete(ctx.author.id)
            except KeyError:
                pass
            await ctx.send('Done.')
        else:
            await ctx.send('Okay, cancelled.')

    @time.command(name='set')
    async def time_set(self, ctx: Context, *, timezone: commands.clean_content = None):
        """Sets your current timezone."""
        target = ctx.author

        if timezone is not None:
            if any(c in timezone for c in ['`', ' ']) or len(timezone) > 80:
                await ctx.send("That's not a timezone.")
                return
            try:
                pytz.timezone(timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                await ctx.send(
                    f'Unknown timezone. Not sure what the timezone codes are? Use `{ctx.prefix}t set` to set your '
                    'timezone interactively through a direct message, or look here: '
                    '<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>'
                )
                return
            if timezone_is_concrete(timezone):
                await ctx.send(
                    "Error! I won't use that timezone because it uses a constant hour offset, "
                    "which almost always results in an invalid time being reported. Please use a "
                    f"more specific timezone. (Run `{ctx.prefix}time set` to set your timezone through a DM.)"
                )
                return
            await self.timezones.put(target.id, timezone)
            await ctx.ok()
            return

        # TODO: refactor, improve, and build upon ask and prompt into a generic interface. should be usable by others.
        #       it's currently too trashy and narrow the way it stands.
        ask_aborted = object()  # sentinel that indicates abort

        async def ask(prompt, *, determiner, on_fail="Invalid response. Please try again."):
            embed = discord.Embed(color=discord.Color.green(), title='Timezone wizard', description=prompt)
            await target.send(embed=embed)
            while True:
                message = await self.bot.wait_for('message', check=lambda m: not m.guild and m.author == target)
                if message.content == 'cancel':
                    return ask_aborted
                try:
                    value = determiner(message.content)
                    if not value:
                        continue
                    else:
                        return value
                except:
                    await target.send(on_fail)
                    continue

        async def prompt(message):
            embed = discord.Embed(color=discord.Color.gold(), title='Confirmation', description=message)
            confirmation: discord.Message = await target.send(embed=embed)
            emoji = ['\N{WHITE HEAVY CHECK MARK}', '\N{NO ENTRY SIGN}']
            for e in emoji:
                await confirmation.add_reaction(e)

            while True:
                def _check(_r, u):
                    return u == target

                reaction, user = await self.bot.wait_for('reaction_add', check=_check)
                if reaction.emoji in emoji:
                    return reaction.emoji == emoji[0]

        try:
            embed = discord.Embed(
                title='Timezone wizard',
                description="Hello! I'll be helping you pick your timezone. By setting your timezone, other people "
                            "will be able to see what time it is for you, and other cool stuff."
            )
            await target.send(embed=embed)
        except discord.HTTPException:
            await ctx.send("I can't DM or interact with you.")
            return

        await ctx.send(f'{target.display_name}: Check your DMs.')

        log.debug('%d: Timezone wizard started.', target.id)

        while True:
            country = await ask(
                'Please send me the name of the country you live in.\n\n'
                'Something like "USA", "United States", or even the two-letter country code like "US".\n'
                "Send 'cancel' to abort.",
                determiner=pycountry.countries.lookup,
                on_fail="Sorry, that didn't seem like a country to me. Please try again, or send 'cancel' to abort."
            )
            if country is ask_aborted:
                await target.send('Operation cancelled. Sorry about that!')
                return

            log.debug('%d: Provided country: %s', target.id, country)

            name = getattr(country, 'official_name', country.name)

            if await prompt(f'Do you live in **{name}**?\n'
                            'Click \N{WHITE HEAVY CHECK MARK} to continue.'):
                break

        code = country.alpha_2
        log.debug('%d: Lives in %s (%s)', target.id, code, country)

        try:
            timezones = pytz.country_timezones[code]
        except KeyError:
            await ctx.send(f"Sorry, but I couldn't find any designated timezones for **{name}**.")
            log.warning('%d: Failed to find any timezones for %s (%s)', target.id, code, country)
            return

        embed = discord.Embed(
            title='Timezone wizard',
            description='Which timezone are you living in?\n\n',
            color=discord.Color.green()
        )
        for timezone in timezones:
            pytz_timezone = pytz.timezone(timezone)
            now_in_timezone: datetime.datetime = datetime.datetime.now(pytz_timezone)
            time_now = now_in_timezone.strftime('%H:%M  (%I:%M %p)')
            embed.description += f'\N{BULLET} {timezone}  {time_now}\n'
        embed.description += '\nPlease send the timezone code.'
        if len(embed.description) > 2048:
            await target.send(
                "Hmm. Looks like there's so many timezones in that region, I can't display them all. "
                "Sorry about that."
            )
            return
        await target.send(embed=embed)

        while True:
            response = await self.bot.wait_for('message', check=lambda m: not m.guild and m.author == target)
            if response.content == 'cancel':
                await target.send('Aborted. Sorry.')
                return
            if response.content not in timezones:
                await target.send("That's not a timezone code that was listed above. Send 'cancel' to abort.")
            else:
                user_timezone = response.content
                break

        log.debug('%d: Timezone is: %s', target.id, user_timezone)
        await self.timezones.put(target.id, user_timezone)
        embed = discord.Embed(title='Timezone set', color=discord.Color.magenta(),
                              description=f'Your timezone is now {user_timezone}.')
        await target.send(embed=embed)
