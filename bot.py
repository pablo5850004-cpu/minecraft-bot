import logging
import os
import asyncio
import json
import sqlite3
import random
import shutil
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 5809098591
CREATOR_USERNAME = "@Strann1k_fiol"

if not BOT_TOKEN:
    raise ValueError("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")

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
    """Создание базы данных клиентов"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    # Клиенты
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            short_desc TEXT NOT NULL,
            full_desc TEXT NOT NULL,
            media TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            version TEXT,
            downloads INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Ресурспаки
    cur.execute('''
        CREATE TABLE IF NOT EXISTS resourcepacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            short_desc TEXT NOT NULL,
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
    
    # Конфиги
    cur.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            short_desc TEXT NOT NULL,
            full_desc TEXT NOT NULL,
            media TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            version TEXT,
            downloads INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Избранное
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

def init_users_db():
    """Создание базы данных пользователей с поддержкой лимитов и VIP"""
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    
    # Основная таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            status TEXT DEFAULT 'user',
            vip_until TIMESTAMP,
            invites INTEGER DEFAULT 0,
            downloads_this_week INTEGER DEFAULT 0,
            last_download_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для реферальных приглашений
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    ''')
    
    # Таблица для отслеживания скачиваний
    cur.execute('''
        CREATE TABLE IF NOT EXISTS downloads_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных пользователей обновлена с поддержкой VIP")

# Инициализация
init_db()
init_users_db()

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========
def get_users_count() -> int:
    """Получить количество пользователей"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users')
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Ошибка получения количества пользователей: {e}")
        return 0

def get_all_users() -> list:
    """Получить список всех пользователей"""
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
    """Получить статус пользователя"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute('''
            SELECT user_id, username, status, vip_until, invites, downloads_this_week 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        user = cur.fetchone()
        
        if not user:
            # Если пользователя нет, создаём нового
            cur.execute('''
                INSERT INTO users (user_id, status) VALUES (?, 'user')
            ''', (user_id,))
            conn.commit()
            status_data = {
                'user_id': user_id,
                'status': 'user',
                'vip_until': None,
                'is_vip': False,
                'is_admin': (user_id == ADMIN_ID),
                'invites': 0,
                'downloads_left': 1
            }
        else:
            # Проверяем, не истёк ли VIP
            vip_until = user[3]
            is_vip = False
            if vip_until:
                try:
                    vip_date = datetime.fromisoformat(vip_until)
                    is_vip = vip_date > datetime.now()
                except:
                    is_vip = False
            
            status_data = {
                'user_id': user[0],
                'status': user[2],
                'vip_until': vip_until,
                'is_vip': is_vip,
                'is_admin': (user_id == ADMIN_ID),
                'invites': user[4] or 0,
                'downloads_left': None if is_vip or user_id == ADMIN_ID else max(0, 1 - (user[5] or 0))
            }
        
        conn.close()
        return status_data
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return {
            'user_id': user_id,
            'status': 'user',
            'is_vip': False,
            'is_admin': (user_id == ADMIN_ID),
            'invites': 0,
            'downloads_left': 1
        }

def can_download(user_id: int) -> tuple:
    """Проверить, может ли пользователь скачать файл"""
    try:
        # Админ может всё
        if user_id == ADMIN_ID:
            return True, "admin"
        
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        # Получаем информацию о пользователе
        cur.execute('SELECT status, vip_until, downloads_this_week, last_download_reset FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        
        if not user:
            conn.close()
            return True, "new_user"  # Новый пользователь может скачать первый раз
        
        status, vip_until, downloads_this_week, last_reset = user
        
        # Проверяем VIP
        if vip_until:
            try:
                vip_date = datetime.fromisoformat(vip_until)
                if vip_date > datetime.now():
                    conn.close()
                    return True, "vip"
            except:
                pass
        
        # Проверяем недельный лимит
        # Если прошло больше недели с последнего сброса - обнуляем
        if last_reset:
            try:
                last_reset_date = datetime.fromisoformat(last_reset)
                if (datetime.now() - last_reset_date).days >= 7:
                    cur.execute('UPDATE users SET downloads_this_week = 0, last_download_reset = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
                    downloads_this_week = 0
                    conn.commit()
            except:
                pass
        
        if downloads_this_week < 1:
            conn.close()
            return True, "user"
        else:
            conn.close()
            return False, "limit_reached"
            
    except Exception as e:
        logger.error(f"Ошибка проверки скачивания: {e}")
        return True, "error"  # В случае ошибки разрешаем

def increment_download_count(user_id: int):
    """Увеличить счётчик скачиваний пользователя"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        # Проверяем, нужно ли сбросить счётчик
        cur.execute('SELECT downloads_this_week, last_download_reset FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        
        downloads = 0
        if user:
            downloads, last_reset = user
            if last_reset:
                try:
                    last_reset_date = datetime.fromisoformat(last_reset)
                    if (datetime.now() - last_reset_date).days >= 7:
                        downloads = 0
                except:
                    pass
        
        cur.execute('''
            UPDATE users SET 
                downloads_this_week = ?,
                last_download_reset = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', ((downloads or 0) + 1, user_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения счётчика: {e}")

def add_referral(referrer_id: int, referred_id: int):
    """Добавить реферала и активировать VIP для пригласившего"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        # Добавляем запись о реферале
        cur.execute('''
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)
        ''', (referrer_id, referred_id))
        
        if cur.rowcount > 0:
            # Увеличиваем счётчик приглашений
            cur.execute('''
                UPDATE users SET invites = invites + 1 WHERE user_id = ?
            ''', (referrer_id,))
            
            # VIP навсегда (ставим дату на 100 лет вперёд)
            far_future = (datetime.now() + timedelta(days=36500)).isoformat()
            cur.execute('''
                UPDATE users SET status = 'vip', vip_until = ? WHERE user_id = ?
            ''', (far_future, referrer_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления реферала: {e}")
        return False

def save_user(message: Message):
    """Сохранить пользователя с проверкой реферальной ссылки"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        # Проверяем, есть ли пользователь
        cur.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cur.fetchone()
        
        if not exists:
            # Новый пользователь - проверяем реферальную ссылку
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
        logger.error(f"Ошибка сохранения пользователя: {e}")

# ========== ОБЩИЕ ФУНКЦИИ ДЛЯ РАБОТЫ С БД ==========
def get_item(table: str, item_id: int):
    """Получить элемент по ID"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
    item = cur.fetchone()
    conn.close()
    return item

def get_all_items(table: str):
    """Получить все элементы"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, short_desc, media, downloads, version FROM {table} ORDER BY created_at DESC')
    items = cur.fetchall()
    conn.close()
    return items

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ ДЛЯ КЛИЕНТОВ ==========
def add_client(name, short_desc, full_desc, url, version, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO clients (name, short_desc, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления клиента: {e}")
        return None

def update_client(item_id, field, value):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

def get_clients_by_version(version, page=1, per_page=10):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, views, version 
        FROM clients WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    items = cur.fetchall()
    total = cur.execute('SELECT COUNT(*) FROM clients WHERE version = ?', (version,)).fetchone()[0]
    conn.close()
    return items, total

def get_all_client_versions():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ РЕСУРСПАКОВ ==========
def add_pack(name, short_desc, full_desc, url, version, author, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO resourcepacks (name, short_desc, full_desc, download_url, version, author, media)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, author, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления ресурспака: {e}")
        return None

def update_pack(item_id, field, value):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

def get_packs_by_version(version, page=1, per_page=10):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, likes, views, version, author 
        FROM resourcepacks WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    items = cur.fetchall()
    total = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (version,)).fetchone()[0]
    conn.close()
    return items, total

def get_all_pack_versions():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM resourcepacks WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ КОНФИГОВ ==========
def add_config(name, short_desc, full_desc, url, version, media=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO configs (name, short_desc, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления конфига: {e}")
        return None

def update_config(item_id, field, value):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

def get_configs_by_version(version, page=1, per_page=10):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, views, version 
        FROM configs WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    items = cur.fetchall()
    total = cur.execute('SELECT COUNT(*) FROM configs WHERE version = ?', (version,)).fetchone()[0]
    conn.close()
    return items, total

def get_all_config_versions():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM configs WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ ИЗБРАННОГО ==========
def toggle_favorite(user_id, pack_id):
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

def get_favorites(user_id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('''
        SELECT r.id, r.name, r.short_desc, r.media, r.downloads, r.likes 
        FROM resourcepacks r JOIN favorites f ON r.id = f.pack_id
        WHERE f.user_id = ? ORDER BY f.added_at DESC
    ''', (user_id,))
    favs = cur.fetchall()
    conn.close()
    return favs

# ========== ФУНКЦИИ ДЛЯ СТАТИСТИКИ ==========
def increment_view(table, item_id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def increment_download(table, item_id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ ДЛЯ БЭКАПОВ ==========
def get_all_backups():
    try:
        files = os.listdir(str(BACKUP_DIR))
        backups = [f for f in files if f.endswith('.zip')]
        backups.sort(reverse=True)
        return backups
    except Exception as e:
        print(f"Ошибка получения списка: {e}")
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

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_number(num):
    if num < 1000: return str(num)
    elif num < 1000000: return f"{num/1000:.1f}K"
    else: return f"{num/1000000:.1f}M"

def get_version_display(version):
    return f"({version})"

# ========== СОСТОЯНИЯ ==========
class AdminStates(StatesGroup):
    client_name = State()
    client_short_desc = State()
    client_full_desc = State()
    client_version = State()
    client_url = State()
    client_media = State()
    
    pack_name = State()
    pack_short_desc = State()
    pack_full_desc = State()
    pack_version = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    
    config_name = State()
    config_short_desc = State()
    config_full_desc = State()
    config_version = State()
    config_url = State()
    config_media = State()
    
    edit_value = State()
    broadcast_text = State()
    broadcast_photo = State()
    waiting_for_backup = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin=False):
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты"), types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="❤️ Избранное"), types.KeyboardButton(text="⚙️ Конфиги"), types.KeyboardButton(text="👤 Профиль")],
        [types.KeyboardButton(text="ℹ️ Инфо"), types.KeyboardButton(text="❓ Помощь")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

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
        item_id, name, short_desc, media_json, downloads = item[0], item[1], item[2], item[3], item[4]
        version = item[6] if len(item) > 6 else "?"
        try:
            media_list = json.loads(media_json) if media_json else []
        except:
            media_list = []
        preview = "🖼️" if media_list else "📄"
        button_text = f"{preview} {name[:30]} ({version})\n{short_desc[:40]}... 📥 {format_number(downloads)}"
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

def get_help_keyboard():
    buttons = [
        [InlineKeyboardButton(text="👤 Связаться с админом", url=f"https://t.me/{CREATOR_USERNAME[1:]}")],
        [InlineKeyboardButton(text="📋 Правила", callback_data="help_rules")],
        [InlineKeyboardButton(text="❓ Часто задаваемые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_broadcast_confirm_keyboard():
    buttons = [
        [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_backups_keyboard():
    backups = get_all_backups()
    buttons = []
    for backup in backups[:5]:
        size = (BACKUP_DIR / backup).stat().st_size // 1024
        buttons.append([InlineKeyboardButton(text=f"📦 {backup[:20]}... ({size} KB)", callback_data=f"restore_{backup}")])
    buttons.append([InlineKeyboardButton(text="📥 Создать бэкап", callback_data="create_backup")])
    buttons.append([InlineKeyboardButton(text="📤 Загрузить ZIP", callback_data="upload_backup")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = (message.from_user.id == ADMIN_ID)
    save_user(message)
    await message.answer(
        "👋 **Привет! Я бот-каталог Minecraft**\n\n"
        "🎮 Клиенты - моды и сборки\n"
        "🎨 Ресурспаки - текстурпаки\n"
        "❤️ Избранное - сохраняй понравившееся\n"
        "⚙️ Конфиги - настройки\n"
        "👤 Профиль - твой статус и лимиты\n"
        "ℹ️ Инфо - о боте и создателе\n"
        "❓ Помощь - связаться с админом\n\n"
        "Используй кнопки ниже:",
        parse_mode="Markdown",
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
    """Показать профиль пользователя"""
    try:
        user_id = message.from_user.id
        status_data = get_user_status(user_id)
        
        # Определяем статус
        if user_id == ADMIN_ID:
            status_text = "👑 СОЗДАТЕЛЬ"
        elif status_data.get('is_admin'):
            status_text = "⚙️ АДМИН"
        elif status_data.get('is_vip'):
            status_text = "💎 VIP"
        else:
            status_text = "👤 ПОЛЬЗОВАТЕЛЬ"
        
        # Информация о лимитах
        if user_id == ADMIN_ID or status_data.get('is_vip'):
            limit_text = "∞ Безлимитно"
        else:
            limit_text = f"{status_data.get('downloads_left', 1)}/1 на этой неделе"
        
        # Реферальная ссылка
        bot_info = await bot.me()
        bot_username = bot_info.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        text = (
            f"**👤 Твой профиль**\n\n"
            f"**Статус:** {status_text}\n"
            f"**ID:** `{user_id}`\n"
            f"**Приглашений:** {status_data.get('invites', 0)}\n"
            f"**Лимит скачиваний:** {limit_text}\n\n"
            f"**💎 Как получить VIP?**\n"
            f"Пригласи 1 друга в бота и получи VIP навсегда!\n\n"
            f"**Твоя реферальная ссылка:**\n"
            f"`{ref_link}`\n\n"
            f"Просто отправь эту ссылку друзьям."
        )
        
        # Кнопки для профиля
        buttons = [
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="profile_stats")],
            [InlineKeyboardButton(text="📋 Мои скачивания", callback_data="profile_downloads")]
        ]
        
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception as e:
        logger.error(f"Ошибка в профиле: {e}")
        await message.answer(
            "❌ **Ошибка загрузки профиля**\n"
            "Попробуй позже или напиши админу.",
            parse_mode="Markdown"
        )

@dp.callback_query(lambda c: c.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    """Показать статистику пользователя"""
    try:
        user_id = callback.from_user.id
        
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        # Количество скачиваний
        cur.execute('SELECT COUNT(*) FROM downloads_log WHERE user_id = ?', (user_id,))
        total_downloads = cur.fetchone()[0]
        
        # Количество приглашений
        cur.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        total_invites = cur.fetchone()[0]
        
        # Последние скачивания
        cur.execute('''
            SELECT item_type, downloaded_at FROM downloads_log 
            WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 5
        ''', (user_id,))
        recent = cur.fetchall()
        
        conn.close()
        
        text = f"**📊 Твоя статистика**\n\n"
        text += f"📥 Всего скачиваний: {total_downloads}\n"
        text += f"👥 Приглашено друзей: {total_invites}\n\n"
        
        if recent:
            text += "**Последние скачивания:**\n"
            for item_type, date in recent:
                date_str = date[:10] if date else "недавно"
                text += f"• {item_type} - {date_str}\n"
        
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка в статистике профиля: {e}")
        await callback.message.edit_text(
            "❌ **Ошибка загрузки статистики**",
            parse_mode="Markdown"
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_downloads")
async def profile_downloads(callback: CallbackQuery):
    """Показать историю скачиваний"""
    try:
        user_id = callback.from_user.id
        
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        cur.execute('''
            SELECT item_type, item_id, downloaded_at FROM downloads_log 
            WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 10
        ''', (user_id,))
        downloads = cur.fetchall()
        conn.close()
        
        if not downloads:
            text = "📭 **У тебя пока нет скачиваний**"
        else:
            text = "**📋 Твои скачивания:**\n\n"
            for i, (item_type, item_id, date) in enumerate(downloads, 1):
                date_str = date[:10] if date else "недавно"
                text += f"{i}. {item_type} (ID: {item_id}) - {date_str}\n"
        
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка в истории скачиваний: {e}")
        await callback.message.edit_text(
            "❌ **Ошибка загрузки истории**",
            parse_mode="Markdown"
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    """Вернуться в профиль"""
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
        title = f"🎮 Клиенты для версии {version}"
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        items, total = get_packs_by_version(version, page)
        title = f"🎨 Ресурспаки для версии {version}"
    else:
        version = data.get("config_version", "1.20")
        items, total = get_configs_by_version(version, page)
        title = f"⚙️ Конфиги для версии {version}"
    
    total_pages = (total + 9) // 10
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
    
    media_list = json.loads(item[4]) if item[4] else []
    
    if category == "clients":
        text = f"**{item[1]}**\n\n{item[3]}\n\nВерсия: {item[6]}\n📥 Скачиваний: {format_number(item[7])}\n👁 Просмотров: {format_number(item[8])}"
    elif category == "packs":
        # Проверяем избранное
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        is_fav = cur.execute('SELECT 1 FROM favorites WHERE user_id = ? AND pack_id = ?', (callback.from_user.id, item_id)).fetchone()
        conn.close()
        text = f"**{item[1]}**\n\n{item[3]}\n\nАвтор: {item[7]}\nВерсия: {item[6]}\n📥 Скачиваний: {format_number(item[8])}\n❤️ В избранном: {format_number(item[9])}\n👁 Просмотров: {format_number(item[10])}"
    else:
        text = f"**{item[1]}**\n\n{item[3]}\n\nВерсия: {item[6]}\n📥 Скачиваний: {format_number(item[7])}\n👁 Просмотров: {format_number(item[8])}"
    
    if media_list and media_list[0]['type'] == 'photo':
        await callback.message.answer_photo(photo=media_list[0]['id'], caption=text, parse_mode="Markdown", reply_markup=get_detail_keyboard(category, item_id, is_fav if category == 'packs' else False))
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_detail_keyboard(category, item_id, is_fav if category == 'packs' else False))
    
    await callback.answer()

# ========== НАВИГАЦИЯ НАЗАД ==========
@dp.callback_query(lambda c: c.data.startswith("back_"))
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("back_", "")
    data = await state.get_data()
    
    if category == "clients":
        version = data.get("client_version", "1.20")
        page = data.get("client_page", 1)
        items, total = get_clients_by_version(version, page)
        title = f"🎮 Клиенты для версии {version}"
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        page = data.get("pack_page", 1)
        items, total = get_packs_by_version(version, page)
        title = f"🎨 Ресурспаки для версии {version}"
    else:
        version = data.get("config_version", "1.20")
        page = data.get("config_page", 1)
        items, total = get_configs_by_version(version, page)
        title = f"⚙️ Конфиги для версии {version}"
    
    total_pages = (total + 9) // 10
    await callback.message.edit_text(f"{title} (стр {page}/{total_pages}):", reply_markup=get_items_keyboard(items, category, page, total_pages))
    await callback.answer()

# ========== СКАЧИВАНИЕ С ПРОВЕРКОЙ ЛИМИТОВ ==========
@dp.callback_query(lambda c: c.data.startswith("download_"))
async def download_item(callback: CallbackQuery):
    """Скачивание с проверкой лимитов"""
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    user_id = callback.from_user.id
    
    # Проверяем, может ли пользователь скачать
    can_dl, reason = can_download(user_id)
    
    if not can_dl:
        if reason == "limit_reached":
            # Получаем реферальную ссылку
            bot_info = await bot.me()
            bot_username = bot_info.username
            ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
            
            await callback.message.answer(
                "⚠️ **Лимит скачиваний исчерпан!**\n\n"
                "На этой неделе ты уже скачал 1 файл.\n\n"
                "💎 **Хочешь скачивать безлимитно?**\n"
                "Пригласи 1 друга в бота и получи VIP навсегда!\n\n"
                f"**Твоя реферальная ссылка:**\n`{ref_link}`\n\n"
                "Просто отправь её друзьям.",
                parse_mode="Markdown"
            )
        await callback.answer("❌ Лимит исчерпан", show_alert=True)
        return
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    # Увеличиваем счётчик скачиваний
    increment_download(category, item_id)
    increment_download_count(user_id)
    
    # Логируем скачивание
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO downloads_log (user_id, item_type, item_id) VALUES (?, ?, ?)
        ''', (user_id, category, item_id))
        conn.commit()
        conn.close()
    except:
        pass
    
    url = item[5]
    name = item[1]
    
    await callback.message.answer(
        f"📥 **Скачать {name}**\n\n{url}",
        parse_mode="Markdown"
    )
    await callback.answer("✅ Ссылка отправлена!")

# ========== ИЗБРАННОЕ ==========
@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("❤️ **Избранное пусто**\n\nДобавляй ресурспаки в избранное кнопкой 🤍", parse_mode="Markdown")
        return
    text = "❤️ **Твоё избранное:**\n\n"
    for fav in favs[:10]:
        text += f"• {fav[1]} - {format_number(fav[4])} 📥\n"
    await message.answer(text, parse_mode="Markdown")

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
    """Информация о боте"""
    try:
        users_count = get_users_count()
        backups_count = len(get_all_backups())
        
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        clients_count = cur.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
        packs_count = cur.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]
        configs_count = cur.execute('SELECT COUNT(*) FROM configs').fetchone()[0]
        conn.close()
        
        await message.answer(
            f"**Информация о боте**\n\n"
            f"Создатель: {CREATOR_USERNAME}\n"
            f"Версия: 13.2\n\n"
            f"📊 **Статистика:**\n"
            f"• Пользователей: {users_count}\n"
            f"• Клиентов: {clients_count}\n"
            f"• Ресурспаков: {packs_count}\n"
            f"• Конфигов: {configs_count}\n"
            f"• ZIP бэкапов: {backups_count}\n\n"
            f"📁 Данные хранятся в `/app/data`\n"
            f"💎 VIP даётся за приглашение друга!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка в info: {e}")
        await message.answer(
            f"**Информация о боте**\n\n"
            f"Создатель: {CREATOR_USERNAME}\n"
            f"Версия: 13.2",
            parse_mode="Markdown"
        )

# ========== ПОМОЩЬ ==========
@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    await message.answer(
        "❓ **Помощь и поддержка**\n\n"
        "Если у тебя возникли вопросы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем",
        parse_mode="Markdown",
        reply_markup=get_help_keyboard()
    )

@dp.callback_query(lambda c: c.data == "help_rules")
async def help_rules(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 **Правила использования**\n\n"
        "1. Все файлы предоставляются 'как есть'\n"
        "2. Автор не несёт ответственности за использование файлов\n"
        "3. Уважайте других пользователей",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help_faq")
async def help_faq(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ **Часто задаваемые вопросы**\n\n"
        "**Q:** Как скачать файл?\n"
        "**A:** Нажми на элемент, затем кнопку 'Скачать'\n\n"
        "**Q:** Как получить VIP?\n"
        "**A:** Пригласи 1 друга в бота по своей реферальной ссылке\n\n"
        "**Q:** Сколько можно скачивать?\n"
        "**A:** 1 файл в неделю, с VIP безлимитно\n\n"
        "**Q:** Как сделать бэкап?\n"
        "**A:** В админ-панели выбери '📦 ZIP Бэкапы' и нажми 'Создать'",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ **Помощь и поддержка**\n\n"
        "Если у тебя возникли вопросы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем",
        parse_mode="Markdown",
        reply_markup=get_help_keyboard()
    )
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ (ГЛАВНАЯ) ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    await message.answer("⚙️ **Админ панель**\n\nВыбери категорию:", parse_mode="Markdown", reply_markup=get_admin_main_keyboard())

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ **Админ панель**\n\nВыбери категорию:", parse_mode="Markdown", reply_markup=get_admin_main_keyboard())
    await callback.answer()

# ========== АДМИН: КЛИЕНТЫ ==========
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
    await callback.message.edit_text("🎮 **Управление клиентами**\n\nВыбери действие:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ----- ДОБАВЛЕНИЕ КЛИЕНТА -----
@dp.callback_query(lambda c: c.data == "add_client")
async def add_client_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.client_name)
    await callback.message.edit_text("📝 **Введи название клиента:**", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.client_name)
async def client_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await state.set_state(AdminStates.client_short_desc)
    await message.answer("📄 Введи **краткое описание**:", parse_mode="Markdown")

@dp.message(AdminStates.client_short_desc)
async def client_short_desc(message: Message, state: FSMContext):
    await state.update_data(client_short_desc=message.text)
    await state.set_state(AdminStates.client_full_desc)
    await message.answer("📚 Введи **полное описание**:", parse_mode="Markdown")

@dp.message(AdminStates.client_full_desc)
async def client_full_desc(message: Message, state: FSMContext):
    await state.update_data(client_full_desc=message.text)
    await state.set_state(AdminStates.client_version)
    await message.answer("🔢 Введи **версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.client_version)
async def client_version(message: Message, state: FSMContext):
    await state.update_data(client_version=message.text)
    await state.set_state(AdminStates.client_url)
    await message.answer("🔗 Введи **ссылку на скачивание:**", parse_mode="Markdown")

@dp.message(AdminStates.client_url)
async def client_url(message: Message, state: FSMContext):
    await state.update_data(client_url=message.text)
    await state.set_state(AdminStates.client_media)
    await message.answer("🖼️ **Отправляй фото** (можно несколько)\n\nПосле того как отправишь все фото, напиши **готово**\nИли напиши **пропустить** чтобы пропустить фото:", parse_mode="Markdown")

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_client(data['client_name'], data['client_short_desc'], data['client_full_desc'], data['client_url'], data['client_version'], media_list)
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Клиент добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении клиента**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_client(data['client_name'], data['client_short_desc'], data['client_full_desc'], data['client_url'], data['client_version'], [])
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Клиент добавлен!**\nID: `{item_id}` (без фото)", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении клиента**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(f"✅ **Фото добавлено!** Всего: {len(media_list)}\nМожешь отправить ещё фото или написать **готово**", parse_mode="Markdown")
    else:
        await message.answer("❌ Отправь фото, или напиши **готово** / **пропустить**", parse_mode="Markdown")

# ----- РЕДАКТИРОВАНИЕ КЛИЕНТА -----
@dp.callback_query(lambda c: c.data == "edit_client_list")
async def edit_client_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("clients")
    if not items:
        await callback.message.edit_text("📭 **Нет клиентов для редактирования**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"edit_client_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")])
    await callback.message.edit_text("✏️ **Выбери клиента для редактирования:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_client_"))
async def edit_client_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("edit_client_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("clients", item_id)
    if not item:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_client_field_name_{item_id}")],
        [InlineKeyboardButton(text="📄 Краткое описание", callback_data=f"edit_client_field_short_{item_id}")],
        [InlineKeyboardButton(text="📚 Полное описание", callback_data=f"edit_client_field_full_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_client_field_version_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_client_field_url_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_client_list")]
    ]
    await callback.message.edit_text(f"✏️ **Редактирование:** {item[1]}\n\nЧто изменить?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=fields))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_client_field_"))
async def edit_client_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    field_map = {'name': 'name', 'short': 'short_desc', 'full': 'full_desc', 'version': 'version', 'url': 'download_url'}
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="clients")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ **Введи новое значение:**", parse_mode="Markdown")
    await callback.answer()

# ----- УДАЛЕНИЕ КЛИЕНТА -----
@dp.callback_query(lambda c: c.data == "delete_client_list")
async def delete_client_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("clients")
    if not items:
        await callback.message.edit_text("📭 **Нет клиентов для удаления**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"delete_client_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")])
    await callback.message.edit_text("🗑 **Выбери клиента для удаления:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_client_") and not c.data.startswith("delete_client_confirm_"))
async def delete_client_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_client_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("clients", item_id)
    if not item:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_client_confirm_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_client_list")]
    ]
    await callback.message.edit_text(f"⚠️ **Подтверждение удаления**\n\nТы действительно хочешь удалить клиента:\n**{item[1]}** (ID: {item_id})?\n\nЭто действие нельзя отменить!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_client_confirm_"))
async def delete_client_execute(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_client_confirm_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    delete_item("clients", item_id)
    await callback.answer("✅ Клиент удалён!", show_alert=True)
    await delete_client_list(callback)

# ----- СПИСОК КЛИЕНТОВ -----
@dp.callback_query(lambda c: c.data == "list_clients")
async def list_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("clients")
    if not items:
        text = "📭 **Список клиентов пуст**"
    else:
        text = "📋 **Список клиентов:**\n\n"
        for item_id, name, short_desc, media_json, downloads, version in items[:20]:
            text += f"`{item_id}`. **{name}** ({version})\n   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]]))
    await callback.answer()

# ========== АДМИН: РЕСУРСПАКИ ==========
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
    await callback.message.edit_text("🎨 **Управление ресурспаками**\n\nВыбери действие:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ----- ДОБАВЛЕНИЕ РЕСУРСПАКА -----
@dp.callback_query(lambda c: c.data == "add_pack")
async def add_pack_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.pack_name)
    await callback.message.edit_text("📝 **Введи название ресурспака:**", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.pack_name)
async def pack_name(message: Message, state: FSMContext):
    await state.update_data(pack_name=message.text)
    await state.set_state(AdminStates.pack_short_desc)
    await message.answer("📄 **Введи краткое описание:**", parse_mode="Markdown")

@dp.message(AdminStates.pack_short_desc)
async def pack_short_desc(message: Message, state: FSMContext):
    await state.update_data(pack_short_desc=message.text)
    await state.set_state(AdminStates.pack_full_desc)
    await message.answer("📚 **Введи полное описание:**", parse_mode="Markdown")

@dp.message(AdminStates.pack_full_desc)
async def pack_full_desc(message: Message, state: FSMContext):
    await state.update_data(pack_full_desc=message.text)
    await state.set_state(AdminStates.pack_version)
    await message.answer("🔢 **Введи версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.pack_version)
async def pack_version(message: Message, state: FSMContext):
    await state.update_data(pack_version=message.text)
    await state.set_state(AdminStates.pack_author)
    await message.answer("✍️ **Введи автора:**", parse_mode="Markdown")

@dp.message(AdminStates.pack_author)
async def pack_author(message: Message, state: FSMContext):
    await state.update_data(pack_author=message.text)
    await state.set_state(AdminStates.pack_url)
    await message.answer("🔗 **Введи ссылку на скачивание:**", parse_mode="Markdown")

@dp.message(AdminStates.pack_url)
async def pack_url(message: Message, state: FSMContext):
    await state.update_data(pack_url=message.text)
    await state.set_state(AdminStates.pack_media)
    await message.answer("🖼️ **Отправляй фото** (можно несколько)\n\nПосле того как отправишь все фото, напиши **готово**\nИли напиши **пропустить** чтобы пропустить фото:", parse_mode="Markdown")

@dp.message(AdminStates.pack_media)
async def pack_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_pack(data['pack_name'], data['pack_short_desc'], data['pack_full_desc'], data['pack_url'], data['pack_version'], data['pack_author'], media_list)
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Ресурспак добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении ресурспака**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_pack(data['pack_name'], data['pack_short_desc'], data['pack_full_desc'], data['pack_url'], data['pack_version'], data['pack_author'], [])
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Ресурспак добавлен!**\nID: `{item_id}` (без фото)", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении ресурспака**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(f"✅ **Фото добавлено!** Всего: {len(media_list)}\nМожешь отправить ещё фото или написать **готово**", parse_mode="Markdown")
    else:
        await message.answer("❌ Отправь фото, или напиши **готово** / **пропустить**", parse_mode="Markdown")

# ----- РЕДАКТИРОВАНИЕ РЕСУРСПАКА -----
@dp.callback_query(lambda c: c.data == "edit_pack_list")
async def edit_pack_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("resourcepacks")
    if not items:
        await callback.message.edit_text("📭 **Нет ресурспаков для редактирования**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"edit_pack_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")])
    await callback.message.edit_text("✏️ **Выбери ресурспак для редактирования:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_pack_"))
async def edit_pack_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("edit_pack_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("resourcepacks", item_id)
    if not item:
        await callback.answer("❌ Ресурспак не найден", show_alert=True)
        return
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_pack_field_name_{item_id}")],
        [InlineKeyboardButton(text="📄 Краткое описание", callback_data=f"edit_pack_field_short_{item_id}")],
        [InlineKeyboardButton(text="📚 Полное описание", callback_data=f"edit_pack_field_full_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_pack_field_version_{item_id}")],
        [InlineKeyboardButton(text="✍️ Автор", callback_data=f"edit_pack_field_author_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_pack_field_url_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_pack_list")]
    ]
    await callback.message.edit_text(f"✏️ **Редактирование:** {item[1]}\n\nЧто изменить?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=fields))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_pack_field_"))
async def edit_pack_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    field_map = {'name': 'name', 'short': 'short_desc', 'full': 'full_desc', 'version': 'version', 'author': 'author', 'url': 'download_url'}
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="resourcepacks")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ **Введи новое значение:**", parse_mode="Markdown")
    await callback.answer()

# ----- УДАЛЕНИЕ РЕСУРСПАКА -----
@dp.callback_query(lambda c: c.data == "delete_pack_list")
async def delete_pack_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("resourcepacks")
    if not items:
        await callback.message.edit_text("📭 **Нет ресурспаков для удаления**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"delete_pack_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")])
    await callback.message.edit_text("🗑 **Выбери ресурспак для удаления:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_pack_") and not c.data.startswith("delete_pack_confirm_"))
async def delete_pack_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_pack_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("resourcepacks", item_id)
    if not item:
        await callback.answer("❌ Ресурспак не найден", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_pack_confirm_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_pack_list")]
    ]
    await callback.message.edit_text(f"⚠️ **Подтверждение удаления**\n\nТы действительно хочешь удалить ресурспак:\n**{item[1]}** (ID: {item_id})?\n\nЭто действие нельзя отменить!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_pack_confirm_"))
async def delete_pack_execute(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_pack_confirm_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    delete_item("resourcepacks", item_id)
    await callback.answer("✅ Ресурспак удалён!", show_alert=True)
    await delete_pack_list(callback)

# ----- СПИСОК РЕСУРСПАКОВ -----
@dp.callback_query(lambda c: c.data == "list_packs")
async def list_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("resourcepacks")
    if not items:
        text = "📭 **Список ресурспаков пуст**"
    else:
        text = "📋 **Список ресурспаков:**\n\n"
        for item_id, name, short_desc, media_json, downloads, version in items[:20]:
            text += f"`{item_id}`. **{name}** ({version})\n   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]]))
    await callback.answer()

# ========== АДМИН: КОНФИГИ ==========
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
    await callback.message.edit_text("⚙️ **Управление конфигами**\n\nВыбери действие:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ----- ДОБАВЛЕНИЕ КОНФИГА -----
@dp.callback_query(lambda c: c.data == "add_config")
async def add_config_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.config_name)
    await callback.message.edit_text("📝 **Введи название конфига:**", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.config_name)
async def config_name(message: Message, state: FSMContext):
    await state.update_data(config_name=message.text)
    await state.set_state(AdminStates.config_short_desc)
    await message.answer("📄 **Введи краткое описание:**", parse_mode="Markdown")

@dp.message(AdminStates.config_short_desc)
async def config_short_desc(message: Message, state: FSMContext):
    await state.update_data(config_short_desc=message.text)
    await state.set_state(AdminStates.config_full_desc)
    await message.answer("📚 **Введи полное описание:**", parse_mode="Markdown")

@dp.message(AdminStates.config_full_desc)
async def config_full_desc(message: Message, state: FSMContext):
    await state.update_data(config_full_desc=message.text)
    await state.set_state(AdminStates.config_version)
    await message.answer("🔢 **Введи версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.config_version)
async def config_version(message: Message, state: FSMContext):
    await state.update_data(config_version=message.text)
    await state.set_state(AdminStates.config_url)
    await message.answer("🔗 **Введи ссылку на скачивание:**", parse_mode="Markdown")

@dp.message(AdminStates.config_url)
async def config_url(message: Message, state: FSMContext):
    await state.update_data(config_url=message.text)
    await state.set_state(AdminStates.config_media)
    await message.answer("🖼️ **Отправляй фото** (можно несколько)\n\nПосле того как отправишь все фото, напиши **готово**\nИли напиши **пропустить** чтобы пропустить фото:", parse_mode="Markdown")

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_config(data['config_name'], data['config_short_desc'], data['config_full_desc'], data['config_url'], data['config_version'], media_list)
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Конфиг добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении конфига**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_config(data['config_name'], data['config_short_desc'], data['config_full_desc'], data['config_url'], data['config_version'], [])
        await state.clear()
        if item_id:
            await message.answer(f"✅ **Конфиг добавлен!**\nID: `{item_id}` (без фото)", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ **Ошибка при добавлении конфига**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(f"✅ **Фото добавлено!** Всего: {len(media_list)}\nМожешь отправить ещё фото или написать **готово**", parse_mode="Markdown")
    else:
        await message.answer("❌ Отправь фото, или напиши **готово** / **пропустить**", parse_mode="Markdown")

# ----- РЕДАКТИРОВАНИЕ КОНФИГА -----
@dp.callback_query(lambda c: c.data == "edit_config_list")
async def edit_config_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("configs")
    if not items:
        await callback.message.edit_text("📭 **Нет конфигов для редактирования**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"edit_config_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    await callback.message.edit_text("✏️ **Выбери конфиг для редактирования:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_config_"))
async def edit_config_select(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("edit_config_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    fields = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_config_field_name_{item_id}")],
        [InlineKeyboardButton(text="📄 Краткое описание", callback_data=f"edit_config_field_short_{item_id}")],
        [InlineKeyboardButton(text="📚 Полное описание", callback_data=f"edit_config_field_full_{item_id}")],
        [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_config_field_version_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_config_field_url_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="edit_config_list")]
    ]
    await callback.message.edit_text(f"✏️ **Редактирование:** {item[1]}\n\nЧто изменить?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=fields))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_config_field_"))
async def edit_config_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    field_map = {'name': 'name', 'short': 'short_desc', 'full': 'full_desc', 'version': 'version', 'url': 'download_url'}
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="configs")
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ **Введи новое значение:**", parse_mode="Markdown")
    await callback.answer()

# ----- УДАЛЕНИЕ КОНФИГА -----
@dp.callback_query(lambda c: c.data == "delete_config_list")
async def delete_config_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("configs")
    if not items:
        await callback.message.edit_text("📭 **Нет конфигов для удаления**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]]))
        await callback.answer()
        return
    buttons = []
    for item_id, name, short_desc, media_json, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(text=f"{item_id}. {name[:30]} ({version}) 📥 {downloads}", callback_data=f"delete_config_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    await callback.message.edit_text("🗑 **Выбери конфиг для удаления:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_config_") and not c.data.startswith("delete_config_confirm_"))
async def delete_config_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_config_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_config_confirm_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_config_list")]
    ]
    await callback.message.edit_text(f"⚠️ **Подтверждение удаления**\n\nТы действительно хочешь удалить конфиг:\n**{item[1]}** (ID: {item_id})?\n\nЭто действие нельзя отменить!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_config_confirm_"))
async def delete_config_execute(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    try:
        item_id = int(callback.data.replace("delete_config_confirm_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    delete_item("configs", item_id)
    await callback.answer("✅ Конфиг удалён!", show_alert=True)
    await delete_config_list(callback)

# ----- СПИСОК КОНФИГОВ -----
@dp.callback_query(lambda c: c.data == "list_configs")
async def list_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    items = get_all_items("configs")
    if not items:
        text = "📭 **Список конфигов пуст**"
    else:
        text = "📋 **Список конфигов:**\n\n"
        for item_id, name, short_desc, media_json, downloads, version in items[:20]:
            text += f"`{item_id}`. **{name}** ({version})\n   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]]))
    await callback.answer()

# ========== ОБЩИЙ ОБРАБОТЧИК РЕДАКТИРОВАНИЯ ==========
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
    await message.answer(
        "✅ **Значение обновлено!**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin=True)
    )

# ========== АДМИН: БЭКАПЫ ==========
@dp.callback_query(lambda c: c.data == "admin_zip_backups")
async def admin_zip_backups(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await callback.message.edit_text("📦 **ZIP Бэкапы**\n\nУправление бэкапами:", parse_mode="Markdown", reply_markup=get_backups_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "create_backup")
async def create_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await callback.message.edit_text("⏳ **Создание бэкапа...**", parse_mode="Markdown")
    zip_path, zip_filename = await create_zip_backup()
    if zip_path:
        await callback.message.answer_document(document=FSInputFile(zip_path), caption=f"✅ Бэкап создан: {zip_filename}")
    else:
        await callback.message.answer("❌ Ошибка создания бэкапа")
    await admin_zip_backups(callback)

@dp.callback_query(lambda c: c.data.startswith("restore_"))
async def restore_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    filename = callback.data.replace("restore_", "")
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        await callback.answer("❌ Файл не найден", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"restore_confirm_{filename}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_zip_backups")]
    ]
    await callback.message.edit_text(f"⚠️ **Восстановить из {filename}?**\n\nВсе текущие данные будут заменены!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("restore_confirm_"))
async def restore_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    filename = callback.data.replace("restore_confirm_", "")
    filepath = BACKUP_DIR / filename
    await callback.message.edit_text("⏳ **Восстановление...**", parse_mode="Markdown")
    success = await restore_from_zip(str(filepath))
    if success:
        await callback.message.edit_text("✅ **База восстановлена!**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))
    else:
        await callback.message.edit_text("❌ **Ошибка восстановления!**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "upload_backup")
async def upload_backup(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_backup)
    await callback.message.edit_text("📤 **Отправь ZIP файл с бэкапом**", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.waiting_for_backup)
async def handle_upload(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    if not message.document or not message.document.file_name.endswith('.zip'):
        await message.answer("❌ Отправь ZIP файл!")
        await state.clear()
        return
    file = await bot.get_file(message.document.file_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = BACKUP_DIR / f"uploaded_{timestamp}_{message.document.file_name}"
    await bot.download_file(file.file_path, str(file_path))
    await message.answer(f"✅ ZIP файл загружен!")
    await state.clear()

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
        f"📊 **Статистика**\n\n"
        f"👤 Пользователей: {users_count}\n"
        f"🎮 Клиентов: {clients_count}\n"
        f"🎨 Ресурспаков: {packs_count}\n"
        f"⚙️ Конфигов: {configs_count}\n"
        f"📦 Бэкапов: {backups_count}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]])
    )
    await callback.answer()

# ========== АДМИН: РАССЫЛКА ==========
@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начало рассылки"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        users_count = get_users_count()
    except:
        users_count = 0
    
    await state.set_state(AdminStates.broadcast_text)
    await callback.message.edit_text(
        f"📢 **Создание рассылки**\n\n"
        f"Всего пользователей: {users_count}\n\n"
        f"Введи текст сообщения для рассылки:",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(message: Message, state: FSMContext):
    """Получение текста рассылки"""
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.broadcast_photo)
    await message.answer(
        "📸 **Отправь фото** для рассылки (или отправь 'пропустить'):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(message: Message, state: FSMContext):
    """Получение фото для рассылки и отправка"""
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'пропустить':
        photo_id = None
    else:
        await message.answer("❌ Отправь фото или напиши 'пропустить'")
        return
    
    # Получаем список пользователей
    users = get_all_users()
    
    if not users:
        await message.answer("❌ Нет пользователей для рассылки")
        await state.clear()
        return
    
    # Показываем предпросмотр
    preview_text = f"📢 **Предпросмотр рассылки**\n\n{text}\n\nВсего получателей: {len(users)}"
    
    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=preview_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_send")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
            ])
        )
    else:
        await message.answer(
            preview_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_send")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
            ])
        )
    
    await state.update_data(broadcast_photo=photo_id)

@dp.callback_query(lambda c: c.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    """Отправка рассылки"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    photo_id = data.get('broadcast_photo')
    
    users = get_all_users()
    sent = 0
    failed = 0
    
    await callback.message.edit_text(
        "📢 **Рассылка началась...**\n\n"
        f"Всего пользователей: {len(users)}",
        parse_mode="Markdown"
    )
    
    for user_id in users:
        try:
            if photo_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_id,
                    caption=text,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown"
                )
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка чтобы не забанили
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
    await state.clear()
    await callback.message.edit_text(
        f"📢 **Рассылка завершена!**\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ **Рассылка отменена**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
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
        media_list = json.loads(item[4]) if item[4] else []
        if not media_list:
            await callback.answer("📭 Нет медиа", show_alert=True)
            return
        await state.update_data(media_list=media_list, media_index=0, media_category=category, media_item_id=item_id)
        await show_media(callback.message, state, 0)
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)

async def show_media(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    if not media_list or index >= len(media_list):
        return
    media = media_list[index]
    buttons = [
        [
            InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{index-1}" if index > 0 else "noop"),
            InlineKeyboardButton(text=f"{index+1}/{len(media_list)}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{index+1}" if index < len(media_list)-1 else "noop")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="media_back")]
    ]
    await state.update_data(media_index=index)
    if media['type'] == 'photo':
        await message.answer_photo(photo=media['id'], caption=f"📸 Медиа {index+1} из {len(media_list)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_nav(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("media_nav_", ""))
    await show_media(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category, item_id = data.get('media_category'), data.get('media_item_id')
    await state.clear()
    if category and item_id:
        callback.data = f"detail_{category}_{item_id}"
        await detail_view(callback, state)
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
    await callback.message.answer("**Главное меню:**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin))
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
    print("   • 👤 Профиль с реферальной системой")
    print("   • 💎 VIP статус за приглашение друга")
    print("   • 📊 Лимит скачиваний (1 файл в неделю)")
    print("   • 🔧 Исправлены все кнопки в админке")
    print("   • ✅ Работает инфо, статистика, рассылка")
    print("="*50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())