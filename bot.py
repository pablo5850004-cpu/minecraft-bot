import logging
import os
import asyncio
import json
import sqlite3
import random
import shutil
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

# ========== БАЗА ДАННЫХ ==========
DB_PATH = 'clients.db'
BACKUP_DIR = 'backups'

os.makedirs(BACKUP_DIR, exist_ok=True)

def backup_db(comment: str = ""):
    """Создаёт бэкап базы данных"""
    try:
        if os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            comment = f"_{comment}" if comment else ""
            backup_name = f"clients_{timestamp}{comment}.db"
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            
            shutil.copy2(DB_PATH, backup_path)
            logger.info(f"✅ Бэкап создан: {backup_name}")
            
            backups = sorted(os.listdir(BACKUP_DIR))
            while len(backups) > 20:
                os.remove(os.path.join(BACKUP_DIR, backups[0]))
                backups.pop(0)
            
            return backup_path
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
        return None

def init_db():
    """Создание базы данных"""
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.close()
            print("✅ База данных существует")
        except:
            print("⚠️ База данных повреждена, удаляем...")
            os.remove(DB_PATH)
            backup_db("corrupted")
    
    conn = sqlite3.connect(DB_PATH)
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
    print("✅ База данных готова")

# Инициализация
try:
    init_db()
except Exception as e:
    print(f"❌ Ошибка: {e}")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()

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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
    item = cur.fetchone()
    conn.close()
    return item

@safe_db
def get_all_items(table: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, short_desc, downloads, version FROM {table} ORDER BY created_at DESC')
    items = cur.fetchall()
    conn.close()
    return items

@safe_db
def delete_item(table: str, item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    backup_db(f"delete_{table}_{item_id}")

# ========== ФУНКЦИИ ДЛЯ КЛИЕНТОВ ==========
def add_client(name: str, short_desc: str, full_desc: str, url: str, version: str, media: List[Dict] = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO clients (name, short_desc, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        backup_db(f"add_client_{item_id}")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении клиента: {e}")
        return None

@safe_db
def update_client(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    backup_db(f"update_client_{item_id}")

@safe_db
def get_clients_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить клиентов по версии"""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ РЕСУРСПАКОВ ==========
def add_pack(name: str, short_desc: str, full_desc: str, url: str, version: str, author: str, media: List[Dict] = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO resourcepacks (name, short_desc, full_desc, download_url, version, author, media)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, author, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        backup_db(f"add_pack_{item_id}")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении ресурспака: {e}")
        return None

@safe_db
def update_pack(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    backup_db(f"update_pack_{item_id}")

@safe_db
def get_packs_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить ресурспаки по версии"""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM resourcepacks WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ФУНКЦИИ ДЛЯ КОНФИГОВ ==========
def add_config(name: str, short_desc: str, full_desc: str, url: str, version: str, media: List[Dict] = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        media_json = json.dumps(media or [])
        cur.execute('''
            INSERT INTO configs (name, short_desc, full_desc, download_url, version, media)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, short_desc, full_desc, url, version, media_json))
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        backup_db(f"add_config_{item_id}")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении конфига: {e}")
        return None

@safe_db
def update_config(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    backup_db(f"update_config_{item_id}")

@safe_db
def get_configs_by_version(version: str, page: int = 1, per_page: int = 10):
    """Получить конфиги по версии"""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM configs WHERE version IS NOT NULL ORDER BY version DESC')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# ========== ОБЩИЕ ФУНКЦИИ ==========
@safe_db
def increment_view(table: str, item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

@safe_db
def increment_download(table: str, item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

@safe_db
def toggle_favorite(user_id: int, pack_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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

class SearchStates(StatesGroup):
    choosing_category = State()
    waiting_for_query = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin: bool = False):
    """Главная клавиатура"""
    buttons = [
        [
            types.KeyboardButton(text="🎮 Клиенты"),
            types.KeyboardButton(text="🎨 Ресурспаки"),
            types.KeyboardButton(text="🔍 Поиск")
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
    """Клавиатура выбора версии"""
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
    """Клавиатура со списком элементов (с версиями в скобках)"""
    buttons = []
    for item in items:
        item_id = item[0]
        name = item[1]
        media_json = item[3] if len(item) > 3 else '[]'
        downloads = item[4] if len(item) > 4 else 0
        
        # Получаем версию для отображения в скобках
        if category == "packs":
            version = item[7] if len(item) > 7 else "?"
        else:
            version = item[6] if len(item) > 6 else "?"
        
        version_text = get_version_display(version)
        
        try:
            media_list = json.loads(media_json) if media_json else []
        except:
            media_list = []
        
        preview = "🖼️" if media_list else "📄"
        buttons.append([InlineKeyboardButton(
            text=f"{preview} {name[:30]} {version_text} ({format_number(downloads)} 📥)", 
            callback_data=f"view_{category}_{item_id}"
        )])
    
    # Пагинация
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{category}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{category}_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_item_detail_keyboard(category: str, item_id: int, is_favorite: bool = False):
    """Клавиатура для детального просмотра"""
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
    """Главная клавиатура админ-панели"""
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📦 Бэкапы", callback_data="admin_backups")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_keyboard(category: str):
    """Клавиатура действий для категории"""
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
    for item_id, name, _, _, version in items[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"{item_id}. {name[:30]} ({version})", 
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

def get_search_category_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="search_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="search_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="search_configs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_backups_keyboard():
    try:
        backups = sorted(os.listdir(BACKUP_DIR), reverse=True)[:10]
        buttons = []
        for backup in backups:
            size = os.path.getsize(os.path.join(BACKUP_DIR, backup)) // 1024
            buttons.append([InlineKeyboardButton(
                text=f"📦 {backup} ({size} KB)",
                callback_data=f"restore_{backup}"
            )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    except:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]])

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        "👋 Привет! Я бот-каталог Minecraft\n\n"
        "🎮 Клиенты - моды и сборки\n"
        "🎨 Ресурспаки - текстурпаки\n"
        "🔍 Поиск - найди что хочешь\n"
        "❤️ Избранное - сохраняй понравившееся\n"
        "⚙️ Конфиги - настройки\n"
        "ℹ️ Инфо - о боте и создателе\n"
        "❓ Помощь - связаться с админом\n\n"
        "Используй кнопки ниже:",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== КЛИЕНТЫ ==========
@dp.message(F.text == "🎮 Клиенты")
async def clients_menu(message: Message):
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
async def packs_menu(message: Message):
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
async def configs_menu(message: Message):
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

# ========== ДЕТАЛЬНЫЙ ПРОСМОТР ==========
@dp.callback_query(lambda c: c.data.startswith("view_"))
async def view_item(callback: CallbackQuery, state: FSMContext):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    increment_view(category, item_id)
    
    if category == "clients":
        media_list = json.loads(item[4]) if item[4] else []
        text = (f"Название: {item[1]}\n\n"
                f"{item[3]}\n\n"
                f"Версия: {item[6]}\n"
                f"Скачиваний: {format_number(item[7])}\n"
                f"Просмотров: {format_number(item[8])}")
        await callback.message.edit_text(
            text,
            reply_markup=get_item_detail_keyboard(category, item_id)
        )
    elif category == "packs":
        media_list = json.loads(item[4]) if item[4] else []
        
        # Проверяем избранное
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT * FROM favorites WHERE user_id = ? AND pack_id = ?', 
                   (callback.from_user.id, item_id))
        is_fav = cur.fetchone() is not None
        conn.close()
        
        text = (f"Название: {item[1]}\n\n"
                f"{item[3]}\n\n"
                f"Автор: {item[7]}\n"
                f"Версия: {item[6]}\n"
                f"Скачиваний: {format_number(item[8])}\n"
                f"В избранном: {format_number(item[9])}\n"
                f"Просмотров: {format_number(item[10])}")
        
        await callback.message.edit_text(
            text,
            reply_markup=get_item_detail_keyboard(category, item_id, is_fav)
        )
    else:
        media_list = json.loads(item[4]) if item[4] else []
        text = (f"Название: {item[1]}\n\n"
                f"{item[3]}\n\n"
                f"Версия: {item[6]}\n"
                f"Скачиваний: {format_number(item[7])}\n"
                f"Просмотров: {format_number(item[8])}")
        await callback.message.edit_text(
            text,
            reply_markup=get_item_detail_keyboard(category, item_id)
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
    backup_db(f"download_{category}_{item_id}")
    
    url = item[5]
    name = item[1]
    
    await callback.message.answer(
        f"Скачать {name}:\n{url}"
    )
    await callback.answer("✅ Ссылка отправлена!")

# ========== ИЗБРАННОЕ ==========
@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    
    if not favs:
        await message.answer(
            "❤️ Избранное пусто\n\n"
            "Добавляй ресурспаки в избранное кнопкой 🤍"
        )
        return
    
    text = "❤️ Твоё избранное:\n\n"
    for fav in favs[:10]:
        media_list = json.loads(fav[3]) if fav[3] else []
        preview = "🖼️" if media_list else "📄"
        text += f"{preview} {fav[1]} - {format_number(fav[4])} 📥\n"
    
    if len(favs) > 10:
        text += f"\n...и еще {len(favs) - 10}"
    
    await message.answer(text)

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
    
    # Обновляем отображение
    await view_item(callback, None)

# ========== ПОИСК ==========
@dp.message(F.text == "🔍 Поиск")
async def search_start(message: Message, state: FSMContext):
    await state.set_state(SearchStates.choosing_category)
    await message.answer(
        "🔍 В какой категории искать?",
        reply_markup=get_search_category_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("search_") and c.data not in ["search_clients", "search_packs", "search_configs"])
async def search_category_selected(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("search_", "")
    await state.update_data(search_category=category)
    await state.set_state(SearchStates.waiting_for_query)
    await callback.message.edit_text("🔍 Введи поисковый запрос:")
    await callback.answer()

@dp.message(SearchStates.waiting_for_query)
async def search_execute(message: Message, state: FSMContext):
    await message.answer("⚠️ Поиск временно недоступен")
    await state.clear()

# ========== ИНФО ==========
@dp.message(F.text == "ℹ️ Инфо")
async def info(message: Message):
    await message.answer(
        f"Информация о боте\n\n"
        f"Создатель: {CREATOR_USERNAME}\n"
        f"Версия: 6.2\n\n"
        f"📊 Статистика будет добавлена позже"
    )

# ========== ПОМОЩЬ ==========
@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    await message.answer(
        "Помощь и поддержка\n\n"
        "Если у тебя возникли вопросы или проблемы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем\n"
        "• Опиши свою проблему подробно",
        reply_markup=get_help_keyboard()
    )

@dp.callback_query(lambda c: c.data == "help_rules")
async def help_rules(callback: CallbackQuery):
    await callback.message.edit_text(
        "Правила использования\n\n"
        "1. Все файлы предоставляются 'как есть'\n"
        "2. Автор не несёт ответственности за использование файлов\n"
        "3. Запрещено выкладывать файлы на других ресурсах без указания автора\n"
        "4. Уважайте других пользователей",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help_faq")
async def help_faq(callback: CallbackQuery):
    await callback.message.edit_text(
        "Часто задаваемые вопросы\n\n"
        "Q: Как скачать файл?\n"
        "A: Нажми на элемент, затем кнопку 'Скачать'\n\n"
        "Q: Почему не работает ссылка?\n"
        "A: Возможно, файл был удалён. Сообщи админу\n\n"
        "Q: Как добавить в избранное?\n"
        "A: В разделе ресурспаков нажми 🤍\n\n"
        "Q: Бот не отвечает, что делать?\n"
        "A: Напиши админу через кнопку 'Связаться'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "Помощь и поддержка\n\n"
        "Если у тебя возникли вопросы или проблемы:\n\n"
        "• Нажми кнопку ниже, чтобы связаться с создателем\n"
        "• Опиши свою проблему подробно",
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
        "⚙️ Админ панель\n\nВыбери категорию:",
        reply_markup=get_admin_main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ Админ панель\n\nВыбери категорию:",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_clients")
async def admin_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎮 Управление клиентами\n\nВыбери действие:",
        reply_markup=get_admin_category_keyboard("clients")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_packs")
async def admin_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎨 Управление ресурспаками\n\nВыбери действие:",
        reply_markup=get_admin_category_keyboard("packs")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_configs")
async def admin_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ Управление конфигами\n\nВыбери действие:",
        reply_markup=get_admin_category_keyboard("configs")
    )
    await callback.answer()

# ========== АДМИН: ДОБАВЛЕНИЕ КЛИЕНТА ==========
@dp.callback_query(lambda c: c.data == "add_clients")
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
    await state.set_state(AdminStates.client_short_desc)
    await message.answer("📄 Введи краткое описание:")

@dp.message(AdminStates.client_short_desc)
async def client_short_desc(message: Message, state: FSMContext):
    await state.update_data(client_short_desc=message.text)
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
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:"
    )

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    # Проверяем команду "готово"
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
                f"✅ Клиент добавлен! ID: {item_id}\n"
                f"Добавлено фото: {len(media_list)}",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    # Проверяем команду "пропустить"
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
                f"✅ Клиент добавлен! ID: {item_id} (без фото)",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    # Обработка фото
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**"
        )
    else:
        await message.answer(
            "❌ Отправь фото, или напиши **готово** / **пропустить**"
        )

# ========== АДМИН: ДОБАВЛЕНИЕ РЕСУРСПАКА ==========
@dp.callback_query(lambda c: c.data == "add_packs")
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
    await state.set_state(AdminStates.pack_short_desc)
    await message.answer("📄 Введи краткое описание:")

@dp.message(AdminStates.pack_short_desc)
async def pack_short_desc(message: Message, state: FSMContext):
    await state.update_data(pack_short_desc=message.text)
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
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:"
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
                f"✅ Ресурспак добавлен! ID: {item_id}\n"
                f"Добавлено фото: {len(media_list)}",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
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
                f"✅ Ресурспак добавлен! ID: {item_id} (без фото)",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**"
        )
    else:
        await message.answer(
            "❌ Отправь фото, или напиши **готово** / **пропустить**"
        )

# ========== АДМИН: ДОБАВЛЕНИЕ КОНФИГА ==========
@dp.callback_query(lambda c: c.data == "add_configs")
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
    await state.set_state(AdminStates.config_short_desc)
    await message.answer("📄 Введи краткое описание:")

@dp.message(AdminStates.config_short_desc)
async def config_short_desc(message: Message, state: FSMContext):
    await state.update_data(config_short_desc=message.text)
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
        "После того как отправишь все фото, напиши **готово**\n"
        "Или напиши **пропустить** если не хочешь добавлять фото:"
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
                f"✅ Конфиг добавлен! ID: {item_id}\n"
                f"Добавлено фото: {len(media_list)}",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
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
                f"✅ Конфиг добавлен! ID: {item_id} (без фото)",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                "❌ Ошибка при добавлении",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(
            f"✅ Фото добавлено! Всего: {len(media_list)}\n"
            f"Можешь отправить ещё фото или написать **готово**"
        )
    else:
        await message.answer(
            "❌ Отправь фото, или напиши **готово** / **пропустить**"
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
            "📭 Нет клиентов для редактирования",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ Выбери клиента для редактирования:",
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
            "📭 Нет ресурспаков для редактирования",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ Выбери ресурспак для редактирования:",
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
            "📭 Нет конфигов для редактирования",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ Выбери конфиг для редактирования:",
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
        "✏️ Что изменить?",
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
        "✏️ Что изменить?",
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
        "✏️ Что изменить?",
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
    await callback.message.edit_text("✏️ Введи новое значение:")
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
    await message.answer("✅ Обновлено!", reply_markup=get_main_keyboard(is_admin=True))

# ========== АДМИН: УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data == "delete_clients")
async def delete_clients_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("clients")
    if not items:
        await callback.message.edit_text(
            "📭 Нет клиентов для удаления",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 Выбери клиента для удаления:",
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
            "📭 Нет ресурспаков для удаления",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 Выбери ресурспак для удаления:",
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
            "📭 Нет конфигов для удаления",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 Выбери конфиг для удаления:",
        reply_markup=get_admin_items_keyboard(items, "configs", "delete_config")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_client_"))
async def delete_client_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_client_", ""))
    delete_item("clients", item_id)
    await callback.answer("✅ Клиент удалён!", show_alert=True)
    await delete_clients_list(callback)

@dp.callback_query(lambda c: c.data.startswith("delete_pack_"))
async def delete_pack_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_pack_", ""))
    delete_item("resourcepacks", item_id)
    await callback.answer("✅ Ресурспак удалён!", show_alert=True)
    await delete_packs_list(callback)

@dp.callback_query(lambda c: c.data.startswith("delete_config_"))
async def delete_config_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    item_id = int(callback.data.replace("delete_config_", ""))
    delete_item("configs", item_id)
    await callback.answer("✅ Конфиг удалён!", show_alert=True)
    await delete_configs_list(callback)

# ========== АДМИН: СПИСОК ==========
@dp.callback_query(lambda c: c.data == "list_clients")
async def list_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    items = get_all_items("clients")
    if not items:
        text = "📭 Список клиентов пуст"
    else:
        text = "📋 Список клиентов:\n\n"
        for item_id, name, short_desc, downloads, version in items:
            text += f"{item_id}. {name} ({version}) - {short_desc[:30]}... 📥 {downloads}\n"
    
    await callback.message.edit_text(
        text,
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
        text = "📭 Список ресурспаков пуст"
    else:
        text = "📋 Список ресурспаков:\n\n"
        for item_id, name, short_desc, downloads, version in items:
            text += f"{item_id}. {name} ({version}) - {short_desc[:30]}... 📥 {downloads}\n"
    
    await callback.message.edit_text(
        text,
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
        text = "📭 Список конфигов пуст"
    else:
        text = "📋 Список конфигов:\n\n"
        for item_id, name, short_desc, downloads, version in items:
            text += f"{item_id}. {name} ({version}) - {short_desc[:30]}... 📥 {downloads}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]
        ])
    )
    await callback.answer()

# ========== БЭКАПЫ ==========
@dp.callback_query(lambda c: c.data == "admin_backups")
async def admin_backups(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    backup_path = backup_db("manual")
    
    text = "📦 Управление бэкапами\n\n"
    if backup_path:
        text += "✅ Новый бэкап создан!\n\n"
    text += "Последние бэкапы:"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_backups_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("restore_"))
async def restore_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    backup_name = callback.data.replace("restore_", "")
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        await callback.answer("❌ Бэкап не найден", show_alert=True)
        return
    
    backup_db("before_restore")
    shutil.copy2(backup_path, DB_PATH)
    
    await callback.answer("✅ База данных восстановлена!", show_alert=True)
    await admin_back(callback)

# ========== СТАТИСТИКА ==========
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
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
        
        backup_count = len(os.listdir(BACKUP_DIR)) if os.path.exists(BACKUP_DIR) else 0
        backup_size = sum(os.path.getsize(os.path.join(BACKUP_DIR, f)) for f in os.listdir(BACKUP_DIR)) // 1024 if backup_count > 0 else 0
        
        text = (f"Статистика\n\n"
                f"Клиенты: {clients}\n"
                f"Ресурспаки: {packs}\n"
                f"Конфиги: {configs}\n"
                f"Всего скачиваний: {format_number(clients_d + packs_d + configs_d)}\n\n"
                f"Бэкапов: {backup_count} ({backup_size} KB)")
    except:
        text = "Статистика\n\nОшибка получения данных"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
    )
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
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

# ========== МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith("media_"))
async def view_media(callback: CallbackQuery, state: FSMContext):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
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

async def show_media(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    media_list = data['media_list']
    
    if index >= len(media_list):
        index = 0
    
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
            caption=f"Медиа {index+1} из {len(media_list)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    elif media['type'] == 'video':
        await message.answer_video(
            video=media['id'],
            caption=f"Видео {index+1} из {len(media_list)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    elif media['type'] == 'animation':
        await message.answer_animation(
            animation=media['id'],
            caption=f"GIF {index+1} из {len(media_list)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_navigation(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("media_nav_", ""))
    await show_media(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    
    await state.clear()
    
    # Показываем детальную информацию
    callback.data = f"view_{category}_{item_id}"
    await view_item(callback, state)

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👤 Создатель: {CREATOR_USERNAME}")
    print("="*50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())