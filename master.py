import os
import random
import logging
import asyncio
import aiocron
import asyncpg
import discord
import urllib.parse as urlparse #для запуска на Heroku
from discord.ext import commands
from discord.utils import get
from captcha.image import ImageCaptcha

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger('discord').setLevel(level=logging.WARNING)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
WORK_DISCORD_CHANNEL_ID = 934875576668414102 #ID канала, в котором работает бот
CAPTCHA_MODE = True #постинг с капчей
WHITELIST_MODE = True #вайтлист - постинг без капчи (кулдаун не убирается)
WHITELIST_IDS = [] #если включён вайтлист, то сюда нужно добавить Discord ID юзеров в цифровом виде
DATABASE_URL = os.environ['DATABASE_URL']

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix=">>", intents=intents)

@aiocron.crontab('*/20 * * * *')
async def pinger():
    """Функция, чтоб бот не останавливал работу на Heroku."""
    logging.info(f"I'm alive!")

async def post_number_worker():
    """Функция для взятия номера поста и прибавления к нему единицы."""
    url = urlparse.urlparse(DATABASE_URL)
    dbname = url.path[1:]
    user = url.username
    password = url.password
    host = url.hostname
    port = url.port
    conn = await asyncpg.connect(database=dbname, user=user, password=password, host=host, port=port)
    post_number = await conn.fetchval('SELECT post_id FROM post_ids')
    post_number += 1
    await conn.execute('UPDATE post_ids SET post_id=$1 WHERE temp_id=1', post_number)
    await conn.close()
    return str(post_number)

async def get_threads():
    """Рабочая функция для запроса тредов."""
    work_channel = await bot.fetch_channel(WORK_DISCORD_CHANNEL_ID)
    actual_threads_list = work_channel.threads
    archived_threads_obj = work_channel.archived_threads()
    actual_threads_dict = {}
    archived_threads_dict = {}
    for thread in actual_threads_list:
        if thread.archived == False: #сортирование активных и архивных тредов 
            actual_threads_dict[thread.name] = thread.id
        else:
            archived_threads_dict[thread.name] = thread.id
    async for thread in archived_threads_obj:
        if thread.archived == True: #сортирование активных и архивных тредов 
            archived_threads_dict[thread.name] = thread.id
        else:
            actual_threads_dict[thread.name] = thread.id
    return actual_threads_dict, archived_threads_dict

async def make_captcha():
    """Создаёт капчу и возвращает ответ, он же название файла."""
    symbols_list = [chr(x) for x in range(ord('a'), ord('z') + 1)] + [chr(x) for x in range(ord('0'), ord('9') + 1)]
    captcha_chance = random.randint(0, 100)
    if captcha_chance <= 33:
        answer = ''.join([random.choice(symbols_list) for i in range(0, 5)])
    elif captcha_chance <= 66:
        answer = ''.join([random.choice(symbols_list) for i in range(0, 6)])
    elif captcha_chance <= 100:
        answer = ''.join([random.choice(symbols_list) for i in range(0, 7)])

    image = ImageCaptcha(width=280, height=90)
    image.generate(answer) 
    image.write(answer, answer + '.png')
    return answer

async def captcha_check(ctx):
    """Проверка юзера капчей. Возвращает булево значение."""
    answer = await make_captcha()
    embed = discord.Embed(colour=discord.Colour.purple())
    embed.add_field(name='Введите ответ на капчу', value='Все буквы в нижнем регистре (маленькие).')
    embed.add_field(name='У вас 90 секунд', value='Если вы не успеете отправить название, то это сообщение удалится.')
    request_captcha_answer_msg = await ctx.send(embed=embed, file=discord.File(answer+'.png'))
    os.remove(answer + '.png')
    def check(message):
        return message.author.id == ctx.author.id

    try:
        answer_msg = await bot.wait_for('message', check=check, timeout=90)
    except:
        await request_captcha_answer_msg.delete()
        return False
    else:
        if answer_msg.content != answer:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name='Вы дали неверный ответ!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_captcha_answer_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_captcha_answer_msg.delete()
            await error_request_captcha_answer_msg.delete()
            logging.info("КАПЧА: Неудачная проверка.")
            return False

    await request_captcha_answer_msg.delete()
    logging.info("КАПЧА: Удачная проверка.")
    return True

@bot.command(aliases=['создать-тред'])
@commands.dm_only()
@commands.cooldown(1, 86400, commands.BucketType.user) #1 день
async def create_thread(ctx):
    """Создать тред."""
    if CAPTCHA_MODE == True and WHITELIST_MODE == True and ctx.author.id not in WHITELIST_IDS:
        captcha_check_result = await captcha_check(ctx)
        if captcha_check_result == False:
            return
    actual_threads_dict, archived_threads_dict = await get_threads()
    embed = discord.Embed(colour=discord.Colour.fuchsia())
    embed.add_field(name='Введите название будущего треда', value='В имени треда должно быть не меньше 5 и не больше 30 символов.')
    embed.add_field(name='У вас 90 секунд', value='Если вы не успеете отправить название, то это сообщение удалится.')
    request_thread_name_msg = await ctx.send(embed=embed)
    thread_name = ''
    thread_first_message = ''

    def check(message):
        return message.author.id == ctx.author.id

    try:
        thread_name_msg = await bot.wait_for('message', check=check, timeout=90)
    except:
        await request_thread_name_msg.delete()
    else:
        if thread_name_msg.content in actual_threads_dict or thread_name_msg.content in archived_threads_dict:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name='Тред с таким названием уже есть!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_name_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_thread_name_msg.delete()
            await error_request_thread_name_msg.delete()
            logging.info("СОЗДАНИЕ ТРЕДА: Попытка создать тред с имеющимся названием.")
            return
        elif len(thread_name_msg.content) <= 4 or len(thread_name_msg.content) > 31:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name=f'Название треда ({str(len(thread_name_msg.content))} символов) слишком мало или велико!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_name_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_thread_name_msg.delete()
            await error_request_thread_name_msg.delete()
            logging.info("СОЗДАНИЕ ТРЕДА: Попытка создания треда с слишком малым или слишком большим названием.")
            return
        thread_name = thread_name_msg.content
    
    embed = discord.Embed(colour=discord.Colour.fuchsia())
    embed.add_field(name='Введите первое сообщение будущего треда', value='В нём должно быть не меньше 5 и не больше 1990 символов. Вы можете прикрепить фото/видео/файл, но обязательно нужно что-то написать.')
    embed.add_field(name='У вас 90 секунд', value='Если вы не успеете отправить название, то это сообщение удалится.')
    request_thread_first_message_msg = await ctx.send(embed=embed)
    try:
        thread_first_message_msg = await bot.wait_for('message', check=check, timeout=90)
    except:
        await request_thread_first_message_msg.delete()
    else:
        if len(thread_first_message_msg.clean_content) <= 4 or len(thread_first_message_msg.clean_content) > 1990:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name=f'Сообщение ({str(len(thread_name_msg.clean_content))} символов) слишком мало или слишком велико!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_first_message_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await thread_name_msg.delete()
            await request_thread_first_message_msg.delete()
            await error_request_thread_first_message_msg.delete()
            logging.info("СОЗДАНИЕ ТРЕДА: Слишком малое или слишком большое первое сообщение.")
            return
        thread_first_message = thread_first_message_msg.clean_content

    if len (thread_name) > 4:
        post_number = await post_number_worker()
        thread_first_message = f'***#{post_number}***\n\n{thread_first_message}'
        work_channel = await bot.fetch_channel(WORK_DISCORD_CHANNEL_ID)
        created_thread = await work_channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
        if thread_first_message_msg.attachments:
            if len(thread_first_message_msg.attachments) > 1:
                ready_attachments = []
                for attachment in thread_first_message_msg.attachments: 
                    ready_attachment = await attachment.to_file()
                    ready_attachments.append(ready_attachment)
                await created_thread.send(thread_first_message, files=ready_attachments)
            else:
                for attachment in thread_first_message_msg.attachments: 
                    ready_attachment = await attachment.to_file()
                await created_thread.send(thread_first_message, file=ready_attachment)
        else:
            await created_thread.send(thread_first_message)
        embed = discord.Embed(colour=discord.Colour.green())
        embed.add_field(name='Тред успешно создан!', value='Это и предыдущее сообщение удалится через 15 секунд.')
        success_msg = await ctx.send(embed=embed)
        await asyncio.sleep(15)
        await request_thread_name_msg.delete()
        await request_thread_first_message_msg.delete()
        await success_msg.delete()
        logging.info(f"СОЗДАНИЕ ТРЕДА: Успешно создан тред {thread_name}.")
    
@bot.command(aliases=['пост'])
@commands.dm_only()
@commands.cooldown(1, 300, commands.BucketType.user) #5 минут
async def post(ctx):
    """Написать в тред."""
    if CAPTCHA_MODE == True and WHITELIST_MODE == True and ctx.author.id not in WHITELIST_IDS:
        captcha_check_result = await captcha_check(ctx)
        if captcha_check_result == False:
            return
    actual_threads_dict, archived_threads_dict = await get_threads()
    embed = discord.Embed(colour=discord.Colour.fuchsia())
    embed.add_field(name='Введите название треда, в который вы хотите написать', value='Вводите точно так же, как название треда написано в списке тредов.')
    embed.add_field(name='У вас 90 секунд', value='Если вы не успеете отправить название, то это сообщение удалится.')
    request_thread_name_msg = await ctx.send(embed=embed)
    thread_name = ''
    thread_message = ''

    def check(message):
        return message.author.id == ctx.author.id

    try:
        thread_name_msg = await bot.wait_for('message', check=check, timeout=90)
    except:
        await request_thread_name_msg.delete()
    else:
        if thread_name_msg.content in archived_threads_dict:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name='Этот тред в архиве!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_name_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_thread_name_msg.delete()
            await error_request_thread_name_msg.delete()
            logging.info("ПОСТ В ТРЕД: Тред в архиве.")
            return
        elif thread_name_msg.content not in actual_threads_dict:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name='Такой тред не найден!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_name_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_thread_name_msg.delete()
            await error_request_thread_name_msg.delete()
            logging.info("ПОСТ В ТРЕД: Тред не найден.")
            return
        thread_name = thread_name_msg.content

    embed = discord.Embed(colour=discord.Colour.fuchsia())
    embed.add_field(name='Введите сообщение', value='В нём должно быть не меньше 5 и не больше 1990 символов. Вы можете прикрепить фото/видео/файл, но обязательно нужно что-то написать.')
    embed.add_field(name='У вас 90 секунд', value='Если вы не успеете отправить, то это сообщение удалится.')
    request_thread_message_msg = await ctx.send(embed=embed)
    try:
        thread_message_msg = await bot.wait_for('message', check=check, timeout=90)
    except:
        await request_thread_message_msg.delete()
    else:
        if len(thread_message_msg.clean_content) <= 4 or len(thread_message_msg.clean_content) > 1990:
            embed = discord.Embed(colour=discord.Colour.red())
            embed.add_field(name=f'Сообщение ({str(len(thread_message_msg.clean_content))} символов) слишком мало или слишком велико!', value='Это и предыдущее сообщение удалится через 15 секунд.')
            error_request_thread_message_msg = await ctx.author.send(embed=embed)
            await asyncio.sleep(15)
            await request_thread_name_msg.delete()
            await request_thread_message_msg.delete()
            await error_request_thread_message_msg.delete()
            logging.info("ПОСТ В ТРЕД: Слишком малое или слишком большое сообщение.")
            return
        thread_message = thread_message_msg.clean_content

    post_number = await post_number_worker()
    thread_message = f'***#{post_number}***\n\n{thread_message}'
    work_channel = await bot.fetch_channel(WORK_DISCORD_CHANNEL_ID)
    thread = work_channel.get_thread(actual_threads_dict[thread_name])
    if thread_message_msg.attachments:
        if len(thread_message_msg.attachments) > 1:
            ready_attachments = []
            for attachment in thread_message_msg.attachments: 
                ready_attachment = await attachment.to_file()
                ready_attachments.append(ready_attachment)
            await thread.send(thread_message, files=ready_attachments)
        else:
            for attachment in thread_message_msg.attachments: 
                ready_attachment = await attachment.to_file()
            await thread.send(thread_message, file=ready_attachment)
    else:
        await thread.send(thread_message)
    embed = discord.Embed(colour=discord.Colour.green())
    embed.add_field(name='Сообщение успешно отправлено!', value='Это и предыдущее сообщение удалится через 15 секунд.')
    success_msg = await ctx.send(embed=embed)
    await asyncio.sleep(15)
    await request_thread_name_msg.delete()
    await request_thread_message_msg.delete()
    await success_msg.delete()
    logging.info("ПОСТ В ТРЕД: Пост успешно отправлен в тред.")

@bot.event
async def on_command_error(ctx, exception):
    if isinstance(exception, commands.PrivateMessageOnly):
        embed = discord.Embed(colour=discord.Colour.red())
        embed.add_field(name='Вводите команды только в личке!', value='Это сообщение удалится через 15 секунд.')
        error_msg = await ctx.author.send(embed=embed)
        await asyncio.sleep(15)
        await error_msg.delete()
        logging.info("ОШИБКА: Команда введена не в личке.")
    elif isinstance(exception, commands.CommandOnCooldown):
        embed = discord.Embed(colour=discord.Colour.red())
        embed.add_field(name=f'Ожидайте ещё {str(int(exception.retry_after))} секунд!', value='Это сообщение удалится через 15 секунд.')
        error_msg = await ctx.author.send(embed=embed)
        await asyncio.sleep(15)
        await error_msg.delete()
        logging.info("ОШИБКА: Команда на кулдауне.")

@bot.event
async def on_ready():
    logging.info(f"Discord Bot is ready!")

bot.run(DISCORD_TOKEN)
