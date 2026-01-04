
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

import asyncio
import importlib.util
import json
import logging
import os
import random

from FunPayAPI.updater.events import NewOrderEvent, NewMessageEvent
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if TYPE_CHECKING:
    from cardinal import Cardinal
    from pyrogram import Client

# ═══════════════════════════════════════════════════════════════════════════
# МЕТАДАННЫЕ
# ═══════════════════════════════════════════════════════════════════════════

NAME = "StarsGifter"
VERSION = "3.2"
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
        "15": [5170145012310081615, 5170233102089322756],
    },
    "plugin_enabled": True,
    "pyrogram": {
        "api_id": 0,
        "api_hash": "",
        "phone_number": "",
        "session_name": "starsgifter_session",
    },
}

CONFIRM_RESPONSES = {"+", "да", "yes", "верно", "confirm"}
CANCEL_RESPONSES = {"-", "нет", "no"}

logger = logging.getLogger("FPC.starsgifter")
logger.setLevel(logging.DEBUG)
LOGGER_PREFIX = "[StarsGifter]"


class StarsGifterPlugin:
    def __init__(self) -> None:
        self.config = self.load_config()
        self.lot_stars_mapping = {
            str(k): int(v) for k, v in self.config.get("lot_stars_mapping", {}).items()
        }
        self.random_gifts = {
            int(k): v
            for k, v in self.config.get("random_gifts", DEFAULT_CONFIG["random_gifts"]).items()
        }
        self.running = self.config.get("plugin_enabled", True)
        self.pyrogram_client: Optional["Client"] = None
        self.funpay_states: Dict[Tuple[int, int], Dict] = {}

    @staticmethod
    def load_config() -> Dict:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_config(cfg: Dict) -> None:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    def persist_config(self) -> None:
        self.save_config(self.config)

    def get_pyrogram_client(self) -> "Client":
        if importlib.util.find_spec("pyrogram") is None:
            raise RuntimeError("pyrogram не установлен. Установите модуль pyrogram.")

        from pyrogram import Client

        pyrogram_config = self.config.get("pyrogram", DEFAULT_CONFIG["pyrogram"])
        return Client(
            pyrogram_config["session_name"],
            api_id=pyrogram_config["api_id"],
            api_hash=pyrogram_config["api_hash"],
            phone_number=pyrogram_config.get("phone_number", ""),
        )

    def init_pyrogram(self) -> bool:
        pyrogram_config = self.config.get("pyrogram", DEFAULT_CONFIG["pyrogram"])

        if not pyrogram_config.get("api_id") or not pyrogram_config.get("api_hash"):
            logger.warning(f"{LOGGER_PREFIX} API ID или API HASH не установлены")
            return False

        try:
            self.pyrogram_client = self.get_pyrogram_client()
            self.pyrogram_client.start()
            logger.info(f"{LOGGER_PREFIX} ✅ Pyrogram запущен")
            return True
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} ❌ Ошибка Pyrogram: {e}")
            return False

    @staticmethod
    async def calc_gifts_quantity(quantity: int) -> Optional[Dict[int, int]]:
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

    @staticmethod
    def format_gifts_result(gifts_dict: Dict[int, int]) -> str:
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

    async def send_stars_gifts(
        self,
        cardinal: "Cardinal",
        username: str,
        stars_count: int,
        chat_id: int,
        order_id: Optional[str] = None,
    ) -> bool:
        """Отправить звёзды"""
        try:
            if self.pyrogram_client is None or not self.pyrogram_client.is_connected:
                cardinal.account.send_message(chat_id, "❌ Клиент Telegram не подключен")
                return False

            gifts_distribution = await self.calc_gifts_quantity(stars_count)
            if not gifts_distribution:
                cardinal.account.send_message(chat_id, "❌ Ошибка расчёта подарков")
                return False

            try:
                user = await self.pyrogram_client.get_users([username])
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
                        gift_id = random.choice(self.random_gifts[price])
                        await self.pyrogram_client.send_gift(chat_id=username, gift_id=gift_id)
                        success_count += 1
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"{LOGGER_PREFIX} Ошибка отправки подарка {price}: {e}")
                        failed_count += 1

            report = f"✅ Отправлено: {stars_count} stars\n\n" + self.format_gifts_result(
                gifts_distribution
            )
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

    def handle_new_order(self, cardinal: "Cardinal", event: NewOrderEvent, *args) -> None:
        """Обработка нового заказа - ОСНОВНАЯ ФУНКЦИЯ"""
        if not self.running:
            return

        try:
            order = event.order
            order_id = order.id
            chat_id = order.chat_id
            buyer_id = order.buyer_id
            lot_id = str(order.lot_id) if hasattr(order, "lot_id") else None

            logger.info(f"{LOGGER_PREFIX} 📦 Новый заказ #{order_id} | Лот: {lot_id}")

            if not lot_id or lot_id not in self.lot_stars_mapping:
                logger.warning(f"{LOGGER_PREFIX} ⚠️ Лот {lot_id} не в маппинге")
                return

            stars_per_lot = self.lot_stars_mapping[lot_id]
            amount = order.amount if hasattr(order, "amount") else 1
            total_stars = stars_per_lot * amount

            if amount != 1:
                cardinal.account.send_message(
                    chat_id,
                    f"❌ Заказали {amount} лотов ({total_stars} Stars). По одному!",
                )
                logger.warning(
                    f"{LOGGER_PREFIX} ⚠️ Заказ #{order_id} - неверное кол-во ({amount})"
                )
                return

            welcome_msg = (
                f"✨ Спасибо за заказ {total_stars} Stars!\n\n"
                "Отправьте ваш username Telegram:\n"
                "• @username\n• username\n• ID пользователя"
            )

            cardinal.account.send_message(chat_id, welcome_msg)

            state_key = (chat_id, buyer_id)
            self.funpay_states[state_key] = {
                "state": "waiting_for_username",
                "data": {
                    "order_id": order_id,
                    "chat_id": chat_id,
                    "stars_count": total_stars,
                },
            }

            logger.info(f"{LOGGER_PREFIX} ✅ Заказ #{order_id} обработан. Ожидаю username")

        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} ❌ Ошибка обработки заказа: {e}")

    def handle_new_message(self, cardinal: "Cardinal", event: NewMessageEvent, *args) -> None:
        """Обработка сообщений от пользователя"""
        if not self.running:
            return

        message = event.message
        state_key = (message.chat_id, message.author_id)
        state = self.funpay_states.get(state_key)

        if not state:
            return

        if state["state"] == "waiting_for_username":
            username = message.text.strip()
            order_id = state["data"]["order_id"]
            stars_count = state["data"]["stars_count"]

            if not username:
                cardinal.account.send_message(message.chat_id, "❌ Отправьте username")
                return

            cardinal.account.send_message(
                message.chat_id,
                f"✓ Проверьте данные:\n• Username: {username}\n• Звёзды: {stars_count}\n\n"
                "Отправьте «+» для подтверждения или новый username",
            )

            self.funpay_states[state_key] = {
                "state": "confirming_username",
                "data": {
                    "username": username,
                    "order_id": order_id,
                    "stars_count": stars_count,
                    "chat_id": message.chat_id,
                },
            }
            return

        if state["state"] == "confirming_username":
            order_id = state["data"]["order_id"]
            response = message.text.strip().lower()

            if response in CONFIRM_RESPONSES:
                username = state["data"]["username"]
                stars_count = state["data"]["stars_count"]
                chat_id = state["data"]["chat_id"]

                cardinal.account.send_message(chat_id, f"🚀 Отправляю {stars_count} звёзд...")
                logger.info(f"{LOGGER_PREFIX} 📤 Отправка #{order_id} | {username} | {stars_count}★")

                asyncio.run(self.send_stars_gifts(cardinal, username, stars_count, chat_id, order_id))

                logger.info(f"{LOGGER_PREFIX} ✅ Заказ #{order_id} завершён!")
                self.funpay_states.pop(state_key, None)
                return

            if response in CANCEL_RESPONSES:
                self.funpay_states[state_key] = {
                    "state": "waiting_for_username",
                    "data": {
                        "order_id": order_id,
                        "stars_count": state["data"]["stars_count"],
                        "chat_id": state["data"]["chat_id"],
                    },
                }
                cardinal.account.send_message(message.chat_id, "🔄 Отправьте новый username")
                return

            new_username = message.text.strip()
            cardinal.account.send_message(
                message.chat_id,
                f"✓ Проверьте:\n• Username: {new_username}\n• Звёзды: {state['data']['stars_count']}\n\n"
                "Отправьте «+» или новый username",
            )

            self.funpay_states[state_key] = {
                "state": "confirming_username",
                "data": {
                    "username": new_username,
                    "order_id": order_id,
                    "stars_count": state["data"]["stars_count"],
                    "chat_id": state["data"]["chat_id"],
                },
            }

    def show_simple_panel(self, cardinal: "Cardinal", chat_id: int) -> None:
        keyboard = InlineKeyboardMarkup(row_width=2)

        status = "🟢 ВКЛЮЧЕН" if self.running else "🔴 ВЫКЛЮЧЕН"
        lots_count = len(self.lot_stars_mapping)

        keyboard.row(
            InlineKeyboardButton(f"Статус: {status}", callback_data="show_status"),
            InlineKeyboardButton("🔄 Вкл/Выкл", callback_data="toggle"),
        )
        keyboard.row(
            InlineKeyboardButton("⚙️ API", callback_data="set_api"),
            InlineKeyboardButton(f"📌 Лоты ({lots_count})", callback_data="manage_lots"),
        )

        text = f"""
⚡ <b>StarsGifter v{VERSION}</b>

📊 <b>Статус:</b> {status}
⚙️ <b>API ID:</b> {"✅" if self.config.get("pyrogram", {}).get("api_id") else "❌"}
📌 <b>Лотов:</b> {lots_count}
"""

        cardinal.telegram.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

    def setup_simple_callbacks(self, cardinal: "Cardinal") -> None:
        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_status")
        def show_status_btn(call):
            status = "🟢 ВКЛЮЧЕН" if self.running else "🔴 ВЫКЛЮЧЕН"
            api_id_ok = "✅" if self.config.get("pyrogram", {}).get("api_id") else "❌"
            api_hash_ok = "✅" if self.config.get("pyrogram", {}).get("api_hash") else "❌"
            lots = len(self.lot_stars_mapping)

            info = (
                "<b>📊 Информация</b>\n\n"
                f"• Статус: {status}\n"
                f"• API ID: {api_id_ok}\n"
                f"• API HASH: {api_hash_ok}\n"
                f"• Лотов: {lots}"
            )
            cardinal.telegram.bot.send_message(call.message.chat.id, info, parse_mode="HTML")

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "toggle")
        def toggle_btn(call):
            self.running = not self.running
            self.config["plugin_enabled"] = self.running
            self.persist_config()

            status = "✅" if self.running else "❌"
            cardinal.telegram.bot.answer_callback_query(call.id, f"Плагин {status}", show_alert=True)
            cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
            self.show_simple_panel(cardinal, call.message.chat.id)

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "set_api")
        def set_api_btn(call):
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton("📝 API ID", callback_data="input_api_id"))
            keyboard.add(InlineKeyboardButton("📝 API HASH", callback_data="input_api_hash"))
            keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
            cardinal.telegram.bot.send_message(
                call.message.chat.id,
                "⚙️ <b>API</b>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_id")
        def input_api_id_btn(call):
            msg = cardinal.telegram.bot.send_message(call.message.chat.id, "📝 API ID:")
            cardinal.telegram.bot.register_next_step_handler(msg, self.process_api_id, cardinal)

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "input_api_hash")
        def input_api_hash_btn(call):
            msg = cardinal.telegram.bot.send_message(call.message.chat.id, "📝 API HASH:")
            cardinal.telegram.bot.register_next_step_handler(msg, self.process_api_hash, cardinal)

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "manage_lots")
        def manage_lots_btn(call):
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton("➕ Добавить", callback_data="add_lot"))
            keyboard.add(InlineKeyboardButton("➖ Удалить", callback_data="remove_lot"))
            keyboard.add(InlineKeyboardButton("📋 Показать", callback_data="show_lots"))
            keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
            cardinal.telegram.bot.send_message(
                call.message.chat.id,
                f"📌 <b>Лоты ({len(self.lot_stars_mapping)})</b>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "add_lot")
        def add_lot_btn(call):
            msg = cardinal.telegram.bot.send_message(
                call.message.chat.id,
                "Формат: <code>123456 100</code>",
                parse_mode="HTML",
            )
            cardinal.telegram.bot.register_next_step_handler(msg, self.process_add_lot, cardinal)

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "remove_lot")
        def remove_lot_btn(call):
            msg = cardinal.telegram.bot.send_message(call.message.chat.id, "ID лота:")
            cardinal.telegram.bot.register_next_step_handler(msg, self.process_remove_lot, cardinal)

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "show_lots")
        def show_lots_btn(call):
            if not self.lot_stars_mapping:
                text = "❌ Пусто"
            else:
                text = "<b>📌 Лоты:</b>\n\n"
                for lot_id, stars in self.lot_stars_mapping.items():
                    text += f"• <code>{lot_id}</code> → <b>{stars}⭐</b>\n"
            cardinal.telegram.bot.send_message(call.message.chat.id, text, parse_mode="HTML")

        @cardinal.telegram.bot.callback_query_handler(func=lambda c: c.data == "back_to_main")
        def back_to_main_btn(call):
            cardinal.telegram.bot.delete_message(call.message.chat.id, call.message.message_id)
            self.show_simple_panel(cardinal, call.message.chat.id)

    def process_api_id(self, message, cardinal: "Cardinal") -> None:
        try:
            api_id = int(message.text.strip())
            self.config["pyrogram"]["api_id"] = api_id
            self.persist_config()
            cardinal.telegram.bot.send_message(
                message.chat.id, f"✅ API ID: <code>{api_id}</code>", parse_mode="HTML"
            )
        except (TypeError, ValueError):
            cardinal.telegram.bot.send_message(message.chat.id, "❌ Ошибка")

    def process_api_hash(self, message, cardinal: "Cardinal") -> None:
        api_hash = message.text.strip()
        self.config["pyrogram"]["api_hash"] = api_hash
        self.persist_config()
        cardinal.telegram.bot.send_message(
            message.chat.id,
            f"✅ API HASH: <code>{api_hash[:10]}...</code>",
            parse_mode="HTML",
        )

    def process_add_lot(self, message, cardinal: "Cardinal") -> None:
        try:
            parts = message.text.strip().split()
            lot_id = parts[0]
            stars = int(parts[1])
            self.lot_stars_mapping[lot_id] = stars
            self.config["lot_stars_mapping"][lot_id] = stars
            self.persist_config()
            cardinal.telegram.bot.send_message(
                message.chat.id,
                f"✅ Лот <code>{lot_id}</code> → <b>{stars}⭐</b>",
                parse_mode="HTML",
            )
        except (IndexError, ValueError):
            cardinal.telegram.bot.send_message(message.chat.id, "❌ Ошибка")

    def process_remove_lot(self, message, cardinal: "Cardinal") -> None:
        lot_id = message.text.strip()
        if lot_id in self.lot_stars_mapping:
            self.lot_stars_mapping.pop(lot_id)
            self.config["lot_stars_mapping"].pop(lot_id, None)
            self.persist_config()
            cardinal.telegram.bot.send_message(
                message.chat.id,
                "✅ Лот удалён",
                parse_mode="HTML",
            )
        else:
            cardinal.telegram.bot.send_message(message.chat.id, "❌ Не найден", parse_mode="HTML")

    def init_plugin(self, cardinal: "Cardinal") -> None:
        logger.info(f"{LOGGER_PREFIX} 🚀 {NAME} v{VERSION}")
        self.init_pyrogram()

        @cardinal.telegram.bot.message_handler(commands=["stars_panel"])
        def panel(m):
            self.show_simple_panel(cardinal, m.chat.id)

        self.setup_simple_callbacks(cardinal)
        logger.info(f"{LOGGER_PREFIX} ✅ Загружен")


PLUGIN = StarsGifterPlugin()


def init_plugin(cardinal: "Cardinal") -> None:
    PLUGIN.init_plugin(cardinal)


def handle_new_order(cardinal: "Cardinal", event: NewOrderEvent, *args) -> None:
    PLUGIN.handle_new_order(cardinal, event, *args)


def handle_new_message(cardinal: "Cardinal", event: NewMessageEvent, *args) -> None:
    PLUGIN.handle_new_message(cardinal, event, *args)


BIND_TO_PRE_INIT = [init_plugin]
BIND_TO_NEW_ORDER = [handle_new_order]
BIND_TO_NEW_MESSAGE = [handle_new_message]
BIND_TO_DELETE = []
