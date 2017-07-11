import logging

import asyncio

import discord
import functools
from PIL import Image, ImageEnhance, ImageDraw, ImageFont
from discord.ext import commands
from io import BytesIO

from dog import Cog
from dog.core import converters, utils
from dog.core.utils import get_bytesio
from wand import image as wndimg

logger = logging.getLogger(__name__)


async def download_image(session, url):
    bio = await get_bytesio(session, url)
    im = Image.open(bio).convert('RGBA')
    bio.close()
    return im


class Meme:
    def __init__(self, source, ctx, *, text_size=32):
        self.ctx = ctx
        self.image_cache = {}
        self.source = Image.open(source)
        self.draw = ImageDraw.Draw(self.source)
        self.font = ImageFont.truetype('resources/font/SourceSansPro-Regular.ttf', text_size)

    async def cache(self, url, size=None, ):
        if url in self.image_cache:
            return

        self.image_cache[url] = await download_image(self.ctx.bot.session, url)
        if size:
            self.image_cache[url] = self.image_cache[url].resize(size, Image.BICUBIC)

    def paste(self, src, coords):
        if isinstance(src, str):
            self.source.paste(self.image_cache[src], coords)
        else:
            self.source.paste(src, coords)

    def text(self, text, x, y, width):
        utils.draw_word_wrap(self.draw, self.font, text, x, y, width)

    async def render(self, filename='image.png'):
        with BytesIO() as bio:
            # export the image
            coro = self.ctx.bot.loop.run_in_executor(None, functools.partial(self.source.save, bio, format='png'))
            await asyncio.wait([coro], loop=self.ctx.bot.loop, timeout=5)

            # upload
            bio.seek(0)
            await self.ctx.send(file=discord.File(bio, filename))

    def cleanup(self):
        for url, im in self.image_cache.items():
            logger.debug('Cleaning up after cached image %s...', url)
            im.close()
        del self.draw
        self.source.close()


class Memes(Cog):
    async def __error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            logger.exception('Memes image processing error!')
            await ctx.send('Something went wrong processing your image. Sorry about that!')
            error.should_suppress = True
        elif isinstance(error, asyncio.TimeoutError):
            await ctx.send('Your image took too long to process, so I dropped it.')
            error.should_suppress = True

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def jpeg(self, ctx, image_source: converters.ImageSourceConverter):
        """
        Drastically lowers an image's quality.

        This command takes an image, and saves it as a JPEG with the quality of 1.
        """
        im_data = await get_bytesio(self.bot.session, image_source)

        def open():
            return Image.open(im_data).convert('RGB')
        im = await ctx.bot.loop.run_in_executor(None, open)

        with BytesIO() as output:
            await ctx.bot.loop.run_in_executor(None, functools.partial(im.save, output, format='jpeg', quality=1))
            output.seek(0)
            await ctx.send(file=discord.File(output, filename='jpeg.jpg'))

        im.close()
        im_data.close()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def mistake(self, ctx, image_source: converters.ImageSourceConverter):
        """
        For really big mistakes.
        """
        async with ctx.typing():
            m = Meme('resources/mistake.png', ctx)
            m.paste(image_source, (239, 241))
            await m.render('mistake.png')
            m.cleanup()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def trustnobody(self, ctx, image_source: converters.ImageSourceConverter):
        """ Trust nobody, not even yourself. """
        async with ctx.typing():
            m = Meme('resources/trust_nobody.png', ctx)

            im = (await download_image(ctx.bot.session, image_source)).resize((100, 100), Image.BICUBIC)
            m.paste(im, (82, 230))
            im = im.crop((0, 0, 62, 100))
            m.paste(im, (420, 250))
            im.close()

            await m.render('trust_nobody.png')
            m.cleanup()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def youvs(self, ctx, a: converters.ImageSourceConverter, b: converters.ImageSourceConverter):
        """ You vs. the guy she tells you not to worry about """
        async with ctx.typing():
            m = Meme('resources/you_vs.png', ctx)
            await m.cache(a, (330, 375))
            await m.cache(b, (327, 377))
            m.paste(a, (22, 162))
            m.paste(b, (365, 161))
            await m.render('youvs.png')
            m.cleanup()

    @commands.command(aliases=['handicap'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def handicapped(self, ctx, image_source: converters.ImageSourceConverter, *, text: commands.clean_content):
        """ Sir, this spot is for the handicapped only!.. """
        async with ctx.typing():
            m = Meme('resources/handicap.png', ctx, text_size=24)

            await m.cache(image_source, (80, 80))

            m.text(text, 270, 310, 270)
            m.paste(image_source, (373, 151))
            m.paste(image_source, (302, 408))
            m.paste(image_source, (357, 690))

            await m.render('handicapped.png')

            m.cleanup()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def floor(self, ctx, image_source: converters.ImageSourceConverter, *, text: commands.clean_content):
        """
        The floor is...

        Generates a "the floor is" type meme. The image source is composited
        on top of the jumper's face. The remaining text is used to render a caption.
        """

        async with ctx.typing():
            m = Meme('resources/floor.png', ctx, text_size=48)

            await m.cache(image_source, (100, 100))

            m.text(text, 25, 25, 1100)
            m.paste(image_source, (783, 229))
            m.paste(image_source, (211, 199))

            await m.render('floor.png')

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def forbidden(self, ctx, *, image_source: converters.ImageSourceConverter = None):
        """ At last! I am free to think the forbidden thoughts. """
        image_source = image_source or ctx.author.avatar_url_as(format='png')

        await ctx.channel.trigger_typing()
        avatar_data = await get_bytesio(self.bot.session, image_source)
        forbid = wndimg.Image(filename='resources/forbidden_thoughts.png')
        avatar = wndimg.Image(file=avatar_data)
        canvas = wndimg.Image(width=forbid.width, height=forbid.height)

        # canvas should be png
        canvas.format = 'png'

        # resize the avatar to an appropriate size
        avatar.resize(580, 580)

        # composite the avatar on the bottom, then the forbidden image on top
        canvas.composite(avatar, 980, 480)
        canvas.composite(forbid, 0, 0)

        # create a bytesio to save it to
        with BytesIO() as bio:
            # save
            await ctx.bot.loop.run_in_executor(None, functools.partial(canvas.save, file=bio))
            bio.seek(0)

            # send it
            await ctx.send(file=discord.File(bio, f'forbidden.png'))

        # close everything
        avatar_data.close()
        forbid.close()
        avatar.close()
        canvas.close()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wacky(self, ctx, image_source: converters.ImageSourceConverter = None):
        """ Applies wacky effects to your avatar. """
        image_source = image_source or ctx.message.author.avatar_url_as(format='png')

        await ctx.channel.trigger_typing()
        avatar_bio = await get_bytesio(self.bot.session, image_source)

        # attempt to load the avatar
        try:
            avatar_im = Image.open(avatar_bio)
        except:
            await ctx.send('I couldn\'t load that person\'s avatar.')
            logger.exception('Wacky avatar processing error.')
            avatar_bio.close()
            return

        enhancer = ImageEnhance.Color(avatar_im)
        avatar_im = await self.bot.loop.run_in_executor(None, enhancer.enhance, 50)

        finished_image = BytesIO()
        try:
            await self.bot.loop.run_in_executor(None, functools.partial(avatar_im.save, finished_image, format='png'))
        except:
            avatar_bio.close()
            avatar_im.close()
            finished_image.close()
            logger.exception('Wacky processing error.')
            return await ctx.send('An error has occurred processing your image.')

        finished_image.seek(0)
        await ctx.send(file=discord.File(finished_image, 'result.png'))

        avatar_bio.close()
        avatar_im.close()
        finished_image.close()


def setup(bot):
    bot.add_cog(Memes(bot))
