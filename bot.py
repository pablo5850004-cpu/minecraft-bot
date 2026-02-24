import logging
import os
import asyncio
import math
import sqlite3
from typing import Optional, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
# Bot-T сам подставит эти значения из настроек бота
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен берется из переменных окружения
ADMIN_ID = int(os.getenv('ADMIN_ID', '5809098591'))  # ID админа тоже из переменных

# Проверяем, что токен получен
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
    """Создание всех таблиц с правильной структурой"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    # Удаляем старые таблицы если они есть
    cur.execute('DROP TABLE IF EXISTS clients')
    cur.execute('DROP TABLE IF EXISTS resourcepacks')
    cur.execute('DROP TABLE IF EXISTS configs')
    
    # Таблица клиентов
    cur.execute('''
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            file_name TEXT,
            file_path TEXT,
            version TEXT,
            file_size INTEGER DEFAULT 0,
            download_url TEXT,
            download_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица ресурспаков
    cur.execute('''
        CREATE TABLE resourcepacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            file_name TEXT,
            file_path TEXT,
            version TEXT,
            file_size INTEGER DEFAULT 0,
            download_url TEXT,
            download_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица конфигов
    cur.execute('''
        CREATE TABLE configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            full_description TEXT NOT NULL,
            file_name TEXT,
            file_path TEXT,
            game_version TEXT,
            file_size INTEGER DEFAULT 0,
            download_url TEXT,
            download_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных успешно создана!")

def get_all_items(table: str):
    """Получить все элементы"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'configs':
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, game_version, file_size, download_url, download_count FROM {table} ORDER BY created_at DESC')
    else:
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, version, file_size, download_url, download_count FROM {table} ORDER BY created_at DESC')
    
    items = cur.fetchall()
    conn.close()
    return items

def get_item(table: str, item_id: int):
    """Получить конкретный элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'configs':
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, game_version, file_size, download_url, download_count FROM {table} WHERE id = ?', (item_id,))
    else:
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, version, file_size, download_url, download_count FROM {table} WHERE id = ?', (item_id,))
    
    item = cur.fetchone()
    conn.close()
    return item

def add_item_with_link(table: str, name: str, description: str, full_description: str, link: str, version: Optional[str] = None):
    """Добавить элемент по внешней ссылке"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'configs':
        cur.execute(
            f'INSERT INTO {table} (name, description, full_description, file_name, download_url, game_version, file_size) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (name, description, full_description, "external_link", link, version, 0)
        )
    else:
        cur.execute(
            f'INSERT INTO {table} (name, description, full_description, file_name, download_url, version, file_size) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (name, description, full_description, "external_link", link, version, 0)
        )
    
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

def add_item_with_file(table: str, name: str, description: str, full_description: str, file_name: str, file_path: str, file_size: int, version: Optional[str] = None):
    """Добавить элемент с локальным файлом"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'configs':
        cur.execute(
            f'INSERT INTO {table} (name, description, full_description, file_name, file_path, game_version, file_size, download_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (name, description, full_description, file_name, file_path, version, file_size, "local_file")
        )
    else:
        cur.execute(
            f'INSERT INTO {table} (name, description, full_description, file_name, file_path, version, file_size, download_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (name, description, full_description, file_name, file_path, version, file_size, "local_file")
        )
    
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id

def update_item(table: str, item_id: int, name: str, description: str, full_description: str, version: Optional[str] = None):
    """Обновить элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    if table == 'configs':
        cur.execute(
            f'UPDATE {table} SET name=?, description=?, full_description=?, game_version=? WHERE id=?',
            (name, description, full_description, version, item_id)
        )
    else:
        cur.execute(
            f'UPDATE {table} SET name=?, description=?, full_description=?, version=? WHERE id=?',
            (name, description, full_description, version, item_id)
        )
    
    conn.commit()
    conn.close()

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    # Сначала получаем информацию о файле
    item = get_item(table, item_id)
    if item and item[5] and os.path.exists(item[5]) and item[4] != "external_link":
        try:
            os.remove(item[5])
        except:
            pass
    
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def increment_download_count(table: str, item_id: int):
    """Увеличить счетчик скачиваний"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'UPDATE {table} SET download_count = download_count + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def get_versions(table: str) -> List[str]:
    """Получить все версии"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    version_col = 'version' if table != 'configs' else 'game_version'
    cur.execute(f'SELECT DISTINCT {version_col} FROM {table} WHERE {version_col} IS NOT NULL ORDER BY {version_col} DESC')
    versions = [v[0] for v in cur.fetchall() if v[0]]
    conn.close()
    return versions

def get_items_by_version(table: str, version: str):
    """Получить элементы по версии"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    version_col = 'version' if table != 'configs' else 'game_version'
    
    if table == 'configs':
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, {version_col}, file_size, download_url, download_count FROM {table} WHERE {version_col}=? ORDER BY created_at DESC', (version,))
    else:
        cur.execute(f'SELECT id, name, description, full_description, file_name, file_path, {version_col}, file_size, download_url, download_count FROM {table} WHERE {version_col}=? ORDER BY created_at DESC', (version,))
    
    items = cur.fetchall()
    conn.close()
    return items

# Инициализация БД
init_db()

# ========== СОСТОЯНИЯ ==========
class AddItemStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_full_description = State()
    waiting_for_version = State()
    waiting_for_file = State()
    waiting_for_external_link = State()

class EditItemStates(StatesGroup):
    waiting_for_item_id = State()
    waiting_for_field = State()
    waiting_for_new_name = State()
    waiting_for_new_description = State()
    waiting_for_new_full_description = State()
    waiting_for_new_version = State()

class DeleteItemStates(StatesGroup):
    waiting_for_item_id = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_size(size_bytes: int) -> str:
    """Форматирование размера"""
    if size_bytes == 0:
        return "0 Б"
    size_names = ["Б", "КБ", "МБ", "ГБ"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_admin: bool = False):
    """Главная клавиатура"""
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты")],
        [types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="⚙️ Конфиги")],
        [types.KeyboardButton(text="ℹ️ О боте")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_category_keyboard(category: str):
    """Клавиатура выбора версии"""
    versions = get_versions(category)
    if not versions:
        return None
    
    buttons = []
    for version in versions:
        buttons.append([InlineKeyboardButton(
            text=f"📌 {version}", 
            callback_data=f"version_{category}_{version}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_items_keyboard(category: str, version: str):
    """Клавиатура списка элементов"""
    items = get_items_by_version(category, version)
    if not items:
        return None
    
    buttons = []
    for item in items:
        file_size_mb = item[7] / (1024 * 1024) if item[7] else 0
        size_text = f" ({file_size_mb:.1f} МБ)" if file_size_mb > 0 else ""
        download_text = f" [{item[9]} 📥]" if item[9] > 0 else ""
        
        buttons.append([InlineKeyboardButton(
            text=f"{item[1]}{size_text}{download_text}", 
            callback_data=f"item_{category}_{item[0]}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data=f"back_to_versions_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_item_detail_keyboard(category: str, item_id: int, download_url: str):
    """Клавиатура детального просмотра"""
    buttons = [
        [InlineKeyboardButton(text="📥 Скачать файл", url=download_url)],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data=f"back_to_items_{category}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_main_keyboard():
    """Главная админ-панель"""
    buttons = [
        [InlineKeyboardButton(text="🎮 Управление клиентами", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Управление ресурспаками", callback_data="admin_resourcepacks")],
        [InlineKeyboardButton(text="⚙️ Управление конфигами", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_keyboard(category: str):
    """Клавиатура управления категорией"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить (файл)", callback_data=f"admin_add_file_{category}")],
        [InlineKeyboardButton(text="🔗 Добавить (ссылка)", callback_data=f"admin_add_link_{category}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_{category}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{category}")],
        [InlineKeyboardButton(text="📋 Список всех", callback_data=f"admin_list_{category}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Старт"""
    is_admin = (message.from_user.id == ADMIN_ID)
    
    await message.answer(
        f"👋 **Привет! Я бот-менеджер для Minecraft**\n\n"
        f"📦 Файлы доступны по ссылкам\n\n"
        f"Используй кнопки ниже:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== ОСНОВНЫЕ РАЗДЕЛЫ ==========
@dp.message(F.text == "🎮 Клиенты")
async def show_clients(message: Message):
    """Показать клиенты"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('clients')
    
    if not keyboard:
        await message.answer(
            "📭 Пока нет доступных клиентов.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    
    await message.answer(
        "🎮 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "🎨 Ресурспаки")
async def show_resourcepacks(message: Message):
    """Показать ресурспаки"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('resourcepacks')
    
    if not keyboard:
        await message.answer(
            "📭 Пока нет доступных ресурспаков.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    
    await message.answer(
        "🎨 **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "⚙️ Конфиги")
async def show_configs(message: Message):
    """Показать конфиги"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('configs')
    
    if not keyboard:
        await message.answer(
            "📭 Пока нет доступных конфигов.",
            reply_markup=get_main_keyboard(is_admin)
        )
        return
    
    await message.answer(
        "⚙️ **Выбери версию Minecraft:**",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    """Информация о боте"""
    is_admin = (message.from_user.id == ADMIN_ID)
    
    clients = get_all_items('clients')
    resourcepacks = get_all_items('resourcepacks')
    configs = get_all_items('configs')
    
    total_downloads = 0
    for items in [clients, resourcepacks, configs]:
        for item in items:
            total_downloads += item[9] if len(item) > 9 else 0
    
    await message.answer(
        "🤖 **О боте**\n\n"
        f"📊 **Статистика:**\n"
        f"• Всего файлов: {len(clients) + len(resourcepacks) + len(configs)}\n"
        f"• Всего скачиваний: {total_downloads}\n\n"
        "📦 Файлы доступны по прямым ссылкам\n\n"
        "⚠️ Все файлы предоставляются 'как есть'.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin)
    )

# ========== НАВИГАЦИЯ ==========
@dp.callback_query(lambda c: c.data.startswith('version_'))
async def show_items_by_version(callback: CallbackQuery):
    """Показать элементы версии"""
    _, category, version = callback.data.split('_', 2)
    
    keyboard = get_items_keyboard(category, version)
    if not keyboard:
        await callback.answer("В этой версии пока нет элементов", show_alert=True)
        return
    
    category_names = {
        'clients': '🎮 Клиенты',
        'resourcepacks': '🎨 Ресурспаки',
        'configs': '⚙️ Конфиги'
    }
    
    await callback.message.edit_text(
        f"{category_names[category]} **{version}**\n\nВыбери элемент:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('item_'))
async def show_item_detail(callback: CallbackQuery):
    """Детали элемента"""
    _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("Элемент не найден!", show_alert=True)
        return
    
    file_size_str = format_size(item[7]) if item[7] else "Неизвестно"
    version_display = item[6] if item[6] else "Не указана"
    download_url = item[8]
    
    keyboard = get_item_detail_keyboard(category, item_id, download_url)
    
    text = (
        f"**{item[1]}**\n\n"
        f"*Версия:* {version_display}\n"
        f"*Размер:* {file_size_str}\n"
        f"*Скачиваний:* {item[9]}\n\n"
        f"*Описание:* {item[2]}\n\n"
        f"*Подробнее:*\n{item[3]}"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    
    # Увеличиваем счетчик просмотров
    increment_download_count(category, item_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('back_to_versions_'))
async def back_to_versions(callback: CallbackQuery):
    """Назад к версиям"""
    category = callback.data.replace('back_to_versions_', '')
    keyboard = get_category_keyboard(category)
    
    category_names = {
        'clients': '🎮 Клиенты',
        'resourcepacks': '🎨 Ресурспаки',
        'configs': '⚙️ Конфиги'
    }
    
    await callback.message.edit_text(
        f"{category_names[category]}\n\nВыбери версию:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('back_to_items_'))
async def back_to_items(callback: CallbackQuery):
    """Назад к списку"""
    await callback.answer("Используй навигацию по версиям")

@dp.callback_query(lambda c: c.data == 'back_to_main')
async def back_to_main(callback: CallbackQuery):
    """В главное меню"""
    await callback.message.delete()
    is_admin = (callback.from_user.id == ADMIN_ID)
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    """Админка"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    
    await message.answer(
        f"⚙️ **Админ панель**\n\n"
        f"Выбери категорию:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )

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

@dp.callback_query(lambda c: c.data == 'admin_resourcepacks')
async def admin_resourcepacks(callback: CallbackQuery):
    """Управление ресурспаками"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎨 **Управление ресурспаками**\n\n"
        "Выбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard('resourcepacks')
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_configs')
async def admin_configs(callback: CallbackQuery):
    """Управление конфигами"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ **Управление конфигами**\n\n"
        "Выбери действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_category_keyboard('configs')
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_back')
async def admin_back(callback: CallbackQuery):
    """Назад в админку"""
    await callback.message.edit_text(
        "⚙️ **Админ панель**\n\n"
        "Выбери категорию:",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_stats')
async def admin_stats(callback: CallbackQuery):
    """Статистика"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    clients = get_all_items('clients')
    resourcepacks = get_all_items('resourcepacks')
    configs = get_all_items('configs')
    
    total_size = 0
    total_downloads = 0
    
    for items in [clients, resourcepacks, configs]:
        for item in items:
            total_size += item[7] if len(item) > 7 else 0
            total_downloads += item[9] if len(item) > 9 else 0
    
    # Считаем место на диске
    disk_total = 0
    if os.path.exists('files'):
        for root, dirs, files in os.walk('files'):
            for file in files:
                file_path = os.path.join(root, file)
                disk_total += os.path.getsize(file_path)
    
    text = (
        "📊 **Статистика**\n\n"
        f"🎮 Клиенты: {len(clients)}\n"
        f"🎨 Ресурспаки: {len(resourcepacks)}\n"
        f"⚙️ Конфиги: {len(configs)}\n"
        f"📁 Всего файлов: {len(clients) + len(resourcepacks) + len(configs)}\n"
        f"📥 Всего скачиваний: {total_downloads}\n"
        f"💾 Размер в БД: {format_size(total_size)}\n"
        f"💿 На диске: {format_size(disk_total)}\n\n"
        f"🆔 Админ ID: {ADMIN_ID}"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()

# ========== ДОБАВЛЕНИЕ ПО ССЫЛКЕ ==========
@dp.callback_query(lambda c: c.data.startswith('admin_add_link_'))
async def admin_add_link_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления по ссылке"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace('admin_add_link_', '')
    await state.update_data(category=category, method='link')
    
    await state.set_state(AddItemStates.waiting_for_name)
    await callback.message.edit_text(
        f"📝 **Добавление по ссылке**\n\n"
        f"Ты добавляешь файл, который уже загружен на внешний сайт\n"
        f"(Catbox, Google Drive, MEGA и т.д.)\n\n"
        f"Введи **название**:",
        parse_mode="Markdown"
    )
    await callback.answer()

# ========== ДОБАВЛЕНИЕ ФАЙЛА ==========
@dp.callback_query(lambda c: c.data.startswith('admin_add_file_'))
async def admin_add_file_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления файла"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace('admin_add_file_', '')
    await state.update_data(category=category, method='file')
    
    await state.set_state(AddItemStates.waiting_for_name)
    await callback.message.edit_text(
        f"📝 **Добавление файла**\n\n"
        f"Введи **название**:",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(AddItemStates.waiting_for_name)
async def admin_add_name(message: Message, state: FSMContext):
    """Получение названия"""
    await state.update_data(name=message.text.strip())
    await state.set_state(AddItemStates.waiting_for_description)
    await message.answer(
        "✅ Название сохранено.\n\n"
        "Теперь введи **краткое описание** (1-2 предложения):"
    )

@dp.message(AddItemStates.waiting_for_description)
async def admin_add_description(message: Message, state: FSMContext):
    """Получение описания"""
    await state.update_data(description=message.text.strip())
    await state.set_state(AddItemStates.waiting_for_full_description)
    await message.answer(
        "✅ Краткое описание сохранено.\n\n"
        "Теперь введи **полное описание**:"
    )

@dp.message(AddItemStates.waiting_for_full_description)
async def admin_add_full_description(message: Message, state: FSMContext):
    """Получение полного описания"""
    await state.update_data(full_description=message.text.strip())
    await state.set_state(AddItemStates.waiting_for_version)
    await message.answer(
        "✅ Полное описание сохранено.\n\n"
        "Теперь введи **версию Minecraft** (например: `1.20.4`)\n"
        "Или отправь `-` чтобы пропустить:"
    )

@dp.message(AddItemStates.waiting_for_version)
async def admin_add_version(message: Message, state: FSMContext):
    """Получение версии"""
    version = message.text.strip()
    if version == '-':
        version = None
    
    await state.update_data(version=version)
    
    # Проверяем, какой метод добавления выбран
    data = await state.get_data()
    if data.get('method') == 'link':
        await state.set_state(AddItemStates.waiting_for_external_link)
        await message.answer(
            "✅ Версия сохранена.\n\n"
            "🔗 **Отправь ссылку на файл**\n"
            "Например:\n"
            "• https://files.catbox.moe/abc123.zip\n"
            "• https://drive.google.com/uc?export=download&id=...\n"
            "• https://mega.nz/file/...\n\n"
            "Просто вставь ссылку сюда:"
        )
    else:
        await state.set_state(AddItemStates.waiting_for_file)
        await message.answer(
            "✅ Версия сохранена.\n\n"
            "📤 **Отправь файл** (до 50 МБ):"
        )

@dp.message(AddItemStates.waiting_for_external_link)
async def admin_add_external_link(message: Message, state: FSMContext):
    """Получение внешней ссылки"""
    link = message.text.strip()
    
    # Простейшая проверка ссылки
    if not link.startswith(('http://', 'https://')):
        await message.answer("❌ Это не похоже на ссылку. Отправь ссылку начинающуюся с http:// или https://")
        return
    
    data = await state.get_data()
    category = data['category']
    
    # Сохраняем в базу
    try:
        item_id = add_item_with_link(
            table=category,
            name=data['name'],
            description=data['description'],
            full_description=data['full_description'],
            link=link,
            version=data.get('version')
        )
        
        await state.clear()
        
        category_names = {
            'clients': 'Клиент',
            'resourcepacks': 'Ресурспак',
            'configs': 'Конфиг'
        }
        
        await message.answer(
            f"✅ **{category_names[category]} успешно добавлен по ссылке!**\n\n"
            f"📄 **Название:** {data['name']}\n"
            f"🔗 **Ссылка:**\n`{link}`\n\n"
            f"ID: `{item_id}`",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при добавлении: {str(e)}",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        await state.clear()

@dp.message(AddItemStates.waiting_for_file)
async def admin_add_file(message: Message, state: FSMContext):
    """Получение файла"""
    if not message.document:
        await message.answer("❌ Пожалуйста, отправь файл (документ).")
        return
    
    data = await state.get_data()
    category = data['category']
    
    # Проверяем размер
    file_size = message.document.file_size
    if file_size > 50 * 1024 * 1024:  # 50 МБ
        await message.answer(
            f"❌ Файл слишком большой! Лимит 50 МБ.\n"
            f"Твой файл: {file_size/(1024*1024):.1f} МБ\n\n"
            f"Используй 'Добавить по ссылке' для больших файлов.\n\n"
            f"Рекомендую Catbox: https://catbox.moe",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        await state.clear()
        return
    
    # Создаем папку
    os.makedirs(f"files/{category}", exist_ok=True)
    
    # Сохраняем файл
    file_name = message.document.file_name
    file_path = f"files/{category}/{file_name}"
    
    # Если файл с таким именем уже есть - добавляем число
    base, ext = os.path.splitext(file_name)
    counter = 1
    while os.path.exists(file_path):
        file_name = f"{base}_{counter}{ext}"
        file_path = f"files/{category}/{file_name}"
        counter += 1
    
    # Отправляем сообщение о прогрессе
    progress_msg = await message.answer(f"⏳ Скачиваю {file_name} ({format_size(file_size)})...")
    
    try:
        # Скачиваем файл
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, file_path)
        
        # Удаляем сообщение о прогрессе
        try:
            await progress_msg.delete()
        except:
            pass
        
        # Сохраняем в базу
        item_id = add_item_with_file(
            table=category,
            name=data['name'],
            description=data['description'],
            full_description=data['full_description'],
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            version=data.get('version')
        )
        
        category_names = {
            'clients': 'Клиент',
            'resourcepacks': 'Ресурспак',
            'configs': 'Конфиг'
        }
        
        await message.answer(
            f"✅ **{category_names[category]} успешно добавлен!**\n\n"
            f"📄 **Название:** {data['name']}\n"
            f"📁 **Файл:** {file_name}\n"
            f"📊 **Размер:** {format_size(file_size)}\n\n"
            f"ID: `{item_id}`\n\n"
            f"⚠️ Файл сохранен локально. Для доступа из интернета используй внешние ссылки.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        
    except Exception as e:
        # Пытаемся удалить сообщение о прогрессе
        try:
            await progress_msg.delete()
        except:
            pass
        
        logging.error(f"Ошибка при скачивании: {e}")
        
        # Специальная обработка для JAR файлов
        if ".jar" in file_name.lower() or "jar" in str(e).lower():
            await message.answer(
                f"❌ Ошибка при скачивании JAR-файла.\n\n"
                f"JAR-файлы лучше загружать через внешние сервисы:\n"
                f"• Catbox: https://catbox.moe (до 200 МБ)\n"
                f"• Pomf: https://pomf.lain.la (до 1 ГБ)\n\n"
                f"Просто загрузи файл туда и добавь ссылку через '🔗 Добавить (ссылка)'",
                reply_markup=get_main_keyboard(is_admin=True)
            )
        else:
            await message.answer(
                f"❌ Ошибка при скачивании файла: {str(e)}",
                reply_markup=get_main_keyboard(is_admin=True)
            )
    
    await state.clear()

# ========== РЕДАКТИРОВАНИЕ ==========
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
    
    text = f"✏️ **Редактирование**\n\nВведи **ID** элемента:\n\n"
    for item in items:
        file_size_str = format_size(item[7]) if item[7] else "?"
        text += f"• `{item[0]}` — {item[1]} (v{item[6] or '?'}, {file_size_str})\n"
    
    await state.update_data(category=category)
    await state.set_state(EditItemStates.waiting_for_item_id)
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(EditItemStates.waiting_for_item_id)
async def admin_edit_get_id(message: Message, state: FSMContext):
    """Получение ID"""
    try:
        item_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи корректный числовой ID.")
        return
    
    data = await state.get_data()
    category = data['category']
    
    item = get_item(category, item_id)
    if not item:
        await message.answer("❌ Элемент с таким ID не найден.")
        await state.clear()
        return
    
    await state.update_data(item_id=item_id, item=item)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data="edit_name")],
        [InlineKeyboardButton(text="📄 Краткое описание", callback_data="edit_description")],
        [InlineKeyboardButton(text="📚 Полное описание", callback_data="edit_full_description")],
        [InlineKeyboardButton(text="🔢 Версию", callback_data="edit_version")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]
    ])
    
    await message.answer(
        f"✏️ **Редактирование:** {item[1]}\n\n"
        f"Текущие данные:\n"
        f"• Версия: {item[6] or 'Не указана'}\n"
        f"• Размер: {format_size(item[7])}\n\n"
        f"Что хочешь изменить?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith('edit_'))
async def admin_edit_field(callback: CallbackQuery, state: FSMContext):
    """Выбор поля"""
    field = callback.data.replace('edit_', '')
    
    if field == 'cancel':
        await state.clear()
        await callback.message.edit_text("❌ Редактирование отменено.")
        await callback.answer()
        return
    
    field_names = {
        'name': 'название',
        'description': 'краткое описание',
        'full_description': 'полное описание',
        'version': 'версию'
    }
    
    await state.update_data(edit_field=field)
    
    state_map = {
        'name': EditItemStates.waiting_for_new_name,
        'description': EditItemStates.waiting_for_new_description,
        'full_description': EditItemStates.waiting_for_new_full_description,
        'version': EditItemStates.waiting_for_new_version
    }
    await state.set_state(state_map[field])
    
    await callback.message.edit_text(
        f"Введи **новое {field_names[field]}**:",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(EditItemStates.waiting_for_new_name)
async def admin_edit_name(message: Message, state: FSMContext):
    """Обновление названия"""
    data = await state.get_data()
    category = data['category']
    item_id = data['item_id']
    item = data['item']
    
    new_value = message.text.strip()
    
    update_item(category, item_id, new_value, item[2], item[3], item[6])
    
    await state.clear()
    await message.answer(
        f"✅ Название обновлено на: {new_value}",
        reply_markup=get_main_keyboard(is_admin=True)
    )

@dp.message(EditItemStates.waiting_for_new_description)
async def admin_edit_description(message: Message, state: FSMContext):
    """Обновление описания"""
    data = await state.get_data()
    category = data['category']
    item_id = data['item_id']
    item = data['item']
    
    new_value = message.text.strip()
    
    update_item(category, item_id, item[1], new_value, item[3], item[6])
    
    await state.clear()
    await message.answer(
        f"✅ Краткое описание обновлено",
        reply_markup=get_main_keyboard(is_admin=True)
    )

@dp.message(EditItemStates.waiting_for_new_full_description)
async def admin_edit_full_description(message: Message, state: FSMContext):
    """Обновление полного описания"""
    data = await state.get_data()
    category = data['category']
    item_id = data['item_id']
    item = data['item']
    
    new_value = message.text.strip()
    
    update_item(category, item_id, item[1], item[2], new_value, item[6])
    
    await state.clear()
    await message.answer(
        f"✅ Полное описание обновлено",
        reply_markup=get_main_keyboard(is_admin=True)
    )

@dp.message(EditItemStates.waiting_for_new_version)
async def admin_edit_version(message: Message, state: FSMContext):
    """Обновление версии"""
    data = await state.get_data()
    category = data['category']
    item_id = data['item_id']
    item = data['item']
    
    new_value = message.text.strip()
    if new_value == '-':
        new_value = None
    
    update_item(category, item_id, item[1], item[2], item[3], new_value)
    
    await state.clear()
    await message.answer(
        f"✅ Версия обновлена на: {new_value or 'Не указана'}",
        reply_markup=get_main_keyboard(is_admin=True)
    )

# ========== УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith('admin_delete_'))
async def admin_delete_start(callback: CallbackQuery, state: FSMContext):
    """Начало удаления"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace('admin_delete_', '')
    items = get_all_items(category)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет элементов для удаления.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
            ])
        )
        await callback.answer()
        return
    
    text = f"🗑 **Удаление**\n\nВведи **ID** элемента для удаления:\n\n"
    for item in items:
        file_size_str = format_size(item[7]) if item[7] else "?"
        text += f"• `{item[0]}` — {item[1]} (v{item[6] or '?'}, {file_size_str})\n"
    
    await state.update_data(category=category)
    await state.set_state(DeleteItemStates.waiting_for_item_id)
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(DeleteItemStates.waiting_for_item_id)
async def admin_delete_confirm(message: Message, state: FSMContext):
    """Подтверждение удаления"""
    try:
        item_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи корректный числовой ID.")
        return
    
    data = await state.get_data()
    category = data['category']
    
    item = get_item(category, item_id)
    if not item:
        await message.answer("❌ Элемент с таким ID не найден.")
        await state.clear()
        return
    
    # Удаляем
    delete_item(category, item_id)
    
    await state.clear()
    await message.answer(
        f"✅ **Элемент удален:** {item[1]}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(is_admin=True)
    )

# ========== СПИСОК ВСЕХ ==========
@dp.callback_query(lambda c: c.data.startswith('admin_list_'))
async def admin_list_all(callback: CallbackQuery):
    """Список всех элементов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace('admin_list_', '')
    items = get_all_items(category)
    
    category_names = {
        'clients': '🎮 Клиенты',
        'resourcepacks': '🎨 Ресурспаки',
        'configs': '⚙️ Конфиги'
    }
    
    if not items:
        await callback.message.edit_text(
            f"{category_names[category]}\n\n📭 Список пуст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
            ])
        )
        await callback.answer()
        return
    
    text = f"{category_names[category]} **(полный список):**\n\n"
    
    for item in items:
        file_size_str = format_size(item[7]) if item[7] else "?"
        text += (
            f"**ID:** `{item[0]}`\n"
            f"**Название:** {item[1]}\n"
            f"**Версия:** {item[6] or 'Не указана'}\n"
            f"**Размер:** {file_size_str}\n"
            f"**Файл:** {item[4] or 'Нет'}\n"
            f"**Скачиваний:** {item[9]}\n"
            f"**Ссылка:**\n`{item[8]}`\n"
            f"{'—' * 20}\n"
        )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]
        ])
    )
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    """Запуск бота"""
    logging.info("Запуск бота...")
    
    # Создаем папки
    os.makedirs("files/clients", exist_ok=True)
    os.makedirs("files/resourcepacks", exist_ok=True)
    os.makedirs("files/configs", exist_ok=True)
    
    print("=" * 50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("📁 Папки для файлов созданы")
    print("=" * 50)
    print("📌 Для JAR-файлов рекомендуется использовать внешние ссылки:")
    print("   Catbox: https://catbox.moe (до 200 МБ)")
    print("   Pomf: https://pomf.lain.la (до 1 ГБ)")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())