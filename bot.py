import logging
import os
import asyncio
import json
import sqlite3
import shutil
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    print("="*60)
    print("❌ ОШИБКА: ТОКЕН БОТА НЕ НАЙДЕН!")
    print("="*60)
    print("🔧 Инструкция для bothost.ru:")
    print("1. Зайдите в панель управления bothost.ru")
    print("2. Откройте раздел 'Переменные окружения'")
    print("3. Добавьте новую переменную:")
    print("   Имя: BOT_TOKEN")
    print("   Значение: ваш_токен_от_BotFather")
    print("4. Сохраните и перезапустите бота")
    print("="*60)
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

ADMIN_ID = 5809098591
CREATOR_USERNAME = "@Strann1k_fiol"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== ПУТИ К ФАЙЛАМ ==========
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "clients.db"
USERS_DB_PATH = DATA_DIR / "users.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

print(f"📁 Папка данных: {DATA_DIR}")
print(f"📁 Папка бэкапов: {BACKUP_DIR}")

# ========== ИНИЦИАЛИЗАЦИЯ БАЗ ДАННЫХ ==========
def init_db():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                version TEXT,
                downloads INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS resourcepacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                version TEXT,
                author TEXT,
                downloads INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                version TEXT,
                downloads INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                pack_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, pack_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных клиентов готова")
    except Exception as e:
        print(f"❌ Ошибка при создании базы клиентов: {e}")

def init_users_db():
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                invites INTEGER DEFAULT 0,
                downloads_total INTEGER DEFAULT 0,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS downloads_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных пользователей готова")
    except Exception as e:
        print(f"❌ Ошибка при создании базы пользователей: {e}")

init_db()
init_users_db()

# ========== ФУНКЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
def get_users_count() -> int:
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users')
        result = cur.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка получения количества пользователей: {e}")
        return 0

def get_all_users() -> list:
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT user_id FROM users ORDER BY last_active DESC')
        users = [row[0] for row in cur.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []

def get_user_status(user_id: int) -> dict:
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cur.fetchone():
            logger.error("Таблица users не существует")
            conn.close()
            return {
                'user_id': user_id,
                'is_admin': (user_id == ADMIN_ID),
                'invites': 0,
                'downloads_total': 0
            }
        
        cur.execute('SELECT user_id, username, invites, downloads_total FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        
        if not user:
            try:
                cur.execute('''
                    INSERT INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)
                ''', (user_id,))
                conn.commit()
                logger.info(f"Создан новый пользователь: {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при создании пользователя {user_id}: {e}")
            
            status_data = {
                'user_id': user_id,
                'is_admin': (user_id == ADMIN_ID),
                'invites': 0,
                'downloads_total': 0
            }
        else:
            status_data = {
                'user_id': user[0],
                'is_admin': (user_id == ADMIN_ID),
                'invites': user[2] if user[2] is not None else 0,
                'downloads_total': user[3] if user[3] is not None else 0
            }
        
        conn.close()
        return status_data
        
    except Exception as e:
        logger.error(f"Ошибка в get_user_status для {user_id}: {e}")
        return {
            'user_id': user_id,
            'is_admin': (user_id == ADMIN_ID),
            'invites': 0,
            'downloads_total': 0
        }

def increment_download_count(user_id: int):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cur.fetchone():
            cur.execute('INSERT INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)', (user_id,))
        
        cur.execute('''
            UPDATE users SET 
                downloads_total = COALESCE(downloads_total, 0) + 1, 
                last_active = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения счётчика для {user_id}: {e}")

def add_referral(referrer_id: int, referred_id: int):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'")
        if not cur.fetchone():
            logger.error("Таблица referrals не существует")
            conn.close()
            return False
        
        cur.execute('''
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)
        ''', (referrer_id, referred_id))
        
        if cur.rowcount > 0:
            cur.execute('''
                UPDATE users SET invites = COALESCE(invites, 0) + 1 WHERE user_id = ?
            ''', (referrer_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления реферала: {e}")
        return False

def save_user(message: Message):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        cur.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cur.fetchone()
        
        if not exists:
            referrer_id = None
            if message.text and message.text.startswith('/start ref_'):
                try:
                    referrer_id = int(message.text.replace('/start ref_', ''))
                    if referrer_id == user_id:
                        referrer_id = None
                except:
                    pass
            
            cur.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
            
            if referrer_id:
                add_referral(referrer_id, user_id)
        else:
            cur.execute('''
                UPDATE users SET 
                    username = ?,
                    first_name = ?,
                    last_name = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (username, first_name, last_name, user_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {message.from_user.id}: {e}")

# ========== ОБЩИЕ ФУНКЦИИ ДЛЯ РАБОТЫ С БД ==========
def get_item(table: str, item_id: int):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
        item = cur.fetchone()
        conn.close()
        
        if item:
            item_list = list(item)
            if table == "clients":
                if len(item_list) > 6 and item_list[6] is not None:
                    item_list[6] = int(item_list[6])
                if len(item_list) > 7 and item_list[7] is not None:
                    item_list[7] = int(item_list[7])
            elif table == "resourcepacks":
                if len(item_list) > 7 and item_list[7] is not None:
                    item_list[7] = int(item_list[7])
                if len(item_list) > 8 and item_list[8] is not None:
                    item_list[8] = int(item_list[8])
                if len(item_list) > 9 and item_list[9] is not None:
                    item_list[9] = int(item_list[9])
            elif table == "configs":
                if len(item_list) > 6 and item_list[6] is not None:
                    item_list[6] = int(item_list[6])
                if len(item_list) > 7 and item_list[7] is not None:
                    item_list[7] = int(item_list[7])
            
            return tuple(item_list)
        return item
    except Exception as e:
        logger.error(f"Ошибка получения элемента {table} {item_id}: {e}")
        return None

def get_all_items_paginated(table: str, page: int = 1, per_page: int = 10):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        cur.execute(f'SELECT id, name, full_desc, media, downloads, version FROM {table} ORDER BY created_at DESC LIMIT ? OFFSET ?', (per_page, offset))
        items = cur.fetchall()
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                item_list[4] = int(item_list[4])
            converted_items.append(tuple(item_list))
        
        total = cur.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения элементов {table}: {e}")
        return [], 0

def delete_item(table: str, item_id: int):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка удаления элемента {table} {item_id}: {e}")

# ========== ФУНКЦИИ ДЛЯ КЛИЕНТОВ ==========
def add_client(name, full_desc, url, version, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO clients (name, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления клиента: {e}")
        return None

def update_client(item_id, field, value):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка обновления клиента {item_id}: {e}")

def update_client_media(item_id: int, media_list: list):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media_list)
        cur.execute('UPDATE clients SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа клиента {item_id}: {e}")
        return False

def get_clients_by_version(version, page=1, per_page=10):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        cur.execute('''
            SELECT id, name, full_desc, media, downloads, views, version 
            FROM clients WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
        ''', (version, per_page, offset))
        items = cur.fetchall()
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                item_list[4] = int(item_list[4])
            if len(item_list) > 5 and item_list[5] is not None:
                item_list[5] = int(item_list[5])
            converted_items.append(tuple(item_list))
        
        total = cur.execute('SELECT COUNT(*) FROM clients WHERE version = ?', (version,)).fetchone()[0]
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения клиентов по версии {version}: {e}")
        return [], 0

def get_all_client_versions():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL ORDER BY version DESC')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий клиентов: {e}")
        return []

# ========== ФУНКЦИИ ДЛЯ РЕСУРСПАКОВ ==========
def add_pack(name, full_desc, url, version, author, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO resourcepacks (name, full_desc, download_url, version, author, media)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, full_desc, url, version, author, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления ресурспака: {e}")
        return None

def update_pack(item_id, field, value):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка обновления ресурспака {item_id}: {e}")

def update_pack_media(item_id: int, media_list: list):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media_list)
        cur.execute('UPDATE resourcepacks SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа ресурспака {item_id}: {e}")
        return False

def get_packs_by_version(version, page=1, per_page=10):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        cur.execute('''
            SELECT id, name, full_desc, media, downloads, likes, views, version, author 
            FROM resourcepacks WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
        ''', (version, per_page, offset))
        items = cur.fetchall()
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                item_list[4] = int(item_list[4])
            if len(item_list) > 5 and item_list[5] is not None:
                item_list[5] = int(item_list[5])
            if len(item_list) > 6 and item_list[6] is not None:
                item_list[6] = int(item_list[6])
            converted_items.append(tuple(item_list))
        
        total = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (version,)).fetchone()[0]
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения ресурспаков по версии {version}: {e}")
        return [], 0

def get_all_pack_versions():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT version FROM resourcepacks WHERE version IS NOT NULL ORDER BY version DESC')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий ресурспаков: {e}")
        return []

# ========== ФУНКЦИИ ДЛЯ КОНФИГОВ ==========
def add_config(name, full_desc, url, version, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO configs (name, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления конфига: {e}")
        return None

def update_config(item_id, field, value):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка обновления конфига {item_id}: {e}")

def update_config_media(item_id: int, media_list: list):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media_list)
        cur.execute('UPDATE configs SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа конфига {item_id}: {e}")
        return False

def get_configs_by_version(version, page=1, per_page=10):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        cur.execute('''
            SELECT id, name, full_desc, media, downloads, views, version 
            FROM configs WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
        ''', (version, per_page, offset))
        items = cur.fetchall()
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                item_list[4] = int(item_list[4])
            if len(item_list) > 5 and item_list[5] is not None:
                item_list[5] = int(item_list[5])
            converted_items.append(tuple(item_list))
        
        total = cur.execute('SELECT COUNT(*) FROM configs WHERE version = ?', (version,)).fetchone()[0]
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения конфигов по версии {version}: {e}")
        return [], 0

def get_all_config_versions():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT version FROM configs WHERE version IS NOT NULL ORDER BY version DESC')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий конфигов: {e}")
        return []

# ========== ФУНКЦИИ ДЛЯ ИЗБРАННОГО ==========
def toggle_favorite(user_id, pack_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        exists = cur.execute('SELECT 1 FROM favorites WHERE user_id = ? AND pack_id = ?', (user_id, pack_id)).fetchone()
        if exists:
            cur.execute('DELETE FROM favorites WHERE user_id = ? AND pack_id = ?', (user_id, pack_id))
            cur.execute('UPDATE resourcepacks SET likes = likes - 1 WHERE id = ?', (pack_id,))
            conn.commit()
            conn.close()
            return False
        else:
            cur.execute('INSERT INTO favorites (user_id, pack_id) VALUES (?, ?)', (user_id, pack_id))
            cur.execute('UPDATE resourcepacks SET likes = likes + 1 WHERE id = ?', (pack_id,))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Ошибка переключения избранного: {e}")
        return False

def get_favorites(user_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('''
            SELECT r.id, r.name, r.full_desc, r.media, r.downloads, r.likes 
            FROM resourcepacks r JOIN favorites f ON r.id = f.pack_id
            WHERE f.user_id = ? ORDER BY f.added_at DESC
        ''', (user_id,))
        favs = cur.fetchall()
        
        converted_favs = []
        for fav in favs:
            fav_list = list(fav)
            if len(fav_list) > 4 and fav_list[4] is not None:
                fav_list[4] = int(fav_list[4])
            if len(fav_list) > 5 and fav_list[5] is not None:
                fav_list[5] = int(fav_list[5])
            converted_favs.append(tuple(fav_list))
        
        conn.close()
        return converted_favs
    except Exception as e:
        logger.error(f"Ошибка получения избранного: {e}")
        return []

# ========== ФУНКЦИИ ДЛЯ СТАТИСТИКИ ==========
def increment_view(table, item_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения просмотров: {e}")

def increment_download(table, item_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения скачиваний: {e}")

# ========== ФУНКЦИИ ДЛЯ БЭКАПОВ ==========
def get_all_backups():
    try:
        files = os.listdir(str(BACKUP_DIR))
        backups = [f for f in files if f.endswith('.zip')]
        backups.sort(reverse=True)
        return backups
    except Exception as e:
        print(f"Ошибка получения списка бэкапов: {e}")
        return []

async def create_zip_backup():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"backup_{timestamp}.zip"
        zip_path = BACKUP_DIR / zip_filename
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if DB_PATH.exists():
                zipf.write(DB_PATH, 'clients.db')
            if USERS_DB_PATH.exists():
                zipf.write(USERS_DB_PATH, 'users.db')
        
        if zip_path.exists():
            return str(zip_path), zip_filename
        return None, None
    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}")
        return None, None

async def restore_from_zip(zip_path):
    try:
        extract_dir = BACKUP_DIR / f"restore_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_dir)
        
        restored = False
        for file in extract_dir.iterdir():
            if file.name == 'clients.db':
                shutil.copy2(file, DB_PATH)
                restored = True
            elif file.name == 'users.db':
                shutil.copy2(file, USERS_DB_PATH)
                restored = True
        
        shutil.rmtree(extract_dir, ignore_errors=True)
        return restored
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
        return False

def check_backup_structure(zip_path):
    """Проверяет структуру бэкапа и возвращает отчет о несоответствиях"""
    issues = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            files = zipf.namelist()
            
            if 'clients.db' not in files:
                issues.append("❌ Отсутствует файл clients.db")
            if 'users.db' not in files:
                issues.append("❌ Отсутствует файл users.db")
            
        return issues
    except Exception as e:
        return [f"❌ Ошибка проверки архива: {str(e)}"]

# ========== ФУНКЦИЯ ФОРМАТИРОВАНИЯ ЧИСЕЛ ==========
def format_number(num):
    """Безопасное форматирование чисел"""
    if num is None:
        return "0"
    try:
        if isinstance(num, str):
            if num.isdigit():
                num = int(num)
            else:
                try:
                    num = int(float(num))
                except:
                    return "0"
        num = int(num)
        if num < 1000:
            return str(num)
        elif num < 1000000:
            return f"{num/1000:.1f}K"
        else:
            return f"{num/1000000:.1f}M"
    except:
        return "0"

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_main_keyboard(is_admin=False):
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты"), types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="❤️ Избранное"), types.KeyboardButton(text="⚙️ Конфиги"), types.KeyboardButton(text="👤 Профиль")],
        [types.KeyboardButton(text="ℹ️ Инфо"), types.KeyboardButton(text="❓ Помощь")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== СОСТОЯНИЯ ==========
class AdminStates(StatesGroup):
    client_name = State()
    client_full_desc = State()
    client_version = State()
    client_url = State()
    client_media = State()
    
    pack_name = State()
    pack_full_desc = State()
    pack_version = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    
    config_name = State()
    config_full_desc = State()
    config_version = State()
    config_url = State()
    config_media = State()
    
    edit_value = State()
    edit_media = State()
    broadcast_text = State()
    broadcast_photo = State()
    waiting_for_backup = State()

# ========== КЛАВИАТУРЫ ==========
def get_version_keyboard(versions, category):
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"ver_{category}_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_items_keyboard(items, category, page, total_pages):
    buttons = []
    for item in items:
        item_id, name, full_desc, media_json, downloads = item[0], item[1], item[2], item[3], item[4]
        version = item[6] if len(item) > 6 else "?"
        try:
            media_list = json.loads(media_json) if media_json else []
        except:
            media_list = []
        preview = "🖼️" if media_list else "📄"
        button_text = f"{preview} {name[:30]} ({version})\n📥 {format_number(downloads)}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"detail_{category}_{item_id}")])
    
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{category}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{category}_{page+1}"))
    if nav_row: buttons.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_detail_keyboard(category, item_id, is_favorite=False):
    buttons = []
    if category == "packs":
        fav_text = "❤️" if is_favorite else "🤍"
        buttons.append([
            InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_{category}_{item_id}"),
            InlineKeyboardButton(text=fav_text, callback_data=f"fav_{category}_{item_id}")
        ])
    else:
        buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_{category}_{item_id}")])
    buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_{category}_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_main_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📦 ZIP Бэкапы", callback_data="admin_zip_backups")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_list_keyboard(items, category, page, total_pages, action):
    buttons = []
    for item in items:
        item_id, name, full_desc, media_json, downloads, version = item
        buttons.append([InlineKeyboardButton(
            text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", 
            callback_data=f"{action}_{category}_{item_id}"
        )])
    
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"list_page_{category}_{action}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"list_page_{category}_{action}_{page+1}"))
    if nav_row: buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_media_keyboard(category, item_id):
    buttons = [
        [InlineKeyboardButton(text="📸 Добавить фото", callback_data=f"add_media_{category}_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить все фото", callback_data=f"del_media_{category}_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_{category}_{item_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_help_keyboard():
    buttons = [
        [InlineKeyboardButton(text="👤 Связаться с админом", url=f"https://t.me/{CREATOR_USERNAME[1:]}")],
        [InlineKeyboardButton(text="📋 Правила", callback_data="help_rules")],
        [InlineKeyboardButton(text="❓ Часто задаваемые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = (message.from_user.id == ADMIN_ID)
    save_user(message)
    await message.answer(
        "👋 Привет! Я бот-каталог Minecraft\n\n"
        "🎮 Клиенты - моды и сборки\n"
        "🎨 Ресурспаки - текстурпаки\n"
        "❤️ Избранное - сохраняй понравившееся\n"
        "⚙️ Конфиги - настройки\n"
        "👤 Профиль - твой профиль\n"
        "ℹ️ Инфо - о боте и создателе\n"
        "❓ Помощь - связаться с админом\n\n"
        "Используй кнопки ниже:",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== КЛИЕНТЫ ==========
@dp.message(F.text == "🎮 Клиенты")
async def clients_menu(message: Message, state: FSMContext):
    versions = get_all_client_versions()
    if not versions:
        await message.answer("📭 Пока нет клиентов")
        return
    await message.answer("🎮 Выбери версию Minecraft:", reply_markup=get_version_keyboard(versions, "clients"))

@dp.callback_query(lambda c: c.data.startswith("ver_clients_"))
async def clients_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_clients_", "")
    items, total = get_clients_by_version(version, 1)
    if not items:
        await callback.message.edit_text(f"❌ Для версии {version} пока нет клиентов", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]))
        await callback.answer()
        return
    total_pages = (total + 9) // 10
    await state.update_data(client_version=version, client_page=1)
    await callback.message.edit_text(f"🎮 Клиенты для версии {version} (стр 1/{total_pages}):", reply_markup=get_items_keyboard(items, "clients", 1, total_pages))
    await callback.answer()

# ========== РЕСУРСПАКИ ==========
@dp.message(F.text == "🎨 Ресурспаки")
async def packs_menu(message: Message, state: FSMContext):
    versions = get_all_pack_versions()
    if not versions:
        await message.answer("📭 Пока нет ресурспаков")
        return
    await message.answer("🎨 Выбери версию Minecraft:", reply_markup=get_version_keyboard(versions, "packs"))

@dp.callback_query(lambda c: c.data.startswith("ver_packs_"))
async def packs_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_packs_", "")
    items, total = get_packs_by_version(version, 1)
    if not items:
        await callback.message.edit_text(f"❌ Для версии {version} пока нет ресурспаков", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]))
        await callback.answer()
        return
    total_pages = (total + 9) // 10
    await state.update_data(pack_version=version, pack_page=1)
    await callback.message.edit_text(f"🎨 Ресурспаки для версии {version} (стр 1/{total_pages}):", reply_markup=get_items_keyboard(items, "packs", 1, total_pages))
    await callback.answer()

# ========== КОНФИГИ ==========
@dp.message(F.text == "⚙️ Конфиги")
async def configs_menu(message: Message, state: FSMContext):
    versions = get_all_config_versions()
    if not versions:
        await message.answer("📭 Пока нет конфигов")
        return
    await message.answer("⚙️ Выбери версию Minecraft:", reply_markup=get_version_keyboard(versions, "configs"))

@dp.callback_query(lambda c: c.data.startswith("ver_configs_"))
async def configs_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_configs_", "")
    items, total = get_configs_by_version(version, 1)
    if not items:
        await callback.message.edit_text(f"❌ Для версии {version} пока нет конфигов", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]))
        await callback.answer()
        return
    total_pages = (total + 9) // 10
    await state.update_data(config_version=version, config_page=1)
    await callback.message.edit_text(f"⚙️ Конфиги для версии {version} (стр 1/{total_pages}):", reply_markup=get_items_keyboard(items, "configs", 1, total_pages))
    await callback.answer()

# ========== ПРОФИЛЬ ==========
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "пользователь"
        status_data = get_user_status(user_id)
        
        if user_id == ADMIN_ID:
            status_text = "👑 СОЗДАТЕЛЬ"
        else:
            status_text = "👤 ПОЛЬЗОВАТЕЛЬ"
        
        bot_info = await bot.me()
        bot_username = bot_info.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        text = (
            f"👋 Привет, {first_name}! ❤️\n\n"
            f"Мой любимый пользователь!\n\n"
            f"🎉 Этот бот абсолютно бесплатный!\n"
            f"Никаких лимитов!\n\n"
            f"Твоя статистика:\n"
            f"• Статус: {status_text}\n"
            f"• ID: {user_id}\n"
            f"• Всего скачиваний: {status_data.get('downloads_total', 0)}\n"
            f"• Приглашено друзей: {status_data.get('invites', 0)}\n\n"
            f"Твоя ссылка для приглашения:\n"
            f"{ref_link}"
        )
        
        buttons = [
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="profile_stats")],
            [InlineKeyboardButton(text="📋 Мои скачивания", callback_data="profile_downloads")]
        ]
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        logger.error(f"Ошибка в профиле: {e}")
        await message.answer("👋 Привет!\n\n🎉 Этот бот абсолютно бесплатный!")

@dp.callback_query(lambda c: c.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        total_downloads = cur.execute('SELECT COUNT(*) FROM downloads_log WHERE user_id = ?', (user_id,)).fetchone()[0]
        total_invites = cur.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,)).fetchone()[0]
        recent = cur.execute('SELECT item_type, downloaded_at FROM downloads_log WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 5', (user_id,)).fetchall()
        conn.close()
        
        text = f"Твоя статистика\n\n📥 Всего скачиваний: {total_downloads}\n👥 Приглашено друзей: {total_invites}\n\n"
        if recent:
            text += "Последние скачивания:\n"
            for item_type, date in recent:
                text += f"• {item_type} - {date[:10] if date else 'недавно'}\n"
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")]]))
    except Exception as e:
        logger.error(f"Ошибка в статистике профиля: {e}")
        await callback.message.edit_text("❌ Ошибка загрузки статистики")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_downloads")
async def profile_downloads(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        downloads = cur.execute('SELECT item_type, item_id, downloaded_at FROM downloads_log WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 10', (user_id,)).fetchall()
        conn.close()
        
        if not downloads:
            text = "📭 У тебя пока нет скачиваний"
        else:
            text = "Твои скачивания:\n\n"
            for i, (item_type, item_id, date) in enumerate(downloads, 1):
                text += f"{i}. {item_type} (ID: {item_id}) - {date[:10] if date else 'недавно'}\n"
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")]]))
    except Exception as e:
        logger.error(f"Ошибка в истории скачиваний: {e}")
        await callback.message.edit_text("❌ Ошибка загрузки истории")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    await show_profile(callback.message)
    await callback.answer()

# ========== ПАГИНАЦИЯ ==========
@dp.callback_query(lambda c: c.data.startswith("page_"))
async def pagination(callback: CallbackQuery, state: FSMContext):
    _, category, page = callback.data.split("_")
    page = int(page)
    data = await state.get_data()
    
    if category == "clients":
        version = data.get("client_version", "1.20")
        items, total = get_clients_by_version(version, page)
        if total == 0:
            await callback.message.edit_text(f"🎮 Нет клиентов для версии {version}")
            await callback.answer()
            return
        title = f"🎮 Клиенты для версии {version}"
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        items, total = get_packs_by_version(version, page)
        if total == 0:
            await callback.message.edit_text(f"🎨 Нет ресурспаков для версии {version}")
            await callback.answer()
            return
        title = f"🎨 Ресурспаки для версии {version}"
    else:
        version = data.get("config_version", "1.20")
        items, total = get_configs_by_version(version, page)
        if total == 0:
            await callback.message.edit_text(f"⚙️ Нет конфигов для версии {version}")
            await callback.answer()
            return
        title = f"⚙️ Конфиги для версии {version}"
    
    total_pages = max(1, (total + 9) // 10)
    await state.update_data({f"{category}_page": page})
    await callback.message.edit_text(f"{title} (стр {page}/{total_pages}):", reply_markup=get_items_keyboard(items, category, page, total_pages))
    await callback.answer()

# ========== ДЕТАЛЬНЫЙ ПРОСМОТР ==========
@dp.callback_query(lambda c: c.data.startswith("detail_"))
async def detail_view(callback: CallbackQuery, state: FSMContext):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    increment_view(category, item_id)
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
    except:
        media_list = []
    
    is_fav = False
    if category == "clients":
        downloads = int(item[6]) if len(item) > 6 and item[6] else 0
        views = int(item[7]) if len(item) > 7 and item[7] else 0
        text = f"🎮 {item[1]}\n\n{item[2]}\n\nВерсия: {item[5]}\n📥 Скачиваний: {format_number(downloads)}\n👁 Просмотров: {format_number(views)}"
    
    elif category == "packs":
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        is_fav = cur.execute('SELECT 1 FROM favorites WHERE user_id = ? AND pack_id = ?', (callback.from_user.id, item_id)).fetchone()
        conn.close()
        
        downloads = int(item[7]) if len(item) > 7 and item[7] else 0
        likes = int(item[8]) if len(item) > 8 and item[8] else 0
        views = int(item[9]) if len(item) > 9 and item[9] else 0
        text = f"🎨 {item[1]}\n\n{item[2]}\n\nАвтор: {item[6]}\nВерсия: {item[5]}\n📥 Скачиваний: {format_number(downloads)}\n❤️ В избранном: {format_number(likes)}\n👁 Просмотров: {format_number(views)}"
    
    else:  # configs
        downloads = int(item[6]) if len(item) > 6 and item[6] else 0
        views = int(item[7]) if len(item) > 7 and item[7] else 0
        text = f"⚙️ {item[1]}\n\n{item[2]}\n\nВерсия: {item[5]}\n📥 Скачиваний: {format_number(downloads)}\n👁 Просмотров: {format_number(views)}"
    
    if media_list and media_list[0]['type'] == 'photo':
        try:
            await callback.message.answer_photo(
                photo=media_list[0]['id'], 
                caption=text, 
                reply_markup=get_detail_keyboard(category, item_id, is_fav)
            )
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await callback.message.edit_text(
                text + "\n\n❌ Фото недоступно", 
                reply_markup=get_detail_keyboard(category, item_id, is_fav)
            )
    else:
        await callback.message.edit_text(
            text, 
            reply_markup=get_detail_keyboard(category, item_id, is_fav)
        )
    
    await callback.answer()

# ========== НАВИГАЦИЯ НАЗАД ==========
@dp.callback_query(lambda c: c.data.startswith("back_"))
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("back_", "")
    data = await state.get_data()
    
    if category == "clients":
        version = data.get("client_version", "1.20")
        items, total = get_clients_by_version(version, 1)
        if total == 0:
            await callback.message.edit_text(f"🎮 Нет клиентов для версии {version}")
            await callback.answer()
            return
        title = f"🎮 Клиенты для версии {version}"
        page = 1
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        items, total = get_packs_by_version(version, 1)
        if total == 0:
            await callback.message.edit_text(f"🎨 Нет ресурспаков для версии {version}")
            await callback.answer()
            return
        title = f"🎨 Ресурспаки для версии {version}"
        page = 1
    else:
        version = data.get("config_version", "1.20")
        items, total = get_configs_by_version(version, 1)
        if total == 0:
            await callback.message.edit_text(f"⚙️ Нет конфигов для версии {version}")
            await callback.answer()
            return
        title = f"⚙️ Конфиги для версии {version}"
        page = 1
    
    total_pages = max(1, (total + 9) // 10)
    await callback.message.edit_text(f"{title} (стр {page}/{total_pages}):", reply_markup=get_items_keyboard(items, category, page, total_pages))
    await callback.answer()

# ========== ИСПРАВЛЕННАЯ ФУНКЦИЯ СКАЧИВАНИЯ ==========
@dp.callback_query(lambda c: c.data.startswith("download_"))
async def download_item(callback: CallbackQuery):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    user_id = callback.from_user.id
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    increment_download(category, item_id)
    increment_download_count(user_id)
    
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('INSERT INTO downloads_log (user_id, item_type, item_id) VALUES (?, ?, ?)', (user_id, category, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка логирования скачивания: {e}")
    
    # Правильные индексы для каждой таблицы
    if category == "clients":
        # clients: id(0), name(1), full_desc(2), media(3), download_url(4), version(5), downloads(6), views(7)
        url = item[4]
        name = item[1]
    elif category == "packs":
        # resourcepacks: id(0), name(1), full_desc(2), media(3), download_url(4), version(5), author(6), downloads(7), likes(8), views(9)
        url = item[4]
        name = item[1]
    else:  # configs
        # configs: id(0), name(1), full_desc(2), media(3), download_url(4), version(5), downloads(6), views(7)
        url = item[4]
        name = item[1]
    
    await callback.message.answer(f"📥 Скачать {name}\n\n{url}")
    await callback.answer("✅ Ссылка отправлена!")

# ========== ИЗБРАННОЕ ==========
@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("❤️ Избранное пусто\n\nДобавляй ресурспаки в избранное кнопкой 🤍")
        return
    text = "❤️ Твоё избранное:\n\n"
    for fav in favs[:10]:
        downloads = int(fav[4]) if fav[4] else 0
        text += f"• {fav[1]} - {format_number(downloads)} 📥\n"
    await message.answer(text)

@dp.callback_query(lambda c: c.data.startswith("fav_"))
async def favorite_handler(callback: CallbackQuery):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    if category != "packs":
        await callback.answer("❌ Только для ресурспаков", show_alert=True)
        return
    toggle_favorite(callback.from_user.id, item_id)
    await callback.answer("✅ Готово!")
    await detail_view(callback, None)

# ========== ИНФО ==========
@dp.message(F.text == "ℹ️ Инфо")
async def info(message: Message):
    try:
        users_count = get_users_count()
        backups_count = len(get_all_backups())
        
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        clients_count = cur.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
        packs_count = cur.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]
        configs_count = cur.execute('SELECT COUNT(*) FROM configs').fetchone()[0]
        conn.close()
        
        text = (
            f"Информация о боте\n\n"
            f"Создатель: {CREATOR_USERNAME}\n"
            f"Версия: 16.0\n\n"
            f"Статистика:\n"
            f"• Пользователей: {users_count}\n"
            f"• Клиентов: {clients_count}\n"
            f"• Ресурспаков: {packs_count}\n"
            f"• Конфигов: {configs_count}\n"
            f"• ZIP бэкапов: {backups_count}\n\n"
            f"📁 Данные хранятся в /app/data\n"
            f"Бот полностью бесплатный!"
        )
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка в info: {e}")
        await message.answer(f"Информация о боте\n\nСоздатель: {CREATOR_USERNAME}\nВерсия: 16.0")

# ========== ПОМОЩЬ ==========
@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    await message.answer(
        "❓ Помощь и поддержка\n\nЕсли у тебя возникли вопросы:\n\n• Нажми кнопку ниже, чтобы связаться с создателем",
        reply_markup=get_help_keyboard()
    )

@dp.callback_query(lambda c: c.data == "help_rules")
async def help_rules(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 Правила использования\n\n1. Все файлы предоставляются 'как есть'\n2. Автор не несёт ответственности за использование файлов\n3. Уважайте других пользователей",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help_faq")
async def help_faq(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ Часто задаваемые вопросы\n\nQ: Как скачать файл?\nA: Нажми на элемент, затем кнопку 'Скачать'\n\nQ: Есть ли лимиты?\nA: Нет! Бот полностью бесплатный, качай сколько хочешь!\n\nQ: Как сделать бэкап?\nA: В админ-панели выбери '📦 ZIP Бэкапы' и нажми 'Создать'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ Помощь и поддержка\n\nЕсли у тебя возникли вопросы:\n\n• Нажми кнопку ниже, чтобы связаться с создателем",
        reply_markup=get_help_keyboard()
    )
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    await message.answer("⚙️ Админ панель\n\nВыбери категорию:", reply_markup=get_admin_main_keyboard())

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.answer("⚙️ Админ панель\n\nВыбери категорию:", reply_markup=get_admin_main_keyboard())
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_clients")
async def admin_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить клиента", callback_data="add_client")],
        [InlineKeyboardButton(text="✏️ Редактировать клиента", callback_data="edit_client_list")],
        [InlineKeyboardButton(text="🗑 Удалить клиента", callback_data="delete_client_list")],
        [InlineKeyboardButton(text="📋 Список клиентов", callback_data="list_clients")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("🎮 Управление клиентами\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_packs")
async def admin_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить ресурспак", callback_data="add_pack")],
        [InlineKeyboardButton(text="✏️ Редактировать ресурспак", callback_data="edit_pack_list")],
        [InlineKeyboardButton(text="🗑 Удалить ресурспак", callback_data="delete_pack_list")],
        [InlineKeyboardButton(text="📋 Список ресурспаков", callback_data="list_packs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("🎨 Управление ресурспаками\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_configs")
async def admin_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить конфиг", callback_data="add_config")],
        [InlineKeyboardButton(text="✏️ Редактировать конфиг", callback_data="edit_config_list")],
        [InlineKeyboardButton(text="🗑 Удалить конфиг", callback_data="delete_config_list")],
        [InlineKeyboardButton(text="📋 Список конфигов", callback_data="list_configs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("⚙️ Управление конфигами\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== АДМИН: СПИСКИ С ПАГИНАЦИЕЙ ==========
@dp.callback_query(lambda c: c.data.startswith("list_page_"))
async def list_pagination(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    action = parts[3]
    page = int(parts[4])
    
    table_map = {
        'clients': 'clients',
        'packs': 'resourcepacks',
        'configs': 'configs'
    }
    table = table_map.get(category)
    if not table:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    items, total = get_all_items_paginated(table, page)
    total_pages = max(1, (total + 9) // 10)
    
    await callback.message.edit_text(
        f"📋 Страница {page}/{total_pages}:",
        reply_markup=get_admin_list_keyboard(items, category, page, total_pages, action)
    )
    await callback.answer()

# ========== АДМИН: РЕДАКТИРОВАНИЕ КЛИЕНТА ==========
@dp.callback_query(lambda c: c.data == "edit_client_list")
async def edit_client_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("clients", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет клиентов для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"✏️ Выбери клиента для редактирования (стр 1/{total_pages}):",
        reply_markup=get_admin_list_keyboard(items, "clients", 1, total_pages, "edit")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_clients_"))
async def edit_client_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("edit_clients_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("clients", item_id)
    if not item:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
        media_count = len(media_list)
    except:
        media_count = 0
    
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_client_field_name_{item_id}")],
        [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_client_field_full_desc_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_client_field_version_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_client_field_download_url_{item_id}")],
        [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_client_media_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_client_list")]
    ]
    
    await callback.message.edit_text(
        f"✏️ Редактирование: {item[1]}\n\nЧто изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=fields)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_client_field_"))
async def edit_client_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    
    field_map = {
        'name': 'name',
        'full_desc': 'full_desc',
        'version': 'version',
        'download_url': 'download_url'
    }
    
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="clients")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ Введи новое значение:")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_client_media_"))
async def edit_client_media(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_client_media_", ""))
    item = get_item("clients", item_id)
    if not item:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
    except:
        media_list = []
    
    await state.update_data(edit_item_id=item_id, edit_category="clients", media_list=media_list)
    await state.set_state(AdminStates.edit_media)
    
    media_count = len(media_list)
    text = f"🖼️ Управление фото для {item[1]}\n\n"
    text += f"Сейчас фото: {media_count}\n\n"
    if media_count > 0:
        text += "Чтобы удалить все фото, нажми кнопку ниже.\n"
        text += "Чтобы добавить новые, просто отправь фото."
    
    await callback.message.edit_text(
        text,
        reply_markup=get_edit_media_keyboard("clients", item_id)
    )
    await callback.answer()

# ========== АДМИН: РЕДАКТИРОВАНИЕ РЕСУРСПАКА ==========
@dp.callback_query(lambda c: c.data == "edit_pack_list")
async def edit_pack_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("resourcepacks", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет ресурспаков для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"✏️ Выбери ресурспак для редактирования (стр 1/{total_pages}):",
        reply_markup=get_admin_list_keyboard(items, "packs", 1, total_pages, "edit")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_packs_"))
async def edit_pack_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("edit_packs_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("resourcepacks", item_id)
    if not item:
        await callback.answer("❌ Ресурспак не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
        media_count = len(media_list)
    except:
        media_count = 0
    
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_pack_field_name_{item_id}")],
        [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_pack_field_full_desc_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_pack_field_version_{item_id}")],
        [InlineKeyboardButton(text="✍️ Автор", callback_data=f"edit_pack_field_author_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_pack_field_download_url_{item_id}")],
        [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_pack_media_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_pack_list")]
    ]
    
    await callback.message.edit_text(
        f"✏️ Редактирование: {item[1]}\n\nЧто изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=fields)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_pack_field_"))
async def edit_pack_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    
    field_map = {
        'name': 'name',
        'full_desc': 'full_desc',
        'version': 'version',
        'author': 'author',
        'download_url': 'download_url'
    }
    
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="resourcepacks")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ Введи новое значение:")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_pack_media_"))
async def edit_pack_media(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_pack_media_", ""))
    item = get_item("resourcepacks", item_id)
    if not item:
        await callback.answer("❌ Ресурспак не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
    except:
        media_list = []
    
    await state.update_data(edit_item_id=item_id, edit_category="resourcepacks", media_list=media_list)
    await state.set_state(AdminStates.edit_media)
    
    media_count = len(media_list)
    text = f"🖼️ Управление фото для {item[1]}\n\n"
    text += f"Сейчас фото: {media_count}\n\n"
    if media_count > 0:
        text += "Чтобы удалить все фото, нажми кнопку ниже.\n"
        text += "Чтобы добавить новые, просто отправь фото."
    
    await callback.message.edit_text(
        text,
        reply_markup=get_edit_media_keyboard("packs", item_id)
    )
    await callback.answer()

# ========== АДМИН: РЕДАКТИРОВАНИЕ КОНФИГА ==========
@dp.callback_query(lambda c: c.data == "edit_config_list")
async def edit_config_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("configs", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"✏️ Выбери конфиг для редактирования (стр 1/{total_pages}):",
        reply_markup=get_admin_list_keyboard(items, "configs", 1, total_pages, "edit")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_configs_"))
async def edit_config_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("edit_configs_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
        media_count = len(media_list)
    except:
        media_count = 0
    
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_config_field_name_{item_id}")],
        [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_config_field_full_desc_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_config_field_version_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_config_field_download_url_{item_id}")],
        [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_config_media_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_config_list")]
    ]
    
    await callback.message.edit_text(
        f"✏️ Редактирование: {item[1]}\n\nЧто изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=fields)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_config_field_"))
async def edit_config_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    
    field_map = {
        'name': 'name',
        'full_desc': 'full_desc',
        'version': 'version',
        'download_url': 'download_url'
    }
    
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="configs")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ Введи новое значение:")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_config_media_"))
async def edit_config_media(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_config_media_", ""))
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[4]) if item[4] else []
    except:
        media_list = []
    
    await state.update_data(edit_item_id=item_id, edit_category="configs", media_list=media_list)
    await state.set_state(AdminStates.edit_media)
    
    media_count = len(media_list)
    text = f"🖼️ Управление фото для {item[1]}\n\n"
    text += f"Сейчас фото: {media_count}\n\n"
    if media_count > 0:
        text += "Чтобы удалить все фото, нажми кнопку ниже.\n"
        text += "Чтобы добавить новые, просто отправь фото."
    
    await callback.message.edit_text(
        text,
        reply_markup=get_edit_media_keyboard("configs", item_id)
    )
    await callback.answer()

# ========== АДМИН: ОБЩИЙ ОБРАБОТЧИК РЕДАКТИРОВАНИЯ ЗНАЧЕНИЙ ==========
@dp.message(AdminStates.edit_value)
async def edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get('edit_item_id')
    field = data.get('edit_field')
    category = data.get('edit_category', 'clients')
    
    if not item_id or not field:
        await message.answer("❌ Ошибка: нет данных для редактирования")
        await state.clear()
        return
    
    if category == 'resourcepacks':
        update_pack(item_id, field, message.text)
    elif category == 'configs':
        update_config(item_id, field, message.text)
    else:
        update_client(item_id, field, message.text)
    
    await state.clear()
    await message.answer("✅ Значение обновлено!", reply_markup=get_main_keyboard(is_admin=True))

# ========== АДМИН: ОБРАБОТЧИК РЕДАКТИРОВАНИЯ МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith("add_media_"))
async def add_media_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    item_id = int(parts[3])
    
    await state.update_data(edit_item_id=item_id, edit_category=category)
    await callback.message.edit_text(
        "📸 Отправляй фото (можно несколько)\n\n"
        "После того как отправишь все фото, напиши 'готово'\n"
        "Или напиши 'отмена' чтобы выйти"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("del_media_"))
async def delete_media(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    item_id = int(parts[3])
    
    if category == "clients":
        update_client_media(item_id, [])
    elif category == "packs":
        update_pack_media(item_id, [])
    else:
        update_config_media(item_id, [])
    
    await callback.message.edit_text(
        "✅ Все фото удалены!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_{category}_{item_id}")]
        ])
    )
    await callback.answer()

@dp.message(AdminStates.edit_media)
async def handle_media_edit(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    
    data = await state.get_data()
    item_id = data.get('edit_item_id')
    category = data.get('edit_category')
    current_media = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        if category == 'clients':
            update_client_media(item_id, current_media)
        elif category == 'resourcepacks':
            update_pack_media(item_id, current_media)
        else:
            update_config_media(item_id, current_media)
        
        await state.clear()
        await message.answer(
            f"✅ Фото сохранено! Всего: {len(current_media)}",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        return
    
    if message.text and message.text.lower() == 'отмена':
        await state.clear()
        await message.answer("❌ Редактирование отменено", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        current_media.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=current_media)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(current_media)}\n"
            f"Можешь отправить ещё фото или написать 'готово'"
        )
    else:
        await message.answer("❌ Отправь фото, или напиши 'готово' / 'отмена'")

# ========== АДМИН: УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data == "delete_client_list")
async def delete_client_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("clients", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет клиентов для удаления", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"🗑 Выбери клиента для удаления (стр 1/{total_pages}):",
        reply_markup=get_admin_list_keyboard(items, "clients", 1, total_pages, "delete")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_clients_") and not c.data.startswith("delete_clients_confirm_"))
async def delete_client_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("delete_clients_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("clients", item_id)
    if not item:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_clients_confirm_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_client_list")]
    ]
    
    await callback.message.edit_text(
        f"⚠️ Подтверждение удаления\n\n"
        f"Ты действительно хочешь удалить клиента:\n"
        f"{item[1]} (ID: {item_id})?\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_clients_confirm_"))
async def delete_client_execute(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("delete_clients_confirm_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    delete_item("clients", item_id)
    await callback.answer("✅ Клиент удалён!", show_alert=True)
    await delete_client_list(callback)

# ========== АДМИН: ДОБАВЛЕНИЕ КЛИЕНТА ==========
@dp.callback_query(lambda c: c.data == "add_client")
async def add_client_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.client_name)
    await callback.message.edit_text("📝 Введи название клиента:")
    await callback.answer()

@dp.message(AdminStates.client_name)
async def client_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await state.set_state(AdminStates.client_full_desc)
    await message.answer("📚 Введи полное описание:")

@dp.message(AdminStates.client_full_desc)
async def client_full_desc(message: Message, state: FSMContext):
    await state.update_data(client_full_desc=message.text)
    await state.set_state(AdminStates.client_version)
    await message.answer("🔢 Введи версию (например 1.20.4):")

@dp.message(AdminStates.client_version)
async def client_version(message: Message, state: FSMContext):
    await state.update_data(client_version=message.text)
    await state.set_state(AdminStates.client_url)
    await message.answer("🔗 Введи ссылку на скачивание:")

@dp.message(AdminStates.client_url)
async def client_url(message: Message, state: FSMContext):
    await state.update_data(client_url=message.text)
    await state.set_state(AdminStates.client_media)
    await message.answer(
        "🖼️ Отправляй фото (можно несколько)\n\n"
        "После того как отправишь все фото, напиши готово\n"
        "Или напиши пропустить чтобы пропустить фото:"
    )

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_client(
            data['client_name'], 
            data['client_full_desc'], 
            data['client_url'], 
            data['client_version'], 
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Клиент добавлен!\nID: {item_id}\nДобавлено фото: {len(media_list)}", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении клиента", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_client(
            data['client_name'], 
            data['client_full_desc'], 
            data['client_url'], 
            data['client_version'], 
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Клиент добавлен!\nID: {item_id} (без фото)", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении клиента", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать готово"
        )
    else:
        await message.answer("❌ Отправь фото, или напиши готово / пропустить")

# ========== АДМИН: ДОБАВЛЕНИЕ РЕСУРСПАКА ==========
@dp.callback_query(lambda c: c.data == "add_pack")
async def add_pack_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.pack_name)
    await callback.message.edit_text("📝 Введи название ресурспака:")
    await callback.answer()

@dp.message(AdminStates.pack_name)
async def pack_name(message: Message, state: FSMContext):
    await state.update_data(pack_name=message.text)
    await state.set_state(AdminStates.pack_full_desc)
    await message.answer("📚 Введи полное описание:")

@dp.message(AdminStates.pack_full_desc)
async def pack_full_desc(message: Message, state: FSMContext):
    await state.update_data(pack_full_desc=message.text)
    await state.set_state(AdminStates.pack_version)
    await message.answer("🔢 Введи версию (например 1.20.4):")

@dp.message(AdminStates.pack_version)
async def pack_version(message: Message, state: FSMContext):
    await state.update_data(pack_version=message.text)
    await state.set_state(AdminStates.pack_author)
    await message.answer("✍️ Введи автора:")

@dp.message(AdminStates.pack_author)
async def pack_author(message: Message, state: FSMContext):
    await state.update_data(pack_author=message.text)
    await state.set_state(AdminStates.pack_url)
    await message.answer("🔗 Введи ссылку на скачивание:")

@dp.message(AdminStates.pack_url)
async def pack_url(message: Message, state: FSMContext):
    await state.update_data(pack_url=message.text)
    await state.set_state(AdminStates.pack_media)
    await message.answer(
        "🖼️ Отправляй фото (можно несколько)\n\n"
        "После того как отправишь все фото, напиши готово\n"
        "Или напиши пропустить чтобы пропустить фото:"
    )

@dp.message(AdminStates.pack_media)
async def pack_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_pack(
            data['pack_name'], 
            data['pack_full_desc'], 
            data['pack_url'], 
            data['pack_version'], 
            data['pack_author'], 
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Ресурспак добавлен!\nID: {item_id}\nДобавлено фото: {len(media_list)}", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении ресурспака", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_pack(
            data['pack_name'], 
            data['pack_full_desc'], 
            data['pack_url'], 
            data['pack_version'], 
            data['pack_author'], 
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Ресурспак добавлен!\nID: {item_id} (без фото)", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении ресурспака", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать готово"
        )
    else:
        await message.answer("❌ Отправь фото, или напиши готово / пропустить")

# ========== АДМИН: ДОБАВЛЕНИЕ КОНФИГА ==========
@dp.callback_query(lambda c: c.data == "add_config")
async def add_config_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.config_name)
    await callback.message.edit_text("📝 Введи название конфига:")
    await callback.answer()

@dp.message(AdminStates.config_name)
async def config_name(message: Message, state: FSMContext):
    await state.update_data(config_name=message.text)
    await state.set_state(AdminStates.config_full_desc)
    await message.answer("📚 Введи полное описание:")

@dp.message(AdminStates.config_full_desc)
async def config_full_desc(message: Message, state: FSMContext):
    await state.update_data(config_full_desc=message.text)
    await state.set_state(AdminStates.config_version)
    await message.answer("🔢 Введи версию (например 1.20.4):")

@dp.message(AdminStates.config_version)
async def config_version(message: Message, state: FSMContext):
    await state.update_data(config_version=message.text)
    await state.set_state(AdminStates.config_url)
    await message.answer("🔗 Введи ссылку на скачивание:")

@dp.message(AdminStates.config_url)
async def config_url(message: Message, state: FSMContext):
    await state.update_data(config_url=message.text)
    await state.set_state(AdminStates.config_media)
    await message.answer(
        "🖼️ Отправляй фото (можно несколько)\n\n"
        "После того как отправишь все фото, напиши готово\n"
        "Или напиши пропустить чтобы пропустить фото:"
    )

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_config(
            data['config_name'], 
            data['config_full_desc'], 
            data['config_url'], 
            data['config_version'], 
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Конфиг добавлен!\nID: {item_id}\nДобавлено фото: {len(media_list)}", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении конфига", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_config(
            data['config_name'], 
            data['config_full_desc'], 
            data['config_url'], 
            data['config_version'], 
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ Конфиг добавлен!\nID: {item_id} (без фото)", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении конфига", 
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать готово"
        )
    else:
        await message.answer("❌ Отправь фото, или напиши готово / пропустить")

# ========== АДМИН: СПИСКИ ==========
@dp.callback_query(lambda c: c.data == "list_clients")
async def list_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("clients", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        text = "📭 Список клиентов пуст"
    else:
        text = f"📋 Список клиентов (стр 1/{total_pages}):\n\n"
        for item_id, name, full_desc, media_json, downloads, version in items:
            downloads = int(downloads) if downloads else 0
            text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data="list_clients_page_2"))
    
    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("list_clients_page_"))
async def list_clients_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("list_clients_page_", ""))
    items, total = get_all_items_paginated("clients", page)
    total_pages = max(1, (total + 9) // 10)
    
    text = f"📋 Список клиентов (стр {page}/{total_pages}):\n\n"
    for item_id, name, full_desc, media_json, downloads, version in items:
        downloads = int(downloads) if downloads else 0
        text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"list_clients_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"list_clients_page_{page+1}"))
    
    buttons = [nav_row] if nav_row else []
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "list_packs")
async def list_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("resourcepacks", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        text = "📭 Список ресурспаков пуст"
    else:
        text = f"📋 Список ресурспаков (стр 1/{total_pages}):\n\n"
        for item_id, name, full_desc, media_json, downloads, version in items:
            downloads = int(downloads) if downloads else 0
            text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data="list_packs_page_2"))
    
    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("list_packs_page_"))
async def list_packs_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("list_packs_page_", ""))
    items, total = get_all_items_paginated("resourcepacks", page)
    total_pages = max(1, (total + 9) // 10)
    
    text = f"📋 Список ресурспаков (стр {page}/{total_pages}):\n\n"
    for item_id, name, full_desc, media_json, downloads, version in items:
        downloads = int(downloads) if downloads else 0
        text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"list_packs_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"list_packs_page_{page+1}"))
    
    buttons = [nav_row] if nav_row else []
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "list_configs")
async def list_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items, total = get_all_items_paginated("configs", 1)
    total_pages = max(1, (total + 9) // 10)
    
    if not items:
        text = "📭 Список конфигов пуст"
    else:
        text = f"📋 Список конфигов (стр 1/{total_pages}):\n\n"
        for item_id, name, full_desc, media_json, downloads, version in items:
            downloads = int(downloads) if downloads else 0
            text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data="list_configs_page_2"))
    
    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("list_configs_page_"))
async def list_configs_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("list_configs_page_", ""))
    items, total = get_all_items_paginated("configs", page)
    total_pages = max(1, (total + 9) // 10)
    
    text = f"📋 Список конфигов (стр {page}/{total_pages}):\n\n"
    for item_id, name, full_desc, media_json, downloads, version in items:
        downloads = int(downloads) if downloads else 0
        text += f"{item_id}. {name} ({version})\n   📥 {format_number(downloads)}\n\n"
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"list_configs_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"list_configs_page_{page+1}"))
    
    buttons = [nav_row] if nav_row else []
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== ИСПРАВЛЕННЫЙ КОД ДЛЯ БЭКАПОВ ==========
@dp.callback_query(lambda c: c.data == "admin_zip_backups")
async def admin_zip_backups(callback: CallbackQuery):
    """Меню ZIP бэкапов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    backups = get_all_backups()
    
    created = [b for b in backups if b.startswith('backup_')]
    uploaded = [b for b in backups if b.startswith('uploaded_')]
    all_backups = created + uploaded
    
    text = "📦 ZIP Бэкапы\n\n"
    text += f"Всего бэкапов: {len(all_backups)}\n\n"
    
    if all_backups:
        for i, b in enumerate(all_backups[:10], 1):
            try:
                size = (BACKUP_DIR / b).stat().st_size // 1024
                if b.startswith('backup_'):
                    display = b.replace('backup_', '📦 ').replace('.zip', '')
                else:
                    display = b.replace('uploaded_', '📤 ').replace('.zip', '')
                text += f"{i}. {display[:30]}... ({size} KB)\n"
            except:
                text += f"{i}. {b[:30]}... (ошибка)\n"
    else:
        text += "❌ Бэкапов пока нет!\n"
    
    buttons = []
    for i, b in enumerate(all_backups[:10], 1):
        safe_name = b.replace('.', '_dot_').replace('-', '_dash_').replace('_', '__')[:50]
        
        try:
            size = (BACKUP_DIR / b).stat().st_size // 1024
            icon = "📦" if b.startswith('backup_') else "📤"
            if b.startswith('backup_'):
                short_name = b[7:20] + "..."
            else:
                short_name = b[9:20] + "..."
            buttons.append([InlineKeyboardButton(
                text=f"{icon} {short_name} ({size} KB)",
                callback_data=f"restore_{safe_name}"
            )])
        except:
            buttons.append([InlineKeyboardButton(
                text=f"{'📦' if b.startswith('backup_') else '📤'} {b[:15]}...",
                callback_data=f"restore_{safe_name}"
            )])
    
    manage = []
    if all_backups:
        manage.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup_backups"))
    manage.extend([
        InlineKeyboardButton(text="📥 Создать", callback_data="create_backup"),
        InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_backup")
    ])
    if manage:
        buttons.append(manage)
    
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_zip_backups")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "create_backup")
async def create_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Создание бэкапа...")
    zip_path, zip_filename = await create_zip_backup()
    
    if zip_path:
        await callback.message.answer_document(
            document=FSInputFile(zip_path),
            caption=f"✅ Бэкап создан: {zip_filename}"
        )
        await admin_zip_backups(callback)
    else:
        await callback.message.edit_text(
            "❌ Ошибка создания бэкапа",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]
            ])
        )

@dp.callback_query(lambda c: c.data.startswith("restore_") and not c.data.startswith("restore_confirm_"))
async def restore_backup(callback: CallbackQuery):
    """Восстановление из бэкапа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    safe_name = callback.data.replace("restore_", "")
    filename = safe_name.replace('_dot_', '.').replace('_dash_', '-').replace('__', '_')
    
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        await callback.answer(f"❌ Файл {filename} не найден", show_alert=True)
        return
    
    issues = check_backup_structure(str(filepath))
    
    try:
        size = filepath.stat().st_size // 1024
        date = datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except:
        size = 0
        date = "?"
    
    icon = "📦" if filename.startswith('backup_') else "📤"
    display = filename.replace('backup_', '').replace('uploaded_', '').replace('.zip', '')
    
    if issues:
        warning_text = "\n\n⚠️ ПРОБЛЕМЫ С БЭКАПОМ:\n" + "\n".join(issues)
        warning_text += "\n\nВосстановление может работать некорректно!"
    else:
        warning_text = ""
    
    safe_name = filename.replace('.', '_dot_').replace('-', '_dash_').replace('_', '__')[:50]
    
    buttons = [
        [InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"restore_confirm_{safe_name}"),
         InlineKeyboardButton(text="❌ Нет", callback_data="admin_zip_backups")]
    ]
    
    await callback.message.edit_text(
        f"{icon} Восстановление\n\nФайл: {display}\nРазмер: {size} KB\nДата: {date}{warning_text}\n\n❗ Данные будут заменены!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("restore_confirm_"))
async def restore_confirm(callback: CallbackQuery):
    """Подтверждение восстановления"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    safe_name = callback.data.replace("restore_confirm_", "")
    filename = safe_name.replace('_dot_', '.').replace('_dash_', '-').replace('__', '_')
    
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        await callback.answer("❌ Файл не найден", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Восстановление...")
    await create_zip_backup()
    success = await restore_from_zip(str(filepath))
    
    if success:
        await callback.message.edit_text(
            "✅ База восстановлена!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ К бэкапам", callback_data="admin_zip_backups")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка восстановления",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]
            ])
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "upload_backup")
async def upload_backup(callback: CallbackQuery, state: FSMContext):
    """Загрузка бэкапа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_backup)
    await callback.message.edit_text(
        "📤 Отправь ZIP файл с бэкапом\n\n"
        "❌ Отмена: /cancel"
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_backup)
async def handle_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Загрузка отменена")
        return
    
    if not message.document:
        await message.answer("❌ Это не файл! Отправь ZIP файл или /cancel")
        return
    
    if not message.document.file_name.endswith('.zip'):
        await message.answer("❌ Файл должен быть ZIP! Отправь ZIP файл или /cancel")
        return
    
    wait_msg = await message.answer("⏳ Загрузка файла...")
    
    try:
        file = await bot.get_file(message.document.file_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        original_name = message.document.file_name.replace('.zip', '')
        safe_name = "".join(c for c in original_name if c.isalnum() or c in '._- ')[:30]
        filename = f"uploaded_{timestamp}_{safe_name}.zip"
        filepath = BACKUP_DIR / filename
        
        await bot.download_file(file.file_path, str(filepath))
        
        issues = check_backup_structure(str(filepath))
        
        size_kb = filepath.stat().st_size // 1024
        
        if issues:
            warning = "\n⚠️ ПРОБЛЕМЫ:\n" + "\n".join(issues)
            await wait_msg.edit_text(
                f"⚠️ Файл загружен, но есть проблемы:\n\n"
                f"Имя: {filename}\n"
                f"Размер: {size_kb} KB{warning}\n\n"
                f"Исправь файл и загрузи снова."
            )
        else:
            await wait_msg.edit_text(
                f"✅ ZIP файл успешно загружен!\n\n"
                f"Имя: {filename}\n"
                f"Размер: {size_kb} KB\n"
                f"Структура: ✅ корректна"
            )
        
        await state.clear()
        
        backups = get_all_backups()
        created = [b for b in backups if b.startswith('backup_')]
        uploaded = [b for b in backups if b.startswith('uploaded_')]
        all_backups = created + uploaded
        
        text = "📦 ZIP Бэкапы\n\n"
        text += f"Всего бэкапов: {len(all_backups)}\n\n"
        
        if all_backups:
            for i, b in enumerate(all_backups[:10], 1):
                try:
                    size = (BACKUP_DIR / b).stat().st_size // 1024
                    if b.startswith('backup_'):
                        display = b.replace('backup_', '📦 ').replace('.zip', '')
                    else:
                        display = b.replace('uploaded_', '📤 ').replace('.zip', '')
                    text += f"{i}. {display[:30]}... ({size} KB)\n"
                except:
                    text += f"{i}. {b[:30]}... (ошибка)\n"
        else:
            text += "❌ Бэкапов пока нет!\n"
        
        buttons = []
        for i, b in enumerate(all_backups[:10], 1):
            safe_name = b.replace('.', '_dot_').replace('-', '_dash_').replace('_', '__')[:50]
            try:
                size = (BACKUP_DIR / b).stat().st_size // 1024
                icon = "📦" if b.startswith('backup_') else "📤"
                if b.startswith('backup_'):
                    short_name = b[7:20] + "..."
                else:
                    short_name = b[9:20] + "..."
                buttons.append([InlineKeyboardButton(
                    text=f"{icon} {short_name} ({size} KB)",
                    callback_data=f"restore_{safe_name}"
                )])
            except:
                buttons.append([InlineKeyboardButton(
                    text=f"{'📦' if b.startswith('backup_') else '📤'} {b[:15]}...",
                    callback_data=f"restore_{safe_name}"
                )])
        
        manage = []
        if all_backups:
            manage.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup_backups"))
        manage.extend([
            InlineKeyboardButton(text="📥 Создать", callback_data="create_backup"),
            InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_backup")
        ])
        if manage:
            buttons.append(manage)
        buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_zip_backups")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: {str(e)}")
        await state.clear()

@dp.callback_query(lambda c: c.data == "cleanup_backups")
async def cleanup_backups(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    buttons = [
        [InlineKeyboardButton(text="🧹 Удалить все", callback_data="cleanup_all"),
         InlineKeyboardButton(text="🗑 Кроме 5 последних", callback_data="cleanup_old")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_zip_backups")]
    ]
    await callback.message.edit_text("🗑 Очистка бэкапов", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cleanup_all")
async def cleanup_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Удаление...")
    deleted = 0
    for b in get_all_backups():
        try:
            (BACKUP_DIR / b).unlink()
            deleted += 1
        except:
            pass
    await callback.message.edit_text(f"✅ Удалено: {deleted}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cleanup_old")
async def cleanup_old(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    backups = get_all_backups()
    backups.sort(reverse=True)
    
    if len(backups) <= 5:
        await callback.answer("❌ Мало бэкапов", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Удаление...")
    deleted = 0
    for b in backups[5:]:
        try:
            (BACKUP_DIR / b).unlink()
            deleted += 1
        except:
            pass
    await callback.message.edit_text(f"✅ Удалено: {deleted}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))
    await callback.answer()

# ========== АДМИН: СТАТИСТИКА ==========
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    users_count = get_users_count()
    backups_count = len(get_all_backups())
    
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    clients_count = cur.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
    packs_count = cur.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]
    configs_count = cur.execute('SELECT COUNT(*) FROM configs').fetchone()[0]
    conn.close()
    
    await callback.message.edit_text(
        f"📊 Статистика\n\n👤 Пользователей: {users_count}\n🎮 Клиентов: {clients_count}\n🎨 Ресурспаков: {packs_count}\n⚙️ Конфигов: {configs_count}\n📦 Бэкапов: {backups_count}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]])
    )
    await callback.answer()

# ========== АДМИН: РАССЫЛКА ==========
@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    users_count = get_users_count()
    await state.set_state(AdminStates.broadcast_text)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📢 Создание рассылки\n\n"
        f"Всего пользователей: {users_count}\n\n"
        f"Введи текст сообщения для рассылки (или отправь /cancel для отмены):"
    )
    await callback.answer()

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.broadcast_photo)
    await message.answer(
        "📸 Отправь фото для рассылки (или отправь 'пропустить' чтобы отправить только текст):\n\n"
        "Или отправь /cancel для отмены"
    )

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'пропустить':
        photo_id = None
    else:
        await message.answer("❌ Отправь фото или напиши 'пропустить' (или /cancel)")
        return
    
    users = get_all_users()
    
    if not users:
        await message.answer("❌ Нет пользователей для рассылки")
        await state.clear()
        return
    
    preview_text = f"📢 ПРЕДПРОСМОТР РАССЫЛКИ\n\n{text}\n\nВсего получателей: {len(users)}"
    
    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=preview_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_send")],
                [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="broadcast_cancel")]
            ])
        )
    else:
        await message.answer(
            preview_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_send")],
                [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="broadcast_cancel")]
            ])
        )
    
    await state.update_data(broadcast_photo=photo_id, broadcast_text=text)

@dp.callback_query(lambda c: c.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    photo_id = data.get('broadcast_photo')
    
    users = get_all_users()
    
    if not users:
        await callback.message.edit_text("❌ Нет пользователей для рассылки")
        await state.clear()
        return
    
    await callback.message.delete()
    status_msg = await callback.message.answer(f"📢 Рассылка началась...\n\n✅ Отправлено: 0/{len(users)}\n⏳ Ожидайте...")
    
    sent = 0
    failed = 0
    
    for i, user_id in enumerate(users, 1):
        try:
            if photo_id:
                await bot.send_photo(chat_id=user_id, photo=photo_id, caption=text)
            else:
                await bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
        
        if i % 10 == 0:
            await status_msg.edit_text(f"📢 Рассылка...\n\n✅ Отправлено: {sent}/{len(users)}\n❌ Ошибок: {failed}")
        
        await asyncio.sleep(0.05)
    
    await state.clear()
    
    result_text = (
        f"📢 РАССЫЛКА ЗАВЕРШЕНА!\n\n"
        f"📊 Статистика:\n"
        f"• Всего пользователей: {len(users)}\n"
        f"• ✅ Успешно отправлено: {sent}\n"
        f"• ❌ Не доставлено: {failed}\n"
        f"• 📈 Процент доставки: {sent/len(users)*100:.1f}%"
    )
    
    await status_msg.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "❌ Рассылка отменена",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    await callback.answer()

# ========== МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith("media_"))
async def view_media(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        
        category, item_id = parts[1], int(parts[2])
        item = get_item(category, item_id)
        
        if not item:
            await callback.answer("❌ Не найден", show_alert=True)
            return
        
        try:
            media_list = json.loads(item[4]) if item[4] else []
        except:
            media_list = []
            logger.error(f"Ошибка парсинга media для {category} {item_id}")
        
        if not media_list:
            await callback.answer("📭 Нет медиа", show_alert=True)
            return
        
        if media_list[0]['type'] != 'photo':
            await callback.answer("❌ Неподдерживаемый тип медиа", show_alert=True)
            return
        
        await state.update_data(
            media_list=media_list, 
            media_index=0, 
            media_category=category, 
            media_item_id=item_id
        )
        
        await show_media(callback.message, state, 0)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в view_media: {e}")
        await callback.answer("❌ Ошибка загрузки медиа", show_alert=True)

async def show_media(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if not media_list or index >= len(media_list):
        await message.answer("❌ Медиа не найдено")
        return
    
    media = media_list[index]
    
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{index-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{index+1}/{len(media_list)}", callback_data="noop"))
    
    if index < len(media_list) - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{index+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))
    
    buttons = [
        nav_buttons,
        [InlineKeyboardButton(text="◀️ Назад", callback_data="media_back")]
    ]
    
    await state.update_data(media_index=index)
    
    try:
        if media['type'] == 'photo':
            await message.answer_photo(
                photo=media['id'], 
                caption=f"📸 {index+1} из {len(media_list)}", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        else:
            await message.answer(
                f"❌ Неподдерживаемый тип медиа\n\n{index+1}/{len(media_list)}", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        await message.answer(
            f"❌ Ошибка загрузки фото {index+1}/{len(media_list)}", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_nav(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.replace("media_nav_", ""))
        await show_media(callback.message, state, index)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка навигации: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    
    await state.clear()
    
    if category and item_id:
        new_callback = callback
        new_callback.data = f"detail_{category}_{item_id}"
        await detail_view(new_callback, state)
    else:
        await callback.message.delete()
        await callback.answer()

# ========== ЗАГЛУШКИ ==========
@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    is_admin = (callback.from_user.id == ADMIN_ID)
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard(is_admin))
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👤 Создатель: {CREATOR_USERNAME}")
    print(f"📁 Папка данных: {DATA_DIR}")
    print("="*50)
    print("📌 Новые функции:")
    print("   • 👤 Профиль с приветствием")
    print("   • 🎉 Бот полностью бесплатный")
    print("   • 📊 Статистика скачиваний")
    print("   • 🔧 Исправлена кнопка Инфо")
    print("   • 🔧 Исправлена пагинация")
    print("   • 🔧 Исправлены бэкапы")
    print("   • 🖼️ Редактирование фото")
    print("   • 📑 Пагинация в админке")
    print("   • 📢 Исправлена рассылка")
    print("   • 🔧 Исправлена ошибка со скачиванием")
    print("   • 🔍 Проверка структуры бэкапов")
    print("="*50)
    
    try:
        me = await bot.get_me()
        print(f"✅ Бот @{me.username} успешно подключен к Telegram!")
    except Exception as e:
        print(f"❌ Ошибка подключения к Telegram: {e}")
        print("Проверьте токен в переменных окружения на bothost.ru")
        return
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⛔ Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")