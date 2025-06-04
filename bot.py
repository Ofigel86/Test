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

bot = telebot.TeleBot("")
plan = {"bumaga": "Бумага разлагается 1,5-2 месяца", "metal": "Метал разлагается 200-500 лет тебя любая банка переживёт дохляк :0", "otxod": "Разлагается от 3 недель до 6 месяцев", "steclo": "Стекло разлаается 1-2 млн лет оно тебя переживёт дохляк :0"}
meme_mems = os.listdir("./img/meme")
musor_musor = os.listdir("./img/musor")
user = {}
WEB_URL = "https://www.google.com"     

def get_duck_image_url():    
    url = 'https://random-d.uk/api/random'
    res = requests.get(url)
    data = res.json()
    return data['url']

def get_tokio_anime():
    url = "https://kitsu.io/api/edge/anime?filter[text]=tokio"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        anime_list = []
        for item in data['data']:
            if 'posterImage' in item['attributes'] and 'original' in item['attributes']['posterImage']:
                anime_list.append(item['attributes']['posterImage']['original'])
        return anime_list
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return []


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

@bot.message_handler(commands=['memes'])
def send_memes(message):
    worlds = message.text.split()
    if len(worlds) < 2:
        bot.reply_to(message, "Укажите категорию мема, например: /memes meme")
        return
    
    cat = worlds[1].lower()
    memes_dir = f"./img/{cat}"
    

    if not os.path.exists(memes_dir):
        bot.reply_to(message, f"Категория '{cat}' не найдена 😢")
        return
    
    try:
        mem_files = os.listdir(memes_dir)
        if not mem_files:
            bot.reply_to(message, f"В категории '{cat}' нет мемов 😢")
            return
    except Exception as e:
        print(f"Ошибка доступа к папке: {e}")
        bot.reply_to(message, "Ошибка при доступе к мемам 😢")
        return
    
    random_file = random.choice(mem_files)
    file_path = os.path.join(memes_dir, random_file)
    
    try:
        with open(file_path, "rb") as f:
            bot.send_photo(message.chat.id, f)
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        bot.reply_to(message, "Не удалось отправить мем 😢")
    

@bot.message_handler(commands=['musor'])
def send_musor(message):
    img = random.choice(musor_musor)
    text = plan[img]
    with open(f"./img/musor/{random.choice()}","rb") as f:
                bot.send_photo(message.chat.id, f)
    


    




@bot.message_handler(commands=['pomogi'])
def send_pomogi(message):
    bot.reply_to(message, "Привет если ты это читаешь то ты должен узнать что НЕЛЬЗЯ ЗА МУРОСИТЬ, и всегда убирай за собой мусор,по моему мнению если люди будут масорить то мы будем дышать не чистым воздухом и  мы умрём (наверное).")


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
