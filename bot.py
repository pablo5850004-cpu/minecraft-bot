import logging
import os
import asyncio
import json
import sqlite3
import random
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

# ========== ИСПРАВЛЕННАЯ БАЗА ДАННЫХ ==========
def init_db():
    """Создание всех таблиц с обработкой ошибок"""
    db_path = 'clients.db'
    
    # Если файл БД повреждён - удаляем его и создаём новый
    if os.path.exists(db_path):
        try:
            # Пробуем открыть БД для проверки
            test_conn = sqlite3.connect(db_path)
            test_cur = test_conn.cursor()
            test_cur.execute("SELECT 1")
            test_conn.close()
            print("✅ Существующая БД в порядке")
        except sqlite3.DatabaseError:
            print("⚠️ База данных повреждена, создаём новую...")
            os.remove(db_path)
    
    # Создаём новую БД
    conn = sqlite3.connect(db_path)
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
    print("✅ База данных успешно создана!")

# Инициализируем БД при запуске
init_db()

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ==========
def get_item(table: str, item_id: int) -> Optional[Tuple]:
    """Получить элемент по ID"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
        item = cur.fetchone()
        conn.close()
        return item
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_item, пересоздаём...")
        init_db()
        return None

def get_all_items(table: str) -> List[Tuple]:
    """Получить все элементы"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'SELECT id, name, description, downloads FROM {table} ORDER BY created_at DESC')
        items = cur.fetchall()
        conn.close()
        return items
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_all_items, пересоздаём...")
        init_db()
        return []

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в delete_item")
        init_db()

# Клиенты
def add_client(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    try:
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в add_client")
        init_db()
        return None

def update_client(item_id: int, field: str, value: str):
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в update_client")
        init_db()

def get_clients_by_version(version: str = 'all') -> List[Tuple]:
    """Получить клиентов по версии"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        if version == 'all':
            cur.execute('SELECT id, name, description, media, downloads, views, version FROM clients ORDER BY downloads DESC')
        else:
            cur.execute('SELECT id, name, description, media, downloads, views, version FROM clients WHERE version = ? ORDER BY downloads DESC', (version,))
        items = cur.fetchall()
        conn.close()
        return items
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_clients_by_version")
        init_db()
        return []

def get_client_versions() -> List[str]:
    """Получить все версии клиентов"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_client_versions")
        init_db()
        return []

# Ресурспаки
def add_pack(name: str, desc: str, full: str, url: str, min_v: str, max_v: str, author: str, media: List[Dict] = None):
    try:
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в add_pack")
        init_db()
        return None

def update_pack(item_id: int, field: str, value: str):
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в update_pack")
        init_db()

def get_packs_by_version(version: str, sort: str = 'popular') -> List[Tuple]:
    """Получить ресурспаки подходящие под версию"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        
        # Преобразуем версию в число для сравнения
        try:
            v_num = float(version)
        except:
            v_num = 0
        
        # Ищем паки, где версия входит в диапазон
        cur.execute('''
            SELECT id, name, description, media, downloads, likes, views, min_version, max_version, author 
            FROM resourcepacks 
            WHERE CAST(min_version AS FLOAT) <= ? AND CAST(max_version AS FLOAT) >= ?
        ''', (v_num, v_num))
        
        packs = cur.fetchall()
        
        # Сортируем
        if sort == 'popular':
            packs.sort(key=lambda x: x[4], reverse=True)  # по downloads
        elif sort == 'likes':
            packs.sort(key=lambda x: x[5], reverse=True)  # по likes
        elif sort == 'random':
            random.shuffle(packs)
        
        conn.close()
        return packs
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_packs_by_version")
        init_db()
        return []

def get_pack_versions() -> List[str]:
    """Получить все доступные версии"""
    try:
        conn = sqlite3.connect('clients.db')
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_pack_versions")
        init_db()
        return []

def toggle_favorite(user_id: int, pack_id: int) -> bool:
    """Добавить/удалить из избранного"""
    try:
        conn = sqlite3.connect('clients.db')
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в toggle_favorite")
        init_db()
        return False

def get_favorites(user_id: int) -> List[Tuple]:
    """Получить избранное пользователя"""
    try:
        conn = sqlite3.connect('clients.db')
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_favorites")
        init_db()
        return []

# Конфиги
def add_config(name: str, desc: str, full: str, url: str, version: str, media: List[Dict] = None):
    try:
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
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в add_config")
        init_db()
        return None

def update_config(item_id: int, field: str, value: str):
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в update_config")
        init_db()

def get_configs_by_version(version: str = 'all') -> List[Tuple]:
    """Получить конфиги по версии"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        if version == 'all':
            cur.execute('SELECT id, name, description, media, downloads, views, game_version FROM configs ORDER BY downloads DESC')
        else:
            cur.execute('SELECT id, name, description, media, downloads, views, game_version FROM configs WHERE game_version = ? ORDER BY downloads DESC', (version,))
        items = cur.fetchall()
        conn.close()
        return items
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_configs_by_version")
        init_db()
        return []

def get_config_versions() -> List[str]:
    """Получить все версии конфигов"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT game_version FROM configs WHERE game_version IS NOT NULL')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в get_config_versions")
        init_db()
        return []

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

# Просмотры и скачивания
def increment_view(table: str, item_id: int):
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в increment_view")
        init_db()

def increment_download(table: str, item_id: int):
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except sqlite3.DatabaseError:
        print(f"⚠️ Ошибка БД в increment_download")
        init_db()

# ========== СОСТОЯНИЯ ==========
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

class BrowseStates(StatesGroup):
    viewing = State()
    media_view = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_number(num: int) -> str:
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    else:
        return f"{num/1000000:.1f}M"

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

# ========== ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ - КЛИЕНТЫ ==========
@dp.message(F.text == "🎮 Клиенты")
async def clients_menu(message: Message, state: FSMContext):
    versions = get_client_versions()
    
    if not versions:
        # Если нет версий, показываем все клиенты
        await state.update_data(client_version='all')
        await show_next_client(message, state, 0, 'clients')
        return
    
    # Показываем клавиатуру выбора версии
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
    
    await message.answer(
        "🎮 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

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
    
    # Увеличиваем просмотры
    increment_view('clients', client_id)
    
    # Получаем медиа
    try:
        media_list = json.loads(client[3]) if client[3] else []
    except:
        media_list = []
    
    text = (
        f"**{client[1]}**\n\n"
        f"{client[2]}\n\n"
        f"*Версия:* {client[6]}\n"
        f"📥 Скачиваний: {format_number(client[4])}\n"
        f"👁 Просмотров: {format_number(client[5])}"
    )
    
    # Кнопки навигации
    buttons = []
    
    # Кнопка скачивания
    buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_clients_{client_id}")])
    
    # Кнопка медиа если есть
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_clients_{client_id}")])
    
    # Навигация
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_clients_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(clients)}", callback_data="noop"))
    if index < len(clients) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_clients_{index+1}"))
    buttons.append(nav_row)
    
    # Кнопка назад
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_client_versions")])
    
    # Сохраняем состояние
    await state.update_data(client_index=index, client_list=[c[0] for c in clients])
    
    # Отправляем
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(
            photo=media_list[0]['id'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

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
    
    await callback.message.edit_text(
        "🎮 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

# ========== ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ - РЕСУРСПАКИ ==========
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
    
    await message.answer(
        "🎨 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(lambda c: c.data.startswith("pack_ver_"))
async def pack_version_selected(callback: CallbackQuery, state: FSMContext):
    version = callback.data.replace("pack_ver_", "")
    
    # Показываем меню сортировки
    buttons = [
        [InlineKeyboardButton(text="🔥 Популярные", callback_data=f"pack_sort_{version}_popular")],
        [InlineKeyboardButton(text="❤️ По лайкам", callback_data=f"pack_sort_{version}_likes")],
        [InlineKeyboardButton(text="🎲 Случайные", callback_data=f"pack_sort_{version}_random")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_pack_versions")]
    ]
    
    await callback.message.edit_text(
        f"🎨 **Версия {version}**\n\nКак отсортировать?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
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
    
    # Увеличиваем просмотры
    increment_view('resourcepacks', pack_id)
    
    # Проверяем в избранном
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute('SELECT * FROM favorites WHERE user_id = ? AND pack_id = ?', (message.chat.id, pack_id))
        is_fav = cur.fetchone() is not None
        conn.close()
    except:
        is_fav = False
    
    # Получаем медиа
    try:
        media_list = json.loads(pack[3]) if pack[3] else []
    except:
        media_list = []
    
    text = (
        f"**{pack[1]}**\n\n"
        f"{pack[2]}\n\n"
        f"*Автор:* {pack[9]}\n"
        f"*Версии:* {pack[7]} - {pack[8]}\n"
        f"📥 Скачиваний: {format_number(pack[4])}\n"
        f"❤️ В избранном: {format_number(pack[5])}\n"
        f"👁 Просмотров: {format_number(pack[6])}"
    )
    
    # Кнопки
    buttons = []
    
    # Кнопки действий
    action_row = [
        InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_packs_{pack_id}")
    ]
    if is_fav:
        action_row.append(InlineKeyboardButton(text="❤️ В избранном", callback_data=f"fav_packs_{pack_id}"))
    else:
        action_row.append(InlineKeyboardButton(text="🤍 В избранное", callback_data=f"fav_packs_{pack_id}"))
    buttons.append(action_row)
    
    # Кнопка медиа
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_packs_{pack_id}")])
    
    # Навигация
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_packs_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(packs)}", callback_data="noop"))
    if index < len(packs) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_packs_{index+1}"))
    buttons.append(nav_row)
    
    # Кнопка назад к версиям
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_pack_versions")])
    
    # Сохраняем состояние
    await state.update_data(pack_index=index, pack_list=[p[0] for p in packs])
    
    # Отправляем
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(
            photo=media_list[0]['id'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

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
    
    if added:
        await callback.answer("❤️ Добавлено в избранное!")
    else:
        await callback.answer("💔 Удалено из избранного")
    
    # Обновляем отображение
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
    
    await callback.message.edit_text(
        "🎨 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

# ========== ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ - КОНФИГИ ==========
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
    
    await message.answer(
        "⚙️ **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

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
    
    # Увеличиваем просмотры
    increment_view('configs', config_id)
    
    # Получаем медиа
    try:
        media_list = json.loads(config[3]) if config[3] else []
    except:
        media_list = []
    
    text = (
        f"**{config[1]}**\n\n"
        f"{config[2]}\n\n"
        f"*Версия:* {config[6]}\n"
        f"📥 Скачиваний: {format_number(config[4])}\n"
        f"👁 Просмотров: {format_number(config[5])}"
    )
    
    # Кнопки
    buttons = []
    
    # Кнопка скачивания
    buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_configs_{config_id}")])
    
    # Кнопка медиа если есть
    if media_list:
        buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_configs_{config_id}")])
    
    # Навигация
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_configs_{index-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{index+1}/{len(configs)}", callback_data="noop"))
    if index < len(configs) - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_configs_{index+1}"))
    buttons.append(nav_row)
    
    # Кнопка назад к версиям
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_config_versions")])
    
    # Сохраняем состояние
    await state.update_data(config_index=index, config_list=[c[0] for c in configs])
    
    # Отправляем
    if media_list and media_list[0]['type'] == 'photo':
        await message.answer_photo(
            photo=media_list[0]['id'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

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
    
    await callback.message.edit_text(
        "⚙️ **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

# ========== ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ - ИЗБРАННОЕ ==========
@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    
    if not favs:
        await message.answer(
            "❤️ **Избранное пусто**\n\n"
            "Добавляй ресурспаки в избранное кнопкой '🤍 В избранное'",
            parse_mode="Markdown"
        )
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
    
    # Увеличиваем счетчик скачиваний
    increment_download(table, item_id)
    
    # Отправляем ссылку
    if table == 'resourcepacks':
        url = item[5]  # download_url
        name = item[1]
    elif table == 'clients':
        url = item[5]  # download_url
        name = item[1]
    else:  # configs
        url = item[5]  # download_url
        name = item[1]
    
    await callback.message.answer(
        f"📥 **Скачать {name}**\n\n"
        f"[Нажми для скачивания]({url})",
        parse_mode="Markdown"
    )
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
        media_list = json.loads(item[4]) if item[4] else []  # media поле
    except:
        media_list = []
    
    if not media_list:
        await callback.answer("📭 Нет медиа", show_alert=True)
        return
    
    await state.update_data(
        media_list=media_list,
        media_index=0,
        media_table=table,
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
    
    # Возвращаемся к просмотру элемента
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
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

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
    
    try:
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
        
        await message.answer(
            "ℹ️ **О боте**\n\n"
            f"📊 **Статистика:**\n"
            f"🎮 Клиентов: {clients}\n"
            f"🎨 Ресурспаков: {packs}\n"
            f"⚙️ Конфигов: {configs}\n"
            f"📥 Всего скачиваний: {format_number(clients_d + packs_d + configs_d)}\n\n"
            "Версия: 3.1\n"
            "Разработчик: @pablo5850004",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin)
        )
    except:
        await message.answer(
            "ℹ️ **О боте**\n\n"
            "Версия: 3.1\n"
            "Разработчик: @pablo5850004",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin)
        )

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("="*50)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())