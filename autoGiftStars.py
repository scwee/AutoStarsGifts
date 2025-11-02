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
from FunPayAPI.updater.events import NewOrderEvent, NewMessageEvent
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

try:
    from pyrogram import Client
except ImportError:
    import subprocess
    import sys
    print("Установка модуля pyrogram...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram"])
    from pyrogram import Client

# ═══════════════════════════════════════════════════════════════════════════
# МЕТАДАННЫЕ
# ═══════════════════════════════════════════════════════════════════════════

NAME = "StarsGifter"
VERSION = "3.1(С божьей помощью работай, умоляю)"
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
FUNPAY_STATES = {}

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def load_config():
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

config = load_config()
LOT_STARS_MAPPING = {str(k): int(v) for k, v in config.get("lot_stars_mapping", {}).items()}
RANDOM_GIFTS = {int(k): v for k, v in config.get("random_gifts", DEFAULT_CONFIG["random_gifts"]).items()}
RUNNING = config.get("plugin_enabled", True)

# ═══════════════════════════════════════════════════════════════════════════
# PYROGRAM
# ═══════════════════════════════════════════════════════════════════════════

def init_pyrogram():
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
        logger.info(f"{LOGGER_PREFIX} ✅ Pyrogram запущен")
        return True
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} ❌ Ошибка Pyrogram: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ОТПРАВКА ЗВЁЗД
# ═══════════════════════════════════════════════════════════════════════════

async def calc_gifts_quantity(quantity):
    """Расчёт подарков"""
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
    """Форматирование подарков"""
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
            cardinal.account.send_message(chat_id, "❌ Клиент Telegram не подключен")
            return False

        gifts_distribution = await calc_gifts_quantity(stars_count)
        if not gifts_distribution:
            cardinal.account.send_message(chat_id, "❌ Ошибка расчёта подарков")
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
            report += f"\n\n❌ Не удалось: {failed_count}"

        cardinal.account.send_message(chat_id, report)

        if failed_count == 0:
            review_msg = (
                "✅ Звезды отправлены на ваш аккаунт!\n\n"
                "❤️ Подтвердите заказ и напишите отзыв."
            )
            if order_id:
                review_msg += f"\n✨ https://funpay.com/orders/{order_id}/"
            cardinal.account.send_message(chat_id, review_msg)
        
        return True

    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка отправки: {e}")
        cardinal.account.send_message(chat_id, f"❌ Ошибка: {str(e)}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА НОВЫХ ЗАКАЗОВ (BIND_TO_NEW_ORDER)
# ═══════════════════════════════════════════════════════════════════════════

def handle_new_order(cardinal, event: NewOrderEvent, *args):
    """Обработка нового заказа - ОСНОВНАЯ ФУНКЦИЯ"""
    global RUNNING
    
    if not RUNNING:
        return
    
    try:
        order = event.order
        order_id = order.id
        chat_id = order.chat_id
        buyer_id = order.buyer_id
        lot_id = str(order.lot_id) if hasattr(order, 'lot_id') else None
        
        logger.info(f"{LOGGER_PREFIX} 📦 Новый заказ #{order_id} | Лот: {lot_id}")
        
        # Проверка лота
        if not lot_id or lot_id not in LOT_STARS_MAPPING:
            logger.warning(f"{LOGGER_PREFIX} ⚠️ Лот {lot_id} не в маппинге")
            return
        
        # Расчет звёзд
        stars_per_lot = LOT_STARS_MAPPING[lot_id]
        amount = order.amount if hasattr(order, 'amount') else 1
        total_stars = stars_per_lot * amount
        
        # Проверка количества
        if amount != 1:
            cardinal.account.send_message(
                chat_id, 
                f"❌ Заказали {amount} лотов ({total_stars} Stars). По одному!"
            )
            logger.warning(f"{LOGGER_PREFIX} ⚠️ Заказ #{order_id} - неверное кол-во ({amount})")
            return
        
        # Отправить приветствие
        welcome_msg = (
            f"✨ Спасибо за заказ {total_stars} Stars!\n\n"
            f"Отправьте ваш username Telegram:\n"
            f"• @username\n• username\n• ID пользователя"
        )
        
        cardinal.account.send_message(chat_id, welcome_msg)
        
        # Сохранить состояние
        state_key = (chat_id, buyer_id)
        FUNPAY_STATES[state_key] = {
            "state": "waiting_for_username",
            "data": {
                "order_id": order_id,
                "chat_id": chat_id,
                "stars_count": total_stars
            }
        }
        
        logger.info(f"{LOGGER_PREFIX} ✅ Заказ #{order_id} обработан. Ожидаю username")
    
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} ❌ Ошибка обработки заказа: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА СООБЩЕНИЙ (ДИАЛОГ С ПОЛЬЗОВАТЕЛЕМ)
# ═══════════════════════════════════════════════════════════════════════════

def handle_new_message(cardinal, event: NewMessageEvent, *args):
    """Обработка сообщений от пользователя"""
    global FUNPAY_STATES, RUNNING
    
    if not RUNNING:
        return
    
    message = event.message
    state_key = (message.chat_id, message.author_id)
    state = FUNPAY_STATES.get(state_key)
    
    if not state:
        return
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ОЖИДАНИЕ USERNAME
    # ═══════════════════════════════════════════════════════════════════════════
    if state["state"] == "waiting_for_username":
        username = message.text.strip()
        order_id = state["data"]["order_id"]
        stars_count = state["data"]["stars_count"]
        
        if not username:
            cardinal.account.send_message(message.chat_id, "❌ Отправьте username")
            return
        
        # Запросить подтверждение
        cardinal.account.send_message(
            message.chat_id,
            f"✓ Проверьте данные:\n• Username: {username}\n• Звёзды: {stars_count}\n\n"
            f"Отправьте «+» для подтверждения или новый username"
        )
        
        FUNPAY_STATES[state_key] = {
            "state": "confirming_username",
            "data": {
                "username": username,
                "order_id": order_id,
                "stars_count": stars_count,
                "chat_id": message.chat_id
            }
        }
        return
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ПОДТВЕРЖДЕНИЕ USERNAME
    # ═══════════════════════════════════════════════════════════════════════════
    if state["state"] == "confirming_username":
        order_id = state["data"]["order_id"]
        response = message.text.strip().lower()
        
        if response in ["+", "да", "yes", "верно", "confirm"]:
            # ПОДТВЕРЖДЕНО - ОТПРАВЛЯЕМ
            username = state["data"]["username"]
            stars_count = state["data"]["stars_count"]
            chat_id = state["data"]["chat_id"]
            
            cardinal.account.send_message(chat_id, f"🚀 Отправляю {stars_count} звёзд...")
            
            logger.info(f"{LOGGER_PREFIX} 📤 Отправка #{order_id} | {username} | {stars_count}★")
            
            asyncio.run(send_stars_gifts(cardinal, username, stars_count, chat_id, order_id))
            
            logger.info(f"{LOGGER_PREFIX} ✅ Заказ #{order_id} завершён!")
            FUNPAY_STATES.pop(state_key, None)
        
        elif response in ["-", "нет", "no"]:
            # ОТМЕНА - НОВЫЙ USERNAME
            FUNPAY_STATES[state_key] = {
                "state": "waiting_for_username",
                "data": {
                    "order_id": order_id,
                    "stars_count": state["data"]["stars_count"],
                    "chat_id": state["data"]["chat_id"]
                }
            }
            cardinal.account.send_message(message.chat_id, "🔄 Отправьте новый username")
        
        else:
            # ДРУГОЙ USERNAME
            new_username = message.text.strip()
            cardinal.account.send_message(
                message.chat_id,
                f"✓ Проверьте:\n• Username: {new_username}\n• Звёзды: {state['data']['stars_count']}\n\n"
                f"Отправьте «+» или новый username"
            )
            
            FUNPAY_STATES[state_key] = {
                "state": "confirming_username",
                "data": {
                    "username": new_username,
                    "order_id": order_id,
                    "stars_count": state["data"]["stars_count"],
                    "chat_id": state["data"]["chat_id"]
                }
            }

# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM ПАНЕЛЬ
# ═══════════════════════════════════════════════════════════════════════════

def show_simple_panel(cardinal, chat_id: int):
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
⚙️ <b>API ID:</b> {'✅' if config.get('pyrogram', {}).get('api_id') else '❌'}
📌 <b>Лотов:</b> {lots_count}
"""
    
    cardinal.telegram.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

def setup_simple_callbacks(cardinal):
    global RUNNING
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_status")
    def show_status_btn(call):
        status = "🟢 ВКЛЮЧЕН" if RUNNING else "🔴 ВЫКЛЮЧЕН"
        api_id_ok = "✅" if config.get('pyrogram', {}).get('api_id') else "❌"
        api_hash_ok = "✅" if config.get('pyrogram', {}).get('api_hash') else "❌"
        lots = len(LOT_STARS_MAPPING)
        
        info = f"<b>📊 Информация</b>\n\n• Статус: {status}\n• API ID: {api_id_ok}\n• API HASH: {api_hash_ok}\n• Лотов: {lots}"
        cardinal.telegram.bot.send_message(call.message.chat.id, info, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "toggle")
    def toggle_btn(call):
        global RUNNING
        RUNNING = not RUNNING
        config["plugin_enabled"] = RUNNING
        save_config(config)
        
        status = "✅" if RUNNING else "❌"
        cardinal.telegram.bot.answer_callback_query(call.id, f"Плагин {status}", show_alert=True)
        cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
        show_simple_panel(cardinal, call.message.chat.id)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "set_api")
    def set_api_btn(call):
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("📝 API ID", callback_data="input_api_id"))
        keyboard.add(InlineKeyboardButton("📝 API HASH", callback_data="input_api_hash"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        cardinal.telegram.bot.send_message(call.message.chat.id, "⚙️ <b>API</b>", reply_markup=keyboard, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_id")
    def input_api_id_btn(call):
        msg = cardinal.telegram.bot.send_message(call.message.chat.id, "📝 API ID:")
        cardinal.telegram.bot.register_next_step_handler(msg, process_api_id, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_hash")
    def input_api_hash_btn(call):
        msg = cardinal.telegram.bot.send_message(call.message.chat.id, "📝 API HASH:")
        cardinal.telegram.bot.register_next_step_handler(msg, process_api_hash, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "manage_lots")
    def manage_lots_btn(call):
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("➕ Добавить", callback_data="add_lot"))
        keyboard.add(InlineKeyboardButton("➖ Удалить", callback_data="remove_lot"))
        keyboard.add(InlineKeyboardButton("📋 Показать", callback_data="show_lots"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        cardinal.telegram.bot.send_message(call.message.chat.id, f"📌 <b>Лоты ({len(LOT_STARS_MAPPING)})</b>", reply_markup=keyboard, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "add_lot")
    def add_lot_btn(call):
        msg = cardinal.telegram.bot.send_message(call.message.chat.id, "Формат: <code>123456 100</code>", parse_mode="HTML")
        cardinal.telegram.bot.register_next_step_handler(msg, process_add_lot, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "remove_lot")
    def remove_lot_btn(call):
        msg = cardinal.telegram.bot.send_message(call.message.chat.id, "ID лота:")
        cardinal.telegram.bot.register_next_step_handler(msg, process_remove_lot, cardinal)
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_lots")
    def show_lots_btn(call):
        if not LOT_STARS_MAPPING:
            text = "❌ Пусто"
        else:
            text = "<b>📌 Лоты:</b>\n\n"
            for lot_id, stars in LOT_STARS_MAPPING.items():
                text += f"• <code>{lot_id}</code> → <b>{stars}⭐</b>\n"
        cardinal.telegram.bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "back_to_main")
    def back_to_main_btn(call):
        cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
        show_simple_panel(cardinal, call.message.chat.id)

def process_api_id(message, cardinal):
    try:
        api_id = int(message.text.strip())
        config["pyrogram"]["api_id"] = api_id
        save_config(config)
        cardinal.telegram.bot.send_message(message.chat.id, f"✅ API ID: <code>{api_id}</code>", parse_mode="HTML")
    except:
        cardinal.telegram.bot.send_message(message.chat.id, "❌ Ошибка")

def process_api_hash(message, cardinal):
    api_hash = message.text.strip()
    config["pyrogram"]["api_hash"] = api_hash
    save_config(config)
    cardinal.telegram.bot.send_message(message.chat.id, f"✅ API HASH: <code>{api_hash[:10]}...</code>", parse_mode="HTML")

def process_add_lot(message, cardinal):
    try:
        parts = message.text.strip().split()
        lot_id = parts[0]
        stars = int(parts[1])
        LOT_STARS_MAPPING[lot_id] = stars
        config["lot_stars_mapping"][lot_id] = stars
        save_config(config)
        cardinal.telegram.bot.send_message(message.chat.id, f"✅ Лот <code>{lot_id}</code> → <b>{stars}⭐</b>", parse_mode="HTML")
    except:
        cardinal.telegram.bot.send_message(message.chat.id, "❌ Ошибка")

def process_remove_lot(message, cardinal):
    lot_id = message.text.strip()
    if lot_id in LOT_STARS_MAPPING:
        LOT_STARS_MAPPING.pop(lot_id)
        config["lot_stars_mapping"].pop(lot_id, None)
        save_config(config)
        cardinal.telegram.bot.send_message(message.chat.id, f"✅ Лот удалён", parse_mode="HTML")
    else:
        cardinal.telegram.bot.send_message(message.chat.id, "❌ Не найден", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def init_plugin(cardinal):
    logger.info(f"{LOGGER_PREFIX} 🚀 {NAME} v{VERSION}")
    init_pyrogram()
    
    @cardinal.telegram.bot.message_handler(commands=["stars_panel"])
    def panel(m):
        show_simple_panel(cardinal, m.chat.id)
    
    setup_simple_callbacks(cardinal)
    logger.info(f"{LOGGER_PREFIX} ✅ Загружен")

# ═══════════════════════════════════════════════════════════════════════════
# BIND POINTS
# ═══════════════════════════════════════════════════════════════════════════

BIND_TO_PRE_INIT = [init_plugin]
BIND_TO_NEW_ORDER = [handle_new_order]
BIND_TO_NEW_MESSAGE = [handle_new_message]
BIND_TO_DELETE = []
