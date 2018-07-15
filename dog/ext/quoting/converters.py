import re
from collections import namedtuple

import discord
from discord.ext import commands
from lifesaver.utils import clean_mentions

from dog.ext.quoting.command import QuoteNotFound

MESSAGE_SPECIFIER_RE = re.compile(r"(\d+)?(?:[:+](-?\d+))?")


class Specifier(namedtuple('Specifier', ['id', 'range'])):
    range_limit = 50

    @classmethod
    def from_string(cls, specifier):
        match = MESSAGE_SPECIFIER_RE.match(specifier)

        (message_id, m_range) = match.groups()

        if not message_id and not m_range:
            return None

        def convert(string):
            return None if string is None else int(string)

        return cls(
            id=convert(message_id),
            range=convert(m_range),
        )

    @property
    def relative(self):
        return self.id is None and self.range

    @property
    def over_limit(self):
        return self.range < -self.range_limit or self.range > self.range_limit


class QuoteName(commands.Converter):
    def __init__(
        self, *,
        require_existance: bool = False,
        require_nonexistance: bool = False,
        force_consume: bool = False
    ):
        super().__init__()
        self.require_existance = require_existance
        self.require_nonexistance = require_nonexistance
        self.force_consume = force_consume

    async def convert(self, ctx, argument):
        cog = ctx.command.instance

        quotes = cog.quotes(ctx.guild)

        # scrub any mentions
        argument = clean_mentions(ctx.channel, argument)

        if argument not in quotes:
            if self.require_existance:
                raise commands.BadArgument(f'Quote "{argument}" does not exist.')

            if self.force_consume:
                # this special exception is used to signal to the converter
                # to reset the view position and use the next word for the name,
                # instead of the entire view.
                raise QuoteNotFound(argument)

        if argument in quotes and self.require_nonexistance:
            raise commands.BadArgument(f'Quote "{argument}" already exists.')

        if len(argument) > 60:
            raise commands.BadArgument('Too long. Maximum of 60 characters.')

        return argument


class Messages(commands.Converter):
    """A converter that is able to resolve a message or range of messages."""

    async def convert(self, ctx, argument):
        spec = Specifier.from_string(argument)

        if not spec:
            raise commands.BadArgument(
                f'Invalid message ID. See `{ctx.prefix}help quote`.'
            )

        if spec.range:
            if spec.over_limit:
                raise commands.BadArgument(
                    f'Ranges can only target up to {Specifier.range_limit} messages.'
                )

            if not spec.relative and spec.range < 1:
                raise commands.BadArgument('Range should be greater than 1.')
            elif spec.relative and spec.range > -1:
                raise commands.BadArgument('Range should be less than -1.')

        try:
            if spec.relative:
                # relative to the sent message instead of a message id, get the
                # last n messages. have to get +1 because history will get the
                # command message too.
                history = await ctx.history(limit=abs(spec.range) + 1).flatten()
                rev = reversed(history[1:])
                return list(rev)

            message = await ctx.get_message(spec.id)

            if spec.range:
                # relative to the specified message id, get the message and
                # n messages after
                after_messages = await ctx.history(
                    after=discord.Object(id=spec.id),
                    limit=spec.range,
                ).flatten()
                return [message] + after_messages

            return message
        except discord.NotFound as error:
            raise commands.BadArgument(f'Not found: {error}')
        except discord.HTTPException as error:
            raise commands.BadArgument(f'Failed to get message(s): {error}')
