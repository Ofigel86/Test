import random
import telebot
import requests
import os
from bot_logic import gen_pass
from telebot import TeleBot
from telebot.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# Инициализация бота
bot = telebot.TeleBot("7780203660:AAGjrQKrNDVCWfq_ZaxbvVxjfeYrQi0FwWQ")

# Переменные окружения
meme_mems = os.listdir("./img/meme")
user = {}
WEB_URL = "https://www.google.com"     

# Функция для получения утки
def get_duck_image_url():    
    url = 'https://random-d.uk/api/random'
    res = requests.get(url)
    data = res.json()
    return data['url']

# Функция для получения аниме
def get_tokio_anime():
    url = "https://kitsu.io/api/edge/anime?filter[text]=tokio"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Извлекаем список аниме с постерами
        anime_list = []
        for item in data['data']:
            if 'posterImage' in item['attributes'] and 'original' in item['attributes']['posterImage']:
                anime_list.append(item['attributes']['posterImage']['original'])
        return anime_list
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return []

# ========================================
# ОБРАБОТЧИКИ КОМАНД (должны быть после объявления bot)
# ========================================

@bot.message_handler(commands=['duck'])
def duck(message):
    image_url = get_duck_image_url()
    bot.reply_to(message, image_url)

@bot.message_handler(commands=['tokio'])
def send_tokio_anime(message):
    anime_images = get_tokio_anime()
    
    if not anime_images:
        bot.reply_to(message, "😢 Не удалось найти аниме по запросу 'tokio'")
        return
    
    random_image = random.choice(anime_images)
    bot.send_photo(message.chat.id, random_image)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Бомжур ёмаё деньги есть?А если найду?\n /hello - поздороваться \n /bye - попрощаться \n /pass (количество)- сгенерировать пароль \n /google - просто гугл \n /heh (кол-во 'heh') - похехекать ")
    
@bot.message_handler(commands=['hello'])
def send_hello(message):
    user = message.from_user.first_name
    bot.reply_to(message, "Привет! " + str(user))
    
@bot.message_handler(commands=['pass'])
def send_pass(message):
    world = message.text.split()
    if len(world) < 2:
        bot.reply_to(message, gen_pass(10))
    else:
        lenght = int(world[1])
        bot.reply_to(message, gen_pass(lenght))

@bot.message_handler(commands=['smile'])
def send_random_smile(message):
    smiles = ['😀', '😂', '😍', '🤩', '😎', '🤯', '👻', '🍕', '🚀', '🎉', '❤️', '🔥']
    random_smile = random.choice(smiles)
    bot.reply_to(message, f"Вот твой случайный смайлик: {random_smile}")

@bot.message_handler(commands=['heh'])
def send_heh(message):
    count_heh = int(message.text.split()[1]) if len(message.text.split()) > 1 else 5
    bot.reply_to(message, "he" * count_heh)

@bot.message_handler(commands=['google'])
def send_google(message):
    reply_keyboard_markup = ReplyKeyboardMarkup(resize_keyboard=True)
    reply_keyboard_markup.row(KeyboardButton("Start MiniApp", web_app=WebAppInfo(WEB_URL)))

    inline_keyboard_markup = InlineKeyboardMarkup()
    inline_keyboard_markup.row(InlineKeyboardButton('Start MiniApp', web_app=WebAppInfo(WEB_URL)))

    bot.reply_to(message, "Click the bottom inline button to start MiniApp", reply_markup=inline_keyboard_markup)
    bot.reply_to(message, "Click keyboard button to start MiniApp", reply_markup=reply_keyboard_markup)

@bot.message_handler(content_types=['web_app_data'])
def web_app(message):
    bot.reply_to(message, f'Your message is "{message.web_app_data.data}"')

# Исправленная функция /memes
@bot.message_handler(commands=['memes'])
def send_memes(message):
    worlds = message.text.split()
    if len(worlds) < 2:
        bot.reply_to(message, "Укажите категорию мема, например: /memes meme")
        return
    
    cat = worlds[1].lower()
    memes_dir = f"./img/{cat}"
    
    # Проверяем существование директории
    if not os.path.exists(memes_dir):
        bot.reply_to(message, f"Категория '{cat}' не найдена 😢")
        return
    
    # Получаем список файлов
    try:
        mem_files = os.listdir(memes_dir)
        if not mem_files:
            bot.reply_to(message, f"В категории '{cat}' нет мемов 😢")
            return
    except Exception as e:
        print(f"Ошибка доступа к папке: {e}")
        bot.reply_to(message, "Ошибка при доступе к мемам 😢")
        return
    
    # Выбираем случайный файл
    random_file = random.choice(mem_files)
    file_path = os.path.join(memes_dir, random_file)
    
    # Отправляем изображение
    try:
        with open(file_path, "rb") as f:
            bot.send_photo(message.chat.id, f)
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        bot.reply_to(message, "Не удалось отправить мем 😢")

@bot.message_handler(commands=['spam'])
def send_spam(message):
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "Использование: /spam [текст] [количество]")
        return
    
    try:
        text = ' '.join(args[1:-1])
        count = int(args[-1])
        
        if count > 20:
            bot.reply_to(message, "Слишком много сообщений! Максимум 20.")
            count = 20
        
        for _ in range(count):
            bot.send_message(message.chat.id, text)
            
    except ValueError:
        bot.reply_to(message, "Ошибка: количество должно быть числом!")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

bot.polling()