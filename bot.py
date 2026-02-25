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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5809098591'))

if not BOT_TOKEN:
    raise ValueError("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
DB_PATH = 'clients.db'

def init_db():
    """Создание базы данных"""
    global DB_PATH
    
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.close()
            print("✅ База данных существует")
        except:
            print("⚠️ База данных повреждена, удаляем...")
            os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Клиенты
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
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
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            media TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            min_version TEXT,
            max_version TEXT,
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
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            media TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            game_version TEXT,
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

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_number(num: int) -> str:
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    else:
        return f"{num/1000000:.1f}M"

def safe_db(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка БД: {e}")
            return None
    return wrapper

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ==========
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
    cur.execute(f'SELECT id, name, description, downloads FROM {table} ORDER BY created_at DESC')
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

# Клиенты
@safe_db
def add_client(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    media_json = json.dumps(media or [])
    cur.execute('''
        INSERT INTO clients (name, description, full_description, download_url, version, media)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, desc, full, url, version, media_json))
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

@safe_db
def update_client(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_clients_by_version(version: str = 'all'):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if version == 'all':
        cur.execute('SELECT id, name, description, media, downloads, views, version FROM clients ORDER BY downloads DESC')
    else:
        cur.execute('SELECT id, name, description, media, downloads, views, version FROM clients WHERE version = ? ORDER BY downloads DESC', (version,))
    items = cur.fetchall()
    conn.close()
    return items

@safe_db
def get_client_versions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

# Ресурспаки
@safe_db
def add_pack(name: str, desc: str, full: str, url: str, min_v: str, max_v: str, author: str, media: List[Dict] = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    media_json = json.dumps(media or [])
    cur.execute('''
        INSERT INTO resourcepacks (name, description, full_description, download_url, min_version, max_version, author, media)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, desc, full, url, min_v, max_v, author, media_json))
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

@safe_db
def update_pack(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_packs_by_version(version: str, sort: str = 'popular'):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        v_num = float(version)
    except:
        v_num = 0
    cur.execute('''
        SELECT id, name, description, media, downloads, likes, views, min_version, max_version, author 
        FROM resourcepacks 
        WHERE CAST(min_version AS FLOAT) <= ? AND CAST(max_version AS FLOAT) >= ?
    ''', (v_num, v_num))
    packs = cur.fetchall()
    if sort == 'popular':
        packs.sort(key=lambda x: x[4], reverse=True)
    elif sort == 'likes':
        packs.sort(key=lambda x: x[5], reverse=True)
    elif sort == 'random':
        random.shuffle(packs)
    conn.close()
    return packs

@safe_db
def get_pack_versions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT min_version FROM resourcepacks UNION SELECT DISTINCT max_version FROM resourcepacks')
    versions = set()
    for v in cur.fetchall():
        try:
            versions.add(str(float(v[0])))
        except:
            pass
    conn.close()
    return sorted(list(versions), key=lambda x: float(x))

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
        SELECT r.id, r.name, r.description, r.media, r.downloads, r.likes 
        FROM resourcepacks r
        JOIN favorites f ON r.id = f.pack_id
        WHERE f.user_id = ?
        ORDER BY f.added_at DESC
    ''', (user_id,))
    favs = cur.fetchall()
    conn.close()
    return favs

# Конфиги
@safe_db
def add_config(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    media_json = json.dumps(media or [])
    cur.execute('''
        INSERT INTO configs (name, description, full_description, download_url, game_version, media)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, desc, full, url, version, media_json))
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

@safe_db
def update_config(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

@safe_db
def get_configs_by_version(version: str = 'all'):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if version == 'all':
        cur.execute('SELECT id, name, description, media, downloads, views, game_version FROM configs ORDER BY downloads DESC')
    else:
        cur.execute('SELECT id, name, description, media, downloads, views, game_version FROM configs WHERE game_version = ? ORDER BY downloads DESC', (version,))
    items = cur.fetchall()
    conn.close()
    return items

@safe_db
def get_config_versions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT game_version FROM configs WHERE game_version IS NOT NULL')
    versions = [v[0] for v in cur.fetchall()]
    conn.close()
    return versions

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

# Медиа
@safe_db
def add_media(table: str, item_id: int, media_type: str, media_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'SELECT media FROM {table} WHERE id = ?', (item_id,))
    result = cur.fetchone()
    if not result:
        return False
    media_list = json.loads(result[0]) if result[0] else []
    media_list.append({'type': media_type, 'id': media_id, 'added_at': datetime.now().isoformat()})
    cur.execute(f'UPDATE {table} SET media = ? WHERE id = ?', (json.dumps(media_list), item_id))
    conn.commit()
    conn.close()
    return True

@safe_db
def remove_media(table: str, item_id: int, index: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'SELECT media FROM {table} WHERE id = ?', (item_id,))
    result = cur.fetchone()
    if not result:
        return False
    media_list = json.loads(result[0]) if result[0] else []
    if 0 <= index < len(media_list):
        del media_list[index]
        cur.execute(f'UPDATE {table} SET media = ? WHERE id = ?', (json.dumps(media_list), item_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# ========== СОСТОЯНИЯ ==========
class AdminStates(StatesGroup):
    client_name = State()
    client_desc = State()
    client_full = State()
    client_version = State()
    client_url = State()
    client_media = State()
    
    pack_name = State()
    pack_desc = State()
    pack_full = State()
    pack_min = State()
    pack_max = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    
    config_name = State()
    config_desc = State()
    config_full = State()
    config_version = State()
    config_url = State()
    config_media = State()
    
    edit_field = State()
    edit_value = State()

class BrowseStates(StatesGroup):
    viewing = State()
    media_view = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin: bool = False):
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты")],
        [types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="❤️ Избранное")],
        [types.KeyboardButton(text="⚙️ Конфиги")],
        [types.KeyboardButton(text="ℹ️ О боте")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_main_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
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

def get_items_keyboard(items: List[Tuple], category: str, action: str):
    buttons = []
    for item_id, name, _, _ in items[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"{item_id}. {name[:30]}", 
            callback_data=f"{action}_{category}_{item_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_fields_keyboard(category: str, item_id: int):
    if category == 'packs':
        fields = [
            ["📝 Название", f"edit_name_{category}_{item_id}"],
            ["📄 Краткое описание", f"edit_desc_{category}_{item_id}"],
            ["📚 Полное описание", f"edit_full_{category}_{item_id}"],
            ["🔢 Мин версия", f"edit_min_{category}_{item_id}"],
            ["🔢 Макс версия", f"edit_max_{category}_{item_id}"],
            ["✍️ Автор", f"edit_author_{category}_{item_id}"],
            ["🔗 Ссылка", f"edit_url_{category}_{item_id}"],
            ["🖼️ Медиа", f"media_{category}_{item_id}"],
        ]
    else:
        fields = [
            ["📝 Название", f"edit_name_{category}_{item_id}"],
            ["📄 Краткое описание", f"edit_desc_{category}_{item_id}"],
            ["📚 Полное описание", f"edit_full_{category}_{item_id}"],
            ["🔢 Версия", f"edit_version_{category}_{item_id}"],
            ["🔗 Ссылка", f"edit_url_{category}_{item_id}"],
            ["🖼️ Медиа", f"media_{category}_{item_id}"],
        ]
    buttons = [[InlineKeyboardButton(text=text, callback_data=cb)] for text, cb in fields]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_media_keyboard(category: str, item_id: int):
    buttons = [
        [InlineKeyboardButton(text="📸 Добавить фото", callback_data=f"media_photo_{category}_{item_id}")],
        [InlineKeyboardButton(text="🎬 Добавить видео/GIF", callback_data=f"media_video_{category}_{item_id}")],
        [InlineKeyboardButton(text="🖼️ Просмотр", callback_data=f"media_view_{category}_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"media_del_{category}_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_{category}_{item_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        "👋 **Привет! Я бот-каталог Minecraft**\n\n"
        "🎮 Клиенты - моды и сборки\n"
        "🎨 Ресурспаки - текстурпаки\n"
        "⚙️ Конфиги - настройки\n"
        "❤️ Избранное - сохраняй понравившееся\n\n"
        "Используй кнопки ниже:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

@dp.message(F.text == "ℹ️ О боте")
async def about(message: Message):
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        "ℹ️ **О боте**\n\nВерсия: 3.2\nРазработчик: @pablo5850004",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== КЛИЕНТЫ ==========
@dp.message(F.text == "🎮 Клиенты")
async def clients_menu(message: Message, state: FSMContext):
    versions = get_client_versions()
    if not versions:
        await state.update_data(client_version='all')
        await show_next_client(message, state, 0, 'clients')
        return
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"client_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="📌 Все версии", callback_data="client_ver_all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await message.answer("🎮 **Выбери версию Minecraft:**", parse_mode="Markdown", 
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("client_ver_"))
async def client_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("client_ver_", "")
    await state.update_data(client_version=version, client_index=0)
    await show_next_client(callback.message, state, 0, 'clients')
    await callback.answer()

async def show_next_client(message: Message, state: FSMContext, index: int, category: str):
    data = await state.get_data()
    version = data.get('client_version', 'all')
    clients = get_clients_by_version(version)
    if not clients or index >= len(clients):
        await message.answer("❌ Больше нет клиентов")
        return
    client = clients[index]
    client_id = client[0]
    increment_view('clients', client_id)
    try:
        media_list = json.loads(client[3]) if client[3] else []
    except:
        media_list = []
    text = (f"**{client[1]}**\n\n{client[2]}\n\n*Версия:* {client[6]}\n"
            f"📥 Скачиваний: {format_number(client[4])}\n👁 Просмотров: {format_number(client[5])}")
    buttons = []
    buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_clients_{client_id}")])
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_clients_{client_id}")])
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_clients_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(clients)}", callback_data="noop"))
    if index < len(clients) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_clients_{index+1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_client_versions")])
    await state.update_data(client_index=index, client_list=[c[0] for c in clients])
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(photo=media_list[0]['id'], caption=text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("nav_clients_"))
async def client_navigation(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("nav_clients_", ""))
    await show_next_client(callback.message, state, index, 'clients')
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_client_versions")
async def back_to_client_versions(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    versions = get_client_versions()
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"client_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="📌 Все версии", callback_data="client_ver_all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await callback.message.edit_text("🎮 **Выбери версию Minecraft:**", parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== РЕСУРСПАКИ ==========
@dp.message(F.text == "🎨 Ресурспаки")
async def packs_menu(message: Message, state: FSMContext):
    versions = get_pack_versions()
    if not versions:
        await message.answer("📭 Пока нет ресурспаков")
        return
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"pack_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await message.answer("🎨 **Выбери версию Minecraft:**", parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("pack_ver_"))
async def pack_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("pack_ver_", "")
    buttons = [
        [InlineKeyboardButton(text="🔥 Популярные", callback_data=f"pack_sort_{version}_popular")],
        [InlineKeyboardButton(text="❤️ По лайкам", callback_data=f"pack_sort_{version}_likes")],
        [InlineKeyboardButton(text="🎲 Случайные", callback_data=f"pack_sort_{version}_random")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_pack_versions")]
    ]
    await callback.message.edit_text(f"🎨 **Версия {version}**\n\nКак отсортировать?", parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pack_sort_"))
async def pack_sort_selected(callback: CallbackQuery, state: FSMContext):
    _, version, sort = callback.data.split("_", 2)
    await state.update_data(pack_version=version, pack_sort=sort, pack_index=0)
    await show_next_pack(callback.message, state, 0)
    await callback.answer()

async def show_next_pack(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    version = data.get('pack_version')
    sort = data.get('pack_sort', 'popular')
    packs = get_packs_by_version(version, sort)
    if not packs or index >= len(packs):
        await message.answer("❌ Больше нет ресурспаков")
        return
    pack = packs[index]
    pack_id = pack[0]
    increment_view('resourcepacks', pack_id)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT * FROM favorites WHERE user_id = ? AND pack_id = ?', (message.chat.id, pack_id))
        is_fav = cur.fetchone() is not None
        conn.close()
    except:
        is_fav = False
    try:
        media_list = json.loads(pack[3]) if pack[3] else []
    except:
        media_list = []
    text = (f"**{pack[1]}**\n\n{pack[2]}\n\n*Автор:* {pack[9]}\n*Версии:* {pack[7]} - {pack[8]}\n"
            f"📥 Скачиваний: {format_number(pack[4])}\n❤️ В избранном: {format_number(pack[5])}\n"
            f"👁 Просмотров: {format_number(pack[6])}")
    buttons = []
    action_row = [InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_packs_{pack_id}")]
    action_row.append(InlineKeyboardButton(text="❤️ В избранном" if is_fav else "🤍 В избранное",
                                          callback_data=f"fav_packs_{pack_id}"))
    buttons.append(action_row)
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_packs_{pack_id}")])
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_packs_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(packs)}", callback_data="noop"))
    if index < len(packs) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_packs_{index+1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_pack_versions")])
    await state.update_data(pack_index=index, pack_list=[p[0] for p in packs])
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(photo=media_list[0]['id'], caption=text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("nav_packs_"))
async def pack_navigation(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("nav_packs_", ""))
    await show_next_pack(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("fav_packs_"))
async def pack_favorite(callback: CallbackQuery, state: FSMContext):
    pack_id = int(callback.data.replace("fav_packs_", ""))
    user_id = callback.from_user.id
    added = toggle_favorite(user_id, pack_id)
    await callback.answer("❤️ Добавлено в избранное!" if added else "💔 Удалено из избранного")
    data = await state.get_data()
    if data:
        await show_next_pack(callback.message, state, data.get('pack_index', 0))
    else:
        await callback.message.delete()

@dp.callback_query(lambda c: c.data == "back_to_pack_versions")
async def back_to_pack_versions(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    versions = get_pack_versions()
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"pack_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await callback.message.edit_text("🎨 **Выбери версию Minecraft:**", parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== КОНФИГИ ==========
@dp.message(F.text == "⚙️ Конфиги")
async def configs_menu(message: Message, state: FSMContext):
    versions = get_config_versions()
    if not versions:
        await state.update_data(config_version='all')
        await show_next_config(message, state, 0)
        return
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"config_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="📌 Все версии", callback_data="config_ver_all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await message.answer("⚙️ **Выбери версию Minecraft:**", parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("config_ver_"))
async def config_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("config_ver_", "")
    await state.update_data(config_version=version, config_index=0)
    await show_next_config(callback.message, state, 0)
    await callback.answer()

async def show_next_config(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    version = data.get('config_version', 'all')
    configs = get_configs_by_version(version)
    if not configs or index >= len(configs):
        await message.answer("❌ Больше нет конфигов")
        return
    config = configs[index]
    config_id = config[0]
    increment_view('configs', config_id)
    try:
        media_list = json.loads(config[3]) if config[3] else []
    except:
        media_list = []
    text = (f"**{config[1]}**\n\n{config[2]}\n\n*Версия:* {config[6]}\n"
            f"📥 Скачиваний: {format_number(config[4])}\n👁 Просмотров: {format_number(config[5])}")
    buttons = []
    buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_configs_{config_id}")])
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_configs_{config_id}")])
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_configs_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(configs)}", callback_data="noop"))
    if index < len(configs) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_configs_{index+1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_config_versions")])
    await state.update_data(config_index=index, config_list=[c[0] for c in configs])
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(photo=media_list[0]['id'], caption=text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("nav_configs_"))
async def config_navigation(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("nav_configs_", ""))
    await show_next_config(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_config_versions")
async def back_to_config_versions(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    versions = get_config_versions()
    buttons = []
    row = []
    for v in versions:
        row.append(InlineKeyboardButton(text=v, callback_data=f"config_ver_{v}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="📌 Все версии", callback_data="config_ver_all")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await callback.message.edit_text("⚙️ **Выбери версию Minecraft:**", parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== ИЗБРАННОЕ ==========
@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("❤️ **Избранное пусто**\n\nДобавляй ресурспаки в избранное кнопкой '🤍 В избранное'",
                            parse_mode="Markdown")
        return
    text = "❤️ **Твое избранное:**\n\n"
    for f in favs[:10]:
        text += f"• {f[1]} - {format_number(f[4])} 📥\n"
    if len(favs) > 10:
        text += f"\n...и еще {len(favs) - 10}"
    await message.answer(text, parse_mode="Markdown")

# ========== ОБЩИЕ ФУНКЦИИ ==========
@dp.callback_query(lambda c: c.data.startswith("download_"))
async def download_item(callback: CallbackQuery):
    _, table, item_id = callback.data.split("_")
    item_id = int(item_id)
    item = get_item(table, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    increment_download(table, item_id)
    name = item[1]
    url = item[5]  # download_url
    await callback.message.answer(f"📥 **Скачать {name}**\n\n[Нажми для скачивания]({url})", parse_mode="Markdown")
    await callback.answer("✅ Ссылка отправлена!")

@dp.callback_query(lambda c: c.data.startswith("media_"))
async def view_media(callback: CallbackQuery, state: FSMContext):
    _, table, item_id = callback.data.split("_")
    item_id = int(item_id)
    item = get_item(table, item_id)
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
    await state.update_data(media_list=media_list, media_index=0, media_table=table, media_item_id=item_id)
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
        await message.answer_photo(photo=media['id'], caption=f"📸 Медиа {index+1} из {len(media_list)}",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif media['type'] == 'video':
        await message.answer_video(video=media['id'], caption=f"🎬 Видео {index+1} из {len(media_list)}",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif media['type'] == 'animation':
        await message.answer_animation(animation=media['id'], caption=f"🎞️ GIF {index+1} из {len(media_list)}",
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_navigation(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("media_nav_", ""))
    await show_media(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    table = data.get('media_table')
    item_id = data.get('media_item_id')
    await state.clear()
    if table == 'resourcepacks':
        await show_next_pack(callback.message, state, 0)
    elif table == 'clients':
        await show_next_client(callback.message, state, 0, table)
    elif table == 'configs':
        await show_next_config(callback.message, state, 0)
    await callback.answer()

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

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    await message.answer("⚙️ **Админ панель**\n\nВыбери категорию:", parse_mode="Markdown",
                        reply_markup=get_admin_main_keyboard())

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ **Админ панель**\n\nВыбери категорию:", parse_mode="Markdown",
                                     reply_markup=get_admin_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["admin_clients", "admin_packs", "admin_configs"])
async def admin_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    category_map = {
        "admin_clients": ("🎮 Клиенты", "clients"),
        "admin_packs": ("🎨 Ресурспаки", "packs"),
        "admin_configs": ("⚙️ Конфиги", "configs")
    }
    title, cat = category_map[callback.data]
    await callback.message.edit_text(f"{title}\n\nВыбери действие:", parse_mode="Markdown",
                                     reply_markup=get_admin_category_keyboard(cat))
    await callback.answer()

# ========== АДМИН: ДОБАВЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("add_"))
async def add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    category = callback.data.replace("add_", "")
    await state.update_data(category=category)
    if category == "packs":
        await state.set_state(AdminStates.pack_name)
        await callback.message.edit_text("📝 Введи **название** ресурспака:", parse_mode="Markdown")
    elif category == "clients":
        await state.set_state(AdminStates.client_name)
        await callback.message.edit_text("📝 Введи **название** клиента:", parse_mode="Markdown")
    elif category == "configs":
        await state.set_state(AdminStates.config_name)
        await callback.message.edit_text("📝 Введи **название** конфига:", parse_mode="Markdown")
    await callback.answer()

@dp.message(AdminStates.client_name)
async def client_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await state.set_state(AdminStates.client_desc)
    await message.answer("📄 Введи **краткое описание**:", parse_mode="Markdown")

@dp.message(AdminStates.client_desc)
async def client_desc(message: Message, state: FSMContext):
    await state.update_data(client_desc=message.text)
    await state.set_state(AdminStates.client_full)
    await message.answer("📚 Введи **полное описание**:", parse_mode="Markdown")

@dp.message(AdminStates.client_full)
async def client_full(message: Message, state: FSMContext):
    await state.update_data(client_full=message.text)
    await state.set_state(AdminStates.client_version)
    await message.answer("🔢 Введи **версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.client_version)
async def client_version(message: Message, state: FSMContext):
    await state.update_data(client_version=message.text)
    await state.set_state(AdminStates.client_url)
    await message.answer("🔗 Введи **ссылку на скачивание**:", parse_mode="Markdown")

@dp.message(AdminStates.client_url)
async def client_url(message: Message, state: FSMContext):
    await state.update_data(client_url=message.text)
    await state.set_state(AdminStates.client_media)
    await message.answer("🖼️ **Добавь медиа**\n\nОтправляй файлы по одному. Когда закончишь, напиши **готово**\nИли **пропустить**:", parse_mode="Markdown")

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    if message.text and message.text.lower() == 'готово':
        item_id = add_client(data['client_name'], data['client_desc'], data['client_full'],
                            data['client_url'], data['client_version'], media_list)
        await state.clear()
        await message.answer(f"✅ **Клиент добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_client(data['client_name'], data['client_desc'], data['client_full'],
                            data['client_url'], data['client_version'], [])
        await state.clear()
        await message.answer(f"✅ **Клиент добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    media_type = None
    media_id = None
    if message.photo:
        media_type = 'photo'
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = 'video'
        media_id = message.video.file_id
    elif message.animation:
        media_type = 'animation'
        media_id = message.animation.file_id
    else:
        await message.answer("❌ Отправь фото, видео, GIF, или **готово**/**пропустить**")
        return
    media_list.append({'type': media_type, 'id': media_id})
    await state.update_data(media_list=media_list)
    await message.answer(f"✅ Медиа добавлено! Всего: {len(media_list)}")

@dp.message(AdminStates.pack_name)
async def pack_name(message: Message, state: FSMContext):
    await state.update_data(pack_name=message.text)
    await state.set_state(AdminStates.pack_desc)
    await message.answer("📄 Введи **краткое описание**:", parse_mode="Markdown")

@dp.message(AdminStates.pack_desc)
async def pack_desc(message: Message, state: FSMContext):
    await state.update_data(pack_desc=message.text)
    await state.set_state(AdminStates.pack_full)
    await message.answer("📚 Введи **полное описание**:", parse_mode="Markdown")

@dp.message(AdminStates.pack_full)
async def pack_full(message: Message, state: FSMContext):
    await state.update_data(pack_full=message.text)
    await state.set_state(AdminStates.pack_min)
    await message.answer("🔢 Введи **минимальную версию** (например 1.8):", parse_mode="Markdown")

@dp.message(AdminStates.pack_min)
async def pack_min(message: Message, state: FSMContext):
    await state.update_data(pack_min=message.text)
    await state.set_state(AdminStates.pack_max)
    await message.answer("🔢 Введи **максимальную версию** (например 1.16):", parse_mode="Markdown")

@dp.message(AdminStates.pack_max)
async def pack_max(message: Message, state: FSMContext):
    await state.update_data(pack_max=message.text)
    await state.set_state(AdminStates.pack_author)
    await message.answer("✍️ Введи **автора** ресурспака:", parse_mode="Markdown")

@dp.message(AdminStates.pack_author)
async def pack_author(message: Message, state: FSMContext):
    await state.update_data(pack_author=message.text)
    await state.set_state(AdminStates.pack_url)
    await message.answer("🔗 Введи **ссылку на скачивание**:", parse_mode="Markdown")

@dp.message(AdminStates.pack_url)
async def pack_url(message: Message, state: FSMContext):
    await state.update_data(pack_url=message.text)
    await state.set_state(AdminStates.pack_media)
    await message.answer("🖼️ **Добавь медиа**\n\nОтправляй файлы по одному. Когда закончишь, напиши **готово**\nИли **пропустить**:", parse_mode="Markdown")

@dp.message(AdminStates.pack_media)
async def pack_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    if message.text and message.text.lower() == 'готово':
        item_id = add_pack(data['pack_name'], data['pack_desc'], data['pack_full'], data['pack_url'],
                          data['pack_min'], data['pack_max'], data['pack_author'], media_list)
        await state.clear()
        await message.answer(f"✅ **Ресурспак добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_pack(data['pack_name'], data['pack_desc'], data['pack_full'], data['pack_url'],
                          data['pack_min'], data['pack_max'], data['pack_author'], [])
        await state.clear()
        await message.answer(f"✅ **Ресурспак добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    media_type = None
    media_id = None
    if message.photo:
        media_type = 'photo'
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = 'video'
        media_id = message.video.file_id
    elif message.animation:
        media_type = 'animation'
        media_id = message.animation.file_id
    else:
        await message.answer("❌ Отправь фото, видео, GIF, или **готово**/**пропустить**")
        return
    media_list.append({'type': media_type, 'id': media_id})
    await state.update_data(media_list=media_list)
    await message.answer(f"✅ Медиа добавлено! Всего: {len(media_list)}")

@dp.message(AdminStates.config_name)
async def config_name(message: Message, state: FSMContext):
    await state.update_data(config_name=message.text)
    await state.set_state(AdminStates.config_desc)
    await message.answer("📄 Введи **краткое описание**:", parse_mode="Markdown")

@dp.message(AdminStates.config_desc)
async def config_desc(message: Message, state: FSMContext):
    await state.update_data(config_desc=message.text)
    await state.set_state(AdminStates.config_full)
    await message.answer("📚 Введи **полное описание**:", parse_mode="Markdown")

@dp.message(AdminStates.config_full)
async def config_full(message: Message, state: FSMContext):
    await state.update_data(config_full=message.text)
    await state.set_state(AdminStates.config_version)
    await message.answer("🔢 Введи **версию** (например 1.20.4):", parse_mode="Markdown")

@dp.message(AdminStates.config_version)
async def config_version(message: Message, state: FSMContext):
    await state.update_data(config_version=message.text)
    await state.set_state(AdminStates.config_url)
    await message.answer("🔗 Введи **ссылку на скачивание**:", parse_mode="Markdown")

@dp.message(AdminStates.config_url)
async def config_url(message: Message, state: FSMContext):
    await state.update_data(config_url=message.text)
    await state.set_state(AdminStates.config_media)
    await message.answer("🖼️ **Добавь медиа**\n\nОтправляй файлы по одному. Когда закончишь, напиши **готово**\nИли **пропустить**:", parse_mode="Markdown")

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    if message.text and message.text.lower() == 'готово':
        item_id = add_config(data['config_name'], data['config_desc'], data['config_full'],
                            data['config_url'], data['config_version'], media_list)
        await state.clear()
        await message.answer(f"✅ **Конфиг добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_config(data['config_name'], data['config_desc'], data['config_full'],
                            data['config_url'], data['config_version'], [])
        await state.clear()
        await message.answer(f"✅ **Конфиг добавлен!**\nID: {item_id}", parse_mode="Markdown",
                            reply_markup=get_main_keyboard(is_admin=True))
        return
    media_type = None
    media_id = None
    if message.photo:
        media_type = 'photo'
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = 'video'
        media_id = message.video.file_id
    elif message.animation:
        media_type = 'animation'
        media_id = message.animation.file_id
    else:
        await message.answer("❌ Отправь фото, видео, GIF, или **готово**/**пропустить**")
        return
    media_list.append({'type': media_type, 'id': media_id})
    await state.update_data(media_list=media_list)
    await message.answer(f"✅ Медиа добавлено! Всего: {len(media_list)}")

# ========== АДМИН: РЕДАКТИРОВАНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("edit_") and not c.data.startswith("edit_"))
async def edit_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    category = callback.data.replace("edit_", "")
    items = get_all_items(category)
    if not items:
        await callback.message.edit_text("📭 Нет элементов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]]))
        await callback.answer()
        return
    await callback.message.edit_text("✏️ **Выбери элемент для редактирования:**", parse_mode="Markdown",
                                     reply_markup=get_items_keyboard(items, category, "edit_select"))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_select_"))
async def edit_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    await state.update_data(edit_category=category, edit_item_id=item_id)
    await callback.message.edit_text("✏️ **Что изменить?**", parse_mode="Markdown",
                                     reply_markup=get_edit_fields_keyboard(category, item_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_name_") or c.data.startswith("edit_desc_") or 
                            c.data.startswith("edit_full_") or c.data.startswith("edit_version_") or
                            c.data.startswith("edit_url_") or c.data.startswith("edit_min_") or
                            c.data.startswith("edit_max_") or c.data.startswith("edit_author_"))
async def edit_field(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    action, category, item_id = callback.data.split("_", 2)
    field_map = {
        'edit_name': 'name', 'edit_desc': 'description', 'edit_full': 'full_description',
        'edit_version': 'version' if category != 'packs' else 'game_version',
        'edit_url': 'download_url', 'edit_min': 'min_version', 'edit_max': 'max_version', 'edit_author': 'author'
    }
    field = field_map.get(action)
    if not field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text("✏️ Введи новое значение:", parse_mode="Markdown")
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
    elif category == 'configs':
        update_config(item_id, field, message.text)
    await state.clear()
    await message.answer("✅ **Обновлено!**", parse_mode="Markdown", reply_markup=get_main_keyboard(is_admin=True))

# ========== АДМИН: МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith("media_"))
async def media_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    action, category, item_id = callback.data.split("_", 2)
    item_id = int(item_id)
    if action in ["media_photo", "media_video"]:
        media_type = "photo" if action == "media_photo" else "video"
        await state.update_data(media_action=media_type, media_category=category, media_item_id=item_id)
        await state.set_state(AdminStates.edit_value)
        await callback.message.edit_text(f"📸 Отправь {'фото' if media_type=='photo' else 'видео/GIF'}:", parse_mode="Markdown")
    elif action == "media_view":
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
    elif action == "media_del":
        item = get_item(category, item_id)
        if not item:
            await callback.answer("❌ Не найден", show_alert=True)
            return
        media_list = json.loads(item[4]) if item[4] else []
        if not media_list:
            await callback.answer("📭 Нет медиа", show_alert=True)
            return
        buttons = []
        for i, m in enumerate(media_list):
            mtype = "🖼️" if m['type'] == 'photo' else "🎬"
            buttons.append([InlineKeyboardButton(text=f"{mtype} Медиа {i+1}", callback_data=f"media_remove_{category}_{item_id}_{i}")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"media_{category}_{item_id}")])
        await callback.message.edit_text("🗑 **Выбери медиа для удаления:**", parse_mode="Markdown",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("media_remove_"))
async def media_remove(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    _, _, category, item_id, index = callback.data.split("_")
    item_id = int(item_id)
    index = int(index)
    if remove_media(category, item_id, index):
        await callback.answer("✅ Удалено!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)
    await media_menu(callback, state)

# ========== АДМИН: УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    category = callback.data.replace("delete_", "")
    items = get_all_items(category)
    if not items:
        await callback.message.edit_text("📭 Нет элементов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]]))
        await callback.answer()
        return
    await callback.message.edit_text("🗑 **Выбери элемент для удаления:**", parse_mode="Markdown",
                                     reply_markup=get_items_keyboard(items, category, "delete_confirm"))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_confirm_"))
async def delete_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    _, category, item_id = callback.data.split("_", 2)
    item_id = int(item_id)
    delete_item(category, item_id)
    await callback.message.edit_text(f"✅ **Элемент удален!**", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]]))
    await callback.answer()

# ========== АДМИН: СПИСОК ==========
@dp.callback_query(lambda c: c.data.startswith("list_"))
async def list_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    category = callback.data.replace("list_", "")
    items = get_all_items(category)
    if not items:
        text = "📭 Список пуст"
    else:
        text = "📋 **Список элементов:**\n\n"
        for item_id, name, desc, downloads in items[:20]:
            text += f"`{item_id}`. **{name}**\n   📥 {downloads}\n"
    await callback.message.edit_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]]))
    await callback.answer()

# ========== АДМИН: СТАТИСТИКА ==========
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
        text = (f"📊 **Статистика**\n\n🎮 Клиенты: {clients}\n🎨 Ресурспаки: {packs}\n⚙️ Конфиги: {configs}\n"
                f"📥 Всего скачиваний: {format_number(clients_d + packs_d + configs_d)}")
    except:
        text = "📊 **Статистика**\n\nОшибка получения данных"
    await callback.message.edit_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("="*50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())