# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal

import logging
import asyncio
import re
import random
import json
import os
from FunPayAPI.updater.events import NewOrderEvent, NewMessageEvent
from FunPayAPI import enums
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import types

try:
    from pyrogram import Client
except ImportError:
    import subprocess
    import sys
    print("Установка модуля pyrogram...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram"])

    from pyrogram import Client


# -*- CREDENTIONALS-*-
NAME = "StarsGifter"
VERSION = "1.5(Fixed)"
DESCRIPTION = "Плагин для отправки звёзд через подарки (исправленная версия)"
CREDITS = "@Scwee_xz"
UUID = "43dd7ceb-3ef2-44c0-8623-03f596a00fbd"
SETTINGS_PAGE = False

CONFIG_FILE = "plugins/starsgifter_config.json"
"""сюда вставляем Id лотов, https://funpay.com/lots/offer?id=40859974, id=40859974, это и есть id"""
""" 15, 25 это количество звезд в заказе, лот id на 15 звезд вставляем в 1"""
DEFAULT_CONFIG = {
    "lot_stars_mapping": {
        "1": 15,
        "2": 25,
        "3": 50,
        "4": 75,
        "5": 100,
        "6": 125,
        "7": 150,
        "123457": 250,
        "123458": 500
    },
    
    "random_gifts": {
        "100": [5168043875654172773, 5170690322832818290, 5170521118301225164],
        "50": [5170144170496491616, 5170314324215857265, 5170564780938756245, 6028601630662853006],
        "25": [5170250947678437525, 5168103777563050263],
        "15": [5170145012310081615, 5170233102089322756]
    },
    "plugin_enabled": True,
    "auto_refund": False,
    "stats": {},
    "pyrogram": {
        "api_id": int(), #Сюда вставляем "api_id": int(Id)
        "api_hash": "" , #Сюда вставляем Hash "api_hash": "Hash"
        "session_name": "starsgifter_session" #Навазние сессии
    }
}

logger = logging.getLogger("FPC.starsgifter")
logger.setLevel(logging.DEBUG)

RUNNING = True
orders_info = {}
stats_data = {}
pyrogram_client = None

def load_config() -> dict:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

def save_config(config: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

config = load_config()
LOT_STARS_MAPPING = {str(k): int(v) for k, v in config.get("lot_stars_mapping", {}).items()}
RANDOM_GIFTS = {int(k): v for k, v in config.get("random_gifts", DEFAULT_CONFIG["random_gifts"]).items()}
RUNNING = config.get("plugin_enabled", True)
stats_data = config.get("stats", {})

def init_pyrogram():
    global pyrogram_client
    pyrogram_config = config.get("pyrogram", DEFAULT_CONFIG["pyrogram"])
    try:
        pyrogram_client = Client(
            pyrogram_config["session_name"],
            api_id=pyrogram_config["api_id"],
            api_hash=pyrogram_config["api_hash"],
            phone_number=pyrogram_config["phone_number"]
        )
        pyrogram_client.start()
        logger.info("✅ Pyrogram клиент запущен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка Pyrogram: {e}")
        return False

def sanitize_telegram_text(text: str) -> str:
    text = text.replace("_", "\\_").replace("*", "\\*")
    text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    return text

async def calc_gifts_quantity(quantity: int) -> dict:
    for d in range(quantity // 100, -1, -1):
        remain_after_100 = quantity - d * 100
        for c in range(remain_after_100 // 50, -1, -1):
            remain_after_50 = remain_after_100 - c * 50
            for b in range(remain_after_50 // 25, -1, -1):
                remain_after_25 = remain_after_50 - b * 25
                if remain_after_25 % 15 == 0:
                    a = remain_after_25 // 15
                    return {100: d, 50: c, 25: b, 15: a}
    return None

def format_gifts_result(gifts_dict: dict) -> str:
    result = []
    for price, count in sorted(gifts_dict.items(), reverse=True):
        if count > 0:
            if count == 1:
                result.append(f"{count} подарок по {price} звёзд")
            elif 2 <= count <= 4:
                result.append(f"{count} подарка по {price} звёзд")
            else:
                result.append(f"{count} подарков по {price} звёзд")
    return "\n".join(result)

async def send_stars_gifts(cardinal: Cardinal, username: str, stars_count: int, chat_id: int):
    global pyrogram_client
    try:
        if pyrogram_client is None or not pyrogram_client.is_connected:
            logger.error("Pyrogram не подключен")
            cardinal.send_message(chat_id, sanitize_telegram_text("❌ Ошибка: клиент Telegram не подключен"))
            return False
        
        gifts_distribution = await calc_gifts_quantity(stars_count)
        if not gifts_distribution:
            cardinal.send_message(chat_id, sanitize_telegram_text("❌ Ошибка: невозможно рассчитать подарки"))
            return False
        
        try:
            user = await pyrogram_client.get_users([username])
            if not user:
                cardinal.send_message(chat_id, sanitize_telegram_text(f"❌ Пользователь {username} не найден"))
                return False
        except Exception as e:
            logger.error(f"Ошибка поиска {username}: {e}")
            cardinal.send_message(chat_id, sanitize_telegram_text(f"❌ Ошибка: {e}"))
            return False
        
        success_count = 0
        for price, count in gifts_distribution.items():
            for _ in range(count):
                try:
                    gift_id = random.choice(RANDOM_GIFTS[price])
                    await pyrogram_client.send_gift(chat_id=username, gift_id=gift_id)
                    success_count += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Ошибка {price}: {e}")
        
        report = f"✅ Отправлено: {stars_count} stars\n\n" + format_gifts_result(gifts_distribution)
       
        cardinal.send_message(chat_id, sanitize_telegram_text(report))

      
        return True
    

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        cardinal.send_message(chat_id, sanitize_telegram_text(f"❌ Ошибка: {str(e)}"))
        return False
    
    


def handle_new_order_stars(cardinal: Cardinal, event: NewOrderEvent, *args):
    """ИСПРАВЛЕННЫЙ обработчик заказов с множественными попытками получить chat_id"""

    global orders_info, RUNNING
    
    if not RUNNING:
        logger.debug("Плагин выключен")
        return
    
    order = event.order
    order_id = order.id
    lot_id = str(order.lot_id)
    amount = order.amount
    buyer_username = order.buyer_username
    
    logger.info(f"📦 Новый заказ #{order_id}, lot_id: {lot_id}, покупатель: {buyer_username}")
    
    # Проверка лота
    if lot_id not in LOT_STARS_MAPPING:
        logger.warning(f"⚠️ Лот {lot_id} не найден в конфигурации")
        return
    
    stars_per_lot = LOT_STARS_MAPPING[lot_id]
    total_stars = stars_per_lot * amount
    
    logger.info(f"💫 Заказ: {stars_per_lot} * {amount} = {total_stars} звёзд")
    

    try:
        buyer_chat = cardinal.account.get_chat_by_name(buyer_username, create_if_not_exists=True)
        if not buyer_chat:
            logger.error(f"❌ Не удалось получить чат с {buyer_username}")
            return
        chat_id = buyer_chat.id
        logger.info(f"✅ chat_id получен: {chat_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения чата: {e}")
        logger.debug("TRACEBACK", exc_info=True)
        return
    
    # Проверка количества лотов
    if amount != 1:
        cardinal.send_message(
            chat_id,
            f"❌ Вы заказали {amount} лотов ({total_stars} Stars). Заказывайте по одному!"
        )
        return
    
 
    welcome_msg = (
        f"✨ Спасибо за заказ {total_stars} Stars!\n\n"
        f"Для отправки звёзд мне нужен ваш username Telegram.\n"
        f"Пожалуйста, отправьте его в любом формате:\n"
        f"• @username\n"
        f"• username\n"
        f"• ID пользователя"
    )
    
    try:
        cardinal.send_message(chat_id, welcome_msg)
        logger.info(f"✅ Приветственное сообщение отправлено в chat_id {chat_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        logger.debug("TRACEBACK", exc_info=True)
        return
    
    # Сохранение заказа
    if chat_id not in orders_info:
        orders_info[chat_id] = []
    
    orders_info[chat_id].append({
        "username": None,
        "confirmed": False,
        "completed": False,
        "orderID": order_id,
        "stars_count": total_stars,
        "lot_id": lot_id,
        "buyer_username": buyer_username
    })
    
    logger.info(f"📝 Заказ #{order_id} сохранён для chat_id {chat_id}")

def handle_new_message_text(cardinal: Cardinal, event: NewMessageEvent, *args):
    global orders_info, RUNNING
    
    if not RUNNING:
        return
    
    chat_id = event.message.chat_id
    my_user = cardinal.account.username
    my_id = cardinal.account.id
    
    if chat_id == my_id or event.message.author.lower() in ["funpay", my_user.lower()]:
        return
    
    if chat_id not in orders_info or not orders_info[chat_id]:
        return
    
    current_order = None
    for o in reversed(orders_info[chat_id]):
        if not o.get("completed", False):
            current_order = o
            break
    
    if not current_order:
        return
    
    if event.message.text.strip().lower().startswith("!отмена"):
        cardinal.account.refund(current_order["orderID"])
        current_order["completed"] = True
        cardinal.send_message(chat_id, sanitize_telegram_text("❌ Заказ отменён"))
        return
    
    if current_order["username"] is None:
        username = event.message.text.strip()
        if not username:
            cardinal.send_message(chat_id, sanitize_telegram_text("❌ Отправьте username"))
            return
        
        current_order["username"] = username
        current_order["confirmed"] = False
        logger.info(f"📝 Username {username} получен для заказа #{current_order['orderID']}")
        cardinal.send_message(chat_id, sanitize_telegram_text(f"Username {username} верный +/-"))
        return
    
    if current_order["username"] and not current_order["confirmed"]:
        resp = event.message.text.strip().lower()
        
        if resp in ["+", "да", "yes", "верно", "правильно"]:
            current_order["confirmed"] = True
            cardinal.send_message(chat_id, sanitize_telegram_text(f"🚀 Начинаю отправку {current_order['stars_count']} звёзд..."))
            
            asyncio.run(send_stars_gifts(
                cardinal,
                current_order["username"],
                current_order["stars_count"],
                chat_id
            ))
            
            current_order["completed"] = True
            
        elif resp in ["-", "нет", "no", "неверно", "ошибка"]:
            current_order["username"] = None
            cardinal.send_message(chat_id, sanitize_telegram_text("FPC: введите корректный username"))


# ============= ПАНЕЛЬ УПРАВЛЕНИЯ =============
def stars_config(cardinal: Cardinal, m: types.Message):
    """Панель управления плагином"""
    import datetime
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_stats = stats_data.get(date_str, {})
    
    successful = today_stats.get("successful", 0)
    unsuccessful = today_stats.get("unsuccessful", 0)
    total_stars = today_stats.get("total_stars", 0)
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    status_btn = InlineKeyboardButton(
        text=f"{'🟢 Включен' if RUNNING else '🔴 Выключен'}",
        callback_data="toggle_plugin"
    )
    
    stats_btn = InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")
    settings_btn = InlineKeyboardButton(text="⚙️ Настройки", callback_data="show_settings")
    
    keyboard.add(status_btn, stats_btn)
    keyboard.add(settings_btn)
    
    status_text = "🟢 Работает" if RUNNING else "🔴 Остановлен"
    pyrogram_status = "🟢 Подключен" if (pyrogram_client and pyrogram_client.is_connected) else "🔴 Не подключен"
    
    message_text = f"""<b>⚡ StarsGifter - Панель управления</b>

<b>Статус:</b> {status_text}
<b>Pyrogram:</b> {pyrogram_status}
<b>Лотов настроено:</b> {len(LOT_STARS_MAPPING)}

<b>📊 Статистика за сегодня:</b>
✅ Успешных: {successful}
❌ Неудачных: {unsuccessful}
⭐ Всего звёзд: {total_stars}
"""
    
    cardinal.telegram.bot.send_message(
        chat_id=m.chat.id,
        text=message_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

def setup_callbacks(cardinal: Cardinal):

    global RUNNING
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda call: call.data in [
        "toggle_plugin", "show_stats", "show_settings"
    ])
    def handle_callbacks(call):
        global RUNNING
        
        try:
            cardinal.telegram.bot.answer_callback_query(call.id)
        except Exception:
            pass
        
        if call.data == "toggle_plugin":
            RUNNING = not RUNNING
            config["plugin_enabled"] = RUNNING
            save_config(config)
            
            status = "включен" if RUNNING else "выключен"
            cardinal.telegram.bot.send_message(call.message.chat.id, f"✅ Плагин {status}!")
        
        elif call.data == "show_stats":
            
            
            stats_text = "<b>📊 Статистика по дням:</b>\n\n"
            
            for date_str in sorted(stats_data.keys(), reverse=True)[:7]:
                day_stats = stats_data[date_str]
                successful = day_stats.get("successful", 0)
                unsuccessful = day_stats.get("unsuccessful", 0)
                total_stars = day_stats.get("total_stars", 0)
                
                stats_text += f"<b>{date_str}</b>\n"
                stats_text += f"✅ Успешных: {successful}\n"
                stats_text += f"❌ Неудачных: {unsuccessful}\n"
                stats_text += f"⭐ Звёзд: {total_stars}\n\n"
            
            if not stats_data:
                stats_text += "Статистика пуста"
            
            cardinal.telegram.bot.send_message(
                call.message.chat.id,
                stats_text,
                parse_mode="HTML"
            )
        
        elif call.data == "show_settings":
            pyrogram_config = config.get("pyrogram", {})
            
            settings_text = f"""<b>⚙️ Настройки плагина:</b>

<b>Pyrogram:</b>
• API ID: {pyrogram_config.get('api_id', 'не указан')}
• Session: {pyrogram_config.get('session_name', 'не указан')}

<b>Лотов настроено:</b> {len(LOT_STARS_MAPPING)}

<b>Маппинг лотов:</b>
"""
            for lot_id, stars in LOT_STARS_MAPPING.items():
                settings_text += f"• Лот {lot_id} = {stars} звёзд\n"
            
            cardinal.telegram.bot.send_message(
                call.message.chat.id,
                settings_text,
                parse_mode="HTML"
            )

# ============= ИНИЦИАЛИЗАЦИЯ =============
def init_plugin(cardinal: Cardinal):
    logger.info(f"🚀 Инициализация {NAME} v{VERSION}")
    
    if not init_pyrogram():
        logger.warning("⚠️ Pyrogram не запущен")
    
    logger.info(f"📋 Загружено {len(LOT_STARS_MAPPING)} лотов:")
    for lot_id, stars in LOT_STARS_MAPPING.items():
        logger.info(f"  • Лот {lot_id} = {stars} звёзд")
    

    @cardinal.telegram.bot.message_handler(commands=["stars_panel"])
    def panel_handler(message):
        logger.info("🎛️ Получена команда /stars_panel")
        stars_config(cardinal, message)
    
  
    setup_callbacks(cardinal)
    
    logger.info(f"✅ Плагин загружен. Статус: {'🟢 Включен' if RUNNING else '🔴 Выключен'}")
    logger.info("✅ Команда /stars_panel зарегистрирована")


def shutdown_plugin():
    global pyrogram_client
    if pyrogram_client and pyrogram_client.is_connected:
        pyrogram_client.stop()
        logger.info("Pyrogram остановлен")

BIND_TO_PRE_INIT = [init_plugin]
BIND_TO_NEW_ORDER = [handle_new_order_stars]
BIND_TO_NEW_MESSAGE = [handle_new_message_text]
BIND_TO_DELETE = [shutdown_plugin]
