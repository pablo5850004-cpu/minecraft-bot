import logging
import os
import sys
import sqlite3
import math
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple

# Настройка логирования - сразу видно в консоли
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
print("\n" + "="*50)
print("🚀 ЗАПУСК БОТА НА RAILWAY")
print("="*50)

# Пробуем получить токен разными способами
BOT_TOKEN = None

# Способ 1: через os.getenv
BOT_TOKEN = "8732938464:AAHIsqjKA8wFCcK8iQi1FRGokH6cf8ypSmY"  # Твой токен
ADMIN_ID = 5809098591  # Твой ID

# Способ 2: через переменные окружения напрямую
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv('BOT_TOKEN')

print(f"📌 Поиск BOT_TOKEN: {'✅ Найден' if BOT_TOKEN else '❌ НЕ НАЙДЕН!'}")
if BOT_TOKEN:
    print(f"📌 Длина токена: {len(BOT_TOKEN)} символов")
    print(f"📌 Первые символы: {BOT_TOKEN[:10]}...")

# Получаем ADMIN_ID
try:
    ADMIN_ID = int(os.environ.get('ADMIN_ID', '5809098591'))
    print(f"📌 ADMIN_ID: {ADMIN_ID} {'✅' if ADMIN_ID else '❌'}")
except:
    ADMIN_ID = 5809098591
    print(f"📌 ADMIN_ID (по умолчанию): {ADMIN_ID}")

if not BOT_TOKEN:
    print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Токен не найден!")
    print("Проверь настройки Variables в Railway:")
    print("1. KEY: BOT_TOKEN")
    print("2. VALUE: 8732938464:AAHIsqjKA8wFCcK8iQi1FRGokH6cf8ypSmY")
    print("\n🔄 Перезапусти деплой после добавления переменной")
    sys.exit(1)

print("="*50 + "\n")

# Импортируем aiogram ПОСЛЕ проверки токена
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def init_db():
    """Создание таблиц"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    
    # Таблица клиентов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
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
        CREATE TABLE IF NOT EXISTS resourcepacks (
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
        CREATE TABLE IF NOT EXISTS configs (
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
    logger.info("✅ База данных инициализирована")

def add_item_with_link(table: str, name: str, description: str, full_description: str, link: str, version: Optional[str] = None):
    """Добавить элемент по ссылке"""
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

def delete_item(table: str, item_id: int):
    """Удалить элемент"""
    conn = sqlite3.connect('clients.db')
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    logger.info(f"🗑 Удален элемент ID {item_id} из {table}")

def increment_download_count(table: str, item_id: int):
    """Увеличить счетчик"""
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
    waiting_for_external_link = State()

# ========== ФУНКЦИИ ==========
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
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_items_keyboard(category: str, version: str):
    """Клавиатура списка элементов"""
    items = get_items_by_version(category, version)
    if not items:
        return None
    
    buttons = []
    for item in items:
        download_text = f" [{item[9]} 📥]" if item[9] > 0 else ""
        buttons.append([InlineKeyboardButton(
            text=f"{item[1]}{download_text}", 
            callback_data=f"item_{category}_{item[0]}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_versions_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_item_detail_keyboard(category: str, item_id: int, download_url: str):
    """Клавиатура детального просмотра"""
    buttons = [
        [InlineKeyboardButton(text="📥 Скачать", url=download_url)],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_items_{category}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_main_keyboard():
    """Админ-панель"""
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_resourcepacks")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_category_keyboard(category: str):
    """Клавиатура управления"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить по ссылке", callback_data=f"admin_add_link_{category}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{category}")],
        [InlineKeyboardButton(text="📋 Список", callback_data=f"admin_list_{category}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========== КОМАНДЫ ==========
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Старт"""
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        f"👋 Привет! Я бот для Minecraft\n\n"
        f"Выбери раздел:",
        reply_markup=get_main_keyboard(is_admin)
    )

@dp.message(F.text == "🎮 Клиенты")
async def show_clients(message: Message):
    """Клиенты"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('clients')
    if not keyboard:
        await message.answer("📭 Нет клиентов", reply_markup=get_main_keyboard(is_admin))
        return
    await message.answer("🎮 Выбери версию:", reply_markup=keyboard)

@dp.message(F.text == "🎨 Ресурспаки")
async def show_resourcepacks(message: Message):
    """Ресурспаки"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('resourcepacks')
    if not keyboard:
        await message.answer("📭 Нет ресурспаков", reply_markup=get_main_keyboard(is_admin))
        return
    await message.answer("🎨 Выбери версию:", reply_markup=keyboard)

@dp.message(F.text == "⚙️ Конфиги")
async def show_configs(message: Message):
    """Конфиги"""
    is_admin = (message.from_user.id == ADMIN_ID)
    keyboard = get_category_keyboard('configs')
    if not keyboard:
        await message.answer("📭 Нет конфигов", reply_markup=get_main_keyboard(is_admin))
        return
    await message.answer("⚙️ Выбери версию:", reply_markup=keyboard)

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    """О боте"""
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        "🤖 Minecraft Bot\n\n"
        "📦 Добавляй ссылки на файлы\n"
        "📊 Считает скачивания",
        reply_markup=get_main_keyboard(is_admin)
    )

@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    """Админка"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет прав")
        return
    await message.answer("⚙️ Админ панель", reply_markup=get_admin_main_keyboard())

# ========== НАВИГАЦИЯ ==========
@dp.callback_query(lambda c: c.data.startswith('version_'))
async def show_items_by_version(callback: CallbackQuery):
    """Элементы версии"""
    _, category, version = callback.data.split('_', 2)
    keyboard = get_items_keyboard(category, version)
    if not keyboard:
        await callback.answer("Нет элементов")
        return
    await callback.message.edit_text(f"📌 {version}\nВыбери:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('item_'))
async def show_item_detail(callback: CallbackQuery):
    """Детали элемента"""
    _, category, item_id = callback.data.split('_')
    item_id = int(item_id)
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден")
        return
    
    download_url = item[8]
    text = f"**{item[1]}**\nВерсия: {item[6] or '?'}\nСкачиваний: {item[9]}\n\n{item[2]}"
    keyboard = get_item_detail_keyboard(category, item_id, download_url)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    increment_download_count(category, item_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'back_to_main')
async def back_to_main(callback: CallbackQuery):
    """В главное меню"""
    await callback.message.delete()
    is_admin = (callback.from_user.id == ADMIN_ID)
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard(is_admin))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('back_to_versions_'))
async def back_to_versions(callback: CallbackQuery):
    """Назад к версиям"""
    category = callback.data.replace('back_to_versions_', '')
    keyboard = get_category_keyboard(category)
    await callback.message.edit_text("Выбери версию:", reply_markup=keyboard)
    await callback.answer()

# ========== АДМИН КОМАНДЫ ==========
@dp.callback_query(lambda c: c.data == 'admin_clients')
async def admin_clients(callback: CallbackQuery):
    await callback.message.edit_text("🎮 Управление клиентами", reply_markup=get_admin_category_keyboard('clients'))
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_resourcepacks')
async def admin_resourcepacks(callback: CallbackQuery):
    await callback.message.edit_text("🎨 Управление ресурспаками", reply_markup=get_admin_category_keyboard('resourcepacks'))
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_configs')
async def admin_configs(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ Управление конфигами", reply_markup=get_admin_category_keyboard('configs'))
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_back')
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text("⚙️ Админ панель", reply_markup=get_admin_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'admin_stats')
async def admin_stats(callback: CallbackQuery):
    clients = get_all_items('clients')
    resourcepacks = get_all_items('resourcepacks')
    configs = get_all_items('configs')
    text = f"📊 Статистика\n\nКлиенты: {len(clients)}\nРесурспаки: {len(resourcepacks)}\nКонфиги: {len(configs)}"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('admin_add_link_'))
async def admin_add_link_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    category = callback.data.replace('admin_add_link_', '')
    await state.update_data(category=category)
    await state.set_state(AddItemStates.waiting_for_name)
    await callback.message.edit_text("📝 Введи название:")
    await callback.answer()

@dp.message(AddItemStates.waiting_for_name)
async def admin_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddItemStates.waiting_for_description)
    await message.answer("✅ Введи краткое описание:")

@dp.message(AddItemStates.waiting_for_description)
async def admin_add_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddItemStates.waiting_for_full_description)
    await message.answer("✅ Введи полное описание:")

@dp.message(AddItemStates.waiting_for_full_description)
async def admin_add_full_description(message: Message, state: FSMContext):
    await state.update_data(full_description=message.text)
    await state.set_state(AddItemStates.waiting_for_version)
    await message.answer("✅ Введи версию (или '-' для пропуска):")

@dp.message(AddItemStates.waiting_for_version)
async def admin_add_version(message: Message, state: FSMContext):
    version = None if message.text == '-' else message.text
    await state.update_data(version=version)
    await state.set_state(AddItemStates.waiting_for_external_link)
    await message.answer("🔗 Отправь ссылку на файл:")

@dp.message(AddItemStates.waiting_for_external_link)
async def admin_add_external_link(message: Message, state: FSMContext):
    link = message.text.strip()
    if not link.startswith(('http://', 'https://')):
        await message.answer("❌ Нужна ссылка http:// или https://")
        return
    
    data = await state.get_data()
    item_id = add_item_with_link(
        table=data['category'],
        name=data['name'],
        description=data['description'],
        full_description=data['full_description'],
        link=link,
        version=data.get('version')
    )
    await state.clear()
    await message.answer(f"✅ Добавлено! ID: {item_id}", reply_markup=get_main_keyboard(is_admin=True))

@dp.callback_query(lambda c: c.data.startswith('admin_delete_'))
async def admin_delete_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    category = callback.data.replace('admin_delete_', '')
    items = get_all_items(category)
    if not items:
        await callback.message.edit_text("📭 Нет элементов", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}"]]))
        await callback.answer()
        return
    
    text = "🗑 Введи ID для удаления:\n\n"
    for item in items:
        text += f"• {item[0]}: {item[1]}\n"
    
    await state.update_data(category=category)
    await state.set_state(DeleteItemStates.waiting_for_id)
    await callback.message.edit_text(text)
    await callback.answer()

class DeleteItemStates(StatesGroup):
    waiting_for_id = State()

@dp.message(DeleteItemStates.waiting_for_id)
async def admin_delete_confirm(message: Message, state: FSMContext):
    try:
        item_id = int(message.text.strip())
    except:
        await message.answer("❌ Введи число")
        return
    
    data = await state.get_data()
    delete_item(data['category'], item_id)
    await state.clear()
    await message.answer(f"✅ Удалено ID {item_id}", reply_markup=get_main_keyboard(is_admin=True))

@dp.callback_query(lambda c: c.data.startswith('admin_list_'))
async def admin_list_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    
    category = callback.data.replace('admin_list_', '')
    items = get_all_items(category)
    
    if not items:
        await callback.message.edit_text("📭 Список пуст", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}"]]))
        await callback.answer()
        return
    
    text = f"📋 Список:\n\n"
    for item in items:
        text += f"ID {item[0]}: {item[1]} (скач: {item[9]})\n{item[8]}\n\n"
    
    await callback.message.edit_text(text[:4000], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}"]]))
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    logger.info("="*50)
    logger.info("✅ Бот запускается...")
    logger.info(f"👤 Админ ID: {ADMIN_ID}")
    logger.info(f"🤖 Токен: {BOT_TOKEN[:10]}...")
    logger.info("="*50)
    
    # Создаем папки
    os.makedirs("files", exist_ok=True)
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())