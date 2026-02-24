import logging
import os
import asyncio
import math
import random
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '5809098591'))

if not BOT_TOKEN:
    raise ValueError("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
# ================================

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def init_db():
    """Создание всех таблиц"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    # Таблица клиентов (с JSON полем для медиа)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            media_json TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            version TEXT,
            downloads INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица ресурспаков (с JSON полем для медиа)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS resourcepacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            media_json TEXT DEFAULT '[]',
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
    
    # Таблица избранного
    cur.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            pack_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, pack_id),
            FOREIGN KEY (pack_id) REFERENCES resourcepacks(id) ON DELETE CASCADE
        )
    ''')
    
    # Таблица статистики скачиваний
    cur.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            user_id INTEGER,
            item_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица конфигов (с JSON полем для медиа)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            media_json TEXT DEFAULT '[]',
            download_url TEXT NOT NULL,
            game_version TEXT,
            downloads INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных успешно создана!")

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С МЕДИА ==========
def add_media_to_item(table: str, item_id: int, media_type: str, media_id: str) -> bool:
    """Добавить медиафайл к элементу"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        
        # Получаем текущий JSON
        cur.execute(f'SELECT media_json FROM {table} WHERE id = ?', (item_id,))
        result = cur.fetchone()
        
        if not result:
            return False
        
        media_list = json.loads(result[0]) if result[0] else []
        
        # Добавляем новый медиафайл
        media_list.append({
            'type': media_type,
            'id': media_id,
            'added_at': datetime.now().isoformat()
        })
        
        # Сохраняем обратно
        cur.execute(f'UPDATE {table} SET media_json = ? WHERE id = ?', 
                   (json.dumps(media_list), item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка при добавлении медиа: {e}")
        return False

def remove_media_from_item(table: str, item_id: int, media_index: int) -> bool:
    """Удалить медиафайл из элемента"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        
        cur.execute(f'SELECT media_json FROM {table} WHERE id = ?', (item_id,))
        result = cur.fetchone()
        
        if not result:
            return False
        
        media_list = json.loads(result[0]) if result[0] else []
        
        if 0 <= media_index < len(media_list):
            del media_list[media_index]
            
            cur.execute(f'UPDATE {table} SET media_json = ? WHERE id = ?', 
                       (json.dumps(media_list), item_id))
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False
    except Exception as e:
        logging.error(f"Ошибка при удалении медиа: {e}")
        return False

def get_item_media(table: str, item_id: int) -> List[Dict]:
    """Получить все медиафайлы элемента"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'SELECT media_json FROM {table} WHERE id = ?', (item_id,))
        result = cur.fetchone()
        conn.close()
        
        if result and result[0]:
            return json.loads(result[0])
        return []
    except Exception as e:
        logging.error(f"Ошибка при получении медиа: {e}")
        return []

def update_item_media(table: str, item_id: int, media_list: List[Dict]) -> bool:
    """Полностью обновить список медиа"""
    try:
        conn = sqlite3.connect('clients.db')
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET media_json = ? WHERE id = ?', 
                   (json.dumps(media_list), item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении медиа: {e}")
        return False

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ДЛЯ КЛИЕНТОВ ==========
def add_client(name: str, description: str, full_description: str, download_url: str, 
               media_list: List[Dict] = None, version: str = None):
    """Добавить нового клиента с медиа"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        INSERT INTO clients (name, description, full_description, download_url, media_json, version)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, description, full_description, download_url, media_json, version))
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

def update_client(client_id: int, name: str, description: str, full_description: str, 
                  download_url: str, media_list: List[Dict] = None, version: str = None):
    """Обновить клиента"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        UPDATE clients 
        SET name=?, description=?, full_description=?, download_url=?, media_json=?, version=?
        WHERE id=?
    ''', (name, description, full_description, download_url, media_json, version, client_id))
    conn.commit()
    conn.close()

def get_clients_by_version(version: str, sort_by: str = "popular"):
    """Получить клиенты по версии"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    query = 'SELECT id, name, description, media_json, downloads, views, version, created_at FROM clients'
    params = []
    
    if version != 'all':
        query += ' WHERE version = ?'
        params.append(version)
    
    if sort_by == "popular":
        query += " ORDER BY downloads DESC, views DESC"
    elif sort_by == "new":
        query += " ORDER BY created_at DESC"
    elif sort_by == "random":
        query += " ORDER BY RANDOM()"
    
    cur.execute(query, params)
    clients = cur.fetchall()
    conn.close()
    return clients

# ========== ФУНКЦИИ ДЛЯ РЕСУРСПАКОВ ==========
def add_resourcepack(name: str, description: str, full_description: str, download_url: str,
                    media_list: List[Dict], min_version: str, max_version: str, author: str = "Unknown"):
    """Добавить новый ресурспак с медиа"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        INSERT INTO resourcepacks 
        (name, description, full_description, download_url, media_json, min_version, max_version, author) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, description, full_description, download_url, media_json, min_version, max_version, author))
    conn.commit()
    pack_id = cur.lastrowid
    conn.close()
    return pack_id

def update_resourcepack(pack_id: int, name: str, description: str, full_description: str,
                       download_url: str, media_list: List[Dict], min_version: str, max_version: str, author: str):
    """Обновить ресурспак"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        UPDATE resourcepacks 
        SET name=?, description=?, full_description=?, download_url=?, 
            media_json=?, min_version=?, max_version=?, author=?
        WHERE id=?
    ''', (name, description, full_description, download_url, media_json, 
          min_version, max_version, author, pack_id))
    conn.commit()
    conn.close()

def get_resourcepacks_by_version(version: str, sort_by: str = "popular"):
    """Получить ресурспаки подходящие под версию"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    query = '''
        SELECT id, name, description, media_json, downloads, likes, views, 
               min_version, max_version, author, created_at 
        FROM resourcepacks 
        WHERE min_version <= ? AND max_version >= ?
    '''
    
    if sort_by == "popular":
        query += " ORDER BY downloads DESC, likes DESC"
    elif sort_by == "new":
        query += " ORDER BY created_at DESC"
    elif sort_by == "random":
        query += " ORDER BY RANDOM()"
    
    cur.execute(query, (version, version))
    packs = cur.fetchall()
    conn.close()
    return packs

def toggle_favorite(user_id: int, pack_id: int) -> bool:
    """Добавить/удалить из избранного"""
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

def get_favorites(user_id: int):
    """Получить избранное пользователя"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT r.id, r.name, r.description, r.media_json, r.downloads, r.likes 
        FROM resourcepacks r
        JOIN favorites f ON r.id = f.pack_id
        WHERE f.user_id = ?
        ORDER BY f.added_at DESC
    ''', (user_id,))
    favorites = cur.fetchall()
    conn.close()
    return favorites

# ========== ФУНКЦИИ ДЛЯ КОНФИГОВ ==========
def add_config(name: str, description: str, full_description: str, download_url: str,
               media_list: List[Dict] = None, game_version: str = None):
    """Добавить новый конфиг с медиа"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        INSERT INTO configs (name, description, full_description, download_url, media_json, game_version)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, description, full_description, download_url, media_json, game_version))
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

def update_config(config_id: int, name: str, description: str, full_description: str,
                  download_url: str, media_list: List[Dict] = None, game_version: str = None):
    """Обновить конфиг"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    media_json = json.dumps(media_list) if media_list else '[]'
    cur.execute('''
        UPDATE configs 
        SET name=?, description=?, full_description=?, download_url=?, media_json=?, game_version=?
        WHERE id=?
    ''', (name, description, full_description, download_url, media_json, game_version, config_id))
    conn.commit()
    conn.close()

def get_configs_by_version(version: str, sort_by: str = "popular"):
    """Получить конфиги по версии"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    query = 'SELECT id, name, description, media_json, downloads, views, game_version, created_at FROM configs'
    params = []
    
    if version != 'all':
        query += ' WHERE game_version = ?'
        params.append(version)
    
    if sort_by == "popular":
        query += " ORDER BY downloads DESC, views DESC"
    elif sort_by == "new":
        query += " ORDER BY created_at DESC"
    elif sort_by == "random":
        query += " ORDER BY RANDOM()"
    
    cur.execute(query, params)
    configs = cur.fetchall()
    conn.close()
    return configs

# ========== ОБЩИЕ ФУНКЦИИ ==========
def get_all_items(table: str):
    """Получить все элементы из таблицы"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'resourcepacks':
        cur.execute('SELECT id, name, description, media_json, downloads, likes, created_at FROM resourcepacks ORDER BY created_at DESC')
    elif table == 'clients':
        cur.execute('SELECT id, name, description, media_json, downloads, created_at FROM clients ORDER BY created_at DESC')
    elif table == 'configs':
        cur.execute('SELECT id, name, description, media_json, downloads, created_at FROM configs ORDER BY created_at DESC')
    
    items = cur.fetchall()
    conn.close()
    return items

def get_item(table: str, item_id: int):
    """Получить конкретный элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'resourcepacks':
        cur.execute('SELECT * FROM resourcepacks WHERE id = ?', (item_id,))
    elif table == 'clients':
        cur.execute('SELECT * FROM clients WHERE id = ?', (item_id,))
    elif table == 'configs':
        cur.execute('SELECT * FROM configs WHERE id = ?', (item_id,))
    
    item = cur.fetchone()
    conn.close()
    return item

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def increment_view(table: str, item_id: int):
    """Увеличить счетчик просмотров"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def increment_download(table: str, item_id: int, user_id: int = None):
    """Увеличить счетчик скачиваний"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
    if user_id:
        cur.execute('INSERT INTO downloads (user_id, item_id, item_type) VALUES (?, ?, ?)', 
                   (user_id, item_id, table))
    conn.commit()
    conn.close()

def get_all_versions(table: str) -> List[str]:
    """Получить все версии для таблицы"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'resourcepacks':
        cur.execute('SELECT DISTINCT min_version FROM resourcepacks UNION SELECT DISTINCT max_version FROM resourcepacks ORDER BY 1 DESC')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return sorted(set(versions), key=lambda x: [int(i) for i in x.split('.')], reverse=True)
    elif table == 'clients':
        cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL ORDER BY version DESC')
        return ['all'] + [v[0] for v in cur.fetchall() if v[0]]
    elif table == 'configs':
        cur.execute('SELECT DISTINCT game_version FROM configs WHERE game_version IS NOT NULL ORDER BY game_version DESC')
        return ['all'] + [v[0] for v in cur.fetchall() if v[0]]
    
    conn.close()
    return []

# Инициализация БД
init_db()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_number(num: int) -> str:
    """Форматирование больших чисел"""
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    else:
        return f"{num/1000000:.1f}M"

def parse_version(version: str) -> List[int]:
    """Преобразовать версию в список чисел"""
    try:
        return [int(x) for x in version.split('.')]
    except:
        return [0]

# ========== СОСТОЯНИЯ ==========
class BrowseStates(StatesGroup):
    browsing = State()
    version_selected = State()
    sort_selected = State()
    category = State()
    viewing_media = State()
    media_index = State()

class AdminStates(StatesGroup):
    choosing_category = State()
    choosing_action = State()
    waiting_for_item_id = State()
    
    # Для добавления клиента
    add_client_name = State()
    add_client_description = State()
    add_client_full_description = State()
    add_client_version = State()
    add_client_download_url = State()
    add_client_media = State()
    
    # Для добавления ресурспака
    add_pack_name = State()
    add_pack_description = State()
    add_pack_full_description = State()
    add_pack_min_version = State()
    add_pack_max_version = State()
    add_pack_author = State()
    add_pack_download_url = State()
    add_pack_media = State()
    
    # Для добавления конфига
    add_config_name = State()
    add_config_description = State()
    add_config_full_description = State()
    add_config_version = State()
    add_config_download_url = State()
    add_config_media = State()
    
    # Для редактирования
    edit_select_field = State()
    edit_new_value = State()
    edit_media_action = State()
    edit_media_index = State()
    edit_new_media = State()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin: bool = False):
    """Главная клавиатура"""
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты")],
        [types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="❤️ Мое избранное")],
        [types.KeyboardButton(text="⚙️ Конфиги")],
        [types.KeyboardButton(text="ℹ️ О боте")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_main_keyboard():
    """Главная клавиатура админ-панели"""
    buttons = [
        [InlineKeyboardButton(text="🎮 Управление клиентами", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Управление ресурспаками", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Управление конфигами", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_keyboard(category: str):
    """Клавиатура управления категорией"""
    category_names = {
        'clients': '🎮 Клиенты',
        'packs': '🎨 Ресурспаки',
        'configs': '⚙️ Конфиги'
    }
    
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить", callback_data=f"admin_add_{category}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_{category}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{category}")],
        [InlineKeyboardButton(text="📋 Список всех", callback_data=f"admin_list_{category}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_media_action_keyboard(category: str, item_id: int):
    """Клавиатура для управления медиа"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data=f"media_add_photo_{category}_{item_id}")],
        [InlineKeyboardButton(text="➕ Добавить видео/GIF", callback_data=f"media_add_video_{category}_{item_id}")],
        [InlineKeyboardButton(text="🖼️ Просмотр медиа", callback_data=f"media_view_{category}_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить медиа", callback_data=f"media_delete_{category}_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_edit_{category}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_media_navigation_keyboard(category: str, item_id: int, current_index: int, total_media: int):
    """Клавиатура для навигации по медиа"""
    buttons = []
    
    nav_row = []
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{category}_{item_id}_{current_index-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"{current_index+1}/{total_media}", callback_data="current_media"))
    
    if current_index < total_media - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{category}_{item_id}_{current_index+1}"))
    
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к управлению", callback_data=f"media_back_{category}_{item_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_media_delete_keyboard(category: str, item_id: int):
    """Клавиатура для выбора медиа для удаления"""
    media_list = get_item_media(category, item_id)
    buttons = []
    
    for i, media in enumerate(media_list[:10]):  # Показываем первые 10
        media_type = "🖼️" if media['type'] == 'photo' else "🎬"
        buttons.append([InlineKeyboardButton(
            text=f"{media_type} Медиа {i+1}", 
            callback_data=f"media_remove_{category}_{item_id}_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"media_back_{category}_{item_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== КЛАВИАТУРЫ ДЛЯ КЛИЕНТОВ ==========
def get_client_version_keyboard():
    """Клавиатура выбора версии для клиентов"""
    versions = get_all_versions('clients')
    if not versions or len(versions) == 1:
        return None
    
    buttons = []
    row = []
    for version in versions:
        display = "📌 Все версии" if version == 'all' else f"📌 {version}"
        row.append(InlineKeyboardButton(text=display, callback_data=f"client_ver_{version}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_client_sort_keyboard(version: str):
    """Клавиатура выбора сортировки для клиентов"""
    buttons = [
        [InlineKeyboardButton(text="🔥 Популярные", callback_data=f"client_sort_{version}_popular")],
        [InlineKeyboardButton(text="🆕 Новые", callback_data=f"client_sort_{version}_new")],
        [InlineKeyboardButton(text="🎲 Случайные", callback_data=f"client_sort_{version}_random")],
        [InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="back_to_client_versions")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_client_navigation_keyboard(client_id: int, current_index: int, total_packs: int, 
                                   version: str, sort: str, has_media: bool = False):
    """Клавиатура навигации по клиентам"""
    buttons = []
    
    action_row = [
        InlineKeyboardButton(text="📥 Скачать", callback_data=f"client_down_{client_id}")
    ]
    if has_media:
        action_row.append(InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"client_media_{client_id}"))
    buttons.append(action_row)
    
    nav_row = []
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"client_nav_{version}_{sort}_{current_index-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"{current_index+1}/{total_packs}", callback_data="current_page"))
    
    if current_index < total_packs - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"client_nav_{version}_{sort}_{current_index+1}"))
    
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к сортировке", callback_data=f"back_to_client_sort_{version}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Старт"""
    is_admin = (message.from_user.id == ADMIN_ID)
    
    await message.answer(
        f"👋 **Привет! Я бот-каталог для Minecraft**\n\n"
        f"🎮 Клиенты - моды и сборки с фото/видео\n"
        f"🎨 Ресурспаки - текстурпаки с галереей\n"
        f"❤️ Избранное - сохраняй понравившееся\n"
        f"⚙️ Конфиги - настройки с примерами\n\n"
        f"У каждого элемента может быть несколько фото и видео!\n\n"
        f"Используй кнопки ниже:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== РАЗДЕЛ КЛИЕНТОВ ==========
@dp.message(F.text == "🎮 Клиенты")
async def show_clients_menu(message: Message, state: FSMContext):
    """Показать меню выбора версии для клиентов"""
    keyboard = get_client_version_keyboard()
    
    if not keyboard:
        # Если нет выбора версий, показываем сразу все
        await state.update_data(client_version='all', client_sort='popular')
        await show_client(message, state, 0)
        return
    
    await state.set_state(BrowseStates.category)
    await state.update_data(category='clients')
    await message.answer(
        "🎮 **Выбери версию Minecraft:**\n\n"
        "Покажу все клиенты для этой версии",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith('client_ver_'))
async def process_client_version(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора версии для клиентов"""
    version = callback.data.replace('client_ver_', '')
    await state.update_data(client_version=version)
    
    keyboard = get_client_sort_keyboard(version)
    await callback.message.edit_text(
        f"🎮 **Версия {version if version != 'all' else 'все'}**\n\n"
        f"Как отсортировать клиенты?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('client_sort_'))
async def process_client_sort(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора сортировки для клиентов"""
    _, version, sort_type = callback.data.split('_', 2)
    
    await state.update_data(client_sort=sort_type, client_version=version)
    await show_client(callback.message, state, 0)
    await callback.answer()

async def show_client(message: Message, state: FSMContext, index: int):
    """Показать клиента по индексу"""
    data = await state.get_data()
    version = data.get('client_version', 'all')
    sort = data.get('client_sort', 'popular')
    
    clients = get_clients_by_version(version, sort)
    
    if not clients or index >= len(clients):
        await message.answer(
            f"❌ Клиенты не найдены",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_client_versions")]
            ])
        )
        return
    
    client = clients[index]
    client_id = client[0]
    
    # Увеличиваем просмотры
    increment_view('clients', client_id)
    
    # Получаем медиа
    media_list = json.loads(client[3]) if client[3] else []
    has_media = len(media_list) > 0
    
    text = (
        f"**{client[1]}**\n\n"
        f"*Версия:* {client[6]}\n"
        f"*Статистика:*\n"
        f"📥 Скачиваний: {format_number(client[4])}\n"
        f"👁 Просмотров: {format_number(client[5])}\n"
        f"🖼️ Медиа: {len(media_list)}\n\n"
        f"*Описание:* {client[2]}"
    )
    
    # Сохраняем список ID для навигации
    client_ids = [c[0] for c in clients]
    await state.update_data(client_ids=client_ids, client_index=index)
    
    keyboard = get_client_navigation_keyboard(
        client_id=client_id,
        current_index=index,
        total_packs=len(clients),
        version=version,
        sort=sort,
        has_media=has_media
    )
    
    # Если есть медиа, показываем первое
    if has_media and media_list[0]['type'] == 'photo':
        await message.answer_photo(
            photo=media_list[0]['id'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    elif has_media and media_list[0]['type'] in ['video', 'animation']:
        await message.answer_video(
            video=media_list[0]['id'],
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith('client_nav_'))
async def process_client_navigation(callback: CallbackQuery, state: FSMContext):
    """Навигация по клиентам"""
    _, version, sort, index = callback.data.split('_', 3)
    index = int(index)
    
    await state.update_data(client_version=version, client_sort=sort)
    await show_client(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('client_down_'))
async def process_client_download(callback: CallbackQuery):
    """Скачивание клиента"""
    client_id = int(callback.data.replace('client_down_', ''))
    client = get_item('clients', client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    increment_download('clients', client_id, callback.from_user.id)
    
    await callback.message.answer(
        f"📥 **Скачать {client[1]}**\n\n"
        f"[Нажми для скачивания]({client[5]})",
        parse_mode="Markdown"
    )
    await callback.answer("✅ Скачивание начато!")

@dp.callback_query(lambda c: c.data.startswith('client_media_'))
async def process_client_media(callback: CallbackQuery, state: FSMContext):
    """Просмотр медиа клиента"""
    client_id = int(callback.data.replace('client_media_', ''))
    client = get_item('clients', client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    media_list = json.loads(client[4]) if client[4] else []
    
    if not media_list:
        await callback.answer("❌ Нет медиафайлов", show_alert=True)
        return
    
    await state.update_data(
        media_category='clients',
        media_item_id=client_id,
        media_list=media_list,
        media_index=0
    )
    await state.set_state(BrowseStates.viewing_media)
    
    await show_media(callback.message, state, 0)
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'back_to_client_versions')
async def back_to_client_versions(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору версии клиентов"""
    keyboard = get_client_version_keyboard()
    if keyboard:
        await callback.message.edit_text(
            "🎮 **Выбери версию Minecraft:**",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await show_client(callback.message, state, 0)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('back_to_client_sort_'))
async def back_to_client_sort(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору сортировки клиентов"""
    version = callback.data.replace('back_to_client_sort_', '')
    keyboard = get_client_sort_keyboard(version)
    await callback.message.edit_text(
        f"🎮 **Версия {version if version != 'all' else 'все'}**\n\nКак отсортировать?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

# ========== ОБРАБОТЧИКИ ПРОСМОТРА МЕДИА ==========
async def show_media(message: Message, state: FSMContext, index: int):
    """Показать медиафайл по индексу"""
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if not media_list or index >= len(media_list):
        await message.answer("❌ Медиа не найдены")
        await state.clear()
        return
    
    media = media_list[index]
    total = len(media_list)
    
    await state.update_data(media_index=index)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{index-1}" if index > 0 else "noop"),
            InlineKeyboardButton(text=f"{index+1}/{total}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{index+1}" if index < total-1 else "noop")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="media_back_to_item")]
    ])
    
    if media['type'] == 'photo':
        await message.answer_photo(
            photo=media['id'],
            caption=f"📸 Медиа {index+1} из {total}",
            reply_markup=keyboard
        )
    elif media['type'] == 'video':
        await message.answer_video(
            video=media['id'],
            caption=f"🎬 Видео {index+1} из {total}",
            reply_markup=keyboard
        )
    elif media['type'] == 'animation':
        await message.answer_animation(
            animation=media['id'],
            caption=f"🎞️ GIF {index+1} из {total}",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith('media_nav_'))
async def process_media_navigation(callback: CallbackQuery, state: FSMContext):
    """Навигация по медиа"""
    index = int(callback.data.replace('media_nav_', ''))
    await show_media(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'media_back_to_item')
async def media_back_to_item(callback: CallbackQuery, state: FSMContext):
    """Назад к элементу"""
    data = await state.get_data()
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    
    await state.clear()
    
    if category == 'clients':
        await show_client(callback.message, state, 0)
    elif category == 'packs':
        await show_pack(callback.message, state, 0)
    elif category == 'configs':
        await show_config(callback.message, state, 0)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'noop')
async def noop(callback: CallbackQuery):
    """Заглушка для неактивных кнопок"""
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    """Главная админ панель"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    
    await message.answer(
        "⚙️ **Админ панель**\n\n"
        "Выбери категорию для управления:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )

@dp.callback_query(lambda c: c.data == 'admin_back')
async def admin_back(callback: CallbackQuery):
    """Назад в главное админ меню"""
    await callback.message.edit_text(
        "⚙️ **Админ панель**\n\n"
        "Выбери категорию:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_clients')
async def admin_clients(callback: CallbackQuery):
    """Управление клиентами"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎮 **Управление клиентами**\n\n"
        "Выбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard('clients')
    )
    await callback.answer()

# ========== АДМИН: УПРАВЛЕНИЕ МЕДИА ==========
@dp.callback_query(lambda c: c.data.startswith('admin_edit_'))
async def admin_edit_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace('admin_edit_', '')
    items = get_all_items(category)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет элементов для редактирования.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
            ])
        )
        await callback.answer()
        return
    
    # Сохраняем категорию и показываем список
    await state.update_data(edit_category=category)
    
    # Создаем клавиатуру со списком элементов
    buttons = []
    for item in items[:10]:
        item_id, name = item[0], item[1]
        buttons.append([InlineKeyboardButton(
            text=f"{item_id}. {name[:30]}", 
            callback_data=f"edit_select_{category}_{item_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
    
    await callback.message.edit_text(
        f"✏️ **Редактирование**\n\nВыбери элемент:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('edit_select_'))
async def admin_edit_select(callback: CallbackQuery, state: FSMContext):
    """Выбор элемента для редактирования"""
    _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Элемент не найден", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id)
    
    # Показываем меню редактирования
    buttons = [
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_name_{category}_{item_id}")],
        [InlineKeyboardButton(text="📄 Краткое описание", callback_data=f"edit_desc_{category}_{item_id}")],
        [InlineKeyboardButton(text="📚 Полное описание", callback_data=f"edit_full_{category}_{item_id}")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_url_{category}_{item_id}")],
        [InlineKeyboardButton(text="🖼️ Управление медиа", callback_data=f"edit_media_{category}_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]
    ]
    
    await callback.message.edit_text(
        f"✏️ **Редактирование:** {item[1]}\n\n"
        f"Что хочешь изменить?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('edit_media_'))
async def admin_edit_media(callback: CallbackQuery, state: FSMContext):
    """Управление медиа"""
    _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    media_list = get_item_media(category, item_id)
    
    await state.update_data(
        media_category=category,
        media_item_id=item_id,
        media_list=media_list
    )
    
    text = f"🖼️ **Управление медиа**\n\n"
    text += f"Всего медиафайлов: {len(media_list)}\n\n"
    
    keyboard = get_media_action_keyboard(category, item_id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('media_add_photo_'))
async def admin_add_photo(callback: CallbackQuery, state: FSMContext):
    """Добавление фото"""
    _, _, category, item_id = callback.data.split('_')
    
    await state.update_data(
        media_action='add_photo',
        media_category=category,
        media_item_id=int(item_id)
    )
    await state.set_state(AdminStates.edit_new_media)
    
    await callback.message.edit_text(
        "📸 **Отправь фото**\n\n"
        "Просто отправь фото, которое хочешь добавить.",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('media_add_video_'))
async def admin_add_video(callback: CallbackQuery, state: FSMContext):
    """Добавление видео/GIF"""
    _, _, category, item_id = callback.data.split('_')
    
    await state.update_data(
        media_action='add_video',
        media_category=category,
        media_item_id=int(item_id)
    )
    await state.set_state(AdminStates.edit_new_media)
    
    await callback.message.edit_text(
        "🎬 **Отправь видео или GIF**\n\n"
        "Можно отправить видео или анимацию.",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('media_view_'))
async def admin_view_media(callback: CallbackQuery, state: FSMContext):
    """Просмотр медиа"""
    _, _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    media_list = get_item_media(category, item_id)
    
    if not media_list:
        await callback.answer("❌ Нет медиафайлов", show_alert=True)
        return
    
    await state.update_data(
        media_category=category,
        media_item_id=item_id,
        media_list=media_list,
        media_index=0
    )
    
    await show_media_admin(callback.message, state, 0)
    await callback.answer()

async def show_media_admin(message: Message, state: FSMContext, index: int):
    """Показать медиа для админа"""
    data = await state.get_data()
    media_list = data.get('media_list', [])
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    
    if not media_list or index >= len(media_list):
        await message.answer("❌ Медиа не найдены")
        return
    
    media = media_list[index]
    total = len(media_list)
    
    await state.update_data(media_index=index)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️", callback_data=f"admin_media_nav_{index-1}" if index > 0 else "noop"),
            InlineKeyboardButton(text=f"{index+1}/{total}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"admin_media_nav_{index+1}" if index < total-1 else "noop")
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"media_remove_{category}_{item_id}_{index}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_media_{category}_{item_id}")]
    ])
    
    if media['type'] == 'photo':
        await message.answer_photo(
            photo=media['id'],
            caption=f"📸 Медиа {index+1} из {total}",
            reply_markup=keyboard
        )
    elif media['type'] == 'video':
        await message.answer_video(
            video=media['id'],
            caption=f"🎬 Видео {index+1} из {total}",
            reply_markup=keyboard
        )
    elif media['type'] == 'animation':
        await message.answer_animation(
            animation=media['id'],
            caption=f"🎞️ GIF {index+1} из {total}",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith('admin_media_nav_'))
async def admin_media_navigation(callback: CallbackQuery, state: FSMContext):
    """Навигация по медиа в админке"""
    index = int(callback.data.replace('admin_media_nav_', ''))
    await show_media_admin(callback.message, state, index)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('media_delete_'))
async def admin_media_delete(callback: CallbackQuery, state: FSMContext):
    """Меню удаления медиа"""
    _, _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    keyboard = get_media_delete_keyboard(category, item_id)
    await callback.message.edit_text(
        "🗑 **Выбери медиа для удаления:**",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('media_remove_'))
async def admin_media_remove(callback: CallbackQuery, state: FSMContext):
    """Удаление конкретного медиа"""
    _, _, category, item_id, index = callback.data.split('_')
    item_id = int(item_id)
    index = int(index)
    
    if remove_media_from_item(category, item_id, index):
        await callback.answer("✅ Медиа удалено!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)
    
    # Возвращаемся к управлению медиа
    await admin_edit_media(callback, state)

@dp.callback_query(lambda c: c.data.startswith('media_back_'))
async def admin_media_back(callback: CallbackQuery, state: FSMContext):
    """Назад к управлению медиа"""
    _, _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    await admin_edit_media(callback, state)

@dp.message(AdminStates.edit_new_media)
async def admin_add_media_file(message: Message, state: FSMContext):
    """Добавление нового медиафайла"""
    data = await state.get_data()
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    action = data.get('media_action')
    
    media_type = None
    media_id = None
    
    if action == 'add_photo' and message.photo:
        media_type = 'photo'
        media_id = message.photo[-1].file_id
    elif action == 'add_video' and message.video:
        media_type = 'video'
        media_id = message.video.file_id
    elif action == 'add_video' and message.animation:
        media_type = 'animation'
        media_id = message.animation.file_id
    else:
        await message.answer("❌ Отправь правильный тип файла (фото, видео или GIF)")
        return
    
    if add_media_to_item(category, item_id, media_type, media_id):
        await message.answer(
            "✅ Медиафайл успешно добавлен!",
            reply_markup=get_main_keyboard(is_admin=True)
        )
    else:
        await message.answer(
            "❌ Ошибка при добавлении медиа",
            reply_markup=get_main_keyboard(is_admin=True)
        )
    
    await state.clear()

# ========== ЗАПУСК ==========
async def main():
    """Запуск бота"""
    logging.info("Запуск бота...")
    
    print("=" * 50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("📁 База данных подключена")
    print("=" * 50)
    print("📌 Новые функции:")
    print("   • Множественные фото/видео/GIF")
    print("   • Галерея с навигацией")
    print("   • Добавление медиа к существующим записям")
    print("   • Удаление отдельных медиафайлов")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())