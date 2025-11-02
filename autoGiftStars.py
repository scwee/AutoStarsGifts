# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cardinal import Cardinal

import logging
import asyncio
import random
import json
import os
import time
import threading
from queue import Queue
from FunPayAPI.updater.events import NewOrderEvent, NewMessageEvent
from FunPayAPI.updater.events import OrderStatuses
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

# ═══════════════════════════════════════════════════════════════════════════
# МЕТАДАННЫЕ ПЛАГИНА
# ═══════════════════════════════════════════════════════════════════════════

NAME = "StarsGifter"
VERSION = "2.1"
DESCRIPTION = "Плагин для отправки звёзд через подарки Telegram"
CREDITS = "@Scwee_xz"
UUID = "298845c5-9c90-4912-b599-7ca26f94a7b1"
SETTINGS_PAGE = False

CONFIG_FILE = "plugins/starsgifter_config.json"
DEFAULT_CONFIG = {
    "lot_stars_mapping": {},
    "random_gifts": {
        "100": [5168043875654172773, 5170690322832818290, 5170521118301225164],
        "50": [5170144170496491616, 5170314324215857265, 5170564780938756245, 6028601630662853006],
        "25": [5170250947678437525, 5168103777563050263],
        "15": [5170145012310081615, 5170233102089322756]
    },
    "plugin_enabled": True,
    "stats": {},
    "pyrogram": {
        "api_id": 0,
        "api_hash": "",
        "phone_number": "",
        "session_name": "starsgifter_session"
    }
}

logger = logging.getLogger("FPC.starsgifter")
logger.setLevel(logging.DEBUG)
LOGGER_PREFIX = "[StarsGifter]"

# ═══════════════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ═══════════════════════════════════════════════════════════════════════════

RUNNING = True
pyrogram_client = None
USER_ORDER_QUEUES = {}
FUNPAY_STATES = {}

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def load_config():
    """Загрузить конфиг"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg):
    """Сохранить конфиг"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()
LOT_STARS_MAPPING = {str(k): int(v) for k, v in config.get("lot_stars_mapping", {}).items()}
RANDOM_GIFTS = {int(k): v for k, v in config.get("random_gifts", DEFAULT_CONFIG["random_gifts"]).items()}
RUNNING = config.get("plugin_enabled", True)

# ═══════════════════════════════════════════════════════════════════════════
# PYROGRAM КЛИЕНТ
# ═══════════════════════════════════════════════════════════════════════════

def init_pyrogram():
    """Инициализировать Pyrogram"""
    global pyrogram_client
    pyrogram_config = config.get("pyrogram", DEFAULT_CONFIG["pyrogram"])
    
    if not pyrogram_config.get("api_id") or not pyrogram_config.get("api_hash"):
        logger.warning(f"{LOGGER_PREFIX} API ID или API HASH не установлены")
        return False
    
    try:
        pyrogram_client = Client(
            pyrogram_config["session_name"],
            api_id=pyrogram_config["api_id"],
            api_hash=pyrogram_config["api_hash"],
            phone_number=pyrogram_config.get("phone_number", "")
        )
        pyrogram_client.start()
        logger.info(f"{LOGGER_PREFIX} ✅ Pyrogram клиент запущен")
        return True
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} ❌ Ошибка Pyrogram: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ОТПРАВКА ЗВЁЗД
# ═══════════════════════════════════════════════════════════════════════════

async def calc_gifts_quantity(quantity):
    """Расчёт комбинации подарков"""
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

def format_gifts_result(gifts_dict):
    """Форматирование результата подарков"""
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

async def send_stars_gifts(cardinal, username, stars_count, chat_id, order_id=None):
    """Отправить звёзды"""
    global pyrogram_client
    try:
        if pyrogram_client is None or not pyrogram_client.is_connected:
            cardinal.account.send_message(chat_id, "❌ Ошибка: клиент Telegram не подключен")
            return False

        gifts_distribution = await calc_gifts_quantity(stars_count)
        if not gifts_distribution:
            cardinal.account.send_message(chat_id, "❌ Ошибка: невозможно рассчитать подарки")
            return False

        try:
            user = await pyrogram_client.get_users([username])
            if not user:
                cardinal.account.send_message(chat_id, f"❌ Пользователь {username} не найден")
                return False
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} Ошибка поиска {username}: {e}")
            cardinal.account.send_message(chat_id, f"❌ Ошибка: {e}")
            return False

        success_count = 0
        failed_count = 0

        for price, count in gifts_distribution.items():
            for _ in range(count):
                try:
                    gift_id = random.choice(RANDOM_GIFTS[price])
                    await pyrogram_client.send_gift(chat_id=username, gift_id=gift_id)
                    success_count += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"{LOGGER_PREFIX} Ошибка отправки подарка {price}: {e}")
                    failed_count += 1

        report = f"✅ Отправлено: {stars_count} stars\n\n" + format_gifts_result(gifts_distribution)
        if failed_count > 0:
            report += f"\n\n❌ Не удалось отправить: {failed_count}"

        cardinal.account.send_message(chat_id, report)

        if failed_count == 0:
            review_msg = (
                "✅ Звезды были успешно отправлены вам на аккаунт через подарок!\n\n"
                "❤️ Подтвердите пожалуйста заказ и напишите отзыв, вам не сложно, а мне это очень сильно поможет."
            )
            if order_id:
                review_msg += f"\n✨ Ссылка для написания отзыва: https://funpay.com/orders/{order_id}/"
            cardinal.account.send_message(chat_id, review_msg)
        
        return True

    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка отправки: {e}")
        cardinal.account.send_message(chat_id, f"❌ Ошибка: {str(e)}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ЗАКАЗОВ
# ═══════════════════════════════════════════════════════════════════════════

def verify_order_exists(cardinal: 'Cardinal', order_id: str) -> bool:
    """Проверка подлинности заказа"""
    try:
        order = cardinal.account.get_order(order_id)
        return order is not None and order.seller_id == cardinal.account.id
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка проверки заказа #{order_id}: {e}")
        return False

def extract_order_id_from_message(text: str):
    """Извлечение ID заказа из сообщения"""
    import re
    match = re.search(r'#(\w+)', text)
    return match.group(1) if match else None

def handle_new_message(cardinal, event: NewMessageEvent, *args):
    """Обработка новых сообщений"""
    global FUNPAY_STATES, RUNNING

    if not RUNNING:
        return

    message = event.message
    state_key = (message.chat_id, message.author_id)
    state = FUNPAY_STATES.get(state_key)

    # Обработка системных сообщений о покупке
    if message.author_id == 0 and message.type and message.type.name == "ORDER_PURCHASED":
        order_id = extract_order_id_from_message(message.text)
        if order_id:
            try:
                order = cardinal.account.get_order(order_id)
                buyer_id = order.buyer_id
                
                USER_ORDER_QUEUES.setdefault(buyer_id, Queue()).put({
                    "order_id": order_id,
                    "chat_id": message.chat_id
                })
                
                threading.Thread(
                    target=process_user_orders,
                    args=(cardinal, buyer_id),
                    daemon=True
                ).start()
                
                logger.info(f"{LOGGER_PREFIX} Заказ #{order_id} добавлен в очередь обработки")
            
            except Exception as e:
                logger.error(f"{LOGGER_PREFIX} Ошибка при получении информации о заказе #{order_id}: {e}")
            return

    # Проверка статуса заказа
    if state and state.get("data", {}).get("order_id"):
        order_id = state["data"]["order_id"]
        try:
            order = cardinal.account.get_order(order_id)
            if order.status in [OrderStatuses.CLOSED, OrderStatuses.REFUNDED]:
                FUNPAY_STATES.pop(state_key, None)
                return
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} Ошибка проверки статуса заказа #{order_id}: {e}")
            FUNPAY_STATES.pop(state_key, None)
            return

    # Ожидание username
    if state and state["state"] == "waiting_for_username":
        username = message.text.strip()
        order_id = state["data"]["order_id"]
        stars_count = state["data"]["stars_count"]

        if not username:
            cardinal.account.send_message(message.chat_id, "❌ Отправьте username")
            return

        cardinal.account.send_message(
            message.chat_id,
            f"• Проверьте данные:\nL Username: {username}\nL Количество звёзд: {stars_count}\n\n"
            f"• Если всё верно, отправьте «+» без кавычек\nL Либо отправьте новый username"
        )
        
        FUNPAY_STATES[state_key] = {
            "state": "confirming_username",
            "data": {
                "username": username,
                "order_id": order_id,
                "stars_count": stars_count
            }
        }
        return

    # Подтверждение username
    if state and state["state"] == "confirming_username":
        order_id = state["data"]["order_id"]
        
        try:
            order = cardinal.account.get_order(order_id)
            if order.status in [OrderStatuses.CLOSED, OrderStatuses.REFUNDED]:
                FUNPAY_STATES.pop(state_key, None)
                return
        except:
            pass

        response = message.text.strip().lower()

        if response in ["+", "да", "yes", "верно", "confirm"]:
            username = state["data"]["username"]
            stars_count = state["data"]["stars_count"]
            
            queue_size = USER_ORDER_QUEUES.get(message.author_id, Queue()).qsize() + 1
            wait_time = int(queue_size * 15)
            
            cardinal.account.send_message(
                message.chat_id,
                f"⏳ Ваш запрос на отправку звёзд добавлен в очередь.\n"
                f"L Ваша позиция: {queue_size}.\n"
                f"L Примерное время ожидания: {wait_time} сек."
            )
            
            logger.info(f"{LOGGER_PREFIX} Начинаю отправку звёзд для заказа #{order_id}")
            
            perform_stars_delivery(cardinal, order_id, username, stars_count, message.chat_id, message.author_id)
        
        elif response in ["-", "нет", "no"]:
            FUNPAY_STATES[state_key] = {
                "state": "waiting_for_username",
                "data": {
                    "order_id": order_id,
                    "stars_count": state["data"]["stars_count"]
                }
            }
            cardinal.account.send_message(message.chat_id, "FPC: введите корректный username")
        
        else:
            new_username = message.text.strip()
            cardinal.account.send_message(
                message.chat_id,
                f"• Проверьте данные:\nL Username: {new_username}\nL Количество звёзд: {state['data']['stars_count']}\n\n"
                f"• Если всё верно, отправьте «+» без кавычек\nL Либо отправьте новый username"
            )
            
            FUNPAY_STATES[state_key] = {
                "state": "confirming_username",
                "data": {
                    "username": new_username,
                    "order_id": order_id,
                    "stars_count": state["data"]["stars_count"]
                }
            }

def perform_stars_delivery(cardinal, order_id: str, username: str, stars_count: int, chat_id: int, author_id: int):
    """Выполнение отправки звёзд"""
    state_key = (chat_id, author_id)
    
    try:
        order = cardinal.account.get_order(order_id)
        if order.status in [OrderStatuses.CLOSED, OrderStatuses.REFUNDED]:
            FUNPAY_STATES.pop(state_key, None)
            return
        
        cardinal.account.send_message(chat_id, f"🚀 Начинаю отправку {stars_count} звёзд...")
        
        asyncio.run(send_stars_gifts(cardinal, username, stars_count, chat_id, order_id))
        
        logger.info(f"{LOGGER_PREFIX} ✅ Заказ #{order_id} успешно выполнен!")
        
    except Exception as e:
        error_msg = str(e)
        cardinal.account.send_message(chat_id, f"❌ Произошла ошибка при выполнении вашего заказа: {error_msg}")
        logger.error(f"{LOGGER_PREFIX} Ошибка выполнения заказа #{order_id}: {error_msg}")
    
    finally:
        FUNPAY_STATES.pop(state_key, None)

def process_order(cardinal, order_id: str, chat_id: int, buyer_id: int):
    """Обработка заказа"""
    time.sleep(3)
    
    try:
        order = cardinal.account.get_order(order_id)
        
        if order.status in [OrderStatuses.CLOSED, OrderStatuses.REFUNDED]:
            FUNPAY_STATES.pop((chat_id, buyer_id), None)
            return
        
        lot_id = str(order.lot_id)
        
        if lot_id not in LOT_STARS_MAPPING:
            logger.warning(f"{LOGGER_PREFIX} Лот {lot_id} не найден в маппинге")
            return
        
        stars_per_lot = LOT_STARS_MAPPING[lot_id]
        amount = order.amount
        total_stars = stars_per_lot * amount
        
        if amount != 1:
            cardinal.account.send_message(chat_id, f"❌ Вы заказали {amount} лотов ({total_stars} Stars). Заказывайте по одному!")
            FUNPAY_STATES.pop((chat_id, buyer_id), None)
            return
        
        welcome_msg = (
            f"✨ Спасибо за заказ {total_stars} Stars!\n\n"
            f"Для отправки звёзд мне нужен ваш username Telegram.\n"
            f"Пожалуйста, отправьте его в любом формате:\n"
            f"• @username\n• username\n• ID пользователя"
        )
        
        cardinal.account.send_message(chat_id, welcome_msg)
        
        FUNPAY_STATES[(chat_id, buyer_id)] = {
            "state": "waiting_for_username",
            "data": {
                "order_id": order_id,
                "stars_count": total_stars
            }
        }
        
        logger.info(f"{LOGGER_PREFIX} Запрошен username для заказа #{order_id}")
    
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка обработки заказа #{order_id}: {e}")
        FUNPAY_STATES.pop((chat_id, buyer_id), None)

def process_user_orders(cardinal, buyer_id: int):
    """Обработка очереди заказов"""
    if buyer_id not in USER_ORDER_QUEUES:
        return
    
    queue = USER_ORDER_QUEUES[buyer_id]
    
    while not queue.empty():
        order_data = queue.get()
        process_order(cardinal, order_data["order_id"], order_data["chat_id"], buyer_id)
        queue.task_done()
    
    del USER_ORDER_QUEUES[buyer_id]

# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM ПАНЕЛЬ (4 КНОПКИ)
# ═══════════════════════════════════════════════════════════════════════════

def show_simple_panel(cardinal, chat_id: int):
    """Простая панель управления"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    status = "🟢 ВКЛЮЧЕН" if RUNNING else "🔴 ВЫКЛЮЧЕН"
    lots_count = len(LOT_STARS_MAPPING)
    
    keyboard.row(
        InlineKeyboardButton(f"Статус: {status}", callback_data="show_status"),
        InlineKeyboardButton("🔄 Вкл/Выкл", callback_data="toggle")
    )
    keyboard.row(
        InlineKeyboardButton("⚙️ API", callback_data="set_api"),
        InlineKeyboardButton(f"📌 Лоты ({lots_count})", callback_data="manage_lots")
    )
    
    text = f"""
⚡ <b>StarsGifter v{VERSION}</b>

📊 <b>Статус:</b> {status}
⚙️ <b>API ID:</b> {'✅ Установлен' if config.get('pyrogram', {}).get('api_id') else '❌ Не установлен'}
📌 <b>Лотов:</b> {lots_count}
"""
    
    cardinal.telegram.bot.send_message(
        chat_id, 
        text, 
        reply_markup=keyboard,
        parse_mode="HTML"
    )

def setup_simple_callbacks(cardinal):
    """Обработчики кнопок"""
    global RUNNING
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_status")
    def show_status_btn(call):
        status = "🟢 ВКЛЮЧЕН" if RUNNING else "🔴 ВЫКЛЮЧЕН"
        api_status = "✅ Установлен" if config.get('pyrogram', {}).get('api_id') else "❌ Не установлен"
        lots = len(LOT_STARS_MAPPING)
        
        info = f"""
<b>📊 Информация о плагине</b>

• Статус: {status}
• API ID: {api_status}
• API HASH: {'✅ Установлен' if config.get('pyrogram', {}).get('api_hash') else '❌ Не установлен'}
• Лотов настроено: {lots}
• Заказов в очереди: {sum(q.qsize() for q in USER_ORDER_QUEUES.values())}
"""
        cardinal.telegram.bot.send_message(call.message.chat.id, info, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "toggle")
    def toggle_btn(call):
        global RUNNING
        RUNNING = not RUNNING
        config["plugin_enabled"] = RUNNING
        save_config(config)
        
        status = "✅ ВКЛЮЧЕН" if RUNNING else "❌ ВЫКЛЮЧЕН"
        cardinal.telegram.bot.answer_callback_query(call.id, f"Плагин {status}", show_alert=True)
        
        cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
        show_simple_panel(cardinal, call.message.chat.id)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "set_api")
    def set_api_btn(call):
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("📝 Ввести API ID", callback_data="input_api_id"))
        keyboard.add(InlineKeyboardButton("📝 Ввести API HASH", callback_data="input_api_hash"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        
        cardinal.telegram.bot.send_message(
            call.message.chat.id,
            "⚙️ <b>Настройка API</b>\n\nВыберите что хотите изменить:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_id")
    def input_api_id_btn(call):
        msg = cardinal.telegram.bot.send_message(
            call.message.chat.id,
            "📝 Отправьте ваш API ID (числа):"
        )
        cardinal.telegram.bot.register_next_step_handler(msg, process_api_id, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_hash")
    def input_api_hash_btn(call):
        msg = cardinal.telegram.bot.send_message(
            call.message.chat.id,
            "📝 Отправьте ваш API HASH (буквы и цифры):"
        )
        cardinal.telegram.bot.register_next_step_handler(msg, process_api_hash, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "manage_lots")
    def manage_lots_btn(call):
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("➕ Добавить лот", callback_data="add_lot"))
        keyboard.add(InlineKeyboardButton("➖ Удалить лот", callback_data="remove_lot"))
        keyboard.add(InlineKeyboardButton("📋 Показать все", callback_data="show_lots"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        
        cardinal.telegram.bot.send_message(
            call.message.chat.id,
            f"📌 <b>Управление лотами</b>\n\nВсего лотов: {len(LOT_STARS_MAPPING)}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "add_lot")
    def add_lot_btn(call):
        msg = cardinal.telegram.bot.send_message(
            call.message.chat.id,
            "📝 Отправьте ID лота и количество звёзд в формате:\n\n<code>123456 100</code>\n\nГде:\n• 123456 - ID лота\n• 100 - количество звёзд",
            parse_mode="HTML"
        )
        cardinal.telegram.bot.register_next_step_handler(msg, process_add_lot, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "remove_lot")
    def remove_lot_btn(call):
        msg = cardinal.telegram.bot.send_message(
            call.message.chat.id,
            "📝 Отправьте ID лота для удаления:"
        )
        cardinal.telegram.bot.register_next_step_handler(msg, process_remove_lot, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_lots")
    def show_lots_btn(call):
        if not LOT_STARS_MAPPING:
            text = "❌ Нет добавленных лотов"
        else:
            text = "<b>📌 Список лотов:</b>\n\n"
            for lot_id, stars in LOT_STARS_MAPPING.items():
                text += f"• Лот <code>{lot_id}</code> → <b>{stars}⭐</b>\n"
        
        cardinal.telegram.bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "back_to_main")
    def back_to_main_btn(call):
        cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
        show_simple_panel(cardinal, call.message.chat.id)

# ═══════════════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ ВВОДОВ
# ═══════════════════════════════════════════════════════════════════════════

def process_api_id(message, cardinal):
    """Обработка API ID"""
    try:
        api_id = int(message.text.strip())
        config["pyrogram"]["api_id"] = api_id
        save_config(config)
        
        cardinal.telegram.bot.send_message(
            message.chat.id,
            f"✅ <b>API ID сохранён:</b> <code>{api_id}</code>",
            parse_mode="HTML"
        )
    except ValueError:
        cardinal.telegram.bot.send_message(
            message.chat.id,
            "❌ Ошибка! API ID должен быть числом"
        )

def process_api_hash(message, cardinal):
    """Обработка API HASH"""
    api_hash = message.text.strip()
    
    if len(api_hash) < 10:
        cardinal.telegram.bot.send_message(
            message.chat.id,
            "❌ Ошибка! API HASH слишком короткий"
        )
        return
    
    config["pyrogram"]["api_hash"] = api_hash
    save_config(config)
    
    cardinal.telegram.bot.send_message(
        message.chat.id,
        f"✅ <b>API HASH сохранён:</b> <code>{api_hash[:10]}...</code>",
        parse_mode="HTML"
    )

def process_add_lot(message, cardinal):
    """Добавить лот"""
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError("Неверный формат")
        
        lot_id = parts[0]
        stars = int(parts[1])
        
        LOT_STARS_MAPPING[lot_id] = stars
        config["lot_stars_mapping"][lot_id] = stars
        save_config(config)
        
        cardinal.telegram.bot.send_message(
            message.chat.id,
            f"✅ <b>Лот добавлен!</b>\n\n• ID: <code>{lot_id}</code>\n• Звёзды: <b>{stars}⭐</b>",
            parse_mode="HTML"
        )
    except:
        cardinal.telegram.bot.send_message(
            message.chat.id,
            "❌ Ошибка! Используйте формат: <code>123456 100</code>",
            parse_mode="HTML"
        )

def process_remove_lot(message, cardinal):
    """Удалить лот"""
    lot_id = message.text.strip()
    
    if lot_id in LOT_STARS_MAPPING:
        stars = LOT_STARS_MAPPING.pop(lot_id)
        config["lot_stars_mapping"].pop(lot_id, None)
        save_config(config)
        
        cardinal.telegram.bot.send_message(
            message.chat.id,
            f"✅ <b>Лот удалён!</b>\n\n• ID: <code>{lot_id}</code>\n• Было: <b>{stars}⭐</b>",
            parse_mode="HTML"
        )
    else:
        cardinal.telegram.bot.send_message(
            message.chat.id,
            f"❌ Лот <code>{lot_id}</code> не найден",
            parse_mode="HTML"
        )

# ═══════════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def init_plugin(cardinal):
    """Инициализация плагина"""
    logger.info(f"{LOGGER_PREFIX} 🚀 Инициализация {NAME} v{VERSION}")
    init_pyrogram()
    
    @cardinal.telegram.bot.message_handler(commands=["stars_panel"])
    def panel(m):
        show_simple_panel(cardinal, m.chat.id)
    
    setup_simple_callbacks(cardinal)
    
    handle_new_message.plugin_uuid = UUID
    if handle_new_message not in cardinal.new_message_handlers:
        cardinal.new_message_handlers.append(handle_new_message)
    
    logger.info(f"{LOGGER_PREFIX} ✅ Плагин загружен")


BIND_TO_PRE_INIT = [init_plugin]
BIND_TO_NEW_MESSAGE = [handle_new_message]
BIND_TO_DELETE = []
