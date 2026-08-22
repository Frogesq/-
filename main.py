#!/usr/bin/env python3
# SWILL Business Extractor - ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
import signal
import sys
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramConflictError

# ======================================================
# КОНФИГ
# ======================================================
BOT_TOKEN = '8389370808:AAEmrhiar8I9NALB913k130BDOOJsEC1AvI'  # ⚠️ ОБНОВИ ТОКЕН!
TARGET_ACCOUNT_ID = 8839956404
SAVE_MEDIA = True
# ======================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Папка для дампа
BASE_PATH = Path.cwd() / f'dump_{TARGET_ACCOUNT_ID}_{int(time.time())}'
os.makedirs(BASE_PATH, exist_ok=True)

# SQLite
conn = sqlite3.connect(BASE_PATH / 'data.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        chat_title TEXT,
        date TEXT,
        from_id TEXT,
        from_name TEXT,
        text TEXT,
        media_type TEXT,
        media_path TEXT,
        is_deleted BOOLEAN DEFAULT 0,
        target_account_id INTEGER
    )
''')
conn.commit()

stats = {'total': 0, 'media': 0, 'errors': 0}

async def log(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(BASE_PATH / 'log.txt', 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] {text}\n')
    print(f'[{timestamp}] {text}')

@dp.message()
async def handle_message(msg: types.Message):
    if msg.from_user and msg.from_user.id == TARGET_ACCOUNT_ID:
        try:
            chat_title = msg.chat.title or msg.chat.full_name or str(msg.chat.id)
            
            cursor.execute('''
                INSERT OR REPLACE INTO messages 
                (id, chat_id, chat_title, date, from_id, from_name, text, target_account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                msg.message_id,
                msg.chat.id,
                chat_title,
                str(msg.date),
                str(msg.from_user.id),
                msg.from_user.full_name or 'unknown',
                msg.text or msg.caption or '',
                TARGET_ACCOUNT_ID
            ))
            conn.commit()
            stats['total'] += 1
            await log(f'✅ Сохранено сообщение {msg.message_id}')
            
        except Exception as e:
            stats['errors'] += 1
            await log(f'❌ Ошибка: {e}')

@dp.my_chat_member()
async def on_bot_added(event: types.ChatMemberUpdated):
    me = await bot.get_me()
    if event.new_chat_member.user.id == me.id:
        await log(f'➕ Бот добавлен в чат: {event.chat.id}')

async def shutdown():
    await log('🛑 Завершение работы, сохраняю данные...')
    conn.commit()
    await log(f'📊 Всего сохранено: {stats["total"]} сообщений')
    await bot.session.close()
    sys.exit(0)

async def main():
    # Обработка сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    await log('='*60)
    await log('🚀 SWILL БОТ ЗАПУЩЕН')
    await log(f'🎯 Целевой ID: {TARGET_ACCOUNT_ID}')
    await log(f'📁 Папка: {BASE_PATH}')
    
    print(f'\n{"="*60}')
    print(f'🚀 SWILL БОТ ЗАПУЩЕН')
    print(f'🎯 Цель: {TARGET_ACCOUNT_ID}')
    print(f'📁 Папка: {BASE_PATH}')
    print(f'{"="*60}\n')
    
    # Проверяем бота
    try:
        me = await bot.get_me()
        await log(f'🤖 Бот: @{me.username} (ID: {me.id})')
        print(f'🤖 Бот: @{me.username} (ID: {me.id})')
    except Exception as e:
        await log(f'❌ Ошибка: {e}')
        print(f'❌ Ошибка: {e}')
        return
    
    # Удаляем вебхук
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await log('✅ Вебхук удалён')
        print('✅ Вебхук удалён')
    except Exception as e:
        await log(f'⚠️ Ошибка удаления вебхука: {e}')
    
    # Запускаем polling
    try:
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=['message', 'my_chat_member']
        )
    except TelegramConflictError as e:
        await log(f'❌ КОНФЛИКТ: {e}')
        print(f'\n❌ КОНФЛИКТ!')
        print('Решение: сбрось токен через @BotFather')
        await bot.session.close()
        sys.exit(1)
    except Exception as e:
        await log(f'❌ Ошибка: {e}')
        await bot.session.close()
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())  # ✅ ПРАВИЛЬНО! БЕЗ "=" В КОНЦЕ!
    except KeyboardInterrupt:
        print('\n👋 Остановка пользователем')
    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')
