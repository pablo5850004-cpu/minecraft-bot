import logging
import os
import asyncio
import json
import sqlite3
import random
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
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

# ========== НАСТРОЙКА ПУТЕЙ (СОГЛАСНО ИНСТРУКЦИИ BOTHOST) ==========
# Используем папку /app/data для постоянного хранения
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Пути к базам данных в постоянной папке
DB_PATH = DATA_DIR / "clients.db"
USERS_DB_PATH = DATA_DIR / "users.db"

# Папка для бэкапов тоже в постоянном хранилище
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

print(f"📁 Папка для данных: {DATA_DIR}")
print(f"📁 Папка для бэкапов: {BACKUP_DIR}")
print(f"📄 База данных клиентов: {DB_PATH}")
print(f"📄 База данных пользователей: {USERS_DB_PATH}")

# ========== ИНИЦИАЛИЗАЦИЯ БАЗ ДАННЫХ ==========
def init_db():
    """Создание базы данных клиентов, если её нет"""
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
    print(f"✅ База данных клиентов инициализирована: {DB_PATH}")

def init_users_db():
    """Создание базы данных пользователей, если её нет"""
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ База данных пользователей инициализирована: {USERS_DB_PATH}")

# Инициализация баз при запуске
init_db()
init_users_db()

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========
def save_user(message: Message):
    """Сохранить или обновить информацию о пользователе"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        cur.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_active)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя: {e}")

def get_all_users():
    """Получить список всех пользователей"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT user_id FROM users ORDER BY last_active DESC')
        users = cur.fetchall()
        conn.close()
        return [user[0] for user in users]
    except Exception as e:
        logger.error(f"Ошибка получения пользователей: {e}")
        return []

def get_users_count():
    """Получить количество пользователей"""
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users')
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Ошибка подсчёта пользователей: {e}")
        return 0

# ========== ФУНКЦИИ ДЛЯ БЭКАПОВ ==========
def get_all_backups():
    """Получает ВСЕ ZIP файлы из папки бэкапов"""
    try:
        files = os.listdir(str(BACKUP_DIR))
        backups = [f for f in files if f.endswith('.zip')]
        backups.sort(reverse=True)
        return backups
    except Exception as e:
        print(f"Ошибка получения списка: {e}")
        return []

async def create_zip_backup():
    """Создаёт ZIP бэкап и сохраняет в папку бэкапов"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"backup_{timestamp}.zip"
        zip_path = BACKUP_DIR / zip_filename
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if DB_PATH.exists():
                zipf.write(DB_PATH, 'clients.db')
            if USERS_DB_PATH.exists():
                zipf.write(USERS_DB_PATH, 'users.db')
            
            # Добавляем информационный файл
            info_content = f"""# Бэкап базы данных Minecraft бота
Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Файлы:
- clients.db - основная база данных
- users.db - база пользователей
"""
            info_path = BACKUP_DIR / "README.txt"
            with open(info_path, 'w', encoding='utf-8') as f:
                f.write(info_content)
            zipf.write(info_path, "README.txt")
            info_path.unlink()  # удаляем временный файл
        
        if zip_path.exists():
            return str(zip_path), zip_filename
        return None, None
    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}")
        return None, None

async def restore_from_zip(zip_path: str):
    """Восстанавливает базу из ZIP архива"""
    try:
        print(f"🔍 Начинаем восстановление из файла: {zip_path}")
        
        # Проверяем, существует ли файл
        if not os.path.exists(zip_path):
            print(f"❌ Файл не существует: {zip_path}")
            return False
        
        # Создаём временную папку для распаковки
        extract_dir = BACKUP_DIR / f"restore_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Временная папка: {extract_dir}")
        
        # Распаковываем ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # Смотрим, что внутри
                file_list = zipf.namelist()
                print(f"📦 Файлы в ZIP: {file_list}")
                zipf.extractall(extract_dir)
        except Exception as e:
            print(f"❌ Ошибка распаковки ZIP: {e}")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return False
        
        # Ищем .db файлы
        db_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.db'):
                    full_path = os.path.join(root, file)
                    db_files.append((file, full_path))
                    print(f"✅ Найден .db файл: {file} ({os.path.getsize(full_path)} bytes)")
        
        if not db_files:
            print("❌ В ZIP нет .db файлов")
            shutil.rmtree(extract_dir, ignore_errors=True)
            return False
        
        # Восстанавливаем файлы
        restored_count = 0
        for filename, filepath in db_files:
            try:
                if 'clients' in filename or filename == 'clients.db':
                    # Сначала создаём бэкап старого файла
                    if DB_PATH.exists():
                        backup_path = BACKUP_DIR / f"clients_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        shutil.copy2(DB_PATH, backup_path)
                        print(f"📦 Создан бэкап старого clients.db: {backup_path}")
                    
                    shutil.copy2(filepath, DB_PATH)
                    print(f"✅ Восстановлен clients.db из {filename}")
                    restored_count += 1
                    
                elif 'users' in filename or filename == 'users.db':
                    if USERS_DB_PATH.exists():
                        backup_path = BACKUP_DIR / f"users_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        shutil.copy2(USERS_DB_PATH, backup_path)
                        print(f"📦 Создан бэкап старого users.db: {backup_path}")
                    
                    shutil.copy2(filepath, USERS_DB_PATH)
                    print(f"✅ Восстановлен users.db из {filename}")
                    restored_count += 1
            except Exception as e:
                print(f"❌ Ошибка при копировании {filename}: {e}")
        
        # Удаляем временную папку
        shutil.rmtree(extract_dir, ignore_errors=True)
        print(f"✅ Восстановление завершено. Восстановлено файлов: {restored_count}")
        
        return restored_count > 0
        
    except Exception as e:
        print(f"❌ Критическая ошибка восстановления: {e}")
        import traceback
        traceback.print_exc()
        return False

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ==========
def safe_db(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка БД: {e}")
            return None
    return wrapper

@safe_db
def get_item(table: str, item_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
    item = cur.fetchone()
    conn.close()
    return item

@safe_db
def get_all_items(table: str):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, short_desc, media, downloads, version FROM {table} ORDER BY created_at DESC')
    items = cur.fetchall()
    conn.close()
    return items

@safe_db
def delete_item(table: str, item_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ ДЛЯ КЛИЕНТОВ ==========
def add_client(name: str, short_desc: str, full_desc: str, url: str, version: str, media: List[Dict] = None):
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
        logger.error(f"Ошибка при добавлении клиента: {e}")
        return None

@safe_db
def update_client(item_id: int, field: str, value: str):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_clients_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить клиентов по версии"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, views, version 
        FROM clients 
        WHERE version = ?
        ORDER BY downloads DESC
        LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    
    items = cur.fetchall()
    
    cur.execute('SELECT COUNT(*) FROM clients WHERE version = ?', (version,))
    total = cur.fetchone()[0]
    conn.close()
    return items, total

@safe_db
def get_all_client_versions():
    """Получить все доступные версии клиентов"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ РЕСУРСПАКОВ ==========
def add_pack(name: str, short_desc: str, full_desc: str, url: str, version: str, author: str, media: List[Dict] = None):
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
        logger.error(f"Ошибка при добавлении ресурспака: {e}")
        return None

@safe_db
def update_pack(item_id: int, field: str, value: str):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_packs_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить ресурспаки по версии"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, likes, views, version, author 
        FROM resourcepacks 
        WHERE version = ?
        ORDER BY downloads DESC
        LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    
    packs = cur.fetchall()
    
    cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (version,))
    total = cur.fetchone()[0]
    
    conn.close()
    return packs, total

@safe_db
def get_all_pack_versions():
    """Получить все доступные версии ресурспаков"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM resourcepacks WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ КОНФИГОВ ==========
def add_config(name: str, short_desc: str, full_desc: str, url: str, version: str, media: List[Dict] = None):
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
        logger.error(f"Ошибка при добавлении конфига: {e}")
        return None

@safe_db
def update_config(item_id: int, field: str, value: str):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_configs_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить конфиги по версии"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    offset = (page - 1) * per_page
    cur.execute('''
        SELECT id, name, short_desc, media, downloads, views, version 
        FROM configs 
        WHERE version = ?
        ORDER BY downloads DESC
        LIMIT ? OFFSET ?
    ''', (version, per_page, offset))
    
    items = cur.fetchall()
    
    cur.execute('SELECT COUNT(*) FROM configs WHERE version = ?', (version,))
    total = cur.fetchone()[0]
    conn.close()
    return items, total

@safe_db
def get_all_config_versions():
    """Получить все доступные версии конфигов"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM configs WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ОБЩИЕ ФУНКЦИИ ==========
@safe_db
def increment_view(table: str, item_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

@safe_db
def increment_download(table: str, item_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

@safe_db
def toggle_favorite(user_id: int, pack_id: int) -> bool:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM favorites WHERE user_id = ? AND pack_id = ?', (user_id, pack_id))
    exists = cur.fetchone()
    
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

@safe_db
def get_favorites(user_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('''
        SELECT r.id, r.name, r.short_desc, r.media, r.downloads, r.likes 
        FROM resourcepacks r
        JOIN favorites f ON r.id = f.pack_id
        WHERE f.user_id = ?
        ORDER BY f.added_at DESC
    ''', (user_id,))
    favs = cur.fetchall()
    conn.close()
    return favs

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_number(num: int) -> str:
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    else:
        return f"{num/1000000:.1f}M"

def get_version_display(version: str) -> str:
    """Получить отображение версии для списка"""
    return f"({version})"

# ========== СОСТОЯНИЯ ==========
class AdminStates(StatesGroup):
    # Для клиентов
    client_name = State()
    client_short_desc = State()
    client_full_desc = State()
    client_version = State()
    client_url = State()
    client_media = State()
    
    # Для ресурспаков
    pack_name = State()
    pack_short_desc = State()
    pack_full_desc = State()
    pack_version = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    
    # Для конфигов
    config_name = State()
    config_short_desc = State()
    config_full_desc = State()
    config_version = State()
    config_url = State()
    config_media = State()
    
    # Для редактирования
    edit_field = State()
    edit_value = State()
    edit_category = State()
    edit_item_id = State()
    
    # Для рассылки
    broadcast_text = State()
    broadcast_photo = State()
    
    # Для бэкапов
    waiting_for_backup = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin: bool = False):
    buttons = [
        [
            types.KeyboardButton(text="🎮 Клиенты"),
            types.KeyboardButton(text="🎨 Ресурспаки")
        ],
        [
            types.KeyboardButton(text="❤️ Избранное"),
            types.KeyboardButton(text="⚙️ Конфиги"),
            types.KeyboardButton(text="ℹ️ Инфо")
        ],
        [
            types.KeyboardButton(text="❓ Помощь")
        ]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_version_keyboard(versions: List[str], category: str):
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"ver_{category}_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_items_keyboard(items: List[Tuple], category: str, page: int, total_pages: int):
    buttons = []
    for item in items:
        item_id = item[0]
        name = item[1]
        short_desc = item[2]
        media_json = item[3] if len(item) > 3 else '[]'
        downloads = item[4] if len(item) > 4 else 0
        
        version = item[6] if len(item) > 6 else "?"
        version_text = get_version_display(version)
        
        try:
            media_list = json.loads(media_json) if media_json else []
        except:
            media_list = []
        
        preview = "🖼️" if media_list else "📄"
        
        button_text = f"{preview} {name[:30]} {version_text}\n{short_desc[:50]}... 📥 {format_number(downloads)}"
        
        buttons.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"detail_{category}_{item_id}"
        )])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{category}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{category}_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_detail_keyboard(category: str, item_id: int, is_favorite: bool = False):
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

def get_admin_category_keyboard(category: str):
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить", callback_data=f"add_{category}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{category}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{category}")],
        [InlineKeyboardButton(text="📋 Список", callback_data=f"list_{category}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_items_keyboard(items: List[Tuple], category: str, action: str):
    """Клавиатура со списком элементов для админа"""
    buttons = []
    for item_id, name, short_desc, downloads, version in items[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"{item_id}. {name[:30]} ({version})\n{short_desc[:30]}... 📥 {downloads}", 
            callback_data=f"{action}_{category}_{item_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_fields_keyboard(category: str, item_id: int):
    """Клавиатура выбора поля для редактирования"""
    if category == "packs":
        fields = [
            ["📝 Название", f"edit_name_{category}_{item_id}"],
            ["📄 Краткое описание", f"edit_short_{category}_{item_id}"],
            ["📚 Полное описание", f"edit_full_{category}_{item_id}"],
            ["🔢 Версия", f"edit_version_{category}_{item_id}"],
            ["✍️ Автор", f"edit_author_{category}_{item_id}"],
            ["🔗 Ссылка", f"edit_url_{category}_{item_id}"],
        ]
    else:
        fields = [
            ["📝 Название", f"edit_name_{category}_{item_id}"],
            ["📄 Краткое описание", f"edit_short_{category}_{item_id}"],
            ["📚 Полное описание", f"edit_full_{category}_{item_id}"],
            ["🔢 Версия", f"edit_version_{category}_{item_id}"],
            ["🔗 Ссылка", f"edit_url_{category}_{item_id}"],
        ]
    
    buttons = [[InlineKeyboardButton(text=text, callback_data=cb)] for text, cb in fields]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
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
    
    await message.answer(
        "🎮 Выбери версию Minecraft:",
        reply_markup=get_version_keyboard(versions, "clients")
    )

@dp.callback_query(lambda c: c.data.startswith("ver_clients_"))
async def clients_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_clients_", "")
    items, total = get_clients_by_version(version, 1)
    
    if not items:
        await callback.message.edit_text(
            f"❌ Для версии {version} пока нет клиентов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    total_pages = (total + 9) // 10
    await state.update_data(client_version=version, client_page=1)
    await callback.message.edit_text(
        f"🎮 Клиенты для версии {version} (стр 1/{total_pages}):",
        reply_markup=get_items_keyboard(items, "clients", 1, total_pages)
    )
    await callback.answer()

# ========== РЕСУРСПАКИ ==========
@dp.message(F.text == "🎨 Ресурспаки")
async def packs_menu(message: Message, state: FSMContext):
    versions = get_all_pack_versions()
    if not versions:
        await message.answer("📭 Пока нет ресурспаков")
        return
    
    await message.answer(
        "🎨 Выбери версию Minecraft:",
        reply_markup=get_version_keyboard(versions, "packs")
    )

@dp.callback_query(lambda c: c.data.startswith("ver_packs_"))
async def packs_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_packs_", "")
    items, total = get_packs_by_version(version, 1)
    
    if not items:
        await callback.message.edit_text(
            f"❌ Для версии {version} пока нет ресурспаков",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    total_pages = (total + 9) // 10
    await state.update_data(pack_version=version, pack_page=1)
    await callback.message.edit_text(
        f"🎨 Ресурспаки для версии {version} (стр 1/{total_pages}):",
        reply_markup=get_items_keyboard(items, "packs", 1, total_pages)
    )
    await callback.answer()

# ========== КОНФИГИ ==========
@dp.message(F.text == "⚙️ Конфиги")
async def configs_menu(message: Message, state: FSMContext):
    versions = get_all_config_versions()
    if not versions:
        await message.answer("📭 Пока нет конфигов")
        return
    
    await message.answer(
        "⚙️ Выбери версию Minecraft:",
        reply_markup=get_version_keyboard(versions, "configs")
    )

@dp.callback_query(lambda c: c.data.startswith("ver_configs_"))
async def configs_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("ver_configs_", "")
    items, total = get_configs_by_version(version, 1)
    
    if not items:
        await callback.message.edit_text(
            f"❌ Для версии {version} пока нет конфигов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    total_pages = (total + 9) // 10
    await state.update_data(config_version=version, config_page=1)
    await callback.message.edit_text(
        f"⚙️ Конфиги для версии {version} (стр 1/{total_pages}):",
        reply_markup=get_items_keyboard(items, "configs", 1, total_pages)
    )
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
    
    if category == "clients":
        media_list = json.loads(item[4]) if item[4] else []
        text = (f"**{item[1]}**\n\n"
                f"{item[3]}\n\n"
                f"Версия: {item[6]}\n"
                f"📥 Скачиваний: {format_number(item[7])}\n"
                f"👁 Просмотров: {format_number(item[8])}")
        
        if media_list and media_list[0]['type'] == 'photo':
            await callback.message.answer_photo(
                photo=media_list[0]['id'],
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id)
            )
            await callback.message.delete()
        else:
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id)
            )
            
    elif category == "packs":
        media_list = json.loads(item[4]) if item[4] else []
        
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT * FROM favorites WHERE user_id = ? AND pack_id = ?', 
                   (callback.from_user.id, item_id))
        is_fav = cur.fetchone() is not None
        conn.close()
        
        text = (f"**{item[1]}**\n\n"
                f"{item[3]}\n\n"
                f"Автор: {item[7]}\n"
                f"Версия: {item[6]}\n"
                f"📥 Скачиваний: {format_number(item[8])}\n"
                f"❤️ В избранном: {format_number(item[9])}\n"
                f"👁 Просмотров: {format_number(item[10])}")
        
        if media_list and media_list[0]['type'] == 'photo':
            await callback.message.answer_photo(
                photo=media_list[0]['id'],
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id, is_fav)
            )
            await callback.message.delete()
        else:
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id, is_fav)
            )
            
    else:
        media_list = json.loads(item[4]) if item[4] else []
        text = (f"**{item[1]}**\n\n"
                f"{item[3]}\n\n"
                f"Версия: {item[6]}\n"
                f"📥 Скачиваний: {format_number(item[7])}\n"
                f"👁 Просмотров: {format_number(item[8])}")
        
        if media_list and media_list[0]['type'] == 'photo':
            await callback.message.answer_photo(
                photo=media_list[0]['id'],
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id)
            )
            await callback.message.delete()
        else:
            await callback.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=get_detail_keyboard(category, item_id)
            )
    
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
    await callback.message.edit_text(
        f"{title} (стр {page}/{total_pages}):",
        reply_markup=get_items_keyboard(items, category, page, total_pages)
    )
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
    await callback.message.edit_text(
        f"{title} (стр {page}/{total_pages}):",
        reply_markup=get_items_keyboard(items, category, page, total_pages)
    )
    await callback.answer()

# ========== СКАЧИВАНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("download_"))
async def download_item(callback: CallbackQuery):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    item = get_item(category, item_id)
    
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    increment_download(category, item_id)
    
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
        await message.answer(
            "❤️ **Избранное пусто**\n\n"
            "Добавляй ресурспаки в избранное кнопкой 🤍",
            parse_mode="Markdown"
        )
        return
    
    text = "❤️ **Твоё избранное:**\n\n"
    for fav in favs[:10]:
        media_list = json.loads(fav[3]) if fav[3] else []
        preview = "🖼️" if media_list else "📄"
        text += f"{preview} {fav[1]} - {format_number(fav[4])} 📥\n"
    
    if len(favs) > 10:
        text += f"\n...и еще {len(favs) - 10}"
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data.startswith("fav_"))
async def favorite_handler(callback: CallbackQuery):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    
    if category != "packs":
        await callback.answer("❌ Только для ресурспаков", show_alert=True)
        return
    
    added = toggle_favorite(callback.from_user.id, item_id)
    
    if added:
        await callback.answer("❤️ Добавлено в избранное!")
    else:
        await callback.answer("💔 Удалено из избранного")
    
    callback.data = f"detail_{category}_{item_id}"
    await detail_view(callback, None)

# ========== ИНФО ==========
@dp.message(F.text == "ℹ️ Инфо")
async def info(message: Message):
    users_count = get_users_count()
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        cur.execute('SELECT COUNT(*) FROM clients')
        clients_count = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM resourcepacks')
        packs_count = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM configs')
        configs_count = cur.fetchone()[0]
        
        cur.execute('SELECT SUM(downloads) FROM clients')
        clients_d = cur.fetchone()[0] or 0
        
        cur.execute('SELECT SUM(downloads) FROM resourcepacks')
        packs_d = cur.fetchone()[0] or 0
        
        cur.execute('SELECT SUM(downloads) FROM configs')
        configs_d = cur.fetchone()[0] or 0
        
        conn.close()
        
        total_downloads = clients_d + packs_d + configs_d
        backup_count = len(get_all_backups())
        
        await message.answer(
            f"**Информация о боте**\n\n"
            f"Создатель: {CREATOR_USERNAME}\n"
            f"Версия: 11.0 (постоянное хранилище)\n\n"
            f"📊 **Статистика:**\n"
            f"• Пользователей: {users_count}\n"
            f"• Клиентов: {clients_count}\n"
            f"• Ресурспаков: {packs_count}\n"
            f"• Конфигов: {configs_count}\n"
            f"• Всего скачиваний: {format_number(total_downloads)}\n"
            f"• ZIP бэкапов: {backup_count}\n\n"
            f"📁 Данные хранятся в `/app/data`\n"
            f"✅ Не пропадают при обновлении",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка в info: {e}")
        await message.answer(
            f"**Информация о боте**\n\n"
            f"Создатель: {CREATOR_USERNAME}\n"
            f"Версия: 11.0",
            parse_mode="Markdown"
        )

# ========== ПОМОЩЬ ==========
@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    await message.answer(
        "❓ **Помощь и поддержка**\n\n"
        "Если у тебя возникли вопросы или проблемы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем\n"
        "• Опиши свою проблему подробно",
        parse_mode="Markdown",
        reply_markup=get_help_keyboard()
    )

@dp.callback_query(lambda c: c.data == "help_rules")
async def help_rules(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 **Правила использования**\n\n"
        "1. Все файлы предоставляются 'как есть'\n"
        "2. Автор не несёт ответственности за использование файлов\n"
        "3. Запрещено выкладывать файлы на других ресурсах без указания автора\n"
        "4. Уважайте других пользователей",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help_faq")
async def help_faq(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ **Часто задаваемые вопросы**\n\n"
        "**Q:** Как скачать файл?\n"
        "**A:** Нажми на элемент, затем кнопку 'Скачать'\n\n"
        "**Q:** Почему не работает ссылка?\n"
        "**A:** Возможно, файл был удалён. Сообщи админу\n\n"
        "**Q:** Как добавить в избранное?\n"
        "**A:** В разделе ресурспаков нажми 🤍\n\n"
        "**Q:** Как сделать бэкап?\n"
        "**A:** В админ-панели выбери '📦 ZIP Бэкапы' и нажми 'Создать'\n\n"
        "**Q:** Бот не отвечает, что делать?\n"
        "**A:** Напиши админу через кнопку 'Связаться'",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ **Помощь и поддержка**\n\n"
        "Если у тебя возникли вопросы или проблемы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем\n"
        "• Опиши свою проблему подробно",
        parse_mode="Markdown",
        reply_markup=get_help_keyboard()
    )
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    
    await message.answer(
        "⚙️ **Админ панель**\n\nВыбери категорию:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ **Админ панель**\n\nВыбери категорию:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_clients")
async def admin_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎮 **Управление клиентами**\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard("clients")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_packs")
async def admin_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎨 **Управление ресурспаками**\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard("packs")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_configs")
async def admin_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ **Управление конфигами**\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard("configs")
    )
    await callback.answer()

# ========== АДМИН: ZIP БЭКАПЫ ==========
@dp.callback_query(lambda c: c.data == "admin_zip_backups")
async def admin_zip_backups(callback: CallbackQuery):
    """Меню ZIP бэкапов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    backups = get_all_backups()
    
    text = "📦 **ZIP Бэкапы**\n\n"
    text += f"📁 **Папка:** `{BACKUP_DIR}`\n"
    text += f"📊 **Всего бэкапов:** {len(backups)}\n\n"
    
    if backups:
        text += "**Доступные бэкапы:**\n"
        for i, backup in enumerate(backups[:10], 1):
            size = (BACKUP_DIR / backup).stat().st_size // 1024
            if backup.startswith('backup_'):
                emoji = "📦"
            elif backup.startswith('uploaded_'):
                emoji = "📤"
            else:
                emoji = "📁"
            text += f"{i}. {emoji} `{backup}` ({size} KB)\n"
    else:
        text += "❌ **Бэкапов пока нет!**\n"
        text += "Создай новый или загрузи существующий."
    
    # Создаём кнопки для каждого бэкапа
    buttons = []
    for backup in backups[:5]:
        if backup.startswith('backup_'):
            btn_text = f"📦 {backup[7:20]}..."
        elif backup.startswith('uploaded_'):
            btn_text = f"📤 {backup[9:20]}..."
        else:
            btn_text = f"📁 {backup[:15]}..."
            
        buttons.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"zip_restore_{backup}"
        )])
    
    # Кнопки действий
    buttons.append([
        InlineKeyboardButton(text="📥 Создать новый", callback_data="zip_backup_create"),
        InlineKeyboardButton(text="📤 Загрузить ZIP", callback_data="zip_backup_upload")
    ])
    buttons.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_zip_backups")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "zip_backup_create")
async def zip_backup_create(callback: CallbackQuery):
    """Создание ZIP бэкапа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ **Создание ZIP бэкапа...**", parse_mode="Markdown")
    
    zip_path, zip_filename = await create_zip_backup()
    
    if zip_path and Path(zip_path).exists():
        size = Path(zip_path).stat().st_size // 1024
        
        await callback.message.answer_document(
            document=FSInputFile(zip_path),
            caption=f"✅ **ZIP бэкап создан!**\n\n"
                    f"📁 Файл: `{zip_filename}`\n"
                    f"📊 Размер: {size} KB\n"
                    f"📍 Сохранён в папку бэкапов"
        )
    else:
        await callback.message.answer("❌ **Ошибка создания бэкапа!**")
    
    await admin_zip_backups(callback)

@dp.callback_query(lambda c: c.data.startswith("zip_restore_"))
async def zip_restore(callback: CallbackQuery):
    """Восстановление из ZIP бэкапа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    filename = callback.data.replace("zip_restore_", "")
    filepath = BACKUP_DIR / filename
    
    # Проверяем существование файла
    if not filepath.exists():
        await callback.answer("❌ Файл не найден", show_alert=True)
        return
    
    # Получаем размер файла для информации
    file_size = filepath.stat().st_size // 1024
    
    # Кнопка подтверждения
    buttons = [
        [InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"zip_restore_confirm_{filename}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_zip_backups")]
    ]
    
    await callback.message.edit_text(
        f"⚠️ **ВНИМАНИЕ!**\n\n"
        f"Ты собираешься восстановить базу из файла:\n`{filename}`\n"
        f"📊 Размер: {file_size} KB\n"
        f"📍 Путь: `{filepath}`\n\n"
        f"Все текущие данные будут **заменены**!\n\n"
        f"Ты уверен?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("zip_restore_confirm_"))
async def zip_restore_confirm(callback: CallbackQuery):
    """Подтверждение восстановления из ZIP"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    filename = callback.data.replace("zip_restore_confirm_", "")
    filepath = BACKUP_DIR / filename
    
    if not filepath.exists():
        await callback.message.edit_text(
            "❌ **Файл не найден!**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "⏳ **Восстановление из ZIP...**\n\n"
        f"Файл: `{filename}`\n"
        "Это может занять несколько секунд...",
        parse_mode="Markdown"
    )
    
    # Сначала создаём бэкап текущего состояния
    await create_zip_backup()
    
    # Восстанавливаем
    success = await restore_from_zip(str(filepath))
    
    if success:
        await callback.message.edit_text(
            "✅ **База успешно восстановлена из ZIP!**\n\n"
            "Все данные восстановлены.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка восстановления!**\n\n"
            "Проверь логи для подробностей.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]
            ])
        )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "zip_backup_upload")
async def zip_backup_upload(callback: CallbackQuery, state: FSMContext):
    """Загрузка ZIP бэкапа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_backup)
    await callback.message.edit_text(
        "📤 **Отправь ZIP файл с бэкапом**\n\n"
        "Файл может называться как угодно, главное чтобы был .zip\n\n"
        "После отправки файл появится в списке бэкапов.",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_backup)
async def handle_zip_upload(message: Message, state: FSMContext):
    """Обработка загруженного ZIP бэкапа"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        await state.clear()
        return
    
    if not message.document:
        await message.answer("❌ Отправь файл!")
        return
    
    if not message.document.file_name.endswith('.zip'):
        await message.answer("❌ Файл должен быть в формате .zip")
        return
    
    file = await bot.get_file(message.document.file_id)
    original_name = message.document.file_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Сохраняем с понятным именем
    if original_name.startswith(('backup_', 'uploaded_')):
        new_filename = original_name
    else:
        new_filename = f"uploaded_{timestamp}_{original_name}"
    
    file_path = BACKUP_DIR / new_filename
    await bot.download_file(file.file_path, str(file_path))
    
    if file_path.exists():
        file_size = file_path.stat().st_size // 1024
        await message.answer(
            f"✅ **ZIP файл успешно загружен!**\n\n"
            f"📁 Имя: `{new_filename}`\n"
            f"📊 Размер: {file_size} KB\n"
            f"📍 Папка: `{BACKUP_DIR}`\n\n"
            f"Теперь файл появится в меню бэкапов.\n"
            f"Нажми **'📦 ZIP Бэкапы'** чтобы увидеть его.",
            parse_mode="Markdown"
        )
        
        # Показываем список всех бэкапов
        all_backups = get_all_backups()
        if all_backups:
            list_text = "**Все доступные бэкапы:**\n"
            for i, b in enumerate(all_backups[:5], 1):
                size = (BACKUP_DIR / b).stat().st_size // 1024
                list_text += f"{i}. `{b[:30]}...` ({size} KB)\n"
            await message.answer(list_text, parse_mode="Markdown")
    else:
        await message.answer("❌ **Ошибка при сохранении файла!**", parse_mode="Markdown")
    
    await state.clear()

# ========== АДМИН: ДОБАВЛЕНИЕ КЛИЕНТА ==========
@dp.callback_query(lambda c: c.data == "add_clients")
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
    await message.answer("📄 **Введи краткое описание:**", parse_mode="Markdown")

@dp.message(AdminStates.client_short_desc)
async def client_short_desc(message: Message, state: FSMContext):
    await state.update_data(client_short_desc=message.text)
    await state.set_state(AdminStates.client_full_desc)
    await message.answer("📚 **Введи полное описание:**", parse_mode="Markdown")

@dp.message(AdminStates.client_full_desc)
async def client_full_desc(message: Message, state: FSMContext):
    await state.update_data(client_full_desc=message.text)
    await state.set_state(AdminStates.client_version)
    await message.answer("🔢 **Введи версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.client_version)
async def client_version(message: Message, state: FSMContext):
    await state.update_data(client_version=message.text)
    await state.set_state(AdminStates.client_url)
    await message.answer("🔗 **Введи ссылку на скачивание:**", parse_mode="Markdown")

@dp.message(AdminStates.client_url)
async def client_url(message: Message, state: FSMContext):
    await state.update_data(client_url=message.text)
    await state.set_state(AdminStates.client_media)
    await message.answer(
        "🖼️ **Отправляй фото** (можно несколько)\n\n"
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_client(
            data['client_name'],
            data['client_short_desc'],
            data['client_full_desc'],
            data['client_url'],
            data['client_version'],
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Клиент добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_client(
            data['client_name'],
            data['client_short_desc'],
            data['client_full_desc'],
            data['client_url'],
            data['client_version'],
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Клиент добавлен!**\nID: `{item_id}` (без фото)",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ **Фото добавлено!** Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ **Отправь фото**, или напиши **готово** / **пропустить**",
            parse_mode="Markdown"
        )

# ========== АДМИН: ДОБАВЛЕНИЕ РЕСУРСПАКА ==========
@dp.callback_query(lambda c: c.data == "add_packs")
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
    await message.answer(
        "🖼️ **Отправляй фото** (можно несколько)\n\n"
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.pack_media)
async def pack_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_pack(
            data['pack_name'],
            data['pack_short_desc'],
            data['pack_full_desc'],
            data['pack_url'],
            data['pack_version'],
            data['pack_author'],
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Ресурспак добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_pack(
            data['pack_name'],
            data['pack_short_desc'],
            data['pack_full_desc'],
            data['pack_url'],
            data['pack_version'],
            data['pack_author'],
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Ресурспак добавлен!**\nID: `{item_id}` (без фото)",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ **Фото добавлено!** Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ **Отправь фото**, или напиши **готово** / **пропустить**",
            parse_mode="Markdown"
        )

# ========== АДМИН: ДОБАВЛЕНИЕ КОНФИГА ==========
@dp.callback_query(lambda c: c.data == "add_configs")
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
    await message.answer(
        "🖼️ **Отправляй фото** (можно несколько)\n\n"
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_config(
            data['config_name'],
            data['config_short_desc'],
            data['config_full_desc'],
            data['config_url'],
            data['config_version'],
            media_list
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Конфиг добавлен!**\nID: `{item_id}`\nДобавлено фото: {len(media_list)}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_config(
            data['config_name'],
            data['config_short_desc'],
            data['config_full_desc'],
            data['config_url'],
            data['config_version'],
            []
        )
        await state.clear()
        if item_id:
            await message.answer(
                f"✅ **Конфиг добавлен!**\nID: `{item_id}` (без фото)",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ **Ошибка при добавлении**",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ **Фото добавлено!** Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ **Отправь фото**, или напиши **готово** / **пропустить**",
            parse_mode="Markdown"
        )

# ========== АДМИН: РЕДАКТИРОВАНИЕ ==========
@dp.callback_query(lambda c: c.data == "edit_clients")
async def edit_clients_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("clients")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет клиентов для редактирования**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ **Выбери клиента для редактирования:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "clients", "edit_client")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "edit_packs")
async def edit_packs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("resourcepacks")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет ресурспаков для редактирования**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ **Выбери ресурспак для редактирования:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "packs", "edit_pack")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "edit_configs")
async def edit_configs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("configs")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет конфигов для редактирования**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ **Выбери конфиг для редактирования:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "configs", "edit_config")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_client_"))
async def edit_client_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_client_", ""))
    await state.update_data(edit_category="clients", edit_item_id=item_id)
    await callback.message.edit_text(
        "✏️ **Что изменить?**",
        parse_mode="Markdown",
        reply_markup=get_edit_fields_keyboard("clients", item_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_pack_"))
async def edit_pack_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_pack_", ""))
    await state.update_data(edit_category="packs", edit_item_id=item_id)
    await callback.message.edit_text(
        "✏️ **Что изменить?**",
        parse_mode="Markdown",
        reply_markup=get_edit_fields_keyboard("packs", item_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_config_"))
async def edit_config_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("edit_config_", ""))
    await state.update_data(edit_category="configs", edit_item_id=item_id)
    await callback.message.edit_text(
        "✏️ **Что изменить?**",
        parse_mode="Markdown",
        reply_markup=get_edit_fields_keyboard("configs", item_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_name_") or c.data.startswith("edit_short_") or
                            c.data.startswith("edit_full_") or c.data.startswith("edit_version_") or
                            c.data.startswith("edit_author_") or c.data.startswith("edit_url_"))
async def edit_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    action, category, item_id = callback.data.split("_", 2)
    
    field_map = {
        'edit_name': 'name',
        'edit_short': 'short_desc',
        'edit_full': 'full_desc',
        'edit_version': 'version',
        'edit_author': 'author',
        'edit_url': 'download_url'
    }
    
    field = field_map.get(action)
    if not field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ **Введи новое значение:**", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.edit_value)
async def edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data['edit_category']
    item_id = data['edit_item_id']
    field = data['edit_field']
    
    if category == 'clients':
        update_client(item_id, field, message.text)
    elif category == 'packs':
        update_pack(item_id, field, message.text)
    else:
        update_config(item_id, field, message.text)
    
    await state.clear()
    await message.answer(
        "✅ **Обновлено!**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin=True)
    )

# ========== АДМИН: УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data == "delete_clients")
async def delete_clients_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("clients")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет клиентов для удаления**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 **Выбери клиента для удаления:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "clients", "delete_client")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "delete_packs")
async def delete_packs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("resourcepacks")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет ресурспаков для удаления**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 **Выбери ресурспак для удаления:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "packs", "delete_pack")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "delete_configs")
async def delete_configs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("configs")
    if not items:
        await callback.message.edit_text(
            "📭 **Нет конфигов для удаления**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 **Выбери конфиг для удаления:**",
        parse_mode="Markdown",
        reply_markup=get_admin_items_keyboard(items, "configs", "delete_config")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_client_"))
async def delete_client_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_client_", ""))
    
    item = get_item("clients", item_id)
    if item:
        name = item[1]
        delete_item("clients", item_id)
        await callback.answer(f"✅ Клиент '{name}' удалён!", show_alert=True)
    else:
        await callback.answer("❌ Клиент не найден", show_alert=True)
    
    await delete_clients_list(callback)

@dp.callback_query(lambda c: c.data.startswith("delete_pack_"))
async def delete_pack_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_pack_", ""))
    
    item = get_item("resourcepacks", item_id)
    if item:
        name = item[1]
        delete_item("resourcepacks", item_id)
        await callback.answer(f"✅ Ресурспак '{name}' удалён!", show_alert=True)
    else:
        await callback.answer("❌ Ресурспак не найден", show_alert=True)
    
    await delete_packs_list(callback)

@dp.callback_query(lambda c: c.data.startswith("delete_config_"))
async def delete_config_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_config_", ""))
    
    item = get_item("configs", item_id)
    if item:
        name = item[1]
        delete_item("configs", item_id)
        await callback.answer(f"✅ Конфиг '{name}' удалён!", show_alert=True)
    else:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
    
    await delete_configs_list(callback)

# ========== АДМИН: СПИСОК ==========
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
        for item_id, name, short_desc, downloads, version in items:
            text += f"`{item_id}`. **{name}** ({version})\n"
            text += f"   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]
        ])
    )
    await callback.answer()

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
        for item_id, name, short_desc, downloads, version in items:
            text += f"`{item_id}`. **{name}** ({version})\n"
            text += f"   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]
        ])
    )
    await callback.answer()

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
        for item_id, name, short_desc, downloads, version in items:
            text += f"`{item_id}`. **{name}** ({version})\n"
            text += f"   _{short_desc[:50]}..._ 📥 {downloads}\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
        ])
    )
    await callback.answer()

# ========== АДМИН: СТАТИСТИКА ==========
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        cur.execute('SELECT COUNT(*) FROM clients')
        clients = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM resourcepacks')
        packs = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM configs')
        configs = cur.fetchone()[0]
        
        cur.execute('SELECT SUM(downloads) FROM clients')
        clients_d = cur.fetchone()[0] or 0
        
        cur.execute('SELECT SUM(downloads) FROM resourcepacks')
        packs_d = cur.fetchone()[0] or 0
        
        cur.execute('SELECT SUM(downloads) FROM configs')
        configs_d = cur.fetchone()[0] or 0
        
        conn.close()
        
        users_count = get_users_count()
        backup_count = len(get_all_backups())
        backup_size = sum((BACKUP_DIR / f).stat().st_size for f in get_all_backups()) // 1024 if backup_count > 0 else 0
        
        text = (f"📊 **Статистика**\n\n"
                f"👤 Пользователей: {users_count}\n"
                f"🎮 Клиенты: {clients}\n"
                f"🎨 Ресурспаки: {packs}\n"
                f"⚙️ Конфиги: {configs}\n"
                f"📥 Всего скачиваний: {format_number(clients_d + packs_d + configs_d)}\n\n"
                f"📦 ZIP бэкапов: {backup_count} ({backup_size} KB)")
    except Exception as e:
        text = f"📊 **Статистика**\n\nОшибка получения данных: {e}"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
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
    await callback.message.edit_text(
        f"📢 **Создание рассылки**\n\n"
        f"Всего пользователей: {users_count}\n\n"
        f"Введи текст сообщения для рассылки:",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(message: Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.broadcast_photo)
    await message.answer(
        "📸 **Отправь фото** для рассылки (или отправь 'пропустить'):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'пропустить':
        photo_id = None
    else:
        await message.answer("❌ Отправь фото или 'пропустить'")
        return
    
    preview_text = f"📢 **Предпросмотр рассылки**\n\n{text}\n\nВсего пользователей: {get_users_count()}"
    
    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=preview_text,
            parse_mode="Markdown",
            reply_markup=get_broadcast_confirm_keyboard()
        )
    else:
        await message.answer(
            preview_text,
            parse_mode="Markdown",
            reply_markup=get_broadcast_confirm_keyboard()
        )
    
    await state.update_data(broadcast_photo=photo_id)

@dp.callback_query(lambda c: c.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    photo_id = data.get('broadcast_photo')
    
    users = get_all_users()
    sent = 0
    failed = 0
    
    await callback.message.edit_text("📢 **Рассылка началась...**", parse_mode="Markdown")
    
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
            await asyncio.sleep(0.05)
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
            await callback.answer("❌ Ошибка формата данных", show_alert=True)
            return
            
        if parts[0] == "media" and len(parts) >= 3:
            category = parts[1]
            item_id = int(parts[2])
        else:
            await callback.answer("❌ Неверный формат", show_alert=True)
            return
        
        item = get_item(category, item_id)
        if not item:
            await callback.answer("❌ Не найден", show_alert=True)
            return
        
        try:
            media_list = json.loads(item[4]) if item[4] else []
        except:
            media_list = []
        
        if not media_list:
            await callback.answer("📭 Нет медиа", show_alert=True)
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
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def show_media(message: Message, state: FSMContext, index: int):
    try:
        data = await state.get_data()
        media_list = data.get('media_list', [])
        
        if not media_list or index >= len(media_list):
            await message.answer("📭 Медиа не найдены")
            await state.clear()
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
            await message.answer_photo(
                photo=media['id'],
                caption=f"📸 Медиа {index+1} из {len(media_list)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        elif media['type'] == 'video':
            await message.answer_video(
                video=media['id'],
                caption=f"🎬 Видео {index+1} из {len(media_list)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        elif media['type'] == 'animation':
            await message.answer_animation(
                animation=media['id'],
                caption=f"🎞️ GIF {index+1} из {len(media_list)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
    except Exception as e:
        logger.error(f"Ошибка в show_media: {e}")
        await message.answer("❌ Ошибка при показе медиа")

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_navigation(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.replace("media_nav_", ""))
        await show_media(callback.message, state, index)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в media_navigation: {e}")
        await callback.answer("❌ Ошибка навигации", show_alert=True)

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        category = data.get('media_category')
        item_id = data.get('media_item_id')
        
        await state.clear()
        
        if category and item_id:
            callback.data = f"detail_{category}_{item_id}"
            await detail_view(callback, state)
        else:
            await callback.message.delete()
            await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в media_back: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

# ========== ЗАГЛУШКИ ==========
@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    is_admin = (callback.from_user.id == ADMIN_ID)
    await callback.message.answer(
        "**Главное меню:**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👤 Создатель: {CREATOR_USERNAME}")
    print(f"📁 Папка для данных: {DATA_DIR}")
    print(f"📁 Папка для бэкапов: {BACKUP_DIR}")
    print("="*50)
    print("📌 Функции:")
    print("   • 10 элементов на страницу")
    print("   • Красивое оформление с картинками")
    print("   • Работающее удаление для всех категорий")
    print("   • Полная админ-панель")
    print("   • Рассылка сообщений")
    print("   • 📦 ZIP бэкапы")
    print("   • ✅ Данные в /app/data (не пропадают)")
    print("="*50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())