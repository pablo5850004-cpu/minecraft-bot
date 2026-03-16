import logging
import os
import asyncio
import json
import sqlite3
import shutil
import zipfile
import base64
from pathlib import Path
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("="*60)
    print("❌ ОШИБКА: ТОКЕН БОТА НЕ НАЙДЕН!")
    print("="*60)
    print("🔧 Инструкция для bothost.ru:")
    print("1. Зайдите в панель управления bothost.ru")
    print("2. Откройте раздел 'Переменные окружения'")
    print("3. Добавьте новую переменную:")
    print("   Имя: BOT_TOKEN")
    print("   Значение: ваш_токен_от_BotFather")
    print("4. Сохраните и перезапустите бота")
    print("="*60)
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

ADMIN_ID = 5809098591
CREATOR_USERNAME = "@Strann1k_fiol"
ADMIN_BOT_LINK = "https://t.me/Strann1k_fiol"
VIP_PRICE = 49

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Правильный путь для bothost.ru - /app/data
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "clients.db"
USERS_DB_PATH = DATA_DIR / "users.db"
BACKUP_DIR = DATA_DIR / "backups"
TEMP_DIR = DATA_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)
TEMP_DB_PATH = TEMP_DIR / "temp_clients.db"

print(f"📁 Папка данных: {DATA_DIR}")
print(f"📁 Папка бэкапов: {BACKUP_DIR}")
print(f"📁 Папка временных файлов: {TEMP_DIR}")

def init_db():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        # Таблица клиентов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                version TEXT,
                is_vip INTEGER DEFAULT 0,
                downloads INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица ресурспаков
        cur.execute('''
            CREATE TABLE IF NOT EXISTS resourcepacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                version TEXT,
                author TEXT,
                is_vip INTEGER DEFAULT 0,
                downloads INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица конфигов (привязаны к названию клиента, не к ID)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                client_version TEXT NOT NULL,
                name TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                media TEXT DEFAULT '[]',
                download_url TEXT NOT NULL,
                is_vip INTEGER DEFAULT 0,
                downloads INTEGER DEFAULT 0,
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
                PRIMARY KEY (user_id, pack_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ База данных клиентов готова")
        
        # Добавляем тестовые данные, если таблицы пустые
        add_test_data_if_empty()
    except Exception as e:
        print(f"❌ Ошибка при создании базы клиентов: {e}")

def add_test_data_if_empty():
    """Добавляет тестовые данные, если таблицы пустые"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        # Проверяем clients
        cur.execute("SELECT COUNT(*) FROM clients")
        if cur.fetchone()[0] == 0:
            print("📝 Добавляю тестовые данные в clients...")
            cur.execute('''
                INSERT INTO clients (name, full_desc, download_url, version, is_vip, downloads) 
                VALUES 
                ('Vanilla Client', 'Обычный ванильный клиент Minecraft', 'https://example.com/vanilla', '1.20.4', 0, 100),
                ('OptiFine Client', 'Клиент с OptiFine для лучшей производительности', 'https://example.com/optifine', '1.20.4', 0, 200),
                ('VIP Client', 'Эксклюзивный VIP клиент с премиум функциями', 'https://example.com/vip', '1.20.4', 1, 50),
                ('Lunar Client', 'Популярный PvP клиент', 'https://example.com/lunar', '1.16.5', 0, 300),
                ('Badlion Client', 'Клиент для PvP с античитами', 'https://example.com/badlion', '1.16.5', 0, 250),
                ('VIP PvP Client', 'Премиум PvP клиент', 'https://example.com/vip-pvp', '1.16.5', 1, 75)
            ''')
            conn.commit()
            print("✅ Тестовые данные добавлены в clients")
        
        # Проверяем resourcepacks
        cur.execute("SELECT COUNT(*) FROM resourcepacks")
        if cur.fetchone()[0] == 0:
            print("📝 Добавляю тестовые данные в resourcepacks...")
            cur.execute('''
                INSERT INTO resourcepacks (name, full_desc, download_url, version, author, is_vip, downloads) 
                VALUES 
                ('Faithful', 'Классический ресурспак в стиле vanilla', 'https://example.com/faithful', '1.20.4', 'Faithful Team', 0, 500),
                ('VIP Texture Pack', 'Эксклюзивный ресурспак для VIP', 'https://example.com/vip', '1.20.4', 'VIP Creator', 1, 30)
            ''')
            conn.commit()
            print("✅ Тестовые данные добавлены в resourcepacks")
        
        # Проверяем configs
        cur.execute("SELECT COUNT(*) FROM configs")
        if cur.fetchone()[0] == 0:
            print("📝 Добавляю тестовые данные в configs...")
            cur.execute('''
                INSERT INTO configs (client_name, client_version, name, full_desc, download_url, is_vip, downloads) 
                VALUES 
                ('OptiFine', '1.20.4', 'OptiFine High Settings', 'Высокие настройки графики для OptiFine', 'https://example.com/optifine-high', 0, 120),
                ('OptiFine', '1.20.4', 'OptiFine Low Settings', 'Низкие настройки для слабых ПК', 'https://example.com/optifine-low', 0, 85),
                ('OptiFine', '1.16.5', 'OptiFine Settings 1.16', 'Настройки для версии 1.16.5', 'https://example.com/optifine-116', 0, 45),
                ('Lunar Client', '1.20.4', 'Lunar PvP Settings', 'PvP настройки для Lunar Client', 'https://example.com/lunar-pvp', 1, 200),
                ('Lunar Client', '1.16.5', 'Lunar Settings', 'Базовые настройки Lunar', 'https://example.com/lunar', 0, 150),
                ('Badlion', '1.20.4', 'Badlion Performance', 'Настройки для максимального FPS', 'https://example.com/badlion-perf', 0, 90),
                ('VIP Client', '1.20.4', 'VIP Config Premium', 'Эксклюзивные настройки для VIP', 'https://example.com/vip-config', 1, 30)
            ''')
            conn.commit()
            print("✅ Тестовые данные добавлены в configs")
        
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка при добавлении тестовых данных: {e}")

def init_users_db():
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                invites INTEGER DEFAULT 0,
                downloads_total INTEGER DEFAULT 0,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS downloads_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                vip_item INTEGER DEFAULT 0,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER,
                action TEXT NOT NULL,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("✅ База данных пользователей готова")
    except Exception as e:
        print(f"❌ Ошибка при создании базы пользователей: {e}")

init_db()
init_users_db()

# Функция для создания временной копии базы данных
def create_temp_db():
    """Создает временную копию базы данных для редактирования"""
    try:
        if TEMP_DB_PATH.exists():
            TEMP_DB_PATH.unlink()
        shutil.copy2(DB_PATH, TEMP_DB_PATH)
        logger.info(f"✅ Создана временная копия БД: {TEMP_DB_PATH}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания временной копии: {e}")
        return False

# Функция для применения изменений из временной БД
def apply_temp_db_changes():
    """Заменяет основную базу данных временной"""
    try:
        # Создаем бэкап перед заменой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"pre_edit_backup_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)
        
        # Заменяем основную БД временной
        if TEMP_DB_PATH.exists():
            shutil.copy2(TEMP_DB_PATH, DB_PATH)
            TEMP_DB_PATH.unlink()  # Удаляем временную копию
            logger.info(f"✅ Изменения применены, создан бэкап: {backup_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка применения изменений: {e}")
        return False

# Функция для отмены изменений
def cancel_temp_db_changes():
    """Отменяет изменения, удаляя временную БД"""
    try:
        if TEMP_DB_PATH.exists():
            TEMP_DB_PATH.unlink()
            logger.info("✅ Временная БД удалена, изменения отменены")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отмены изменений: {e}")
        return False

def check_all_clients():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT id, name, version, is_vip FROM clients ORDER BY id DESC LIMIT 20")
        clients = cur.fetchall()
        cur.execute("SELECT DISTINCT version FROM clients WHERE version IS NOT NULL AND version != ''")
        versions = [v[0] for v in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM resourcepacks")
        packs_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM configs")
        configs_count = cur.fetchone()[0]
        conn.close()
        print("\n" + "="*50)
        print("📊 ДИАГНОСТИКА БАЗЫ ДАННЫХ")
        print("="*50)
        print(f"📋 Всего клиентов в БД: {len(clients) if clients else 0}")
        print(f"📋 Всего ресурспаков: {packs_count}")
        print(f"📋 Всего конфигов: {configs_count}")
        print(f"📋 Уникальные версии клиентов: {versions}")
        print("-"*50)
        print("📋 Последние 20 клиентов:")
        for client in clients:
            vip_mark = "💎" if client[3] == 1 else "📦"
            print(f"   {vip_mark} ID: {client[0]}, {client[1]}, версия: '{client[2]}'")
        print("="*50 + "\n")
        return clients
    except Exception as e:
        logger.error(f"Ошибка проверки клиентов: {e}")
        return []

def get_all_backups():
    try:
        files = os.listdir(str(BACKUP_DIR))
        backups = [f for f in files if f.endswith('.zip')]
        backups.sort(reverse=True)
        return backups
    except Exception as e:
        print(f"Ошибка получения списка бэкапов: {e}")
        return []

def check_backup_structure(zip_path):
    issues = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            files = zipf.namelist()
            if 'clients.db' not in files:
                issues.append("❌ Отсутствует clients.db")
            if 'users.db' not in files:
                issues.append("❌ Отсутствует users.db")
            for file in files:
                info = zipf.getinfo(file)
                if info.file_size == 0:
                    issues.append(f"⚠️ Файл {file} пустой")
        return issues
    except zipfile.BadZipFile:
        return ["❌ Файл поврежден (не является ZIP архивом)"]
    except Exception as e:
        return [f"❌ Ошибка проверки: {str(e)}"]

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
        restored_files = []
        for file in extract_dir.iterdir():
            if file.name == 'clients.db':
                if DB_PATH.exists():
                    backup_path = BACKUP_DIR / f"pre_restore_clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(DB_PATH, backup_path)
                shutil.copy2(file, DB_PATH)
                restored = True
                restored_files.append('clients.db')
            elif file.name == 'users.db':
                if USERS_DB_PATH.exists():
                    backup_path = BACKUP_DIR / f"pre_restore_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(USERS_DB_PATH, backup_path)
                shutil.copy2(file, USERS_DB_PATH)
                restored = True
                restored_files.append('users.db')
        shutil.rmtree(extract_dir, ignore_errors=True)
        if restored:
            logger.info(f"✅ Восстановлены файлы: {', '.join(restored_files)}")
        return restored
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
        return False

def get_users_count():
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users')
        result = cur.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка получения количества пользователей: {e}")
        return 0

def get_vip_users_count():
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' in columns:
            cur.execute('SELECT COUNT(*) FROM users WHERE is_vip = 1')
            result = cur.fetchone()
            conn.close()
            return result[0] if result else 0
        else:
            conn.close()
            return 0
    except Exception as e:
        logger.error(f"Ошибка получения количества VIP пользователей: {e}")
        return 0

def get_all_users():
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

def get_all_users_with_details():
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        has_balance = 'balance' in columns
        has_vip = 'is_vip' in columns
        if has_balance and has_vip:
            cur.execute('SELECT user_id, username, first_name, balance, is_vip FROM users ORDER BY last_active DESC')
        elif has_balance:
            cur.execute('SELECT user_id, username, first_name, balance, 0 as is_vip FROM users ORDER BY last_active DESC')
        elif has_vip:
            cur.execute('SELECT user_id, username, first_name, 0 as balance, is_vip FROM users ORDER BY last_active DESC')
        else:
            cur.execute('SELECT user_id, username, first_name, 0 as balance, 0 as is_vip FROM users ORDER BY last_active DESC')
        users = cur.fetchall()
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        return []

def get_user_status(user_id: int):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        has_balance = 'balance' in columns
        has_vip = 'is_vip' in columns
        cur.execute('SELECT user_id, username, invites, downloads_total FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        if not user:
            try:
                if has_balance and has_vip:
                    cur.execute('INSERT INTO users (user_id, balance, is_vip, last_active) VALUES (?, 0, 0, CURRENT_TIMESTAMP)', (user_id,))
                else:
                    cur.execute('INSERT INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)', (user_id,))
                conn.commit()
                logger.info(f"Создан новый пользователь: {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при создании пользователя {user_id}: {e}")
            status_data = {
                'user_id': user_id,
                'is_admin': (user_id == ADMIN_ID),
                'balance': 0,
                'is_vip': False,
                'invites': 0,
                'downloads_total': 0
            }
        else:
            balance = 0
            is_vip = False
            if has_balance:
                cur.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
                bal_result = cur.fetchone()
                balance = bal_result[0] if bal_result else 0
            if has_vip:
                cur.execute('SELECT is_vip FROM users WHERE user_id = ?', (user_id,))
                vip_result = cur.fetchone()
                is_vip = vip_result[0] == 1 if vip_result else False
            status_data = {
                'user_id': user[0],
                'is_admin': (user_id == ADMIN_ID),
                'balance': balance,
                'is_vip': is_vip,
                'invites': user[2] if user[2] is not None else 0,
                'downloads_total': user[3] if user[3] is not None else 0
            }
        conn.close()
        return status_data
    except Exception as e:
        logger.error(f"Ошибка в get_user_status для {user_id}: {e}")
        return {
            'user_id': user_id,
            'is_admin': (user_id == ADMIN_ID),
            'balance': 0,
            'is_vip': False,
            'invites': 0,
            'downloads_total': 0
        }

def add_balance(user_id: int, amount: int, admin_id: int = None):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'balance' not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")
        cur.execute('UPDATE users SET balance = COALESCE(balance, 0) + ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (amount, user_id))
        cur.execute("INSERT INTO balance_history (user_id, amount, action, admin_id) VALUES (?, ?, 'add', ?)", (user_id, amount, admin_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления баланса для {user_id}: {e}")
        return False

def set_user_vip(user_id: int, admin_id: int = None):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0")
        cur.execute('UPDATE users SET is_vip = 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        cur.execute("INSERT INTO balance_history (user_id, action, admin_id) VALUES (?, 'vip_grant', ?)", (user_id, admin_id))
        conn.commit()
        conn.close()
        logger.info(f"VIP статус установлен для пользователя {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка установки VIP статуса для {user_id}: {e}")
        return False

def remove_user_vip(user_id: int, admin_id: int = None):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0")
        cur.execute('UPDATE users SET is_vip = 0, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        cur.execute("INSERT INTO balance_history (user_id, action, admin_id) VALUES (?, 'vip_remove', ?)", (user_id, admin_id))
        conn.commit()
        conn.close()
        logger.info(f"VIP статус снят с пользователя {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка снятия VIP статуса для {user_id}: {e}")
        return False

def increment_download_count(user_id: int, vip_item: bool = False):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cur.fetchone():
            cur.execute('INSERT INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)', (user_id,))
        cur.execute('UPDATE users SET downloads_total = COALESCE(downloads_total, 0) + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("INSERT INTO downloads_log (user_id, item_type, item_id, vip_item) VALUES (?, 'download', 0, ?)", (user_id, 1 if vip_item else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения счётчика для {user_id}: {e}")

def save_user(message: Message):
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        cur.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cur.fetchone()
        if not exists:
            referrer_id = None
            if message.text and message.text.startswith('/start ref_'):
                try:
                    referrer_id = int(message.text.replace('/start ref_', ''))
                    if referrer_id == user_id:
                        referrer_id = None
                except:
                    pass
            cur.execute('INSERT INTO users (user_id, username, first_name, last_name, last_active) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)', (user_id, username, first_name, last_name))
        else:
            cur.execute('UPDATE users SET username=?, first_name=?, last_name=?, last_active=CURRENT_TIMESTAMP WHERE user_id=?', (username, first_name, last_name, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {message.from_user.id}: {e}")

def get_item(table: str, item_id: int, use_temp: bool = False):
    """Получает элемент из указанной таблицы (из основной или временной БД)"""
    try:
        db_path = TEMP_DB_PATH if use_temp and TEMP_DB_PATH.exists() else DB_PATH
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,))
        item = cur.fetchone()
        conn.close()
        if item:
            item_list = list(item)
            for i in range(len(item_list)):
                if isinstance(item_list[i], (int, float, str)) and str(item_list[i]).isdigit():
                    item_list[i] = int(item_list[i])
            return tuple(item_list)
        return item
    except Exception as e:
        logger.error(f"Ошибка получения элемента {table} {item_id}: {e}")
        return None

def get_all_items_paginated(table: str, page: int = 1, per_page: int = 10, vip_filter: str = "all", use_temp: bool = False):
    """Получает элементы с пагинацией из основной или временной БД"""
    try:
        db_path = TEMP_DB_PATH if use_temp and TEMP_DB_PATH.exists() else DB_PATH
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        
        cur.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cur.fetchall()]
        has_vip = 'is_vip' in columns
        
        # Сначала получаем общее количество
        if vip_filter == "vip" and has_vip:
            cur.execute(f'SELECT COUNT(*) FROM {table} WHERE is_vip = 1')
        elif vip_filter == "regular" and has_vip:
            cur.execute(f'SELECT COUNT(*) FROM {table} WHERE is_vip = 0')
        else:
            cur.execute(f'SELECT COUNT(*) FROM {table}')
        total = cur.fetchone()[0]
        
        # Формируем запрос в зависимости от таблицы
        if table == "clients":
            if has_vip:
                if vip_filter == "vip":
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM clients WHERE is_vip = 1 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                elif vip_filter == "regular":
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM clients WHERE is_vip = 0 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                else:
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM clients ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
            else:
                cur.execute('SELECT id, name, full_desc, media, downloads, version, 0 as is_vip FROM clients ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
        
        elif table == "resourcepacks":
            if has_vip:
                if vip_filter == "vip":
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM resourcepacks WHERE is_vip = 1 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                elif vip_filter == "regular":
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM resourcepacks WHERE is_vip = 0 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                else:
                    cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM resourcepacks ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
            else:
                cur.execute('SELECT id, name, full_desc, media, downloads, version, 0 as is_vip FROM resourcepacks ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
        
        elif table == "configs":
            if has_vip:
                if vip_filter == "vip":
                    cur.execute('SELECT id, client_name, client_version, name, full_desc, media, downloads, is_vip FROM configs WHERE is_vip = 1 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                elif vip_filter == "regular":
                    cur.execute('SELECT id, client_name, client_version, name, full_desc, media, downloads, is_vip FROM configs WHERE is_vip = 0 ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
                else:
                    cur.execute('SELECT id, client_name, client_version, name, full_desc, media, downloads, is_vip FROM configs ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
            else:
                cur.execute('SELECT id, client_name, client_version, name, full_desc, media, downloads, 0 as is_vip FROM configs ORDER BY id DESC LIMIT ? OFFSET ?', (per_page, offset))
        
        items = cur.fetchall()
        
        # Конвертируем значения в правильные типы
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 6 and item_list[6] is not None:
                try:
                    item_list[6] = int(item_list[6])
                except (ValueError, TypeError):
                    item_list[6] = 0
            converted_items.append(tuple(item_list))
        
        conn.close()
        
        db_type = "временной" if use_temp else "основной"
        logger.info(f"📊 {table}: найдено {len(items)} элементов из {total} (страница {page}) в {db_type} БД")
        
        return converted_items, total
        
    except Exception as e:
        logger.error(f"Ошибка получения элементов {table}: {e}")
        return [], 0

def delete_item_from_temp(table: str, item_id: int):
    """Удаляет элемент из временной БД"""
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        cur.execute(f'DELETE FROM {table} WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Элемент ID {item_id} удален из временной БД (таблица {table})")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления элемента из временной БД: {e}")
        return False

def update_item_in_temp(table: str, item_id: int, field: str, value):
    """Обновляет поле элемента во временной БД"""
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET {field} = ? WHERE id = ?', (value, item_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ Поле {field} элемента ID {item_id} обновлено во временной БД")
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления элемента во временной БД: {e}")
        return False

def toggle_vip_in_temp(table: str, item_id: int):
    """Переключает VIP статус элемента во временной БД"""
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        
        # Проверяем наличие колонки is_vip
        cur.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' not in columns:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN is_vip INTEGER DEFAULT 0")
        
        cur.execute(f'SELECT is_vip FROM {table} WHERE id = ?', (item_id,))
        result = cur.fetchone()
        if result:
            new_status = 0 if result[0] == 1 else 1
            cur.execute(f'UPDATE {table} SET is_vip = ? WHERE id = ?', (new_status, item_id))
            conn.commit()
            conn.close()
            logger.info(f"✅ VIP статус элемента ID {item_id} переключен на {new_status} во временной БД")
            return new_status == 1
        conn.close()
        return False
    except Exception as e:
        logger.error(f"Ошибка переключения VIP статуса во временной БД: {e}")
        return False

def get_clients_by_version(version, page=1, per_page=10, user_id=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        is_admin = (user_id == ADMIN_ID)
        
        search_version = version.strip()
        
        logger.info(f"🔍 Поиск клиентов по версии: '{search_version}'")
        
        cur.execute("PRAGMA table_info(clients)")
        columns = [col[1] for col in cur.fetchall()]
        has_vip = 'is_vip' in columns
        
        if has_vip:
            cur.execute('SELECT id, name, full_desc, media, downloads, version, is_vip FROM clients WHERE version = ? ORDER BY id DESC LIMIT ? OFFSET ?', 
                       (search_version, per_page, offset))
        else:
            cur.execute('SELECT id, name, full_desc, media, downloads, version, 0 as is_vip FROM clients WHERE version = ? ORDER BY id DESC LIMIT ? OFFSET ?', 
                       (search_version, per_page, offset))
        
        items = cur.fetchall()
        
        cur.execute('SELECT COUNT(*) FROM clients WHERE version = ?', (search_version,))
        total = cur.fetchone()[0]
        
        logger.info(f"📊 Найдено клиентов: {len(items)} из {total}")
        
        if len(items) == 0:
            cur.execute("SELECT id, name, version FROM clients WHERE LOWER(version) = LOWER(?)", (search_version,))
            alternative = cur.fetchall()
            if alternative:
                logger.info(f"✅ Найдено по LOWER совпадению: {alternative}")
                ids = [str(a[0]) for a in alternative]
                if has_vip:
                    cur.execute(f'SELECT id, name, full_desc, media, downloads, version, is_vip FROM clients WHERE id IN ({",".join(ids)}) ORDER BY id DESC')
                else:
                    cur.execute(f'SELECT id, name, full_desc, media, downloads, version, 0 as is_vip FROM clients WHERE id IN ({",".join(ids)}) ORDER BY id DESC')
                items = cur.fetchall()
                total = len(items)
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                try:
                    item_list[4] = int(item_list[4])
                except:
                    item_list[4] = 0
            converted_items.append(tuple(item_list))
        
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения клиентов по версии {version}: {e}")
        return [], 0

def get_all_client_versions(user_id=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        
        cur.execute('SELECT DISTINCT version FROM clients WHERE version IS NOT NULL AND version != ""')
        versions = []
        for v in cur.fetchall():
            clean_version = v[0].strip()
            if clean_version and clean_version not in versions:
                versions.append(clean_version)
        
        if not versions:
            logger.warning("⚠️ Нет версий в БД")
            versions = []
        else:
            versions.sort(reverse=True)
        
        logger.info(f"📋 Найденные версии клиентов: {versions}")
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий клиентов: {e}")
        return []

def get_packs_by_version(version, page=1, per_page=10, user_id=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        is_admin = (user_id == ADMIN_ID)
        cur.execute("PRAGMA table_info(resourcepacks)")
        columns = [col[1] for col in cur.fetchall()]
        has_vip = 'is_vip' in columns
        search_version = version.strip()
        if has_vip:
            if is_admin:
                cur.execute('SELECT id, name, full_desc, media, downloads, likes, views, version, author, is_vip FROM resourcepacks WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?', (search_version, per_page, offset))
                total = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (search_version,)).fetchone()[0]
            else:
                cur.execute('SELECT id, name, full_desc, media, downloads, likes, views, version, author, is_vip FROM resourcepacks WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?', (search_version, per_page, offset))
                total = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (search_version,)).fetchone()[0]
        else:
            cur.execute('SELECT id, name, full_desc, media, downloads, likes, views, version, author, 0 as is_vip FROM resourcepacks WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?', (search_version, per_page, offset))
            total = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE version = ?', (search_version,)).fetchone()[0]
        items = cur.fetchall()
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 4 and item_list[4] is not None:
                try:
                    item_list[4] = int(item_list[4])
                except:
                    item_list[4] = 0
            if len(item_list) > 5 and item_list[5] is not None:
                try:
                    item_list[5] = int(item_list[5])
                except:
                    item_list[5] = 0
            if len(item_list) > 6 and item_list[6] is not None:
                try:
                    item_list[6] = int(item_list[6])
                except:
                    item_list[6] = 0
            converted_items.append(tuple(item_list))
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения ресурспаков по версии {version}: {e}")
        return [], 0

def get_all_pack_versions(user_id=None):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT version FROM resourcepacks WHERE version IS NOT NULL AND version != "" ORDER BY version DESC')
        versions = [v[0] for v in cur.fetchall()]
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий ресурспаков: {e}")
        return []

# ========== НОВЫЕ ФУНКЦИИ ДЛЯ КОНФИГОВ ==========

def get_all_config_clients():
    """Получает список уникальных клиентов, для которых есть конфиги"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT client_name FROM configs ORDER BY client_name')
        clients = [row[0] for row in cur.fetchall()]
        conn.close()
        return clients
    except Exception as e:
        logger.error(f"Ошибка получения списка клиентов для конфигов: {e}")
        return []

def get_config_versions_by_client(client_name: str):
    """Получает список версий для конкретного клиента"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute('SELECT DISTINCT client_version FROM configs WHERE client_name = ? ORDER BY client_version DESC', (client_name,))
        versions = [row[0] for row in cur.fetchall()]
        conn.close()
        return versions
    except Exception as e:
        logger.error(f"Ошибка получения версий конфигов для клиента {client_name}: {e}")
        return []

def get_configs_by_client_and_version(client_name: str, version: str, page: int = 1, per_page: int = 10, user_id: int = None):
    """Получает конфиги для конкретного клиента и версии"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        offset = (page - 1) * per_page
        
        cur.execute('''
            SELECT id, client_name, client_version, name, full_desc, media, download_url, is_vip, downloads, views 
            FROM configs 
            WHERE client_name = ? AND client_version = ? 
            ORDER BY id DESC LIMIT ? OFFSET ?
        ''', (client_name, version, per_page, offset))
        
        items = cur.fetchall()
        
        cur.execute('SELECT COUNT(*) FROM configs WHERE client_name = ? AND client_version = ?', (client_name, version))
        total = cur.fetchone()[0]
        
        converted_items = []
        for item in items:
            item_list = list(item)
            if len(item_list) > 8 and item_list[8] is not None:
                try:
                    item_list[8] = int(item_list[8])
                except:
                    item_list[8] = 0
            converted_items.append(tuple(item_list))
        
        conn.close()
        return converted_items, total
    except Exception as e:
        logger.error(f"Ошибка получения конфигов: {e}")
        return [], 0

def add_config(client_name: str, client_version: str, name: str, full_desc: str, url: str, is_vip: int = 0, media: list = None):
    """Добавляет конфиг во временную БД"""
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return None
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        
        if media is None:
            media = []
        media_json = json.dumps(media)
        
        cur.execute('''
            INSERT INTO configs (client_name, client_version, name, full_desc, download_url, is_vip, media) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (client_name, client_version, name, full_desc, url, is_vip, media_json))
        
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        logger.info(f"✅ Конфиг добавлен во временную БД: ID={item_id}, name={name}")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления конфига: {e}")
        return None

def update_config(item_id: int, field: str, value):
    return update_item_in_temp("configs", item_id, field, value)

def update_config_media(item_id: int, media_list: list):
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        if media_list is None:
            media_list = []
        media_json = json.dumps(media_list)
        cur.execute('UPDATE configs SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа конфига {item_id}: {e}")
        return False

def add_client(name, full_desc, url, version, is_vip=0, media=None):
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return None
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        
        if media is None:
            media = []
        media_json = json.dumps(media)
        
        if not version or version.strip() == "":
            version = "1.20"
        else:
            version = version.strip()
            version = version.rstrip('.')
        
        cur.execute("PRAGMA table_info(clients)")
        columns = [col[1] for col in cur.fetchall()]
        
        if 'is_vip' in columns:
            cur.execute('INSERT INTO clients (name, full_desc, download_url, version, is_vip, media) VALUES (?, ?, ?, ?, ?, ?)', 
                       (name, full_desc, url, version, is_vip, media_json))
        else:
            cur.execute('INSERT INTO clients (name, full_desc, download_url, version, media) VALUES (?, ?, ?, ?, ?)', 
                       (name, full_desc, url, version, media_json))
        
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        
        logger.info(f"✅ Клиент добавлен во временную БД: ID={item_id}, name={name}, version='{version}'")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления клиента: {e}")
        return None

def update_client(item_id, field, value):
    return update_item_in_temp("clients", item_id, field, value)

def update_client_media(item_id: int, media_list: list):
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        if media_list is None:
            media_list = []
        media_json = json.dumps(media_list)
        cur.execute('UPDATE clients SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа клиента {item_id}: {e}")
        return False

def add_pack(name, full_desc, url, version, author, is_vip=0, media=None):
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return None
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        
        if media is None:
            media = []
        media_json = json.dumps(media)
        
        if not version or version.strip() == "":
            version = "1.20"
        version = version.strip()
        
        cur.execute("PRAGMA table_info(resourcepacks)")
        columns = [col[1] for col in cur.fetchall()]
        
        if 'is_vip' in columns:
            cur.execute('INSERT INTO resourcepacks (name, full_desc, download_url, version, author, is_vip, media) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                       (name, full_desc, url, version, author, is_vip, media_json))
        else:
            cur.execute('INSERT INTO resourcepacks (name, full_desc, download_url, version, author, media) VALUES (?, ?, ?, ?, ?, ?)', 
                       (name, full_desc, url, version, author, media_json))
        
        conn.commit()
        item_id = cur.lastrowid
        conn.close()
        logger.info(f"✅ Ресурспак добавлен во временную БД: ID={item_id}, name={name}")
        return item_id
    except Exception as e:
        logger.error(f"Ошибка добавления ресурспака: {e}")
        return None

def update_pack(item_id, field, value):
    return update_item_in_temp("resourcepacks", item_id, field, value)

def update_pack_media(item_id: int, media_list: list):
    try:
        if not TEMP_DB_PATH.exists():
            logger.error("Временная БД не существует")
            return False
            
        conn = sqlite3.connect(str(TEMP_DB_PATH))
        cur = conn.cursor()
        if media_list is None:
            media_list = []
        media_json = json.dumps(media_list)
        cur.execute('UPDATE resourcepacks SET media = ? WHERE id = ?', (media_json, item_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления медиа ресурспака {item_id}: {e}")
        return False

def toggle_favorite(user_id, pack_id):
    try:
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
    except Exception as e:
        logger.error(f"Ошибка переключения избранного: {e}")
        return False

def get_favorites(user_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(resourcepacks)")
        columns = [col[1] for col in cur.fetchall()]
        has_vip = 'is_vip' in columns
        if has_vip:
            cur.execute('SELECT r.id, r.name, r.full_desc, r.media, r.downloads, r.likes, r.is_vip FROM resourcepacks r JOIN favorites f ON r.id = f.pack_id WHERE f.user_id = ? ORDER BY f.added_at DESC', (user_id,))
        else:
            cur.execute('SELECT r.id, r.name, r.full_desc, r.media, r.downloads, r.likes, 0 as is_vip FROM resourcepacks r JOIN favorites f ON r.id = f.pack_id WHERE f.user_id = ? ORDER BY f.added_at DESC', (user_id,))
        favs = cur.fetchall()
        converted_favs = []
        for fav in favs:
            fav_list = list(fav)
            if len(fav_list) > 4 and fav_list[4] is not None:
                try:
                    fav_list[4] = int(fav_list[4])
                except:
                    fav_list[4] = 0
            if len(fav_list) > 5 and fav_list[5] is not None:
                try:
                    fav_list[5] = int(fav_list[5])
                except:
                    fav_list[5] = 0
            converted_favs.append(tuple(fav_list))
        conn.close()
        return converted_favs
    except Exception as e:
        logger.error(f"Ошибка получения избранного: {e}")
        return []

def increment_view(table, item_id):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения просмотров: {e}")

def increment_download(table, item_id, vip_item=False):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка увеличения скачиваний: {e}")

def format_number(num):
    if num is None:
        return "0"
    try:
        if isinstance(num, str):
            if num.isdigit():
                num = int(num)
            else:
                try:
                    num = int(float(num))
                except:
                    return "0"
        num = int(num)
        if num < 1000:
            return str(num)
        elif num < 1000000:
            return f"{num/1000:.1f}K"
        else:
            return f"{num/1000000:.1f}M"
    except:
        return "0"

def get_main_keyboard(is_admin=False, is_vip=False):
    buttons = [
        [types.KeyboardButton(text="🎮 Клиенты"), types.KeyboardButton(text="🎨 Ресурспаки")],
        [types.KeyboardButton(text="❤️ Избранное"), types.KeyboardButton(text="⚙️ Конфиги"), types.KeyboardButton(text="👤 Профиль")],
        [types.KeyboardButton(text="💎 VIP"), types.KeyboardButton(text="ℹ️ Инфо"), types.KeyboardButton(text="❓ Помощь")]
    ]
    if is_admin:
        buttons.append([types.KeyboardButton(text="⚙️ Админ панель")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

class AdminStates(StatesGroup):
    client_name = State()
    client_full_desc = State()
    client_version = State()
    client_url = State()
    client_media = State()
    client_vip = State()
    
    pack_name = State()
    pack_full_desc = State()
    pack_version = State()
    pack_author = State()
    pack_url = State()
    pack_media = State()
    pack_vip = State()
    
    # Состояния для конфигов
    config_client_name = State()
    config_client_version = State()
    config_name = State()
    config_full_desc = State()
    config_url = State()
    config_media = State()
    config_vip = State()
    
    edit_value = State()
    edit_media = State()
    broadcast_text = State()
    broadcast_photo = State()
    waiting_for_backup = State()
    
    balance_user_id = State()
    balance_amount = State()
    vip_user_id = State()
    
    edit_session_active = State()
    edit_item_id = State()
    edit_category = State()
    edit_media_list = State()

def get_version_keyboard(versions, category, user_id=None):
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

def get_items_keyboard(items, category, page, total_pages, show_vip=False):
    buttons = []
    for item in items:
        if category == "configs":
            # Для конфигов другая структура
            item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
            try:
                media_list = json.loads(media_json) if media_json else []
            except:
                media_list = []
            preview = "🖼️" if media_list else "📄"
            vip_icon = "💎 " if is_vip and show_vip else ""
            button_text = f"{preview} {vip_icon}{name[:30]} (v{client_version})\n📥 {format_number(downloads)}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"detail_configs_{item_id}")])
        else:
            item_id, name, full_desc, media_json, downloads = item[0], item[1], item[2], item[3], item[4]
            version = item[5] if len(item) > 5 else "?"
            is_vip = item[6] if len(item) > 6 else 0
            try:
                media_list = json.loads(media_json) if media_json else []
            except:
                media_list = []
            preview = "🖼️" if media_list else "📄"
            vip_icon = "💎 " if is_vip and show_vip else ""
            button_text = f"{preview} {vip_icon}{name[:30]} ({version})\n📥 {format_number(downloads)}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"detail_{category}_{item_id}")])
    
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{category}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{category}_{page+1}"))
    if nav_row: buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_detail_keyboard(category, item_id, is_favorite=False, is_vip=False, user_is_vip=False, user_is_admin=False):
    buttons = []
    can_download = not is_vip or user_is_vip or user_is_admin
    if category == "packs":
        fav_text = "❤️" if is_favorite else "🤍"
        if can_download:
            buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_{category}_{item_id}"), InlineKeyboardButton(text=fav_text, callback_data=f"fav_{category}_{item_id}")])
        else:
            buttons.append([InlineKeyboardButton(text="💎 VIP Only", callback_data="vip_only"), InlineKeyboardButton(text=fav_text, callback_data=f"fav_{category}_{item_id}")])
    else:
        if can_download:
            buttons.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"download_{category}_{item_id}")])
        else:
            buttons.append([InlineKeyboardButton(text="💎 VIP Only", callback_data="vip_only")])
    buttons.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_{category}_{item_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_main_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎮 Клиенты", callback_data="admin_clients")],
        [InlineKeyboardButton(text="🎨 Ресурспаки", callback_data="admin_packs")],
        [InlineKeyboardButton(text="⚙️ Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton(text="👑 VIP управление", callback_data="admin_vip")],
        [InlineKeyboardButton(text="📦 ZIP Бэкапы", callback_data="admin_zip_backups")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_list_keyboard(items, category, page, total_pages, action):
    """Создает клавиатуру со списком элементов для админки"""
    buttons = []
    for item in items:
        if category == "configs":
            item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
            vip_icon = "💎 " if is_vip else ""
            button_text = f"{item_id}. {vip_icon}{name[:30]} ({client_name} v{client_version}) 📥 {downloads}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"{action}_{category}_{item_id}")])
        else:
            item_id, name, full_desc, media_json, downloads, version, is_vip = item
            vip_icon = "💎 " if is_vip else ""
            button_text = f"{item_id}. {vip_icon}{name[:30]} ({version}) 📥 {downloads}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"{action}_{category}_{item_id}")])
    
    # Навигация по страницам
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"list_page_{category}_{action}_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"list_page_{category}_{action}_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_item_keyboard(category, item_id, media_count=0, is_vip=False):
    """Создает клавиатуру для редактирования элемента"""
    vip_status = "💎 VIP" if is_vip else "🔘 Обычный"
    
    if category == "clients":
        fields = [
            [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_field_{category}_name_{item_id}")],
            [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_field_{category}_full_desc_{item_id}")],
            [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_field_{category}_version_{item_id}")],
            [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_field_{category}_download_url_{item_id}")],
            [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_media_{category}_{item_id}")],
            [InlineKeyboardButton(text=f"{vip_status}", callback_data=f"toggle_vip_{category}_{item_id}")],
            [InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_{category}")],
            [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_{category}")],
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data=f"edit_{category}_list")]
        ]
    elif category == "packs":
        fields = [
            [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_field_{category}_name_{item_id}")],
            [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_field_{category}_full_desc_{item_id}")],
            [InlineKeyboardButton(text="🔢 Версия", callback_data=f"edit_field_{category}_version_{item_id}")],
            [InlineKeyboardButton(text="✍️ Автор", callback_data=f"edit_field_{category}_author_{item_id}")],
            [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_field_{category}_download_url_{item_id}")],
            [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_media_{category}_{item_id}")],
            [InlineKeyboardButton(text=f"{vip_status}", callback_data=f"toggle_vip_{category}_{item_id}")],
            [InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_{category}")],
            [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_{category}")],
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data=f"edit_{category}_list")]
        ]
    else:  # configs
        fields = [
            [InlineKeyboardButton(text="📝 Название конфига", callback_data=f"edit_field_{category}_name_{item_id}")],
            [InlineKeyboardButton(text="📚 Описание", callback_data=f"edit_field_{category}_full_desc_{item_id}")],
            [InlineKeyboardButton(text="🎮 Клиент", callback_data=f"edit_field_{category}_client_name_{item_id}")],
            [InlineKeyboardButton(text="🔢 Версия клиента", callback_data=f"edit_field_{category}_client_version_{item_id}")],
            [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"edit_field_{category}_download_url_{item_id}")],
            [InlineKeyboardButton(text=f"🖼️ Фото ({media_count})", callback_data=f"edit_media_{category}_{item_id}")],
            [InlineKeyboardButton(text=f"{vip_status}", callback_data=f"toggle_vip_{category}_{item_id}")],
            [InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_{category}")],
            [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_{category}")],
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data=f"edit_{category}_list")]
        ]
    
    return InlineKeyboardMarkup(inline_keyboard=fields)

def get_edit_media_keyboard(category, item_id):
    buttons = [
        [InlineKeyboardButton(text="📸 Добавить фото", callback_data=f"add_media_{category}_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить все фото", callback_data=f"del_media_{category}_{item_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_{category}_{item_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_save_cancel_keyboard(category):
    """Клавиатура для сохранения/отмены изменений после добавления"""
    buttons = [
        [InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_{category}")],
        [InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_{category}")],
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data=f"admin_{category}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_config_clients_keyboard(clients):
    """Клавиатура для выбора клиента из списка конфигов"""
    buttons = []
    row = []
    for client in clients:
        row.append(InlineKeyboardButton(text=client, callback_data=f"config_client_{client}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_config_versions_keyboard(client_name, versions):
    """Клавиатура для выбора версии клиента"""
    buttons = []
    row = []
    for version in versions:
        row.append(InlineKeyboardButton(text=version, callback_data=f"config_version_{client_name}_{version}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад к клиентам", callback_data="config_back_to_clients")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_help_keyboard():
    buttons = [
        [InlineKeyboardButton(text="👤 Связаться с админом", url=f"https://t.me/{CREATOR_USERNAME[1:]}")],
        [InlineKeyboardButton(text="📋 Правила", callback_data="help_rules")],
        [InlineKeyboardButton(text="❓ Часто задаваемые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💎 Получить VIP", url=ADMIN_BOT_LINK)],
        [InlineKeyboardButton(text="📊 История", callback_data="profile_history")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("check_db"))
async def cmd_check_db(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    check_all_clients()
    await message.answer("✅ Диагностика выполнена, проверь логи!")

@dp.message(Command("debug_admin"))
async def debug_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    items, total = get_all_items_paginated("clients", 1)
    text = f"📊 Всего клиентов: {total}\n\n"
    for item in items:
        item_id, name, full_desc, media_json, downloads, version, is_vip = item
        text += f"ID: {item_id}, {name}, версия: {version}, загрузок: {downloads}, VIP: {is_vip}\n"
    
    await message.answer(text)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_status = get_user_status(user_id)
    is_admin = (user_id == ADMIN_ID)
    is_vip = user_status.get('is_vip', False)
    save_user(message)
    welcome_text = "👋 Привет! Я бот-каталог Minecraft\n\n🎮 Клиенты - моды и сборки\n🎨 Ресурспаки - текстурпаки\n❤️ Избранное - сохраняй понравившееся\n⚙️ Конфиги - настройки для клиентов\n👤 Профиль - твой профиль\n💎 VIP - эксклюзивный контент\nℹ️ Инфо - о боте и создателе\n❓ Помощь - связаться с админом\n\n"
    if is_vip:
        welcome_text += "✨ У тебя есть VIP статус! Тебе доступен эксклюзивный контент.\n"
    welcome_text += "Используй кнопки ниже:"
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin, is_vip))

@dp.message(F.text == "🎮 Клиенты")
async def clients_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    versions = get_all_client_versions(user_id)
    if not versions:
        await message.answer("📭 Пока нет клиентов")
        return
    await message.answer("🎮 Выбери версию Minecraft:", reply_markup=get_version_keyboard(versions, "clients", user_id))

@dp.callback_query(lambda c: c.data.startswith("ver_clients_"))
async def clients_version_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    version = callback.data.replace("ver_clients_", "")
    items, total = get_clients_by_version(version, 1, user_id=user_id)
    if not items:
        await callback.message.edit_text(f"❌ Для версии {version} пока нет доступных клиентов", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]))
        await callback.answer()
        return
    total_pages = (total + 9) // 10
    await state.update_data(client_version=version, client_page=1)
    await callback.message.edit_text(f"🎮 Клиенты для версии {version} (стр 1/{total_pages}):", reply_markup=get_items_keyboard(items, "clients", 1, total_pages, show_vip=True))
    await callback.answer()

@dp.message(F.text == "🎨 Ресурспаки")
async def packs_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    versions = get_all_pack_versions(user_id)
    if not versions:
        await message.answer("📭 Пока нет ресурспаков")
        return
    await message.answer("🎨 Выбери версию Minecraft:", reply_markup=get_version_keyboard(versions, "packs", user_id))

@dp.callback_query(lambda c: c.data.startswith("ver_packs_"))
async def packs_version_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    version = callback.data.replace("ver_packs_", "")
    items, total = get_packs_by_version(version, 1, user_id=user_id)
    if not items:
        await callback.message.edit_text(f"❌ Для версии {version} пока нет доступных ресурспаков", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]))
        await callback.answer()
        return
    total_pages = (total + 9) // 10
    await state.update_data(pack_version=version, pack_page=1)
    await callback.message.edit_text(f"🎨 Ресурспаки для версии {version} (стр 1/{total_pages}):", reply_markup=get_items_keyboard(items, "packs", 1, total_pages, show_vip=True))
    await callback.answer()

# ========== НОВАЯ ЛОГИКА ДЛЯ КОНФИГОВ ==========

@dp.message(F.text == "⚙️ Конфиги")
async def configs_menu(message: Message, state: FSMContext):
    """Показывает список клиентов, для которых есть конфиги"""
    clients = get_all_config_clients()
    if not clients:
        await message.answer("📭 Пока нет доступных конфигов")
        return
    
    await message.answer(
        "⚙️ Выбери клиент, для которого нужен конфиг:",
        reply_markup=get_config_clients_keyboard(clients)
    )

@dp.callback_query(lambda c: c.data.startswith("config_client_") and not c.data.startswith("config_client_ver_"))
async def config_client_selected(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора клиента для конфига"""
    client_name = callback.data.replace("config_client_", "")
    
    # Получаем список версий для этого клиента
    versions = get_config_versions_by_client(client_name)
    
    if not versions:
        await callback.message.edit_text(
            f"❌ Для клиента {client_name} пока нет конфигов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="config_back_to_clients")]])
        )
        await callback.answer()
        return
    
    # Если только одна версия, показываем конфиги сразу
    if len(versions) == 1:
        await show_configs_for_client(callback.message, client_name, versions[0], state)
    else:
        # Если несколько версий, спрашиваем какую выбрать
        await callback.message.edit_text(
            f"📌 Выбери версию для {client_name}:",
            reply_markup=get_config_versions_keyboard(client_name, versions)
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("config_version_"))
async def config_version_selected(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора версии клиента"""
    data = callback.data.replace("config_version_", "")
    # Разделяем на клиента и версию (версия может содержать точки)
    parts = data.split("_", 1)
    client_name = parts[0]
    version = parts[1] if len(parts) > 1 else "1.20.4"
    
    await show_configs_for_client(callback.message, client_name, version, state)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "config_back_to_clients")
async def config_back_to_clients(callback: CallbackQuery):
    """Возврат к списку клиентов"""
    clients = get_all_config_clients()
    if not clients:
        await callback.message.edit_text("📭 Пока нет доступных конфигов")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "⚙️ Выбери клиент, для которого нужен конфиг:",
        reply_markup=get_config_clients_keyboard(clients)
    )
    await callback.answer()

async def show_configs_for_client(message: Message, client_name: str, version: str, state: FSMContext):
    """Показывает конфиги для конкретного клиента и версии"""
    user_id = message.chat.id
    
    items, total = get_configs_by_client_and_version(client_name, version, 1, user_id=user_id)
    
    if not items:
        await message.edit_text(
            f"❌ Для {client_name} версии {version} пока нет конфигов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="config_back_to_clients")]])
        )
        return
    
    total_pages = (total + 9) // 10
    await state.update_data(config_client_name=client_name, config_version=version, config_page=1)
    
    await message.edit_text(
        f"⚙️ Конфиги для {client_name} (версия {version}) (стр 1/{total_pages}):",
        reply_markup=get_items_keyboard(items, "configs", 1, total_pages, show_vip=True)
    )

# ========== ДЕТАЛЬНЫЙ ПРОСМОТР КОНФИГА ==========

@dp.callback_query(lambda c: c.data.startswith("detail_configs_"))
async def config_detail_view(callback: CallbackQuery, state: FSMContext):
    """Детальный просмотр конфига"""
    item_id = int(callback.data.replace("detail_configs_", ""))
    user_id = callback.from_user.id
    
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    is_admin = (user_id == ADMIN_ID)
    user_status = get_user_status(user_id)
    is_vip = user_status.get('is_vip', False)
    
    # item: id, client_name, client_version, name, full_desc, media, download_url, is_vip, downloads, views, created_at
    client_name = item[1]
    client_version = item[2]
    name = item[3]
    full_desc = item[4]
    media = item[5]
    download_url = item[6]
    item_is_vip = item[7] == 1
    downloads = int(item[8]) if item[8] else 0
    views = int(item[9]) if item[9] else 0
    
    try:
        media_list = json.loads(media) if media else []
    except:
        media_list = []
    
    vip_text = "💎 VIP\n\n" if item_is_vip else ""
    text = f"⚙️ {name}\n\nДля клиента: {client_name} (версия {client_version})\n\n{vip_text}{full_desc}\n\n📥 Скачиваний: {format_number(downloads)}\n👁 Просмотров: {format_number(views)}"
    
    increment_view("configs", item_id)
    
    if media_list and media_list[0]['type'] == 'photo':
        try:
            await callback.message.answer_photo(
                photo=media_list[0]['id'], 
                caption=text, 
                reply_markup=get_detail_keyboard("configs", item_id, False, item_is_vip, is_vip, is_admin)
            )
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await callback.message.edit_text(
                text + "\n\n❌ Фото недоступно", 
                reply_markup=get_detail_keyboard("configs", item_id, False, item_is_vip, is_vip, is_admin)
            )
    else:
        await callback.message.edit_text(
            text, 
            reply_markup=get_detail_keyboard("configs", item_id, False, item_is_vip, is_vip, is_admin)
        )
    
    await callback.answer()

# ========== ПАГИНАЦИЯ ДЛЯ КОНФИГОВ ==========

@dp.callback_query(lambda c: c.data.startswith("page_configs_"))
async def config_pagination(callback: CallbackQuery, state: FSMContext):
    """Пагинация для списка конфигов"""
    page = int(callback.data.replace("page_configs_", ""))
    data = await state.get_data()
    
    client_name = data.get("config_client_name")
    version = data.get("config_version")
    user_id = callback.from_user.id
    
    if not client_name or not version:
        await config_back_to_clients(callback)
        return
    
    items, total = get_configs_by_client_and_version(client_name, version, page, user_id=user_id)
    
    if total == 0:
        await callback.message.edit_text(f"⚙️ Нет конфигов для {client_name} версии {version}")
        await callback.answer()
        return
    
    total_pages = max(1, (total + 9) // 10)
    await state.update_data(config_page=page)
    
    await callback.message.edit_text(
        f"⚙️ Конфиги для {client_name} (версия {version}) (стр {page}/{total_pages}):",
        reply_markup=get_items_keyboard(items, "configs", page, total_pages, show_vip=True)
    )
    await callback.answer()

# ========== НАЗАД К СПИСКУ КОНФИГОВ ==========

@dp.callback_query(lambda c: c.data == "back_configs")
async def back_to_configs(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку конфигов"""
    data = await state.get_data()
    
    client_name = data.get("config_client_name")
    version = data.get("config_version")
    user_id = callback.from_user.id
    
    if not client_name or not version:
        await config_back_to_clients(callback)
        return
    
    items, total = get_configs_by_client_and_version(client_name, version, 1, user_id=user_id)
    
    if total == 0:
        await callback.message.edit_text(
            f"⚙️ Нет конфигов для {client_name} версии {version}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="config_back_to_clients")]])
        )
        await callback.answer()
        return
    
    total_pages = max(1, (total + 9) // 10)
    await state.update_data(config_page=1)
    
    try:
        await callback.message.edit_text(
            f"⚙️ Конфиги для {client_name} (версия {version}) (стр 1/{total_pages}):",
            reply_markup=get_items_keyboard(items, "configs", 1, total_pages, show_vip=True)
        )
    except TelegramBadRequest as e:
        if "there is no text in the message to edit" in str(e):
            await callback.message.delete()
            await callback.message.answer(
                f"⚙️ Конфиги для {client_name} (версия {version}) (стр 1/{total_pages}):",
                reply_markup=get_items_keyboard(items, "configs", 1, total_pages, show_vip=True)
            )
        else:
            logger.error(f"Ошибка при возврате к списку конфигов: {e}")
            await callback.message.answer(
                f"⚙️ Конфиги для {client_name} (версия {version}) (стр 1/{total_pages}):",
                reply_markup=get_items_keyboard(items, "configs", 1, total_pages, show_vip=True)
            )
    
    await callback.answer()

# ========== СКАЧИВАНИЕ КОНФИГА ==========

@dp.callback_query(lambda c: c.data.startswith("download_configs_"))
async def download_config(callback: CallbackQuery):
    """Скачивание конфига"""
    item_id = int(callback.data.replace("download_configs_", ""))
    user_id = callback.from_user.id
    
    item = get_item("configs", item_id)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    is_admin = (user_id == ADMIN_ID)
    user_status = get_user_status(user_id)
    is_vip = user_status.get('is_vip', False)
    
    name = item[3]
    download_url = item[6]
    item_is_vip = item[7] == 1
    
    if item_is_vip and not is_vip and not is_admin:
        await callback.answer("💎 Это VIP контент! Получи VIP статус у админа", show_alert=True)
        return
    
    increment_download("configs", item_id, item_is_vip)
    increment_download_count(user_id, item_is_vip)
    
    vip_prefix = "💎 " if item_is_vip else ""
    await callback.message.answer(f"📥 Скачать {vip_prefix}{name}\n\n{download_url}")
    await callback.answer("✅ Ссылка отправлена!")

# ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ==========

@dp.message(F.text == "💎 VIP")
async def vip_menu(message: Message):
    user_id = message.from_user.id
    user_status = get_user_status(user_id)
    is_vip = user_status.get('is_vip', False)
    text = "💎 VIP раздел\n\n"
    if is_vip:
        text += "✅ У тебя есть VIP статус!\n\nТебе доступен эксклюзивный контент:\n• 💎 VIP клиенты\n• 💎 VIP ресурспаки\n• 💎 VIP конфиги\n\nПросто выбери нужную категорию в главном меню!"
    else:
        text += "❌ У тебя нет VIP статуса\n\nVIP статус дает доступ к эксклюзивному контенту:\n• 💎 VIP клиенты\n• 💎 VIP ресурспаки\n• 💎 VIP конфиги\n\nСвяжись с админом для получения VIP:"
    buttons = []
    if not is_vip:
        buttons.append([InlineKeyboardButton(text="💎 Получить VIP", url=ADMIN_BOT_LINK)])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data == "vip_only")
async def vip_only(callback: CallbackQuery):
    await callback.answer("💎 Это VIP контент! Получи VIP статус у админа", show_alert=True)

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "пользователь"
        status_data = get_user_status(user_id)
        if user_id == ADMIN_ID:
            status_text = "👑 СОЗДАТЕЛЬ"
        elif status_data.get('is_vip', False):
            status_text = "💎 VIP"
        else:
            status_text = "👤 ПОЛЬЗОВАТЕЛЬ"
        bot_info = await bot.me()
        bot_username = bot_info.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        text = f"👋 Привет, {first_name}!\n\nТвой профиль:\n• Статус: {status_text}\n• ID: {user_id}\n• Всего скачиваний: {status_data.get('downloads_total', 0)}\n• Приглашено друзей: {status_data.get('invites', 0)}\n\nТвоя реферальная ссылка:\n{ref_link}"
        await message.answer(text, reply_markup=get_profile_keyboard())
    except Exception as e:
        logger.error(f"Ошибка в профиле: {e}")
        await message.answer("👋 Привет!")

@dp.callback_query(lambda c: c.data == "profile_history")
async def profile_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='downloads_log'")
        if cur.fetchone():
            downloads = cur.execute('SELECT item_type, downloaded_at FROM downloads_log WHERE user_id = ? ORDER BY downloaded_at DESC LIMIT 10', (user_id,)).fetchall()
        else:
            downloads = []
        conn.close()
        if not downloads:
            text = "📭 История скачиваний пуста"
        else:
            text = "📊 Последние скачивания:\n\n"
            for item_type, date in downloads:
                text += f"• {item_type} - {date[:10] if date else 'недавно'}\n"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")]]))
    except Exception as e:
        logger.error(f"Ошибка истории: {e}")
        await callback.message.edit_text("❌ Ошибка загрузки истории")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    await show_profile(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("page_") and not c.data.startswith("page_configs_"))
async def pagination(callback: CallbackQuery, state: FSMContext):
    _, category, page = callback.data.split("_")
    page = int(page)
    data = await state.get_data()
    user_id = callback.from_user.id
    
    if category == "clients":
        version = data.get("client_version", "1.20")
        items, total = get_clients_by_version(version, page, user_id=user_id)
        if total == 0:
            await callback.message.edit_text(f"🎮 Нет клиентов для версии {version}")
            await callback.answer()
            return
        title = f"🎮 Клиенты для версии {version}"
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        items, total = get_packs_by_version(version, page, user_id=user_id)
        if total == 0:
            await callback.message.edit_text(f"🎨 Нет ресурспаков для версии {version}")
            await callback.answer()
            return
        title = f"🎨 Ресурспаки для версии {version}"
    else:
        await callback.answer()
        return
    
    total_pages = max(1, (total + 9) // 10)
    await state.update_data({f"{category}_page": page})
    await callback.message.edit_text(f"{title} (стр {page}/{total_pages}):", reply_markup=get_items_keyboard(items, category, page, total_pages, show_vip=True))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("detail_") and not c.data.startswith("detail_configs_"))
async def detail_view(callback: CallbackQuery, state: FSMContext):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    user_id = callback.from_user.id
    
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    
    logger.info(f"📋 Детальный просмотр: {category} ID={item_id}, данные={item}")
    
    is_admin = (user_id == ADMIN_ID)
    user_status = get_user_status(user_id)
    is_vip = user_status.get('is_vip', False)
    
    if category == "clients":
        name = item[1]
        full_desc = item[2]
        media = item[3]
        download_url = item[4]
        version = item[5]
        item_is_vip = item[6] == 1 if len(item) > 6 else False
        downloads = int(item[7]) if len(item) > 7 and item[7] else 0
        views = int(item[8]) if len(item) > 8 and item[8] else 0
        
        try:
            media_list = json.loads(media) if media else []
        except:
            media_list = []
        
        vip_text = "💎 VIP\n\n" if item_is_vip else ""
        text = f"🎮 {name}\n\n{vip_text}{full_desc}\n\nВерсия: {version}\n📥 Скачиваний: {format_number(downloads)}\n👁 Просмотров: {format_number(views)}"
    
    elif category == "packs":
        name = item[1]
        full_desc = item[2]
        media = item[3]
        download_url = item[4]
        version = item[5]
        author = item[6] if len(item) > 6 else "Неизвестен"
        item_is_vip = item[7] == 1 if len(item) > 7 else False
        downloads = int(item[8]) if len(item) > 8 and item[8] else 0
        likes = int(item[9]) if len(item) > 9 and item[9] else 0
        views = int(item[10]) if len(item) > 10 and item[10] else 0
        
        try:
            media_list = json.loads(media) if media else []
        except:
            media_list = []
        
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        is_fav = cur.execute('SELECT 1 FROM favorites WHERE user_id = ? AND pack_id = ?', (callback.from_user.id, item_id)).fetchone()
        conn.close()
        
        vip_text = "💎 VIP\n\n" if item_is_vip else ""
        text = f"🎨 {name}\n\n{vip_text}{full_desc}\n\nАвтор: {author}\nВерсия: {version}\n📥 Скачиваний: {format_number(downloads)}\n❤️ В избранном: {format_number(likes)}\n👁 Просмотров: {format_number(views)}"
    
    increment_view(category, item_id)
    
    if media_list and media_list[0]['type'] == 'photo':
        try:
            await callback.message.answer_photo(photo=media_list[0]['id'], caption=text, reply_markup=get_detail_keyboard(category, item_id, is_fav if category == 'packs' else False, item_is_vip, is_vip, is_admin))
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await callback.message.edit_text(text + "\n\n❌ Фото недоступно", reply_markup=get_detail_keyboard(category, item_id, is_fav if category == 'packs' else False, item_is_vip, is_vip, is_admin))
    else:
        await callback.message.edit_text(text, reply_markup=get_detail_keyboard(category, item_id, is_fav if category == 'packs' else False, item_is_vip, is_vip, is_admin))
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("back_") and not c.data.startswith("back_to_") and c.data != "back_configs")
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("back_", "")
    data = await state.get_data()
    user_id = callback.from_user.id
    
    if category == "clients":
        version = data.get("client_version", "1.20")
        items, total = get_clients_by_version(version, 1, user_id=user_id)
        if total == 0:
            try:
                await callback.message.edit_text(f"🎮 Нет клиентов для версии {version}")
            except TelegramBadRequest:
                await callback.message.delete()
                await callback.message.answer(f"🎮 Нет клиентов для версии {version}")
            await callback.answer()
            return
        title = f"🎮 Клиенты для версии {version}"
        page = 1
    elif category == "packs":
        version = data.get("pack_version", "1.20")
        items, total = get_packs_by_version(version, 1, user_id=user_id)
        if total == 0:
            try:
                await callback.message.edit_text(f"🎨 Нет ресурспаков для версии {version}")
            except TelegramBadRequest:
                await callback.message.delete()
                await callback.message.answer(f"🎨 Нет ресурспаков для версии {version}")
            await callback.answer()
            return
        title = f"🎨 Ресурспаки для версии {version}"
        page = 1
    else:
        await callback.answer()
        return
    
    total_pages = max(1, (total + 9) // 10)
    await state.update_data({f"{category}_page": page})
    
    try:
        await callback.message.edit_text(
            f"{title} (стр {page}/{total_pages}):", 
            reply_markup=get_items_keyboard(items, category, page, total_pages, show_vip=True)
        )
    except TelegramBadRequest as e:
        if "there is no text in the message to edit" in str(e):
            await callback.message.delete()
            await callback.message.answer(
                f"{title} (стр {page}/{total_pages}):", 
                reply_markup=get_items_keyboard(items, category, page, total_pages, show_vip=True)
            )
        else:
            logger.error(f"Ошибка при возврате к списку: {e}")
            await callback.message.answer(
                f"{title} (стр {page}/{total_pages}):", 
                reply_markup=get_items_keyboard(items, category, page, total_pages, show_vip=True)
            )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("download_") and not c.data.startswith("download_configs_"))
async def download_item(callback: CallbackQuery):
    _, category, item_id = callback.data.split("_")
    item_id = int(item_id)
    user_id = callback.from_user.id
    item = get_item(category, item_id)
    if not item:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    is_admin = (user_id == ADMIN_ID)
    user_status = get_user_status(user_id)
    is_vip = user_status.get('is_vip', False)
    
    if category == "clients":
        item_is_vip = item[6] == 1 if len(item) > 6 else False
        url = item[4]
        name = item[1]
    elif category == "packs":
        item_is_vip = item[7] == 1 if len(item) > 7 else False
        url = item[4]
        name = item[1]
    else:
        await callback.answer("❌ Неизвестная категория", show_alert=True)
        return
    
    if item_is_vip and not is_vip and not is_admin:
        await callback.answer("💎 Это VIP контент! Получи VIP статус у админа", show_alert=True)
        return
    
    increment_download(category, item_id, item_is_vip)
    increment_download_count(user_id, item_is_vip)
    
    vip_prefix = "💎 " if item_is_vip else ""
    await callback.message.answer(f"📥 Скачать {vip_prefix}{name}\n\n{url}")
    await callback.answer("✅ Ссылка отправлена!")

@dp.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("❤️ Избранное пусто\n\nДобавляй ресурспаки в избранное кнопкой 🤍")
        return
    text = "❤️ Твоё избранное:\n\n"
    for fav in favs[:10]:
        downloads = int(fav[4]) if fav[4] else 0
        is_vip = fav[6] if len(fav) > 6 else 0
        vip_icon = "💎 " if is_vip else ""
        text += f"• {vip_icon}{fav[1]} - {format_number(downloads)} 📥\n"
    await message.answer(text)

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

@dp.message(F.text == "ℹ️ Инфо")
async def info(message: Message):
    try:
        users_count = get_users_count()
        vip_count = get_vip_users_count()
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        clients_count = cur.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
        cur.execute("PRAGMA table_info(clients)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' in columns:
            vip_clients = cur.execute('SELECT COUNT(*) FROM clients WHERE is_vip = 1').fetchone()[0]
        else:
            vip_clients = 0
        packs_count = cur.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]
        cur.execute("PRAGMA table_info(resourcepacks)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' in columns:
            vip_packs = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE is_vip = 1').fetchone()[0]
        else:
            vip_packs = 0
        configs_count = cur.execute('SELECT COUNT(*) FROM configs').fetchone()[0]
        cur.execute("PRAGMA table_info(configs)")
        columns = [col[1] for col in cur.fetchall()]
        if 'is_vip' in columns:
            vip_configs = cur.execute('SELECT COUNT(*) FROM configs WHERE is_vip = 1').fetchone()[0]
        else:
            vip_configs = 0
        conn.close()
        text = f"ℹ️ Информация о боте\n\nСоздатель: {CREATOR_USERNAME}\nВерсия: 23.0\n\n📊 Статистика:\n• Пользователей: {users_count} (💎 VIP: {vip_count})\n• Клиентов: {clients_count} (💎 VIP: {vip_clients})\n• Ресурспаков: {packs_count} (💎 VIP: {vip_packs})\n• Конфигов: {configs_count} (💎 VIP: {vip_configs})"
        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка в info: {e}")
        await message.answer(f"ℹ️ Информация о боте\n\nСоздатель: {CREATOR_USERNAME}\nВерсия: 23.0")

@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    await message.answer("❓ Помощь и поддержка\n\nЕсли у тебя возникли вопросы:\n\n• Нажми кнопку ниже, чтобы связаться с создателем", reply_markup=get_help_keyboard())

@dp.callback_query(lambda c: c.data == "help_rules")
async def help_rules(callback: CallbackQuery):
    await callback.message.edit_text("📋 Правила использования\n\n1. Все файлы предоставляются 'как есть'\n2. Автор не несёт ответственности за использование файлов\n3. Уважайте других пользователей\n4. VIP контент доступен только после покупки", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help_faq")
async def help_faq(callback: CallbackQuery):
    await callback.message.edit_text("❓ Часто задаваемые вопросы\n\nQ: Как скачать файл?\nA: Нажми на элемент, затем кнопку 'Скачать'\n\nQ: Что такое VIP контент?\nA: Это эксклюзивные файлы, отмеченные значком 💎\n\nQ: Как получить VIP?\nA: Свяжись с админом в разделе 💎 VIP\n\nQ: Как сделать бэкап?\nA: В админ-панели выбери '📦 ZIP Бэкапы' и нажми 'Создать'", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_help")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_help")
async def back_to_help(callback: CallbackQuery):
    await callback.message.edit_text("❓ Помощь и поддержка\n\nЕсли у тебя возникли вопросы:\n\n• Нажми кнопку ниже, чтобы связаться с создателем", reply_markup=get_help_keyboard())
    await callback.answer()

@dp.message(F.text == "⚙️ Админ панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет прав администратора.")
        return
    await message.answer("⚙️ Админ панель\n\nВыбери категорию:", reply_markup=get_admin_main_keyboard())

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.answer("⚙️ Админ панель\n\nВыбери категорию:", reply_markup=get_admin_main_keyboard())
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_vip")
async def admin_vip(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="👑 Список VIP пользователей", callback_data="vip_list")],
        [InlineKeyboardButton(text="➕ Выдать VIP", callback_data="vip_add")],
        [InlineKeyboardButton(text="➖ Снять VIP", callback_data="vip_remove")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("👑 VIP управление\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vip_list")
async def vip_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    users = get_all_users_with_details()
    vip_users = [u for u in users if u[4] == 1]
    if not vip_users:
        await callback.message.edit_text("📭 Нет VIP пользователей", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_vip")]]))
        await callback.answer()
        return
    text = "👑 VIP пользователи:\n\n"
    for user_id, username, first_name, balance, is_vip in vip_users:
        name = first_name or username or str(user_id)
        text += f"• {name} (ID: {user_id})\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_vip")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vip_add")
async def vip_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.vip_user_id)
    await state.update_data(vip_action='add')
    await callback.message.edit_text("➕ Выдача VIP статуса\n\nВведи ID пользователя:\n\n❌ Отмена: /cancel")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "vip_remove")
async def vip_remove_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.vip_user_id)
    await state.update_data(vip_action='remove')
    await callback.message.edit_text("➖ Снятие VIP статуса\n\nВведи ID пользователя:\n\n❌ Отмена: /cancel")
    await callback.answer()

@dp.message(AdminStates.vip_user_id)
async def vip_handle_user_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Операция отменена")
        return
    try:
        user_id = int(message.text.strip())
    except:
        await message.answer("❌ Неверный ID. Введи число или /cancel")
        return
    data = await state.get_data()
    action = data.get('vip_action', 'add')
    if action == 'add':
        success = set_user_vip(user_id, ADMIN_ID)
        if success:
            await message.answer(f"✅ VIP статус выдан пользователю {user_id}!")
        else:
            await message.answer("❌ Ошибка при выдаче VIP статуса")
    else:
        success = remove_user_vip(user_id, ADMIN_ID)
        if success:
            await message.answer(f"✅ VIP статус снят с пользователя {user_id}!")
        else:
            await message.answer("❌ Ошибка при снятии VIP статуса")
    await state.clear()

# ========== УПРАВЛЕНИЕ КЛИЕНТАМИ ==========
@dp.callback_query(lambda c: c.data == "admin_clients")
async def admin_clients(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить клиента", callback_data="add_client")],
        [InlineKeyboardButton(text="✏️ Редактировать клиента", callback_data="edit_clients_list")],
        [InlineKeyboardButton(text="🗑 Удалить клиента", callback_data="delete_clients_list")],
        [InlineKeyboardButton(text="💎 Переключить VIP", callback_data="toggle_vip_clients")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("🎮 Управление клиентами\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_packs")
async def admin_packs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить ресурспак", callback_data="add_pack")],
        [InlineKeyboardButton(text="✏️ Редактировать ресурспак", callback_data="edit_packs_list")],
        [InlineKeyboardButton(text="🗑 Удалить ресурспак", callback_data="delete_packs_list")],
        [InlineKeyboardButton(text="💎 Переключить VIP", callback_data="toggle_vip_packs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("🎨 Управление ресурспаками\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== УПРАВЛЕНИЕ КОНФИГАМИ ==========

@dp.callback_query(lambda c: c.data == "admin_configs")
async def admin_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить конфиг", callback_data="add_config_start")],
        [InlineKeyboardButton(text="✏️ Редактировать конфиг", callback_data="edit_configs_list")],
        [InlineKeyboardButton(text="🗑 Удалить конфиг", callback_data="delete_configs_list")],
        [InlineKeyboardButton(text="💎 Переключить VIP", callback_data="toggle_vip_configs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    await callback.message.edit_text("⚙️ Управление конфигами\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ========== ДОБАВЛЕНИЕ КОНФИГА ==========

@dp.callback_query(lambda c: c.data == "add_config_start")
async def add_config_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    # Создаем временную копию БД для добавления
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    await state.set_state(AdminStates.config_client_name)
    await callback.message.edit_text("📝 Введи название клиента, для которого предназначен конфиг:")
    await callback.answer()

@dp.message(AdminStates.config_client_name)
async def config_client_name(message: Message, state: FSMContext):
    await state.update_data(config_client_name=message.text)
    await state.set_state(AdminStates.config_client_version)
    await message.answer("🔢 Введи версию клиента (например 1.20.4):")

@dp.message(AdminStates.config_client_version)
async def config_client_version(message: Message, state: FSMContext):
    await state.update_data(config_client_version=message.text)
    await state.set_state(AdminStates.config_name)
    await message.answer("📝 Введи название конфига:")

@dp.message(AdminStates.config_name)
async def config_name(message: Message, state: FSMContext):
    await state.update_data(config_name=message.text)
    await state.set_state(AdminStates.config_full_desc)
    await message.answer("📚 Введи полное описание конфига:")

@dp.message(AdminStates.config_full_desc)
async def config_full_desc(message: Message, state: FSMContext):
    await state.update_data(config_full_desc=message.text)
    await state.set_state(AdminStates.config_url)
    await message.answer("🔗 Введи ссылку на скачивание:")

@dp.message(AdminStates.config_url)
async def config_url(message: Message, state: FSMContext):
    await state.update_data(config_url=message.text)
    await state.set_state(AdminStates.config_vip)
    await message.answer("💎 Это VIP конфиг?\n\nОтветь 'да' или 'нет':")

@dp.message(AdminStates.config_vip)
async def config_vip(message: Message, state: FSMContext):
    is_vip = 1 if message.text.lower() in ['да', 'yes', '1', 'true'] else 0
    await state.update_data(config_vip=is_vip)
    await state.set_state(AdminStates.config_media)
    await message.answer("🖼️ Отправляй фото (можно несколько)\n\nПосле того как отправишь все фото, напиши готово\nИли напиши пропустить чтобы пропустить фото:")

@dp.message(AdminStates.config_media)
async def config_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        client_name = data.get('config_client_name')
        client_version = data.get('config_client_version')
        name = data.get('config_name')
        full_desc = data.get('config_full_desc')
        url = data.get('config_url')
        is_vip = data.get('config_vip', 0)
        
        if not client_version or client_version.strip() == "":
            client_version = "1.20"
        
        item_id = add_config(client_name, client_version, name, full_desc, url, is_vip, media_list)
        await state.clear()
        
        if item_id:
            vip_text = "💎 VIP" if is_vip else "📦 Обычный"
            await message.answer(
                f"✅ Конфиг добавлен во временную БД!\nID: {item_id}\nДля клиента: {client_name} (версия {client_version})\n{vip_text}\nДобавлено фото: {len(media_list)}",
                reply_markup=get_save_cancel_keyboard("configs")
            )
        else:
            await message.answer("❌ Ошибка при добавлении конфига", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.text and message.text.lower() == 'пропустить':
        client_name = data.get('config_client_name')
        client_version = data.get('config_client_version')
        name = data.get('config_name')
        full_desc = data.get('config_full_desc')
        url = data.get('config_url')
        is_vip = data.get('config_vip', 0)
        
        if not client_version or client_version.strip() == "":
            client_version = "1.20"
        
        item_id = add_config(client_name, client_version, name, full_desc, url, is_vip, [])
        await state.clear()
        
        if item_id:
            vip_text = "💎 VIP" if is_vip else "📦 Обычный"
            await message.answer(
                f"✅ Конфиг добавлен во временную БД!\nID: {item_id}\nДля клиента: {client_name} (версия {client_version})\n{vip_text}\nБез фото",
                reply_markup=get_save_cancel_keyboard("configs")
            )
        else:
            await message.answer("❌ Ошибка при добавлении конфига", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        media_list.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=media_list)
        await message.answer(f"✅ Фото добавлено! Всего: {len(media_list)}\nМожешь отправить ещё фото или написать готово")
    else:
        await message.answer("❌ Отправь фото, или напиши готово / пропустить")

# ========== РЕДАКТИРОВАНИЕ КОНФИГОВ ==========

@dp.callback_query(lambda c: c.data == "edit_configs_list")
async def edit_configs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    items, total = get_all_items_paginated("configs", 1, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    logger.info(f"📋 Найдено конфигов для редактирования: {len(items)} из {total}")
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({client_name} v{client_version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_item_configs_{item_id}")])
    
    if total_pages > 1:
        nav_row = []
        nav_row.append(InlineKeyboardButton(text=f"1/{total_pages}", callback_data="noop"))
        if 1 < total_pages:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"edit_configs_page_2"))
        if nav_row:
            buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(
        f"✏️ Редактирование конфигов (всего: {total})\n\nВыбери конфиг для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_configs_page_"))
async def edit_configs_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("edit_configs_page_", ""))
    items, total = get_all_items_paginated("configs", page, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({client_name} v{client_version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_item_configs_{item_id}")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"edit_configs_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"edit_configs_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(
        f"✏️ Редактирование конфигов (стр {page}/{total_pages}):\n\nВыбери конфиг для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("edit_item_configs_"))
async def edit_config_select(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("edit_item_configs_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("configs", item_id, use_temp=True)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    try:
        media_list = json.loads(item[5]) if item[5] else []
        media_count = len(media_list)
    except:
        media_count = 0
    
    is_vip = item[7] == 1 if len(item) > 7 else 0
    
    await state.update_data(edit_item_id=item_id, edit_category="configs")
    
    await callback.message.edit_text(
        f"✏️ Редактирование конфига: {item[3]}\nДля клиента: {item[1]} (версия {item[2]})\n\nЧто изменить?",
        reply_markup=get_edit_item_keyboard("configs", item_id, media_count, is_vip)
    )
    await callback.answer()

# ========== РЕДАКТИРОВАНИЕ ПОЛЕЙ КОНФИГА ==========

@dp.callback_query(lambda c: c.data.startswith("edit_field_configs_"))
async def edit_config_field_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    field = parts[3]
    item_id = int(parts[4])
    
    field_map = {
        'name': 'name',
        'full_desc': 'full_desc',
        'client_name': 'client_name',
        'client_version': 'client_version',
        'download_url': 'download_url'
    }
    
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category="configs")
    await state.set_state(AdminStates.edit_value)
    
    await callback.message.edit_text(f"✏️ Введи новое значение для поля {field}:")
    await callback.answer()

# ========== УДАЛЕНИЕ КОНФИГОВ ==========

@dp.callback_query(lambda c: c.data == "delete_configs_list")
async def delete_configs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    items, total = get_all_items_paginated("configs", 1, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для удаления", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({client_name} v{client_version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"delete_item_configs_{item_id}")])
    
    if total_pages > 1:
        nav_row = []
        nav_row.append(InlineKeyboardButton(text=f"1/{total_pages}", callback_data="noop"))
        if 1 < total_pages:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"delete_configs_page_2"))
        if nav_row:
            buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(
        f"🗑 Выбери конфиг для удаления (всего: {total}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_configs_page_"))
async def delete_configs_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("delete_configs_page_", ""))
    items, total = get_all_items_paginated("configs", page, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для удаления", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({client_name} v{client_version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"delete_item_configs_{item_id}")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"delete_configs_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"delete_configs_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(
        f"🗑 Выбери конфиг для удаления (стр {page}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_item_configs_") and not c.data.startswith("delete_item_configs_confirm_"))
async def delete_config_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("delete_item_configs_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    item = get_item("configs", item_id, use_temp=True)
    if not item:
        await callback.answer("❌ Конфиг не найден", show_alert=True)
        return
    
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_item_configs_confirm_{item_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_configs_list")]
    ]
    
    await callback.message.edit_text(
        f"⚠️ Подтверждение удаления\n\nТы действительно хочешь удалить конфиг:\n{item[3]}\nДля клиента: {item[1]} (версия {item[2]}) (ID: {item_id})?\n\nЭто действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_item_configs_confirm_"))
async def delete_config_execute(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    try:
        item_id = int(callback.data.replace("delete_item_configs_confirm_", ""))
    except ValueError:
        await callback.answer("❌ Неверный ID", show_alert=True)
        return
    
    success = delete_item_from_temp("configs", item_id)
    
    if success:
        await callback.answer("✅ Конфиг удален из временной БД!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка при удалении!", show_alert=True)
    
    await delete_configs_list(callback)

# ========== ПЕРЕКЛЮЧЕНИЕ VIP ДЛЯ КОНФИГОВ ==========

@dp.callback_query(lambda c: c.data.startswith("toggle_vip_configs"))
async def toggle_vip_configs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    if len(parts) == 3:
        # Показ списка конфигов для переключения VIP
        items, total = get_all_items_paginated("configs", 1, 50, use_temp=True)
        total_pages = max(1, (total + 49) // 50)
        
        if not items:
            await callback.message.edit_text(
                "📭 Нет конфигов для переключения VIP", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
            )
            await callback.answer()
            return
        
        buttons = []
        for item in items:
            item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
            status = "💎 VIP" if is_vip else "🔘 Обычный"
            button_text = f"{item_id}. {name[:30]} ({client_name} v{client_version}) - {status}"
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"toggle_vip_configs_{item_id}")])
        
        if total_pages > 1:
            nav_row = []
            nav_row.append(InlineKeyboardButton(text=f"1/{total_pages}", callback_data="noop"))
            if 1 < total_pages:
                nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"toggle_vip_configs_page_2"))
            if nav_row:
                buttons.append(nav_row)
        
        buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
        buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
        
        await callback.message.edit_text(
            f"💎 Переключение VIP статуса для конфигов\n\nВыбери конфиг:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    elif len(parts) >= 4:
        # Переключение конкретного конфига
        item_id = int(parts[3])
        new_status = toggle_vip_in_temp("configs", item_id)
        
        if new_status:
            await callback.answer("✅ Конфиг теперь VIP во временной БД!", show_alert=True)
        else:
            await callback.answer("✅ Конфиг теперь обычный во временной БД!", show_alert=True)
        
        await toggle_vip_configs(callback)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("toggle_vip_configs_page_"))
async def toggle_vip_configs_page(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    page = int(callback.data.replace("toggle_vip_configs_page_", ""))
    items, total = get_all_items_paginated("configs", page, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет конфигов для переключения VIP", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, client_name, client_version, name, full_desc, media_json, downloads, is_vip = item
        status = "💎 VIP" if is_vip else "🔘 Обычный"
        button_text = f"{item_id}. {name[:30]} ({client_name} v{client_version}) - {status}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"toggle_vip_configs_{item_id}")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"toggle_vip_configs_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"toggle_vip_configs_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_configs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_configs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_configs")])
    
    await callback.message.edit_text(
        f"💎 Переключение VIP статуса для конфигов (стр {page}/{total_pages})\n\nВыбери конфиг:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    
    await callback.answer()

# ========== РЕДАКТИРОВАНИЕ КЛИЕНТОВ (кратко) ==========

@dp.callback_query(lambda c: c.data == "edit_clients_list")
async def edit_clients_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]])
        )
        await callback.answer()
        return
    
    items, total = get_all_items_paginated("clients", 1, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет клиентов для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, name, full_desc, media_json, downloads, version, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_item_clients_{item_id}")])
    
    if total_pages > 1:
        nav_row = []
        nav_row.append(InlineKeyboardButton(text=f"1/{total_pages}", callback_data="noop"))
        if 1 < total_pages:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"edit_clients_page_2"))
        if nav_row:
            buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_clients")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_clients")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")])
    
    await callback.message.edit_text(
        f"✏️ Редактирование клиентов (всего: {total})\n\nВыбери клиента для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

# ========== РЕДАКТИРОВАНИЕ РЕСУРСПАКОВ (кратко) ==========

@dp.callback_query(lambda c: c.data == "edit_packs_list")
async def edit_packs_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]])
        )
        await callback.answer()
        return
    
    items, total = get_all_items_paginated("resourcepacks", 1, 50, use_temp=True)
    total_pages = max(1, (total + 49) // 50)
    
    if not items:
        await callback.message.edit_text(
            "📭 Нет ресурспаков для редактирования", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]])
        )
        await callback.answer()
        return
    
    buttons = []
    for item in items:
        item_id, name, full_desc, media_json, downloads, version, is_vip = item
        vip_icon = "💎 " if is_vip else ""
        button_text = f"{item_id}. {vip_icon}{name[:30]} ({version}) 📥 {downloads}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_item_packs_{item_id}")])
    
    if total_pages > 1:
        nav_row = []
        nav_row.append(InlineKeyboardButton(text=f"1/{total_pages}", callback_data="noop"))
        if 1 < total_pages:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"edit_packs_page_2"))
        if nav_row:
            buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(text="✅ СОХРАНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"save_edit_packs")])
    buttons.append([InlineKeyboardButton(text="❌ ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ", callback_data=f"cancel_edit_packs")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")])
    
    await callback.message.edit_text(
        f"✏️ Редактирование ресурспаков (всего: {total})\n\nВыбери ресурспак для редактирования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

# ========== ДОБАВЛЕНИЕ КЛИЕНТА (кратко) ==========

@dp.callback_query(lambda c: c.data == "add_client")
async def add_client_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_clients")]])
        )
        await callback.answer()
        return
    
    await state.set_state(AdminStates.client_name)
    await callback.message.edit_text("📝 Введи название клиента:")
    await callback.answer()

# ========== ДОБАВЛЕНИЕ РЕСУРСПАКА (кратко) ==========

@dp.callback_query(lambda c: c.data == "add_pack")
async def add_pack_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    if not create_temp_db():
        await callback.message.edit_text(
            "❌ Ошибка создания временной копии БД", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_packs")]])
        )
        await callback.answer()
        return
    
    await state.set_state(AdminStates.pack_name)
    await callback.message.edit_text("📝 Введи название ресурспака:")
    await callback.answer()

# ========== ОБЩИЕ ФУНКЦИИ РЕДАКТИРОВАНИЯ ==========

@dp.callback_query(lambda c: c.data.startswith("edit_field_") and not c.data.startswith("edit_field_configs_"))
async def edit_field_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    field = parts[3]
    item_id = int(parts[4])
    
    field_map = {
        'name': 'name',
        'full_desc': 'full_desc',
        'version': 'version',
        'author': 'author',
        'download_url': 'download_url'
    }
    
    db_field = field_map.get(field)
    if not db_field:
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_item_id=item_id, edit_field=db_field, edit_category=category)
    await state.set_state(AdminStates.edit_value)
    
    await callback.message.edit_text(f"✏️ Введи новое значение для поля {field}:")
    await callback.answer()

@dp.message(AdminStates.edit_value)
async def edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get('edit_item_id')
    field = data.get('edit_field')
    category = data.get('edit_category')
    
    if not item_id or not field or not category:
        await message.answer("❌ Ошибка: нет данных для редактирования")
        await state.clear()
        return
    
    success = False
    if category == 'clients':
        success = update_item_in_temp("clients", item_id, field, message.text)
    elif category == 'packs':
        success = update_item_in_temp("resourcepacks", item_id, field, message.text)
    elif category == 'configs':
        success = update_item_in_temp("configs", item_id, field, message.text)
    
    await state.clear()
    
    if success:
        await message.answer("✅ Значение обновлено во временной БД!\n\nНе забудь сохранить изменения кнопкой 'Сохранить и выйти'", reply_markup=get_main_keyboard(is_admin=True))
    else:
        await message.answer("❌ Ошибка при обновлении", reply_markup=get_main_keyboard(is_admin=True))

# ========== РЕДАКТИРОВАНИЕ МЕДИА ==========

@dp.callback_query(lambda c: c.data.startswith("edit_media_"))
async def edit_media_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    item_id = int(parts[3])
    
    item = get_item(category, item_id, use_temp=True)
    if not item:
        await callback.answer("❌ Элемент не найден", show_alert=True)
        return
    
    media_index = 5 if category == "configs" else 3
    
    try:
        media_list = json.loads(item[media_index]) if item[media_index] else []
    except:
        media_list = []
    
    await state.update_data(edit_item_id=item_id, edit_category=category, media_list=media_list)
    await state.set_state(AdminStates.edit_media)
    
    media_count = len(media_list)
    text = f"🖼️ Управление фото для {item[1]}\n\nСейчас фото: {media_count}\n\n"
    if media_count > 0:
        text += "Чтобы удалить все фото, нажми кнопку ниже.\nЧтобы добавить новые, просто отправь фото."
    
    await callback.message.edit_text(text, reply_markup=get_edit_media_keyboard(category, item_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("add_media_"))
async def add_media_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    item_id = int(parts[3])
    
    await state.update_data(edit_item_id=item_id, edit_category=category)
    await callback.message.edit_text("📸 Отправляй фото (можно несколько)\n\nПосле того как отправишь все фото, напиши 'готово'\nИли напиши 'отмена' чтобы выйти")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("del_media_"))
async def delete_media(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    category = parts[2]
    item_id = int(parts[3])
    
    success = False
    if category == "clients":
        success = update_client_media(item_id, [])
    elif category == "packs":
        success = update_pack_media(item_id, [])
    elif category == "configs":
        success = update_config_media(item_id, [])
    
    if success:
        await callback.message.edit_text("✅ Все фото удалены из временной БД!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_media_{category}_{item_id}")]]))
    else:
        await callback.message.edit_text("❌ Ошибка при удалении фото", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"edit_media_{category}_{item_id}")]]))
    await callback.answer()

@dp.message(AdminStates.edit_media)
async def handle_media_edit(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    
    data = await state.get_data()
    item_id = data.get('edit_item_id')
    category = data.get('edit_category')
    current_media = data.get('media_list', [])
    
    if message.text and message.text.lower() == 'готово':
        success = False
        if category == 'clients':
            success = update_client_media(item_id, current_media)
        elif category == 'packs':
            success = update_pack_media(item_id, current_media)
        elif category == 'configs':
            success = update_config_media(item_id, current_media)
        
        await state.clear()
        if success:
            await message.answer(f"✅ Фото сохранено во временной БД! Всего: {len(current_media)}\n\nНе забудь сохранить изменения кнопкой 'Сохранить и выйти'", reply_markup=get_main_keyboard(is_admin=True))
        else:
            await message.answer("❌ Ошибка при сохранении фото", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.text and message.text.lower() == 'отмена':
        await state.clear()
        await message.answer("❌ Редактирование отменено", reply_markup=get_main_keyboard(is_admin=True))
        return
    
    if message.photo:
        current_media.append({'type': 'photo', 'id': message.photo[-1].file_id})
        await state.update_data(media_list=current_media)
        await message.answer(f"✅ Фото добавлено во временную БД! Всего: {len(current_media)}\nМожешь отправить ещё фото или написать 'готово'")
    else:
        await message.answer("❌ Отправь фото, или напиши 'готово' / 'отмена'")

# ========== СОХРАНЕНИЕ И ОТМЕНА ИЗМЕНЕНИЙ ==========

@dp.callback_query(lambda c: c.data.startswith("save_edit_"))
async def save_edit_changes(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace("save_edit_", "")
    
    if apply_temp_db_changes():
        await callback.message.edit_text(
            f"✅ Изменения сохранены! База данных обновлена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]])
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка при сохранении изменений",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]])
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_edit_"))
async def cancel_edit_changes(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    category = callback.data.replace("cancel_edit_", "")
    
    if cancel_temp_db_changes():
        await callback.message.edit_text(
            f"❌ Изменения отменены. База данных не изменена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]])
        )
    else:
        await callback.message.edit_text(
            f"⚠️ Временная БД уже удалена или произошла ошибка",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_{category}")]])
        )
    
    await callback.answer()

# ========== ФУНКЦИИ ДЛЯ БЭКАПОВ ==========

def encode_filename(filename):
    filename_bytes = filename.encode('utf-8')
    encoded = base64.b64encode(filename_bytes).decode('utf-8')
    return encoded[:50]

def decode_filename(encoded):
    try:
        decoded_bytes = base64.b64decode(encoded)
        return decoded_bytes.decode('utf-8')
    except:
        return encoded

@dp.callback_query(lambda c: c.data == "admin_zip_backups")
async def admin_zip_backups(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    backups = get_all_backups()
    created = [b for b in backups if b.startswith('backup_')]
    uploaded = [b for b in backups if b.startswith('uploaded_')]
    all_backups = created + uploaded
    text = "📦 ZIP Бэкапы\n\nВсего бэкапов: " + str(len(all_backups)) + "\n\n"
    if all_backups:
        for i, b in enumerate(all_backups[:10], 1):
            try:
                size = (BACKUP_DIR / b).stat().st_size // 1024
                if b.startswith('backup_'):
                    display = b.replace('backup_', '📦 ').replace('.zip', '')
                else:
                    display = b.replace('uploaded_', '📤 ').replace('.zip', '')
                short_display = display[:20] + "..." if len(display) > 20 else display
                text += f"{i}. {short_display} ({size} KB)\n"
            except Exception as e:
                text += f"{i}. {b[:20]}... (ошибка чтения)\n"
    else:
        text += "❌ Бэкапов пока нет!\n"
    buttons = []
    for i, b in enumerate(all_backups[:10], 1):
        encoded_name = encode_filename(b)
        try:
            size = (BACKUP_DIR / b).stat().st_size // 1024
            icon = "📦" if b.startswith('backup_') else "📤"
            if b.startswith('backup_'):
                short_name = b[7:15] + "..." if len(b) > 15 else b[7:]
            else:
                short_name = b[9:15] + "..." if len(b) > 15 else b[9:]
            buttons.append([InlineKeyboardButton(text=f"{icon} {short_name} ({size} KB)", callback_data=f"restore_{encoded_name}")])
        except Exception as e:
            buttons.append([InlineKeyboardButton(text=f"{'📦' if b.startswith('backup_') else '📤'} {b[:10]}...", callback_data=f"restore_{encoded_name}")])
    manage = []
    if all_backups:
        manage.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup_backups"))
    manage.extend([InlineKeyboardButton(text="📥 Создать", callback_data="create_backup"), InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_backup")])
    if manage:
        buttons.append(manage)
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_zip_backups")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "create_backup")
async def create_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await callback.message.edit_text("⏳ Создание бэкапа...")
    zip_path, zip_filename = await create_zip_backup()
    if zip_path:
        await callback.message.answer_document(document=FSInputFile(zip_path), caption=f"✅ Бэкап создан: {zip_filename}")
        await admin_zip_backups(callback)
    else:
        await callback.message.edit_text("❌ Ошибка создания бэкапа", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))

@dp.callback_query(lambda c: c.data.startswith("restore_") and not c.data.startswith("restore_confirm_"))
async def restore_backup(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    encoded_name = callback.data.replace("restore_", "")
    filename = decode_filename(encoded_name)
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        found = False
        for f in get_all_backups():
            if filename in f or f in filename:
                filepath = BACKUP_DIR / f
                filename = f
                found = True
                break
        if not found:
            await callback.answer(f"❌ Файл не найден", show_alert=True)
            return
    issues = check_backup_structure(str(filepath))
    try:
        size = filepath.stat().st_size // 1024
        date = datetime.fromtimestamp(filepath.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except:
        size = 0
        date = "?"
    icon = "📦" if filename.startswith('backup_') else "📤"
    display = filename.replace('backup_', '').replace('uploaded_', '').replace('.zip', '')
    if issues:
        warning_text = "\n\n⚠️ ПРОБЛЕМЫ С БЭКАПОМ:\n" + "\n".join(issues) + "\n\nВосстановление может работать некорректно!"
    else:
        warning_text = ""
    encoded_name = encode_filename(filename)
    buttons = [[InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"restore_confirm_{encoded_name}"), InlineKeyboardButton(text="❌ Нет", callback_data="admin_zip_backups")]]
    await callback.message.edit_text(f"{icon} Восстановление\n\nФайл: {display}\nРазмер: {size} KB\nДата: {date}{warning_text}\n\n❗ Данные будут заменены!", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("restore_confirm_"))
async def restore_confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    encoded_name = callback.data.replace("restore_confirm_", "")
    filename = decode_filename(encoded_name)
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        found = False
        for f in get_all_backups():
            if filename in f or f in filename:
                filepath = BACKUP_DIR / f
                filename = f
                found = True
                break
        if not found:
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
    await callback.message.edit_text("⏳ Восстановление... (это может занять несколько секунд)")
    await create_zip_backup()
    success = await restore_from_zip(str(filepath))
    if success:
        await callback.message.edit_text("✅ База данных успешно восстановлена!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ К бэкапам", callback_data="admin_zip_backups")]]))
    else:
        await callback.message.edit_text("❌ Ошибка восстановления!\n\nПроверьте целостность ZIP файла.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))

@dp.callback_query(lambda c: c.data == "upload_backup")
async def upload_backup(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_backup)
    await callback.message.edit_text("📤 Отправь ZIP файл с бэкапом\n\n❌ Отмена: /cancel")
    await callback.answer()

@dp.message(AdminStates.waiting_for_backup)
async def handle_upload(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Загрузка отменена")
        return
    if not message.document:
        await message.answer("❌ Это не файл! Отправь ZIP файл")
        return
    if not message.document.file_name.endswith('.zip'):
        await message.answer("❌ Файл должен быть ZIP архивом")
        return
    wait_msg = await message.answer("⏳ Загрузка файла...")
    try:
        file = await bot.get_file(message.document.file_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = message.document.file_name.replace('.zip', '')
        safe_name = "".join(c for c in original_name if c.isalnum() or c in '._- ')[:30]
        filename = f"uploaded_{timestamp}_{safe_name}.zip"
        filepath = BACKUP_DIR / filename
        await bot.download_file(file.file_path, str(filepath))
        issues = check_backup_structure(str(filepath))
        size_kb = filepath.stat().st_size // 1024
        if issues:
            warning = "\n".join(issues)
            await wait_msg.edit_text(f"⚠️ Файл загружен, но есть проблемы:\n\nИмя: {filename}\nРазмер: {size_kb} KB\nПроблемы:\n{warning}\n\nВосстановление может не работать!")
        else:
            await wait_msg.edit_text(f"✅ ZIP файл успешно загружен!\n\nИмя: {filename}\nРазмер: {size_kb} KB\nСтруктура: ✅ корректна")
        await state.clear()
        backups = get_all_backups()
        created = [b for b in backups if b.startswith('backup_')]
        uploaded = [b for b in backups if b.startswith('uploaded_')]
        all_backups = created + uploaded
        text = "📦 ZIP Бэкапы\n\nВсего бэкапов: " + str(len(all_backups)) + "\n\n"
        if all_backups:
            for i, b in enumerate(all_backups[:10], 1):
                try:
                    size = (BACKUP_DIR / b).stat().st_size // 1024
                    if b.startswith('backup_'):
                        display = b.replace('backup_', '📦 ').replace('.zip', '')
                    else:
                        display = b.replace('uploaded_', '📤 ').replace('.zip', '')
                    short_display = display[:20] + "..." if len(display) > 20 else display
                    text += f"{i}. {short_display} ({size} KB)\n"
                except:
                    text += f"{i}. {b[:20]}...\n"
        else:
            text += "❌ Бэкапов пока нет!\n"
        buttons = []
        for i, b in enumerate(all_backups[:10], 1):
            encoded_name = encode_filename(b)
            try:
                size = (BACKUP_DIR / b).stat().st_size // 1024
                icon = "📦" if b.startswith('backup_') else "📤"
                if b.startswith('backup_'):
                    short_name = b[7:15] + "..." if len(b) > 15 else b[7:]
                else:
                    short_name = b[9:15] + "..." if len(b) > 15 else b[9:]
                buttons.append([InlineKeyboardButton(text=f"{icon} {short_name} ({size} KB)", callback_data=f"restore_{encoded_name}")])
            except:
                buttons.append([InlineKeyboardButton(text=f"{'📦' if b.startswith('backup_') else '📤'} {b[:10]}...", callback_data=f"restore_{encoded_name}")])
        manage = []
        if all_backups:
            manage.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup_backups"))
        manage.extend([InlineKeyboardButton(text="📥 Создать", callback_data="create_backup"), InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_backup")])
        if manage:
            buttons.append(manage)
        buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_zip_backups")])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка при загрузке: {str(e)}")
        await state.clear()

@dp.callback_query(lambda c: c.data == "cleanup_backups")
async def cleanup_backups(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text="🧹 Удалить все", callback_data="cleanup_all"), InlineKeyboardButton(text="🗑 Кроме 5 последних", callback_data="cleanup_old")], [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_zip_backups")]]
    await callback.message.edit_text("🗑 Очистка бэкапов", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cleanup_all")
async def cleanup_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    await callback.message.edit_text("⏳ Удаление...")
    deleted = 0
    for b in get_all_backups():
        try:
            (BACKUP_DIR / b).unlink()
            deleted += 1
        except:
            pass
    await callback.message.edit_text(f"✅ Удалено: {deleted}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))

@dp.callback_query(lambda c: c.data == "cleanup_old")
async def cleanup_old(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    backups = get_all_backups()
    backups.sort(reverse=True)
    if len(backups) <= 5:
        await callback.answer("❌ Мало бэкапов", show_alert=True)
        return
    await callback.message.edit_text("⏳ Удаление...")
    deleted = 0
    for b in backups[5:]:
        try:
            (BACKUP_DIR / b).unlink()
            deleted += 1
        except:
            pass
    await callback.message.edit_text(f"✅ Удалено: {deleted}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_zip_backups")]]))

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    users_count = get_users_count()
    vip_count = get_vip_users_count()
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    clients_count = cur.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
    cur.execute("PRAGMA table_info(clients)")
    columns = [col[1] for col in cur.fetchall()]
    if 'is_vip' in columns:
        vip_clients = cur.execute('SELECT COUNT(*) FROM clients WHERE is_vip = 1').fetchone()[0]
    else:
        vip_clients = 0
    packs_count = cur.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]
    cur.execute("PRAGMA table_info(resourcepacks)")
    columns = [col[1] for col in cur.fetchall()]
    if 'is_vip' in columns:
        vip_packs = cur.execute('SELECT COUNT(*) FROM resourcepacks WHERE is_vip = 1').fetchone()[0]
    else:
        vip_packs = 0
    configs_count = cur.execute('SELECT COUNT(*) FROM configs').fetchone()[0]
    cur.execute("PRAGMA table_info(configs)")
    columns = [col[1] for col in cur.fetchall()]
    if 'is_vip' in columns:
        vip_configs = cur.execute('SELECT COUNT(*) FROM configs WHERE is_vip = 1').fetchone()[0]
    else:
        vip_configs = 0
    conn.close()
    await callback.message.edit_text(f"📊 Статистика\n\n👤 Пользователей: {users_count} (💎 VIP: {vip_count})\n🎮 Клиентов: {clients_count} (💎 VIP: {vip_clients})\n🎨 Ресурспаков: {packs_count} (💎 VIP: {vip_packs})\n⚙️ Конфигов: {configs_count} (💎 VIP: {vip_configs})", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    users_count = get_users_count()
    await state.set_state(AdminStates.broadcast_text)
    await callback.message.delete()
    await callback.message.answer(f"📢 Создание рассылки\n\nВсего пользователей: {users_count}\n\nВведи текст сообщения для рассылки (или отправь /cancel для отмены):")
    await callback.answer()

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=get_main_keyboard(is_admin=True))
        return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.broadcast_photo)
    await message.answer("📸 Отправь фото для рассылки (или отправь 'пропустить' чтобы отправить только текст):\n\nИли отправь /cancel для отмены")

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    if message.text and message.text.lower() == '/cancel':
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=get_main_keyboard(is_admin=True))
        return
    data = await state.get_data()
    text = data.get('broadcast_text')
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'пропустить':
        photo_id = None
    else:
        await message.answer("❌ Отправь фото или напиши 'пропустить' (или /cancel)")
        return
    users = get_all_users()
    if not users:
        await message.answer("❌ Нет пользователей для рассылки")
        await state.clear()
        return
    preview_text = f"📢 ПРЕДПРОСМОТР РАССЫЛКИ\n\n{text}\n\nВсего получателей: {len(users)}"
    if photo_id:
        await message.answer_photo(photo=photo_id, caption=preview_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_send")], [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="broadcast_cancel")]]))
    else:
        await message.answer(preview_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_send")], [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="broadcast_cancel")]]))
    await state.update_data(broadcast_photo=photo_id, broadcast_text=text)

@dp.callback_query(lambda c: c.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    text = data.get('broadcast_text')
    photo_id = data.get('broadcast_photo')
    users = get_all_users()
    if not users:
        await callback.message.edit_text("❌ Нет пользователей для рассылки")
        await state.clear()
        return
    await callback.message.delete()
    status_msg = await callback.message.answer(f"📢 Рассылка началась...\n\n✅ Отправлено: 0/{len(users)}\n⏳ Ожидайте...")
    sent = 0
    failed = 0
    for i, user_id in enumerate(users, 1):
        try:
            if photo_id:
                await bot.send_photo(chat_id=user_id, photo=photo_id, caption=text)
            else:
                await bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
        if i % 10 == 0:
            await status_msg.edit_text(f"📢 Рассылка...\n\n✅ Отправлено: {sent}/{len(users)}\n❌ Ошибок: {failed}")
        await asyncio.sleep(0.05)
    await state.clear()
    result_text = f"📢 РАССЫЛКА ЗАВЕРШЕНА!\n\n📊 Статистика:\n• Всего пользователей: {len(users)}\n• ✅ Успешно отправлено: {sent}\n• ❌ Не доставлено: {failed}\n• 📈 Процент доставки: {sent/len(users)*100:.1f}%"
    await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back")]]))

@dp.callback_query(lambda c: c.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Рассылка отменена", reply_markup=get_main_keyboard(is_admin=True))

# ========== ФУНКЦИИ ДЛЯ ПРОСМОТРА МЕДИА ==========

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
        
        media_index = 5 if category == "configs" else 3
        
        try:
            media_list = json.loads(item[media_index]) if item[media_index] else []
        except:
            media_list = []
            logger.error(f"Ошибка парсинга media для {category} {item_id}")
        if not media_list:
            await callback.answer("📭 Нет медиа", show_alert=True)
            return
        if media_list[0]['type'] != 'photo':
            await callback.answer("❌ Неподдерживаемый тип медиа", show_alert=True)
            return
        await state.update_data(media_list=media_list, media_index=0, media_category=category, media_item_id=item_id)
        await show_media(callback.message, state, 0)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в view_media: {e}")
        await callback.answer("❌ Ошибка загрузки медиа", show_alert=True)

async def show_media(message: Message, state: FSMContext, index: int):
    data = await state.get_data()
    media_list = data.get('media_list', [])
    if not media_list or index >= len(media_list):
        await message.answer("❌ Медиа не найдено")
        return
    media = media_list[index]
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"media_nav_{index-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))
    nav_buttons.append(InlineKeyboardButton(text=f"{index+1}/{len(media_list)}", callback_data="noop"))
    if index < len(media_list) - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"media_nav_{index+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))
    buttons = [nav_buttons, [InlineKeyboardButton(text="◀️ Назад", callback_data="media_back")]]
    await state.update_data(media_index=index)
    try:
        if media['type'] == 'photo':
            await message.answer_photo(photo=media['id'], caption=f"📸 {index+1} из {len(media_list)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(f"❌ Неподдерживаемый тип медиа\n\n{index+1}/{len(media_list)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        await message.answer(f"❌ Ошибка загрузки фото {index+1}/{len(media_list)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(lambda c: c.data.startswith("media_nav_"))
async def media_nav(callback: CallbackQuery, state: FSMContext):
    try:
        index = int(callback.data.replace("media_nav_", ""))
        await show_media(callback.message, state, index)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка навигации: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data == "media_back")
async def media_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get('media_category')
    item_id = data.get('media_item_id')
    await state.clear()
    if category and item_id:
        new_callback = callback
        new_callback.data = f"detail_{category}_{item_id}"
        await detail_view(new_callback, state)
    else:
        await callback.message.delete()
        await callback.answer()

@dp.callback_query(lambda c: c.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    user_id = callback.from_user.id
    user_status = get_user_status(user_id)
    is_admin = (user_id == ADMIN_ID)
    is_vip = user_status.get('is_vip', False)
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard(is_admin, is_vip))

async def main():
    print("="*50)
    print("✅ Бот запущен!")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"👤 Создатель: {CREATOR_USERNAME}")
    print(f"📁 Папка данных: {DATA_DIR}")
    print("="*50)
    print("📌 Функции:")
    print("   • 💎 VIP контент")
    print("   • 🎮 Клиенты, ресурспаки, конфиги")
    print("   • 👑 VIP управление")
    print("   • 📦 Бэкапы")
    print("   • 📢 Рассылка")
    print("   • 🔍 Диагностика БД (/check_db, /debug_admin)")
    print("   • 🔄 Редактирование через временную БД")
    print("   • ⚙️ Конфиги привязаны к названиям клиентов")
    print("="*50)
    
    # Проверяем данные при запуске
    check_all_clients()
    
    try:
        me = await bot.get_me()
        print(f"✅ Бот @{me.username} успешно подключен к Telegram!")
    except Exception as e:
        print(f"❌ Ошибка подключения к Telegram: {e}")
        print("Проверьте токен в переменных окружения на bothost.ru")
        return
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⛔ Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")