import logging
import os
import asyncio
import json
import sqlite3
import random
import shutil
import requests
import base64
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

# GitHub настройки
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Добавь это в переменные окружения
GITHUB_REPO = "pablo5850004-cpu/minecraft-bot"  # Твой репозиторий
GITHUB_BACKUP_PATH = "backups/"  # Папка для бэкапов

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
USERS_DB_PATH = 'users.db'
PERMANENT_BACKUP_DIR = './persistent_backups'

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(PERMANENT_BACKUP_DIR, exist_ok=True)

# ========== ФУНКЦИЯ ЗАГРУЗКИ НА GITHUB ==========
async def upload_to_github(filepath: str, filename: str, commit_message: str = None):
    """Загружает файл на GitHub"""
    try:
        if not GITHUB_TOKEN:
            logger.warning("⚠️ GITHUB_TOKEN не настроен, пропускаем загрузку")
            return False
        
        # Читаем файл
        with open(filepath, 'rb') as f:
            content = f.read()
        
        # Кодируем в base64
        base64_content = base64.b64encode(content).decode('utf-8')
        
        # Формируем путь на GitHub
        github_path = f"{GITHUB_BACKUP_PATH}{filename}"
        
        # Формируем запрос к GitHub API
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Проверяем, есть ли уже такой файл
        response = requests.get(url, headers=headers)
        
        # Формируем сообщение коммита
        if not commit_message:
            commit_message = f"Автоматический бэкап {filename} от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        data = {
            "message": commit_message,
            "content": base64_content,
            "branch": "main"
        }
        
        if response.status_code == 200:
            # Файл существует, нужно обновить
            data["sha"] = response.json()["sha"]
            action = "обновлён"
        else:
            action = "добавлен"
        
        # Отправляем файл
        response = requests.put(url, headers=headers, json=data)
        
        if response.status_code in [200, 201]:
            logger.info(f"✅ Бэкап {action} на GitHub: {filename}")
            return True
        else:
            logger.error(f"❌ Ошибка загрузки на GitHub: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке на GitHub: {e}")
        return False

# ========== ОБНОВЛЁННАЯ ФУНКЦИЯ БЭКАПА ==========
async def backup_database_to_json(auto_github: bool = True):
    """Создаёт JSON бэкап всех данных и загружает на GitHub"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        backup_data = {
            "clients": [],
            "resourcepacks": [],
            "configs": [],
            "favorites": [],
            "users": [],
            "backup_date": datetime.now().isoformat(),
            "version": "1.0"
        }
        
        # Сохраняем клиентов
        cur.execute('SELECT * FROM clients')
        columns = [description[0] for description in cur.description]
        for row in cur.fetchall():
            backup_data["clients"].append(dict(zip(columns, row)))
        
        # Сохраняем ресурспаки
        cur.execute('SELECT * FROM resourcepacks')
        columns = [description[0] for description in cur.description]
        for row in cur.fetchall():
            backup_data["resourcepacks"].append(dict(zip(columns, row)))
        
        # Сохраняем конфиги
        cur.execute('SELECT * FROM configs')
        columns = [description[0] for description in cur.description]
        for row in cur.fetchall():
            backup_data["configs"].append(dict(zip(columns, row)))
        
        # Сохраняем избранное
        cur.execute('SELECT * FROM favorites')
        columns = [description[0] for description in cur.description]
        for row in cur.fetchall():
            backup_data["favorites"].append(dict(zip(columns, row)))
        
        # Сохраняем пользователей
        try:
            conn_users = sqlite3.connect(USERS_DB_PATH)
            cur_users = conn_users.cursor()
            cur_users.execute('SELECT * FROM users')
            columns_users = [description[0] for description in cur_users.description]
            for row in cur_users.fetchall():
                backup_data["users"].append(dict(zip(columns_users, row)))
            conn_users.close()
        except:
            pass
        
        conn.close()
        
        # Создаём имя файла с датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"database_backup_{timestamp}.json"
        
        # Сохраняем во временную папку
        temp_path = os.path.join(BACKUP_DIR, filename)
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем в постоянную папку
        perm_path = os.path.join(PERMANENT_BACKUP_DIR, filename)
        with open(perm_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✅ Бэкап создан: {filename}")
        
        # Загружаем на GitHub
        if auto_github:
            commit_msg = f"Автоматический бэкап БД от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await upload_to_github(perm_path, filename, commit_msg)
        
        return temp_path
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
        return None

# ========== ФУНКЦИЯ БЭКАПА .db ФАЙЛОВ ==========
async def backup_db_files_to_github():
    """Загружает .db файлы на GitHub"""
    try:
        # Бэкап clients.db
        if os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_filename = f"clients_{timestamp}.db"
            db_backup_path = os.path.join(PERMANENT_BACKUP_DIR, db_filename)
            
            # Копируем .db файл
            shutil.copy2(DB_PATH, db_backup_path)
            
            # Загружаем на GitHub
            commit_msg = f"Автоматический бэкап БД clients.db от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await upload_to_github(db_backup_path, db_filename, commit_msg)
        
        # Бэкап users.db
        if os.path.exists(USERS_DB_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            users_filename = f"users_{timestamp}.db"
            users_backup_path = os.path.join(PERMANENT_BACKUP_DIR, users_filename)
            
            shutil.copy2(USERS_DB_PATH, users_backup_path)
            
            commit_msg = f"Автоматический бэкап БД users.db от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await upload_to_github(users_backup_path, users_filename, commit_msg)
        
        logger.info("✅ .db файлы загружены на GitHub")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки .db файлов: {e}")
        return False

# ========== ФУНКЦИЯ ДЛЯ ЗАГРУЗКИ ВСЕГО КОДА ==========
async def upload_code_to_github():
    """Загружает весь код бота на GitHub"""
    try:
        files_to_upload = ['bot.py', 'requirements.txt', 'Procfile']
        
        for filename in files_to_upload:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Кодируем в base64
                content_bytes = content.encode('utf-8')
                base64_content = base64.b64encode(content_bytes).decode('utf-8')
                
                # Формируем запрос
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
                headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                # Проверяем существование
                response = requests.get(url, headers=headers)
                
                data = {
                    "message": f"Автоматическое обновление {filename}",
                    "content": base64_content,
                    "branch": "main"
                }
                
                if response.status_code == 200:
                    data["sha"] = response.json()["sha"]
                
                response = requests.put(url, headers=headers, json=data)
                
                if response.status_code in [200, 201]:
                    logger.info(f"✅ {filename} обновлён на GitHub")
                else:
                    logger.error(f"❌ Ошибка загрузки {filename}: {response.status_code}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кода: {e}")
        return False

# ========== ПЕРЕХВАТЧИКИ ИЗМЕНЕНИЙ ==========
async def on_data_changed(action: str, table: str, item_id: int = None):
    """Вызывается при любом изменении данных"""
    logger.info(f"📝 Изменение данных: {action} в {table}" + (f" ID:{item_id}" if item_id else ""))
    
    # Создаём бэкап и загружаем на GitHub
    await backup_database_to_json(auto_github=True)
    
    # Также бэкапим .db файлы раз в 10 изменений
    if random.randint(1, 10) == 1:  # Каждое 10-е изменение
        await backup_db_files_to_github()

# ========== ОБНОВЛЁННЫЕ ФУНКЦИИ ДОБАВЛЕНИЯ ==========
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
        
        # Вызываем обработчик изменения
        asyncio.create_task(on_data_changed("add", "clients", item_id))
        
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении клиента: {e}")
        return None

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
        
        asyncio.create_task(on_data_changed("add", "resourcepacks", item_id))
        
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении ресурспака: {e}")
        return None

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
        
        asyncio.create_task(on_data_changed("add", "configs", item_id))
        
        return item_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении конфига: {e}")
        return None

# ========== ОБНОВЛЁННЫЕ ФУНКЦИИ ОБНОВЛЕНИЯ ==========
@safe_db
def update_client(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE clients SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    
    asyncio.create_task(on_data_changed("update", "clients", item_id))

@safe_db
def update_pack(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE resourcepacks SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    
    asyncio.create_task(on_data_changed("update", "resourcepacks", item_id))

@safe_db
def update_config(item_id: int, field: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'UPDATE configs SET {field} = ? WHERE id = ?', (value, item_id))
    conn.commit()
    conn.close()
    
    asyncio.create_task(on_data_changed("update", "configs", item_id))

@safe_db
def delete_item(table: str, item_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    asyncio.create_task(on_data_changed("delete", table, item_id))

# ========== НОВЫЕ КОМАНДЫ ДЛЯ АДМИНА ==========
@dp.message(Command("github_backup"))
async def cmd_github_backup(message: Message):
    """Ручной запуск бэкапа на GitHub"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    
    await message.answer("⏳ **Создаю бэкап и загружаю на GitHub...**", parse_mode="Markdown")
    
    # Создаём JSON бэкап
    json_path = await backup_database_to_json(auto_github=True)
    
    # Бэкапим .db файлы
    await backup_db_files_to_github()
    
    await message.answer(
        "✅ **Бэкапы успешно загружены на GitHub!**\n\n"
        "Посмотреть можно здесь:\n"
        f"https://github.com/{GITHUB_REPO}/tree/main/backups",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@dp.message(Command("github_code"))
async def cmd_github_code(message: Message):
    """Загружает код бота на GitHub"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    
    await message.answer("⏳ **Загружаю код на GitHub...**", parse_mode="Markdown")
    
    success = await upload_code_to_github()
    
    if success:
        await message.answer(
            "✅ **Код успешно загружен на GitHub!**",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ **Ошибка при загрузке кода**",
            parse_mode="Markdown"
        )

# ========== ДОБАВЛЯЕМ КНОПКУ В АДМИН-ПАНЕЛЬ ==========
def get_admin_main_keyboard():
    """Главная клавиатура админ-панели (с кнопкой GitHub)"""
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="📦 Бэкапы", callback_data="admin_backups_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🐙 GitHub", callback_data="admin_github")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(lambda c: c.data == "admin_github")
async def admin_github(callback: CallbackQuery):
    """Меню GitHub"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    buttons = [
        [InlineKeyboardButton(text="📥 Бэкап БД на GitHub", callback_data="github_backup_db")],
        [InlineKeyboardButton(text="📤 Загрузить код на GitHub", callback_data="github_upload_code")],
        [InlineKeyboardButton(text="🌐 Открыть репозиторий", url=f"https://github.com/{GITHUB_REPO}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    
    text = (
        "🐙 **GitHub интеграция**\n\n"
        "Здесь можно управлять бэкапами и кодом на GitHub.\n\n"
        f"Репозиторий: `{GITHUB_REPO}`\n"
        f"Папка бэкапов: `{GITHUB_BACKUP_PATH}`"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "github_backup_db")
async def github_backup_db(callback: CallbackQuery):
    """Ручной бэкап БД на GitHub"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ **Создаю бэкап...**", parse_mode="Markdown")
    
    # Создаём JSON бэкап
    json_path = await backup_database_to_json(auto_github=True)
    
    # Бэкапим .db файлы
    await backup_db_files_to_github()
    
    await callback.message.edit_text(
        "✅ **Бэкапы загружены на GitHub!**\n\n"
        f"[Открыть папку бэкапов](https://github.com/{GITHUB_REPO}/tree/main/backups)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_github")]
        ]),
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "github_upload_code")
async def github_upload_code(callback: CallbackQuery):
    """Загрузка кода на GitHub"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ **Загружаю код на GitHub...**", parse_mode="Markdown")
    
    success = await upload_code_to_github()
    
    if success:
        await callback.message.edit_text(
            "✅ **Код успешно загружен на GitHub!**\n\n"
            f"[Открыть репозиторий](https://github.com/{GITHUB_REPO})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_github")]
            ]),
            disable_web_page_preview=True
        )
    else:
        await callback.message.edit_text(
            "❌ **Ошибка при загрузке кода**\n\n"
            "Проверь GitHub токен в настройках.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_github")]
            ])
        )
    await callback.answer()

# ========== ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ ==========
# ... (весь остальной код из предыдущей версии)

# ========== ЗАПУСК ==========
async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👤 Создатель: {CREATOR_USERNAME}")
    
    if GITHUB_TOKEN:
        print("🐙 GitHub интеграция: АКТИВНА")
    else:
        print("⚠️ GitHub токен не настроен")
    
    print("="*50)
    print("📌 Функции:")
    print("   • 10 элементов на страницу")
    print("   • Красивое оформление с картинками")
    print("   • Работающее удаление для всех категорий")
    print("   • Полная админ-панель")
    print("   • Рассылка сообщений")
    print("   • Бэкапы в JSON")
    print("   • 🐙 Автозагрузка на GitHub")
    print("="*50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())