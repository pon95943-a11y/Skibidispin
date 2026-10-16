import asyncio
import os
import random
import sqlite3
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv(8828163971:AAFcyWMENFCzFHJkKO6CQfygpsjReLE3AR0)

PULL_COST = 100          # цена одной крутки
DAILY_REWARD = 300       # ежедневный бонус
START_COINS = 500        # стартовые монеты
PITY_LIMIT = 50          # гарантия легендарки через N круток без неё

# Редкости: (название, шанс в %, эмодзи, монет за дубликат)
RARITIES = {
    "common":    ("Обычный",     60.0, "⚪", 20),
    "rare":      ("Редкий",      25.0, "🔵", 50),
    "epic":      ("Эпический",   11.0, "🟣", 120),
    "legendary": ("Легендарный",  4.0, "🌟", 400),
}

# Персонажи (можешь свободно добавлять своих)
CHARACTERS = {
    "common": [
        "Базовый Скибиди Туалет", "Мини Скибиди", "Туалет-Новичок",
        "Камерамен-Стажёр", "Спикермен-Стажёр",
    ],
    "rare": [
        "Камерамен", "Спикермен", "ТВ-мен", "Джетпак Скибиди", "Скибиди-Шпион",
    ],
    "epic": [
        "Большой Спикермен", "Титан Камерамен", "Скибиди-Босс", "G-Man Туалет",
    ],
    "legendary": [
        "Титан ТВ-мен", "Титан Спикермен", "Великий Скибиди-Император",
    ],
}

db = sqlite3.connect("gacha.db", check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, coins INTEGER, pity INTEGER DEFAULT 0, last_daily REAL DEFAULT 0)""")
db.execute("""CREATE TABLE IF NOT EXISTS inv(
    user_id INTEGER, name TEXT, rarity TEXT, count INTEGER DEFAULT 1,
    PRIMARY KEY(user_id, name))""")
db.commit()


def get_user(uid: int):
    row = db.execute("SELECT coins, pity, last_daily FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        db.execute("INSERT INTO users(id, coins) VALUES(?, ?)", (uid, START_COINS))
        db.commit()
        return START_COINS, 0, 0.0
    return row


def roll_rarity(pity: int) -> str:
    if pity + 1 >= PITY_LIMIT:
        return "legendary"
    keys = list(RARITIES)
    weights = [RARITIES[k][1] for k in keys]
    return random.choices(keys, weights=weights)[0]


def do_pull(uid: int):
    coins, pity, _ = get_user(uid)
    if coins < PULL_COST:
        return None
    rarity = roll_rarity(pity)
    pity = 0 if rarity == "legendary" else pity + 1
    name = random.choice(CHARACTERS[rarity])

    existing = db.execute("SELECT count FROM inv WHERE user_id=? AND name=?", (uid, name)).fetchone()
    refund = 0
    if existing:
        db.execute("UPDATE inv SET count=count+1 WHERE user_id=? AND name=?", (uid, name))
        refund = RARITIES[rarity][3]
    else:
        db.execute("INSERT INTO inv(user_id, name, rarity) VALUES(?,?,?)", (uid, name, rarity))

    coins = coins - PULL_COST + refund
    db.execute("UPDATE users SET coins=?, pity=? WHERE id=?", (coins, pity, uid))
    db.commit()
    return name, rarity, bool(existing), refund, coins, pity


def pull_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🚽 Крутить ещё ({PULL_COST})", callback_data="pull")
    ]])


def format_pull(res) -> str:
    name, rarity, dup, refund, coins, pity = res
    title, _, emoji, _ = RARITIES[rarity]
    text = f"{emoji} <b>{title}</b>\n<b>{name}</b>\n"
    if dup:
        text += f"\n♻️ Дубликат! Возврат: +{refund} 🪙"
    else:
        text += "\n✨ Новый персонаж!"
    text += f"\n\n🪙 Баланс: {coins}\n🎯 До гаранта: {PITY_LIMIT - pity}"
    return text


dp = Dispatcher()


@dp.message(Command("start"))
async def start(m: Message):
    get_user(m.from_user.id)
    await m.answer(
        "🚽 <b>Skibidi Gacha</b>\n\n"
        "Крути туалеты и собирай коллекцию!\n\n"
        "/pull — крутка\n"
        "/daily — ежедневный бонус\n"
        "/collection — твоя коллекция\n"
        "/balance — баланс\n"
        "/top — топ коллекционеров",
        parse_mode="HTML",
    )


@dp.message(Command("balance"))
async def balance(m: Message):
    coins, pity, _ = get_user(m.from_user.id)
    await m.answer(f"🪙 Монеты: {coins}\n🎯 До гаранта легендарки: {PITY_LIMIT - pity}")


@dp.message(Command("daily"))
async def daily(m: Message):
    coins, _, last = get_user(m.from_user.id)
    left = 86400 - (time.time() - last)
    if left > 0:
        h, mn = int(left // 3600), int(left % 3600 // 60)
        return await m.answer(f"⏳ Бонус будет доступен через {h}ч {mn}м")
    db.execute("UPDATE users SET coins=coins+?, last_daily=? WHERE id=?",
               (DAILY_REWARD, time.time(), m.from_user.id))
    db.commit()
    await m.answer(f"🎁 +{DAILY_REWARD} 🪙! Баланс: {coins + DAILY_REWARD}")


@dp.message(Command("pull"))
async def pull_cmd(m: Message):
    res = do_pull(m.from_user.id)
    if not res:
        return await m.answer("😢 Не хватает монет. Забери /daily")
    await m.answer(format_pull(res), parse_mode="HTML", reply_markup=pull_keyboard())


@dp.callback_query(F.data == "pull")
async def pull_btn(c: CallbackQuery):
    res = do_pull(c.from_user.id)
    if not res:
        return await c.answer("Не хватает монет 😢", show_alert=True)
    await c.message.answer(format_pull(res), parse_mode="HTML", reply_markup=pull_keyboard())
    await c.answer()


@dp.message(Command("collection"))
async def collection(m: Message):
    rows = db.execute("SELECT name, rarity, count FROM inv WHERE user_id=?", (m.from_user.id,)).fetchall()
    if not rows:
        return await m.answer("Коллекция пуста. Попробуй /pull")
    order = list(RARITIES)[::-1]
    rows.sort(key=lambda r: order.index(r[1]))
    total = sum(len(v) for v in CHARACTERS.values())
    lines = [f"📚 <b>Коллекция {len(rows)}/{total}</b>\n"]
    for name, rarity, cnt in rows:
        lines.append(f"{RARITIES[rarity][2]} {name} x{cnt}")
    await m.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("top"))
async def top(m: Message):
    rows = db.execute(
        "SELECT user_id, COUNT(*) c FROM inv GROUP BY user_id ORDER BY c DESC LIMIT 10").fetchall()
    if not rows:
        return await m.answer("Пока никого нет")
    text = "🏆 <b>Топ коллекционеров</b>\n\n" + "\n".join(
        f"{i}. id{uid} — {c} перс." for i, (uid, c) in enumerate(rows, 1))
    await m.answer(text, parse_mode="HTML")


async def main():
    bot = Bot(TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
