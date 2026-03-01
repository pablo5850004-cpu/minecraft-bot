import logging
import os
import asyncio
import json
import sqlite3
import shutil
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5809098591
CREATOR = "@Strann1k_fiol"
if not BOT_TOKEN: raise ValueError("❌ BOT_TOKEN не найден!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "clients.db"
USERS_DB = DATA_DIR / "users.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

backup_map = {}

def init_dbs():
    for path, queries in [
        (DB_PATH, [
            '''CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, full_desc TEXT NOT NULL, media TEXT DEFAULT '[]', download_url TEXT NOT NULL, version TEXT, downloads INTEGER DEFAULT 0, views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS resourcepacks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, full_desc TEXT NOT NULL, media TEXT DEFAULT '[]', download_url TEXT NOT NULL, version TEXT, author TEXT, downloads INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS configs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, full_desc TEXT NOT NULL, media TEXT DEFAULT '[]', download_url TEXT NOT NULL, version TEXT, downloads INTEGER DEFAULT 0, views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER NOT NULL, pack_id INTEGER NOT NULL, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, pack_id))'''
        ]),
        (USERS_DB, [
            '''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, invites INTEGER DEFAULT 0, downloads_total INTEGER DEFAULT 0, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL, referred_id INTEGER NOT NULL UNIQUE, referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS downloads_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, item_type TEXT NOT NULL, item_id INTEGER NOT NULL, downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''
        ])
    ]:
        conn = sqlite3.connect(str(path))
        for q in queries: conn.execute(q)
        conn.commit(); conn.close()
init_dbs()

def get_item(table, id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM {table} WHERE id = ?', (id,))
    item = cur.fetchone()
    conn.close()
    return item

def get_all(table):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT id, name, full_desc, media, downloads, version FROM {table} ORDER BY created_at DESC')
    items = cur.fetchall()
    conn.close()
    return items

def get_versions(table):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(f'SELECT DISTINCT version FROM {table} WHERE version IS NOT NULL ORDER BY version DESC')
    v = [r[0] for r in cur.fetchall()]
    conn.close()
    return v

def get_by_version(table, version, page=1, per=10):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    offset = (page-1)*per
    if table == 'resourcepacks':
        cur.execute(f'SELECT id, name, full_desc, media, downloads, likes, views, version, author FROM {table} WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?', (version, per, offset))
    else:
        cur.execute(f'SELECT id, name, full_desc, media, downloads, views, version FROM {table} WHERE version = ? ORDER BY downloads DESC LIMIT ? OFFSET ?', (version, per, offset))
    items = cur.fetchall()
    total = cur.execute(f'SELECT COUNT(*) FROM {table} WHERE version = ?', (version,)).fetchone()[0]
    conn.close()
    return items, total

def add_item(table, **kwargs):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    media = json.dumps(kwargs.get('media', []))
    if table == 'resourcepacks':
        cur.execute(f'INSERT INTO {table} (name, full_desc, download_url, version, author, media) VALUES (?,?,?,?,?,?)',
                   (kwargs['name'], kwargs['full_desc'], kwargs['url'], kwargs['version'], kwargs['author'], media))
    else:
        cur.execute(f'INSERT INTO {table} (name, full_desc, download_url, version, media) VALUES (?,?,?,?,?)',
                   (kwargs['name'], kwargs['full_desc'], kwargs['url'], kwargs['version'], media))
    conn.commit()
    id = cur.lastrowid
    conn.close()
    return id

def update_item(table, id, field, value):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(f'UPDATE {table} SET {field} = ? WHERE id = ?', (value, id))
    conn.commit(); conn.close()

def delete_item(table, id):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(f'DELETE FROM {table} WHERE id = ?', (id,))
    conn.commit(); conn.close()

def inc_view(table, id):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(f'UPDATE {table} SET views = views + 1 WHERE id = ?', (id,))
    conn.commit(); conn.close()

def inc_download(table, id):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(f'UPDATE {table} SET downloads = downloads + 1 WHERE id = ?', (id,))
    conn.commit(); conn.close()

def toggle_fav(user_id, pack_id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    exists = cur.execute('SELECT 1 FROM favorites WHERE user_id = ? AND pack_id = ?', (user_id, pack_id)).fetchone()
    if exists:
        cur.execute('DELETE FROM favorites WHERE user_id = ? AND pack_id = ?', (user_id, pack_id))
        cur.execute('UPDATE resourcepacks SET likes = likes - 1 WHERE id = ?', (pack_id,))
        conn.commit(); conn.close()
        return False
    else:
        cur.execute('INSERT INTO favorites (user_id, pack_id) VALUES (?, ?)', (user_id, pack_id))
        cur.execute('UPDATE resourcepacks SET likes = likes + 1 WHERE id = ?', (pack_id,))
        conn.commit(); conn.close()
        return True

def get_favs(user_id):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT r.id, r.name, r.full_desc, r.media, r.downloads, r.likes FROM resourcepacks r JOIN favorites f ON r.id = f.pack_id WHERE f.user_id = ? ORDER BY f.added_at DESC', (user_id,))
    f = cur.fetchall()
    conn.close()
    return f

def get_users_count():
    conn = sqlite3.connect(str(USERS_DB))
    c = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    return c

def get_all_users():
    conn = sqlite3.connect(str(USERS_DB))
    u = [r[0] for r in conn.execute('SELECT user_id FROM users ORDER BY last_active DESC').fetchall()]
    conn.close()
    return u

def save_user(msg):
    conn = sqlite3.connect(str(USERS_DB))
    uid = msg.from_user.id
    un = msg.from_user.username
    fn = msg.from_user.first_name
    ln = msg.from_user.last_name
    if not conn.execute('SELECT 1 FROM users WHERE user_id = ?', (uid,)).fetchone():
        ref = None
        if msg.text and msg.text.startswith('/start ref_'):
            try: ref = int(msg.text.replace('/start ref_', ''))
            except: pass
            if ref == uid: ref = None
        conn.execute('INSERT INTO users (user_id, username, first_name, last_name, last_active) VALUES (?,?,?,?, CURRENT_TIMESTAMP)', (uid, un, fn, ln))
        if ref:
            conn.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (ref, uid))
            conn.execute('UPDATE users SET invites = invites + 1 WHERE user_id = ?', (ref,))
    else:
        conn.execute('UPDATE users SET username=?, first_name=?, last_name=?, last_active=CURRENT_TIMESTAMP WHERE user_id=?', (un, fn, ln, uid))
    conn.commit(); conn.close()

def user_status(uid):
    conn = sqlite3.connect(str(USERS_DB))
    u = conn.execute('SELECT invites, downloads_total FROM users WHERE user_id = ?', (uid,)).fetchone()
    conn.close()
    return {'is_admin': uid == ADMIN_ID, 'invites': u[0] if u else 0, 'downloads': u[1] if u else 0}

def inc_user_downloads(uid):
    conn = sqlite3.connect(str(USERS_DB))
    conn.execute('UPDATE users SET downloads_total = downloads_total + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (uid,))
    conn.commit(); conn.close()
    conn = sqlite3.connect(str(USERS_DB))
    conn.execute('INSERT INTO downloads_log (user_id, item_type, item_id) VALUES (?,?,?)', (uid, 'download', 0))
    conn.commit(); conn.close()

def get_backups():
    try:
        f = [f for f in os.listdir(str(BACKUP_DIR)) if f.endswith('.zip')]
        f.sort(reverse=True)
        return f
    except: return []

async def create_zip():
    try:
        name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        path = BACKUP_DIR / name
        with zipfile.ZipFile(path, 'w') as z:
            if DB_PATH.exists(): z.write(DB_PATH, 'clients.db')
            if USERS_DB.exists(): z.write(USERS_DB, 'users.db')
        return str(path) if path.exists() else None, name
    except: return None, None

async def restore_zip(path):
    try:
        ext = BACKUP_DIR / f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ext.mkdir()
        with zipfile.ZipFile(path, 'r') as z: z.extractall(ext)
        ok = False
        for f in ext.iterdir():
            if f.name == 'clients.db': shutil.copy2(f, DB_PATH); ok = True
            elif f.name == 'users.db': shutil.copy2(f, USERS_DB); ok = True
        shutil.rmtree(ext)
        return ok
    except: return False

def fmt_num(n):
    if n < 1000: return str(n)
    if n < 1000000: return f"{n/1000:.1f}K"
    return f"{n/1000000:.1f}M"

class States(StatesGroup):
    add_name = State(); add_desc = State(); add_ver = State(); add_url = State(); add_media = State()
    edit_val = State(); broadcast_t = State(); broadcast_p = State(); wait_backup = State()

def main_kb(admin=False):
    kb = [["🎮 Клиенты", "🎨 Ресурспаки"], ["❤️ Избранное", "⚙️ Конфиги", "👤 Профиль"], ["ℹ️ Инфо", "❓ Помощь"]]
    if admin: kb.append(["⚙️ Админ панель"])
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def ver_kb(vers, cat):
    btns = []
    for i in range(0, len(vers), 3):
        row = [InlineKeyboardButton(text=v, callback_data=f"ver_{cat}_{v}") for v in vers[i:i+3]]
        btns.append(row)
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def items_kb(items, cat, page, total):
    btns = []
    for i in items:
        mid = i[0]
        name = i[1]
        media = json.loads(i[3]) if i[3] else []
        dls = i[4]
        ver = i[6] if len(i) > 6 else "?"
        btns.append([InlineKeyboardButton(text=f"{'🖼️' if media else '📄'} {name[:25]} ({ver}) 📥 {fmt_num(dls)}", callback_data=f"det_{cat}_{mid}")])
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{cat}_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="noop"))
    if page < total: nav.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{cat}_{page+1}"))
    if nav: btns.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=btns)

def det_kb(cat, id, fav=False):
    btns = []
    if cat == "packs":
        btns.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"dl_{cat}_{id}"),
                     InlineKeyboardButton(text="❤️" if fav else "🤍", callback_data=f"fav_{cat}_{id}")])
    else:
        btns.append([InlineKeyboardButton(text="📥 Скачать", callback_data=f"dl_{cat}_{id}")])
    btns.append([InlineKeyboardButton(text="🖼️ Медиа", callback_data=f"media_{cat}_{id}")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

@dp.message(CommandStart())
async def start(msg: Message):
    save_user(msg)
    await msg.answer("👋 Привет! Я бот-каталог Minecraft\n\nИспользуй кнопки ниже:", reply_markup=main_kb(msg.from_user.id == ADMIN_ID))

@dp.message(F.text == "🎮 Клиенты")
async def clients(msg: Message, state: FSMContext):
    v = get_versions('clients')
    await msg.answer("🎮 Выбери версию:" if v else "📭 Пока нет клиентов", reply_markup=ver_kb(v, 'clients') if v else None)

@dp.message(F.text == "🎨 Ресурспаки")
async def packs(msg: Message):
    v = get_versions('resourcepacks')
    await msg.answer("🎨 Выбери версию:" if v else "📭 Пока нет ресурспаков", reply_markup=ver_kb(v, 'packs') if v else None)

@dp.message(F.text == "⚙️ Конфиги")
async def configs(msg: Message):
    v = get_versions('configs')
    await msg.answer("⚙️ Выбери версию:" if v else "📭 Пока нет конфигов", reply_markup=ver_kb(v, 'configs') if v else None)

@dp.message(F.text == "❤️ Избранное")
async def favs(msg: Message):
    f = get_favs(msg.from_user.id)
    await msg.answer("❤️ Твоё избранное:\n\n" + "\n".join([f"• {x[1]} - {fmt_num(x[4])} 📥" for x in f[:10]]) if f else "❤️ Избранное пусто")

@dp.message(F.text == "👤 Профиль")
async def profile(msg: Message):
    s = user_status(msg.from_user.id)
    botu = (await bot.me()).username
    await msg.answer(f"👋 Привет, {msg.from_user.first_name}!\n\nСтатус: {'👑 СОЗДАТЕЛЬ' if s['is_admin'] else '👤 ПОЛЬЗОВАТЕЛЬ'}\nID: {msg.from_user.id}\n📥 Скачиваний: {s['downloads']}\n👥 Приглашений: {s['invites']}\n\nТвоя ссылка: https://t.me/{botu}?start=ref_{msg.from_user.id}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]]))

@dp.message(F.text == "ℹ️ Инфо")
async def info(msg: Message):
    c = sqlite3.connect(str(DB_PATH))
    await msg.answer(f"Инфо\n\nСоздатель: {CREATOR}\n👤 Пользователей: {get_users_count()}\n🎮 Клиентов: {c.execute('SELECT COUNT(*) FROM clients').fetchone()[0]}\n🎨 Ресурспаков: {c.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]}\n⚙️ Конфигов: {c.execute('SELECT COUNT(*) FROM configs').fetchone()[0]}\n📦 Бэкапов: {len(get_backups())}")
    c.close()

@dp.message(F.text == "❓ Помощь")
async def help(msg: Message):
    await msg.answer("❓ Помощь", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Связаться", url=f"https://t.me/{CREATOR[1:]}")]]))

@dp.message(F.text == "⚙️ Админ панель")
async def admin(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    btns = [[InlineKeyboardButton(text=x[0], callback_data=x[1])] for x in [("🎮 Клиенты", "adm_clients"), ("🎨 Ресурспаки", "adm_packs"), ("⚙️ Конфиги", "adm_configs"), ("📦 Бэкапы", "adm_backups"), ("📊 Статистика", "adm_stats"), ("📢 Рассылка", "adm_broadcast")]]
    await msg.answer("⚙️ Админ панель", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# Callback handlers
@dp.callback_query(lambda c: c.data.startswith("ver_"))
async def ver_selected(call: CallbackQuery, state: FSMContext):
    _, cat, ver = call.data.split("_", 2)
    table = {'clients':'clients','packs':'resourcepacks','configs':'configs'}[cat]
    items, total = get_by_version(table, ver)
    if not items: await call.answer("❌ Пусто"); return
    tp = (total+9)//10
    await state.update_data({f"{cat}_ver": ver})
    await call.message.edit_text(f"{'🎮' if cat=='clients' else '🎨' if cat=='packs' else '⚙️'} {ver} (1/{tp}):", reply_markup=items_kb(items, cat, 1, tp))
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("page_"))
async def page(call: CallbackQuery, state: FSMContext):
    _, cat, page = call.data.split("_")
    page = int(page)
    data = await state.get_data()
    ver = data.get(f"{cat}_ver", "1.20")
    table = {'clients':'clients','packs':'resourcepacks','configs':'configs'}[cat]
    items, total = get_by_version(table, ver, page)
    tp = max(1, (total+9)//10)
    await state.update_data({f"{cat}_page": page})
    await call.message.edit_text(f"{'🎮' if cat=='clients' else '🎨' if cat=='packs' else '⚙️'} {ver} ({page}/{tp}):", reply_markup=items_kb(items, cat, page, tp))
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("det_"))
async def detail(call: CallbackQuery):
    _, cat, id = call.data.split("_")
    id = int(id)
    table = {'clients':'clients','packs':'resourcepacks','configs':'configs'}[cat]
    item = get_item(table, id)
    if not item: await call.answer("❌ Не найден"); return
    inc_view(table, id)
    media = json.loads(item[4]) if item[4] else []
    if cat == 'packs':
        conn = sqlite3.connect(str(DB_PATH))
        fav = conn.execute('SELECT 1 FROM favorites WHERE user_id=? AND pack_id=?', (call.from_user.id, id)).fetchone()
        conn.close()
        text = f"{item[1]}\n\n{item[2]}\n\nАвтор: {item[6]}\nВерсия: {item[5]}\n📥 {fmt_num(item[7])} ❤️ {fmt_num(item[8])} 👁 {fmt_num(item[9])}"
    else:
        text = f"{item[1]}\n\n{item[2]}\n\nВерсия: {item[5]}\n📥 {fmt_num(item[6])} 👁 {fmt_num(item[7])}"
    if media and media[0]['type'] == 'photo':
        await call.message.answer_photo(photo=media[0]['id'], caption=text, reply_markup=det_kb(cat, id, fav if cat=='packs' else False))
        await call.message.delete()
    else:
        await call.message.edit_text(text, reply_markup=det_kb(cat, id, fav if cat=='packs' else False))
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("back_"))
async def back(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("back_", "")
    data = await state.get_data()
    ver = data.get(f"{cat}_ver", "1.20")
    table = {'clients':'clients','packs':'resourcepacks','configs':'configs'}[cat]
    items, total = get_by_version(table, ver)
    if not items: await call.answer("❌ Пусто"); return
    tp = (total+9)//10
    await call.message.edit_text(f"{'🎮' if cat=='clients' else '🎨' if cat=='packs' else '⚙️'} {ver} (1/{tp}):", reply_markup=items_kb(items, cat, 1, tp))
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("dl_"))
async def download(call: CallbackQuery):
    _, cat, id = call.data.split("_")
    id = int(id)
    table = {'clients':'clients','packs':'resourcepacks','configs':'configs'}[cat]
    item = get_item(table, id)
    if not item: await call.answer("❌ Не найден"); return
    inc_download(table, id)
    inc_user_downloads(call.from_user.id)
    await call.message.answer(f"📥 {item[1]}\n\n{item[5]}")
    await call.answer("✅ Ссылка отправлена")

@dp.callback_query(lambda c: c.data.startswith("fav_"))
async def fav(call: CallbackQuery):
    _, cat, id = call.data.split("_")
    if cat != 'packs': await call.answer("❌ Только для ресурспаков"); return
    toggle_fav(call.from_user.id, int(id))
    await call.answer("✅ Готово")
    await detail(call)

@dp.callback_query(lambda c: c.data == "stats")
async def stats(call: CallbackQuery):
    uid = call.from_user.id
    conn = sqlite3.connect(str(USERS_DB))
    dls = conn.execute('SELECT COUNT(*) FROM downloads_log WHERE user_id=?', (uid,)).fetchone()[0]
    inv = conn.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id=?', (uid,)).fetchone()[0]
    conn.close()
    await call.message.edit_text(f"📊 Твоя статистика\n\n📥 Скачиваний: {dls}\n👥 Приглашений: {inv}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_profile")]]))
    await call.answer()

@dp.callback_query(lambda c: c.data == "back_profile")
async def back_profile(call: CallbackQuery):
    await profile(call.message)
    await call.answer()

# Admin backup handlers
def get_file_key(name): return hashlib.md5(name.encode()).hexdigest()[:8]

@dp.callback_query(lambda c: c.data == "adm_backups")
async def adm_backups(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    backup_map.clear()
    backs = get_backups()
    created = [b for b in backs if b.startswith('backup_')]
    uploaded = [b for b in backs if b.startswith('uploaded_')]
    allb = created + uploaded
    text = f"📦 Бэкапы ({len(allb)})\n\n" + "\n".join([f"{i}. {b[:20]}... ({(BACKUP_DIR/b).stat().st_size//1024} KB)" for i,b in enumerate(allb[:10],1)]) if allb else "📦 Бэкапов нет"
    btns = []
    for b in allb[:10]:
        key = get_file_key(b)
        backup_map[key] = b
        icon = "📦" if b.startswith('backup_') else "📤"
        size = (BACKUP_DIR/b).stat().st_size//1024
        btns.append([InlineKeyboardButton(text=f"{icon} {b[7:20] if b.startswith('backup_') else b[9:20]}... ({size} KB)", callback_data=f"restore_{key}")])
    cbtns = []
    if allb: cbtns.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup"))
    cbtns.extend([InlineKeyboardButton(text="📥 Создать", callback_data="create_bkp"), InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_bkp")])
    if cbtns: btns.append(cbtns)
    btns.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="adm_backups")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await call.answer()

@dp.callback_query(lambda c: c.data == "create_bkp")
async def create_bkp(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("⏳ Создание...")
    path, name = await create_zip()
    if path:
        await call.message.answer_document(document=FSInputFile(path), caption=f"✅ {name}")
        await adm_backups(call)
    else:
        await call.message.edit_text("❌ Ошибка", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_backups")]]))

@dp.callback_query(lambda c: c.data.startswith("restore_") and not c.data.startswith("restore_confirm_"))
async def restore(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    key = call.data.replace("restore_", "")
    name = backup_map.get(key)
    if not name: await call.answer("❌ Не найден"); return
    path = BACKUP_DIR / name
    if not path.exists(): await call.answer("❌ Файл отсутствует"); return
    size = path.stat().st_size//1024
    date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    icon = "📦" if name.startswith('backup_') else "📤"
    btns = [[InlineKeyboardButton(text="✅ Да", callback_data=f"restore_confirm_{key}"), InlineKeyboardButton(text="❌ Нет", callback_data="adm_backups")]]
    await call.message.edit_text(f"{icon} Восстановить {name[:20]}...?\n\nРазмер: {size} KB\nДата: {date}\n\n❗ Данные будут заменены!", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("restore_confirm_"))
async def restore_confirm(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    key = call.data.replace("restore_confirm_", "")
    name = backup_map.get(key)
    if not name: await call.answer("❌ Не найден"); return
    path = BACKUP_DIR / name
    await call.message.edit_text("⏳ Восстановление...")
    await create_zip()
    ok = await restore_zip(str(path))
    if ok:
        await call.message.edit_text("✅ Восстановлено", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_backups")]]))
    else:
        await call.message.edit_text("❌ Ошибка", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_backups")]]))

@dp.callback_query(lambda c: c.data == "upload_bkp")
async def upload(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(States.wait_backup)
    await call.message.edit_text("📤 Отправь ZIP файл")
    await call.answer()

@dp.message(States.wait_backup)
async def handle_upload(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: await state.clear(); return
    if not msg.document or not msg.document.file_name.endswith('.zip'):
        await msg.answer("❌ Нужен ZIP"); await state.clear(); return
    wait = await msg.answer("⏳ Загрузка...")
    file = await bot.get_file(msg.document.file_id)
    name = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{msg.document.file_name.replace('.zip','')[:20]}.zip"
    path = BACKUP_DIR / name
    await bot.download_file(file.file_path, str(path))
    try:
        with zipfile.ZipFile(path, 'r') as z:
            if not any(f in ['clients.db','users.db'] for f in z.namelist()):
                path.unlink()
                await wait.edit_text("❌ Нет clients.db/users.db")
                await state.clear()
                return
    except:
        path.unlink()
        await wait.edit_text("❌ Файл поврежден")
        await state.clear()
        return
    await wait.edit_text(f"✅ Загружен: {name[:30]}... ({path.stat().st_size//1024} KB)")
    await state.clear()
    await adm_backups_type(msg)

async def adm_backups_type(msg: Message):
    backup_map.clear()
    backs = get_backups()
    created = [b for b in backs if b.startswith('backup_')]
    uploaded = [b for b in backs if b.startswith('uploaded_')]
    allb = created + uploaded
    text = f"📦 Бэкапы ({len(allb)})\n\n" + "\n".join([f"{i}. {b[:20]}... ({(BACKUP_DIR/b).stat().st_size//1024} KB)" for i,b in enumerate(allb[:10],1)]) if allb else "📦 Бэкапов нет"
    btns = []
    for b in allb[:10]:
        key = get_file_key(b)
        backup_map[key] = b
        icon = "📦" if b.startswith('backup_') else "📤"
        size = (BACKUP_DIR/b).stat().st_size//1024
        btns.append([InlineKeyboardButton(text=f"{icon} {b[7:20] if b.startswith('backup_') else b[9:20]}... ({size} KB)", callback_data=f"restore_{key}")])
    cbtns = []
    if allb: cbtns.append(InlineKeyboardButton(text="🗑 Очистить", callback_data="cleanup"))
    cbtns.extend([InlineKeyboardButton(text="📥 Создать", callback_data="create_bkp"), InlineKeyboardButton(text="📤 Загрузить", callback_data="upload_bkp")])
    if cbtns: btns.append(cbtns)
    btns.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="adm_backups")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(lambda c: c.data == "cleanup")
async def cleanup(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    btns = [[InlineKeyboardButton(text="🧹 Все", callback_data="clean_all"), InlineKeyboardButton(text="🗑 Старые (кроме 5)", callback_data="clean_old")], [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_backups")]]
    await call.message.edit_text("🗑 Очистка бэкапов", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await call.answer()

@dp.callback_query(lambda c: c.data == "clean_all")
async def clean_all(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("⏳ Удаление...")
    cnt = 0
    for b in get_backups():
        try: (BACKUP_DIR / b).unlink(); cnt += 1
        except: pass
    await call.message.edit_text(f"✅ Удалено: {cnt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_backups")]]))

@dp.callback_query(lambda c: c.data == "clean_old")
async def clean_old(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    backs = get_backups()
    backs.sort(reverse=True)
    if len(backs) <= 5: await call.answer("❌ Мало бэкапов"); return
    await call.message.edit_text("⏳ Удаление...")
    cnt = 0
    for b in backs[5:]:
        try: (BACKUP_DIR / b).unlink(); cnt += 1
        except: pass
    await call.message.edit_text(f"✅ Удалено: {cnt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_backups")]]))

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(call: CallbackQuery):
    btns = [[InlineKeyboardButton(text=x[0], callback_data=x[1])] for x in [("🎮 Клиенты", "adm_clients"), ("🎨 Ресурспаки", "adm_packs"), ("⚙️ Конфиги", "adm_configs"), ("📦 Бэкапы", "adm_backups"), ("📊 Статистика", "adm_stats"), ("📢 Рассылка", "adm_broadcast")]]
    await call.message.edit_text("⚙️ Админ панель", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await call.answer()

@dp.callback_query(lambda c: c.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(str(DB_PATH))
    await call.message.edit_text(f"📊 Статистика\n\n👤 Пользователей: {get_users_count()}\n🎮 Клиентов: {conn.execute('SELECT COUNT(*) FROM clients').fetchone()[0]}\n🎨 Ресурспаков: {conn.execute('SELECT COUNT(*) FROM resourcepacks').fetchone()[0]}\n⚙️ Конфигов: {conn.execute('SELECT COUNT(*) FROM configs').fetchone()[0]}\n📦 Бэкапов: {len(get_backups())}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    conn.close()

@dp.callback_query(lambda c: c.data == "noop")
async def noop(call: CallbackQuery): await call.answer()

@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=main_kb(call.from_user.id == ADMIN_ID))
    await call.answer()

async def main():
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())