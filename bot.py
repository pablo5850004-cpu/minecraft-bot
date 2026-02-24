import logging
import os
import asyncio
import json
import sqlite3
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
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Создание всех таблиц"""
    conn = sqlite3.connect('clients.db')
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

init_db()

# ========== СОСТОЯНИЯ ДЛЯ FSM ==========
class AdminStates(StatesGroup):
    # Для клиентов
    client_name = State()
    client_desc = State()
    client_full = State()
    client_version = State()
    client_url = State()
    client_media = State()
    
    # Для ресурспаков
    pack_name = State()
    pack_desc = State()
    pack_full = State()
    pack_min = State()
    pack_max = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    
    # Для конфигов
    config_name = State()
    config_desc = State()
    config_full = State()
    config_version = State()
    config_url = State()
    config_media = State()
    
    # Для редактирования
    edit_field = State()
    edit_value = State()

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ==========
def get_item(table: str, item_id: int) -> Optional[Tuple]:
    """Получить элемент по ID"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
    item = cur.fetchone()
    conn.close()
    return item

def get_all_items(table: str) -> List[Tuple]:
    """Получить все элементы"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, description, downloads FROM {table} ORDER BY created_at DESC')
    items = cur.fetchall()
    conn.close()
    return items

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

# Клиенты
def add_client(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    conn = sqlite3.connect('clients.db')
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

def update_client(item_id: int, field: str, value: str):
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

# Ресурспаки
def add_pack(name: str, desc: str, full: str, url: str, min_v: str, max_v: str, author: str, media: List[Dict] = None):
    conn = sqlite3.connect('clients.db')
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

def update_pack(item_id: int, field: str, value: str):
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

# Конфиги
def add_config(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    conn = sqlite3.connect('clients.db')
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

def update_config(item_id: int, field: str, value: str):
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()

# Медиа
def add_media(table: str, item_id: int, media_type: str, media_id: str) -> bool:
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'SELECT media FROM {table} WHERE id = ?', (item_id,))
        result = cur.fetchone()
        if not result:
            return False
        
        media_list = json.loads(result[0]) if result[0] else []
        media_list.append({
            'type': media_type,
            'id': media_id,
            'added_at': datetime.now().isoformat()
        })
        
        cur.execute(f'UPDATE {table} SET media = ? WHERE id = ?', (json.dumps(media_list), item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка добавления медиа: {e}")
        return False

def remove_media(table: str, item_id: int, index: int) -> bool:
    try:
        conn = sqlite3.connect('clients.db')
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
    except Exception as e:
        logging.error(f"Ошибка удаления медиа: {e}")
        return False

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
        "ℹ️ **О боте**\n\n"
        "Версия: 3.0\n"
        "Разработчик: @pablo5850004\n\n"
        "Функции:\n"
        "• Полное управление контентом\n"
        "• Медиа-галерея (фото/видео/GIF)\n"
        "• Статистика скачиваний\n"
        "• Избранное для ресурспаков",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
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
    await callback.message.edit_text(
        f"{title}\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard(cat)
    )
    await callback.answer()

# ========== ДОБАВЛЕНИЕ ==========
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

# Клиент: название
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
    await message.answer(
        "🖼️ **Добавь медиа** (фото/видео/GIF)\n\n"
        "Отправляй файлы по одному.\n"
        "Когда закончишь, напиши **готово**\n"
        "Или **пропустить** чтобы продолжить без медиа:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.client_media)
async def client_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_client(
            name=data['client_name'],
            desc=data['client_desc'],
            full=data['client_full'],
            url=data['client_url'],
            version=data['client_version'],
            media=media_list
        )
        await state.clear()
        await message.answer(
            f"✅ **Клиент добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_client(
            name=data['client_name'],
            desc=data['client_desc'],
            full=data['client_full'],
            url=data['client_url'],
            version=data['client_version'],
            media=[]
        )
        await state.clear()
        await message.answer(
            f"✅ **Клиент добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
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
    await message.answer(f"✅ Медиа добавлено! Всего: {len(media_list)}. Можешь добавить ещё.")

# Ресурспак: название
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
    await message.answer(
        "🖼️ **Добавь медиа** (фото/видео/GIF)\n\n"
        "Отправляй файлы по одному.\n"
        "Когда закончишь, напиши **готово**\n"
        "Или **пропустить**:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.pack_media)
async def pack_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_pack(
            name=data['pack_name'],
            desc=data['pack_desc'],
            full=data['pack_full'],
            url=data['pack_url'],
            min_v=data['pack_min'],
            max_v=data['pack_max'],
            author=data['pack_author'],
            media=media_list
        )
        await state.clear()
        await message.answer(
            f"✅ **Ресурспак добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_pack(
            name=data['pack_name'],
            desc=data['pack_desc'],
            full=data['pack_full'],
            url=data['pack_url'],
            min_v=data['pack_min'],
            max_v=data['pack_max'],
            author=data['pack_author'],
            media=[]
        )
        await state.clear()
        await message.answer(
            f"✅ **Ресурспак добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
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

# Конфиг: название
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
    await message.answer(
        "🖼️ **Добавь медиа** (фото/видео/GIF)\n\n"
        "Отправляй файлы по одному.\n"
        "Когда закончишь, напиши **готово**\n"
        "Или **пропустить**:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        item_id = add_config(
            name=data['config_name'],
            desc=data['config_desc'],
            full=data['config_full'],
            url=data['config_url'],
            version=data['config_version'],
            media=media_list
        )
        await state.clear()
        await message.answer(
            f"✅ **Конфиг добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        return
    
    if message.text and message.text.lower() == 'пропустить':
        item_id = add_config(
            name=data['config_name'],
            desc=data['config_desc'],
            full=data['config_full'],
            url=data['config_url'],
            version=data['config_version'],
            media=[]
        )
        await state.clear()
        await message.answer(
            f"✅ **Конфиг добавлен!**\nID: {item_id}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
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

# ========== РЕДАКТИРОВАНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("edit_") and not c.data.startswith("edit_"))
async def edit_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace("edit_", "")
    items = get_all_items(category)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет элементов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "✏️ **Выбери элемент для редактирования:**",
        parse_mode="Markdown",
        reply_markup=get_items_keyboard(items, category, "edit_select")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_select_"))
async def edit_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    
    await state.update_data(edit_category=category, edit_item_id=item_id)
    
    await callback.message.edit_text(
        f"✏️ **Что изменить?**",
        parse_mode="Markdown",
        reply_markup=get_edit_fields_keyboard(category, item_id)
    )
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
        'edit_name': 'name',
        'edit_desc': 'description',
        'edit_full': 'full_description',
        'edit_version': 'version' if category != 'packs' else 'game_version',
        'edit_url': 'download_url',
        'edit_min': 'min_version',
        'edit_max': 'max_version',
        'edit_author': 'author'
    }
    
    field = field_map.get(action)
    if not field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.edit_value)
    await callback.message.edit_text(f"✏️ Введи новое значение:", parse_mode="Markdown")
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
    await message.answer(
        "✅ **Обновлено!**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin=True)
    )

# ========== МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith("media_"))
async def media_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    action, category, item_id = callback.data.split("_", 2)
    item_id = int(item_id)
    
    if action == "media_photo" or action == "media_video":
        media_type = "photo" if action == "media_photo" else "video"
        await state.update_data(
            media_action=media_type,
            media_category=category,
            media_item_id=item_id
        )
        await state.set_state(AdminStates.edit_value)
        await callback.message.edit_text(
            f"📸 Отправь {'фото' if media_type=='photo' else 'видео/GIF'}:",
            parse_mode="Markdown"
        )
    
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
        for i, media in enumerate(media_list):
            media_type = "🖼️" if media['type'] == 'photo' else "🎬"
            buttons.append([InlineKeyboardButton(
                text=f"{media_type} Медиа {i+1}",
                callback_data=f"media_remove_{category}_{item_id}_{i}"
            )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"media_{category}_{item_id}")])
        
        await callback.message.edit_text(
            "🗑 **Выбери медиа для удаления:**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
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
    
    # Возвращаемся в меню медиа
    await media_menu(callback, state)

async def show_media(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    media_list = data['media_list']
    category = data['media_category']
    item_id = data['media_item_id']
    
    if index >= len(media_list):
        index = 0
    
    media = media_list[index]
    
    buttons = [
        [
            InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{index-1}" if index > 0 else "noop"),
            InlineKeyboardButton(text=f"{index+1}/{len(media_list)}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{index+1}" if index < len(media_list)-1 else "noop")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"media_{category}_{item_id}")]
    ]
    
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

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_nav(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.replace("media_nav_", ""))
    await show_media(callback.message, state, index)
    await callback.answer()

# ========== УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_category(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace("delete_", "")
    items = get_all_items(category)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет элементов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑 **Выбери элемент для удаления:**",
        parse_mode="Markdown",
        reply_markup=get_items_keyboard(items, category, "delete_confirm")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_confirm_"))
async def delete_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    _, category, item_id = callback.data.split("_", 2)
    item_id = int(item_id)
    
    delete_item(category, item_id)
    
    await callback.message.edit_text(
        f"✅ **Элемент удален!**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
        ])
    )
    await callback.answer()

# ========== СПИСОК ==========
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
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
        ])
    )
    await callback.answer()

# ========== СТАТИСТИКА ==========
@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    conn = sqlite3.connect('clients.db')
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
    
    text = (
        "📊 **Статистика**\n\n"
        f"🎮 Клиенты: {clients}\n"
        f"🎨 Ресурспаки: {packs}\n"
        f"⚙️ Конфиги: {configs}\n"
        f"📥 Всего скачиваний: {clients_d + packs_d + configs_d}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
    )
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