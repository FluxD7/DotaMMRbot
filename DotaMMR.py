import os
import random
import aiosqlite
import asyncio
import requests
from datetime import datetime, date
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

# Загружаем токен из .env
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
DB_PATH = "players.db"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Ранги
RANKS = [
    (0, "Рекрут 1"), (154, "Рекрут 2"), (308, "Рекрут 3"),
    (770, "Страж 1"), (924, "Страж 2"), (1078, "Страж 3"),
    (1540, "Рыцарь 1"), (1694, "Рыцарь 2"), (1848, "Рыцарь 3"),
    (2310, "Герой 1"), (2464, "Герой 2"), (2218, "Герой 3"),
    (2400, "Легенда 1"), (2600, "Легенда 2"), (2800, "Легенда 3"),
    (3000, "Властелин 1"), (3200, "Властелин 2"), (3400, "Властелин 3"),
    (3600, "Божество 1"), (3800, "Божество 2"), (4000, "Божество 3"),
    (4200, "Титан 1")
]

def get_rank(mmr):
    current = RANKS[0][1]
    for req, name in RANKS:
        if mmr >= req:
            current = name
        else:
            break
    return current

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            mmr INTEGER,
            last_play TEXT,
            streak INTEGER
        )
        """)
        await db.commit()

async def get_player(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        return await cur.fetchone()

async def save_player(user_id, name, mmr=1000, last_play="2000-01-01", streak=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT OR REPLACE INTO players (user_id, name, mmr, last_play, streak)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, mmr, last_play, streak))
        await db.commit()

async def update_player(user_id, **fields):
    if not fields:
        return
    parts = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE players SET {parts} WHERE user_id = ?", values)
        await db.commit()

# --- Команды ---

@dp.message(Command("mmr"))
async def start_cmd(message: types.Message):
    await init_db()
    uid = message.from_user.id
    name = message.from_user.first_name
    player = await get_player(uid)
    if not player:
        await save_player(uid, name)

    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 Играть", callback_data="play")
    kb.button(text="🏆 Топ", callback_data="top")
    kb.button(text="👤 Профиль", callback_data="profile")
    kb.adjust(1)

    await message.answer(
        f"Привет, {name}! 👋\n"
        f"Нажми 'Играть', чтобы получить свой рейтинг на сегодня!",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(lambda c: c.data == "play")
async def play(callback: types.CallbackQuery):
    uid = callback.from_user.id
    player = await get_player(uid)
    if not player:
        await save_player(uid, callback.from_user.first_name)
        player = await get_player(uid)

    user_id, name, mmr, last_play, streak = player
    today = date.today()
    last_play_date = datetime.fromisoformat(last_play).date()

    if today == last_play_date:
        await callback.answer("Ты уже играл сегодня! Возвращайся завтра 🔥", show_alert=True)
        return

    streak = streak + 1 if (today - last_play_date).days == 1 else 1
    bonus = min(streak * 2, 10)
    delta = random.randint(-30, 30) + bonus
    new_mmr = mmr + delta

    await update_player(uid, mmr=new_mmr, last_play=today.isoformat(), streak=streak)

    await callback.message.answer(
        f"Ты {'прибавил' if delta >= 0 else 'потерял'} {abs(delta)} MMR.\n"
        f"🔥 Серия: {streak} дней.\n"
        f"Твой новый MMR: {new_mmr} ({get_rank(new_mmr)})"
    )

@dp.callback_query(lambda c: c.data == "top")
async def top(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name, mmr FROM players ORDER BY mmr DESC LIMIT 10")
        top_players = await cur.fetchall()

    text = "🏆 Топ игроков:\n\n"
    for i, (name, mmr) in enumerate(top_players, start=1):
        text += f"{i}. {name} — {mmr} ({get_rank(mmr)})\n"

    await callback.message.answer(text)

@dp.callback_query(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    player = await get_player(callback.from_user.id)
    if not player:
        await save_player(callback.from_user.id, callback.from_user.first_name)
        player = await get_player(callback.from_user.id)
    _, name, mmr, last_play, streak = player
    await callback.message.answer(
        f"👤 {name}\nMMR: {mmr}\nРанг: {get_rank(mmr)}\nСерия: {streak}"
    )

# === ПИНГ-СЕРВЕР ===
async def handle(request):
    return web.Response(text="✅ Bot is alive!")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 Web server started on port 8080")

async def ping_self():
    while True:
        try:
            url = os.getenv("RENDER_EXTERNAL_URL")
            if url:
                requests.get(url)
                print("🔄 Pinged self to stay awake")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        await asyncio.sleep(300)  # каждые 5 минут


# --- Запуск ---
async def main():
    await init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
