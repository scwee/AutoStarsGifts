# AutoStarsGifts
# 🌟 StarsGifter - Плагин для FunPayCardinal

Автоматизированный плагин для отправки Telegram Stars через подарки с проверкой username и панелью управления.

## 📋 Описание

StarsGifter автоматизирует процесс продажи Telegram Stars на FunPay:
1. ✅ Покупатель оплачивает заказ на FunPay
2. ✅ Бот запрашивает Telegram username
3. ✅ Покупатель отправляет свой @username
4. ✅ Бот спрашивает подтверждение: "Username верный +/-"
5. ✅ После подтверждения автоматически отправляет подарки через Pyrogram
6. ✅ Выводит отчёт и просит оставить отзыв

## 🚀 Установка

### 1. Скачивание плагина

Скопируйте файл `StarsGifter.py` в папку `plugins/` вашего FunPayCardinal:

### 2. Установка зависимостей

Плагин автоматически установит Pyrogram при первом запуске, но вы можете установить вручную:
### 3. Настройка конфигурации

После первого запуска создастся файл `plugins/starsgifter_config.json`. Откройте его и настройте:

#### 3.1. Маппинг лотов (lot_stars_mapping)

**Как узнать lot_id:**

**Способ 1:** Создайте тестовый заказ и посмотрите в логи Cardinal:#### 

3.2. Настройка Pyrogram
{
"pyrogram": {
"api_id": int()
"api_hash": "",
"phone_number": "+1234567890",
"session_name": "starsgifter_session"
}
}

**Получение API ID и API Hash:**
1. Перейдите на https://my.telegram.org
2. Войдите в аккаунт
3. Перейдите в "API development tools"
4. Создайте приложение и скопируйте `api_id` и `api_hash`

#### 3.3. ID подарков (random_gifts)

#### 4. первый запуск

При первом запуске Pyrogram попросит код из SMS:


Введите код подтверждения из Telegram. Сессия сохранится в файл starsgifter_session.session.

🎮 Использование
Панель управления

В Telegram боте Cardinal введите команду:

/stars_panel

Появится панель с кнопками:

    🟢/🔴 Включен/Выключен — включить/выключить плагин

    📊 Статистика — статистика продаж за 7 дней

    ⚙️ Настройки — просмотр текущих настроек




#### Конфигурация
#### Полный пример конфига

{
    "lot_stars_mapping": {
        "234567": 15,
        "234568": 25,
        "234569": 50,
        "234570": 100,
        "234571": 250,
        "234572": 500,
        "234573": 1000
    },
    "random_gifts": {
        "100": [5168043875654172773, 5170690322832818290, 51705211183015, 5170564780nabled": true,
    "auto_refund": false,
    "stats": {},
    "pyrogram": {
        "api_id": int(1234556),
        "api_hash": "rando",
        "phone_number": "+79001234567",
        "session_name": "starsgifter_session"
    }
}

#### LOGS

🚀 Инициализация StarsGifter v1.5
📋 Загружено 7 лотов
✅ Pyrogram клиент запущен
✅ Команда /stars_panel зарегистрирована
📦 Новый заказ #12345, lot_id: 234570, покупатель: User
✅ chat_id получен: 987654
✅ Приветственное сообщение отправлено
📝 Username @durov получен
✅ Отправлен подарок 100 звёзд


#### Параметры


lot_stars_mapping	Соответствие lot_id → количество звёзд	| Object
random_gifts	ID подарков для разных номиналов	| Object
plugin_enabled	Включен ли плагин	| Boolean
auto_refund	Автовозврат при ошибках	| Boolean
stats	Статистика (автоматически)| Object
pyrogram	Настройки Pyrogram | Object

ДОНАТ 
TON: UQBNtmJU2OQ7iDbz9ngl8zYD_JFSoQTvbJ3q3pXSK3iGiMf3
ETH: 0x83Ca50C7D33aD6E086d386B1F6dB2908a1d158f1
TRX: TEkxC7hNTR4iVqiGEy3XEc8tzkGGaB3FSR



