import os
from threading import Thread
import random
import time
import sqlite3
import html
from flask import Flask
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8828163971:AAHNLvX88C12qzhR-aQJaTB52FznXDyi5hM")
DB_PATH = os.getenv("DB_PATH", "database.db")

# ---------------- КОНСТАНТЫ ----------------
SPIN_COOLDOWN = 3600
CASE_COST = 3000
FARM_CAP_HOURS = 12
FARM_CAP = FARM_CAP_HOURS * 3600

# ---------------- ВЕБ-СЕРВЕР ДЛЯ RENDER ----------------
app = Flask(__name__)


@app.route("/")
def home():
    return "Бот работает 24/7!"


# ---------------- БАЗА ДАННЫХ ----------------
from contextlib import contextmanager

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS balances (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 0)")
    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER, item_name TEXT, count INTEGER, PRIMARY KEY (user_id, item_name))""")
    c.execute("CREATE TABLE IF NOT EXISTS cooldowns (user_id INTEGER PRIMARY KEY, last_time REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS farm_times (user_id INTEGER PRIMARY KEY, last_time REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS promo_used (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))")


def remember_user(uid, name):
    with db() as c:
        c.execute(
            "INSERT INTO users(user_id, name) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET name = excluded.name",
            (uid, name),
        )


def get_balance(uid):
    with db() as c:
        row = c.execute("SELECT coins FROM balances WHERE user_id = ?", (uid,)).fetchone()
    return row["coins"] if row else 0


def add_coins(uid, amount):
    with db() as c:
        c.execute(
            "INSERT INTO balances(user_id, coins) VALUES(?, MAX(0, ?)) "
            "ON CONFLICT(user_id) DO UPDATE SET coins = MAX(0, coins + ?)",
            (uid, amount, amount),
        )


def spend_coins(uid, cost):
    with db() as c:
        cur = c.execute(
            "UPDATE balances SET coins = coins - ? WHERE user_id = ? AND coins >= ?",
            (cost, uid, cost),
        )
        return cur.rowcount > 0


def get_inventory(uid):
    with db() as c:
        rows = c.execute("SELECT item_name, count FROM inventory WHERE user_id = ?", (uid,)).fetchall()
    return {r["item_name"]: r["count"] for r in rows}


def _add_item(uid, item):
    with db() as c:
        c.execute(
            "INSERT INTO inventory(user_id, item_name, count) VALUES(?, ?, 1) "
            "ON CONFLICT(user_id, item_name) DO UPDATE SET count = count + 1",
            (uid, item),
        )


def get_last_spin(uid):
    with db() as c:
        row = c.execute("SELECT last_time FROM cooldowns WHERE user_id = ?", (uid,)).fetchone()
    return row["last_time"] if row else 0


def claim_spin(uid):
    now = time.time()
    with db() as c:
        c.execute("INSERT OR IGNORE INTO cooldowns(user_id, last_time) VALUES(?, 0)", (uid,))
        cur = c.execute(
            "UPDATE cooldowns SET last_time = ? WHERE user_id = ? AND last_time <= ?",
            (now, uid, now - SPIN_COOLDOWN),
        )
        if cur.rowcount:
            return 0
        last = c.execute("SELECT last_time FROM cooldowns WHERE user_id = ?", (uid,)).fetchone()["last_time"]
    return max(1, int(SPIN_COOLDOWN - (now - last)))


# ---------------- ДАННЫЕ ИГРЫ ----------------
PROMO_CODES = {
    "SLADCIYKRYT": {"coins": 1000000, "item": None},
    "SKIBIDI": {"coins": 500, "item": None},
    "UPDATE": {"coins": 1000, "item": "✨ Эксклюзивный — Обычный Камерамен Учёный"},
}

REWARD_COINS = {
    "⚪ Обычный": 10,
    "🔵 Редкий": 30,
    "🟣 Эпический": 70,
    "🟡 Легендарный": 160,
    "🔴 МИФИЧЕСКИЙ": 400,
}

FARM_RATES_PER_HOUR = {
    "✨ Эксклюзивный — Обычный Камерамен Учёный": 200,
    "✨ Эксклюзивный — Большой Камерамен Учёный": 1000,
    "✨ Эксклюзивный — Инженер Камерамен": 5000,
}

GACHA_POOL = {
    "⚪ Обычный": [
        {"name": "Обычный Камерамен", "photo": "AgACAgIAAxkBAAM2atF_9oFMTdxTRDAl5TfLaJKKlSgAAvIeaxtpKohKAaYNEMymzUMBAAMCAAN4AAM9BA"},
        {"name": "Обычный Спикермен", "photo": "AgACAgIAAxkBAAMwatF_IJKMqqiR41a3ucnaaftJ39EAAvUeaxtpKohKVZx6eWMZMZIBAAMCAAN4AAM9BA"},
    ],
    "🔵 Редкий": [
        {"name": "Большой Спикермен", "photo": "AgACAgIAAxkBAANMatGJQ6tVvCpJG3OrctfOW9IOl6AAAgUfaxtpKohK5TL8RmFMXUgBAAMCAAN4AAM9BA"},
        {"name": "Большой Камерамен", "photo": "AgACAgIAAxkBAANSatGJyzGYl0XWuPVoekp2cIPS3bcAAgsfaxtpKohKWHToAAEHYHRAAQADAgADeAADPQQ"},
        {"name": "ТВ-мен", "photo": "AgACAgIAAxkBAAM4atGAGEyuP2vFGkW2ui9tSYGb5wgAAvYeaxtpKohKe6f0E2Xan8EBAAMCAAN4AAM9BA"},
        {"name": "Симп Камерамен", "photo": "AgACAgIAAxkBAANIatGIsqrRjfHYayRoPjhL4b_ZfiIAAgQfaxtpKohKCk20eMwsUJEBAAMCAAN4AAM9BA"},
    ],
    "🟣 Эпический": [
        {"name": "Вантузмен", "photo": "AgACAgIAAxkBAANQatGJw_bAopEqVKLtpGEhhNzeB7MAAgofaxtpKohKTBU12Qqf0wEBAAMCAAN4AAM9BA"},
        {"name": "Большой ТВ-мен 1.0", "photo": "AgACAgIAAxkBAANOatGJa0NJxx8aIpda5XKs2T9FpbkAAgkfaxtpKohK60yeE-mvaIsBAAMCAAN4AAM9BA"},
    ],
    "🟡 Легендарный": [
        {"name": "Камера-Титан 1.0", "photo": "AgACAgIAAxkBAANUatGJzglJG5MUxaopP_9EAAEr-lb9AAIMH2sbaSqISkd82X8HEDFhAQADAgADeAADPQQ"},
        {"name": "Спикер-Титан 1.0", "photo": "AgACAgIAAxkBAANYatGJ1PdbUQZKSbjs4EgOuOjMRmsAAg4faxtpKohK5T1sYjzRVVUBAAMCAAN4AAM9BA"},
        {"name": "ТВ-Титан 1.0", "photo": "AgACAgIAAxkBAANWatGJ0Y9efUDfjCY3ThWixV7M9X0AAg0faxtpKohKVjPouIIhOUMBAAMCAAN4AAM9BA"},
        {"name": "Спикервумен", "photo": "AgACAgIAAxkBAANaatGJ2KRexMgi6IiYc1FIeojQDtsAAg8faxtpKohKeF7f-8vHJMIBAAMCAAN4AAM9BA"},
    ],
    "🔴 МИФИЧЕСКИЙ": [
        {"name": "Камерамен Титан 2.0", "photo": "AgACAgIAAxkBAANcatGJ29AeApFutaztCK8lG0mvusEAAhAfaxtpKohK4hGQ5luQ_pYBAAMCAAN4AAM9BA"},
        {"name": "Спикермен Титан 2.0", "photo": "AgACAgIAAxkBAANeatGJ3niIOvupuuEzkhmq0CuFe8YAAhEfaxtpKohKFuZWZzxokp4BAAMCAAN4AAM9BA"},
    ],
}

RARITY_WEIGHTS = {
    "⚪ Обычный": 69.9,
    "🔵 Редкий": 25,
    "🟣 Эпический": 4,
    "🟡 Легендарный": 1.0,
    "🔴 МИФИЧЕСКИЙ": 0.1,
}

SCIENTIST_CASE_POOL = [
    {"name": "Обычный Камерамен Учёный", "rarity_label": "✨ Эксклюзивный", "weight": 93.0, "photo": "AgACAgIAAxkBAANhatGLYm7M7u2dDlU-oXLBG9hCuUsAAhIfaxtpKohKY3U7gy9B2o0BAAMCAAN4AAM9BA"},
    {"name": "Большой Камерамен Учёный", "rarity_label": "✨ Эксклюзивный", "weight": 6.0, "photo": "AgACAgIAAxkBAANiatGLZ2VMe_Yw3e7TWu5ktNgcqzwAAhMfaxtpKohKgfRhBNwh6FsBAAMCAAN4AAM9BA"},
    {"name": "Инженер Камерамен", "rarity_label": "✨ Эксклюзивный", "weight": 1.0, "photo": "AgACAgIAAxkBAANjatGLasg7RHfLLR5RBrg_adHxankAAhQfaxtpKohKBX_reeD_jHQBAAMCAAN4AAM9BA"},
]

RARITY_ORDER = ["🔴 МИФИЧЕСКИЙ", "🟡 Легендарный", "🟣 Эпический", "🔵 Редкий", "⚪ Обычный", "✨ Эксклюзивный"]

BTN_CARD = "🎴 Карта"
BTN_TOP = "🏆 Топ"
BTN_PROFILE = "👤 Профиль"
BTN_INV = "🎒 Инвентарь"
BTN_SHOP = "🛒 Магазин"
BTN_LAB = "🧪 Лаборатория"
BTN_CHANCES = "📊 Шансы"
BTN_PROMO = "🎁 Промокод"
MENU_TEXTS = {BTN_CARD, BTN_TOP, BTN_PROFILE, BTN_INV, BTN_SHOP, BTN_LAB, BTN_CHANCES, BTN_PROMO}

awaiting_promo = set()


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CARD), KeyboardButton(text=BTN_TOP)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_INV)],
            [KeyboardButton(text=BTN_SHOP)],
            [KeyboardButton(text=BTN_LAB), KeyboardButton(text=BTN_CHANCES)],
            [KeyboardButton(text=BTN_PROMO)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие 👇",
    )


def num(n):
    return f"{int(n):,}".replace(",", " ")


def fmt_time(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    parts = []
    if h:
        parts.append(f"{h} ч")
    if m:
        parts.append(f"{m} мин")
    if s or not parts:
        parts.append(f"{s} сек")
    return " ".join(parts)


def farm_rate(uid):
    inv = get_inventory(uid)
    rate = sum(FARM_RATES_PER_HOUR[k] * inv.get(k, 0) for k in FARM_RATES_PER_HOUR)
    count = sum(inv.get(k, 0) for k in FARM_RATES_PER_HOUR)
    return rate, count


def collect_farm(uid):
    now = time.time()
    rate, _ = farm_rate(uid)
    earned = 0
    with db() as c:
        row = c.execute("SELECT last_time FROM farm_times WHERE user_id = ?", (uid,)).fetchone()
        reset = False
        if rate == 0 or row is None:
            reset = True
        else:
            elapsed = min(now - row["last_time"], FARM_CAP)
            earned = int(rate / 3600 * elapsed)
            reset = earned > 0
        if reset:
            c.execute(
                "INSERT INTO farm_times(user_id, last_time) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_time = excluded.last_time",
                (uid, now),
            )
    if earned > 0:
        add_coins(uid, earned)
    return earned


def farm_pending(uid, rate):
    if rate == 0:
        return 0
    with db() as c:
        row = c.execute("SELECT last_time FROM farm_times WHERE user_id = ?", (uid,)).fetchone()
    if row is None:
        return 0
    return int(rate / 3600 * min(time.time() - row["last_time"], FARM_CAP))


def grant_item(uid, item):
    if item in FARM_RATES_PER_HOUR:
        collect_farm(uid)
    _add_item(uid, item)


async def send_photo_or_text(target: Message, photo, caption, **kwargs):
    if photo:
        try:
            await target.answer_photo(photo=photo, caption=caption, parse_mode="HTML", **kwargs)
            return
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
    await target.answer(caption, parse_mode="HTML", **kwargs)


class TouchMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            remember_user(user.id, user.full_name)
            if isinstance(event, Message) and event.text in MENU_TEXTS:
                awaiting_promo.discard(user.id)
        return await handler(event, data)


dp = Dispatcher()
dp.message.outer_middleware(TouchMiddleware())
dp.callback_query.outer_middleware(TouchMiddleware())


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🛸 <b>Skibidi Gacha</b> приветствует тебя!\n"
        "Собирай редких Скибиди, копи монеты и соревнуйся с другими!\n\n"
        "🎴 Жми <b>Карта</b> — раз в час можно получить нового персонажа.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Меню 👇", reply_markup=main_menu())


@dp.message(Command("spin"))
@dp.message(F.text == BTN_CARD)
async def cmd_spin(message: Message):
    uid = message.from_user.id
    left = claim_spin(uid)
    if left > 0:
        await message.reply(f"⏳ Карта ещё не готова! Подожди <b>{fmt_time(left)}</b>.", parse_mode="HTML")
        return

    rarity = random.choices(list(RARITY_WEIGHTS), weights=list(RARITY_WEIGHTS.values()), k=1)[0]
    unit = random.choice(GACHA_POOL[rarity])
    coins = REWARD_COINS[rarity]

    add_coins(uid, coins)
    grant_item(uid, f"{rarity} — {unit['name']}")

    caption = (
        f"👤 {message.from_user.mention_html()}\n\n"
        f"🌀 <b>Тебе выпал: {unit['name']}</b>\n"
        f"Редкость: <b>{rarity}</b>\n"
        f"Шанс: <code>{RARITY_WEIGHTS[rarity]}%</code>\n\n"
        f"💰 +{coins} монет · Баланс: <b>{num(get_balance(uid))}</b>\n"
        f"⏳ Следующая карта через 1 час"
    )
    await send_photo_or_text(message, unit.get("photo"), caption)


@dp.message(Command("balance"))
@dp.message(Command("profile"))
@dp.message(F.text == BTN_PROFILE)
async def cmd_profile(message: Message):
    uid = message.from_user.id
    inv = get_inventory(uid)
    rate, sc = farm_rate(uid)
    left = SPIN_COOLDOWN - (time.time() - get_last_spin(uid))
    spin = "✅ готова" if left <= 0 else f"через {fmt_time(left)}"
    await message.answer(
        f"👤 <b>Профиль</b> — {message.from_user.mention_html()}\n\n"
        f"🪙 Баланс: <b>{num(get_balance(uid))}</b>\n"
        f"🎒 Карт: <b>{sum(inv.values())}</b> (уникальных: {len(inv)})\n"
        f"🧪 Учёных: <b>{sc}</b> · доход {num(rate)}/ч\n"
        f"🎴 Следующая карта: <b>{spin}</b>",
        parse_mode="HTML",
    )


@dp.message(Command("inventory"))
@dp.message(F.text == BTN_INV)
async def cmd_inventory(message: Message):
    inv = get_inventory(message.from_user.id)
    if not inv:
        await message.answer("🎒 Инвентарь пуст. Жми <b>🎴 Карта</b>!", parse_mode="HTML")
        return

    def key(it):
        label = it[0].split(" — ")[0]
        return RARITY_ORDER.index(label) if label in RARITY_ORDER else 99

    lines = []
    for name, cnt in sorted(inv.items(), key=key):
        lines.append(f"{name} <b>×{cnt}</b>" if cnt > 1 else name)
    await message.answer(
        f"🎒 <b>Коллекция</b> {message.from_user.mention_html()}\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )


@dp.message(Command("top"))
@dp.message(F.text == BTN_TOP)
async def cmd_top(message: Message):
    with db() as c:
        rows = c.execute(
            "SELECT u.name AS name, b.coins AS coins FROM balances b "
            "LEFT JOIN users u ON u.user_id = b.user_id ORDER BY b.coins DESC LIMIT 10"
        ).fetchall()
    if not rows:
        await message.answer("Пока никого нет в топе.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, r in enumerate(rows):
        mark = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{mark} {html.escape(r['name'] or 'Игрок')} — <b>{num(r['coins'])}</b> 🪙")
    await message.answer("🏆 <b>Топ по монетам</b>\n\n" + "\n".join(lines), parse_mode="HTML")


@dp.message(Command("chances"))
@dp.message(F.text == BTN_CHANCES)
async def cmd_chances(message: Message):
    lines = ["📊 <b>Шансы</b>\n", "🎴 <b>Карта (раз в час)</b>"]
    for rar, w in RARITY_WEIGHTS.items():
        lines.append(f"{rar} — {w}% (+{REWARD_COINS[rar]} 🪙)")
    lines.append(f"\n🧪 <b>Кейс Учёных ({num(CASE_COST)} 🪙)</b>")
    for u in SCIENTIST_CASE_POOL:
        rate = FARM_RATES_PER_HOUR[f"{u['rarity_label']} — {u['name']}"]
        lines.append(f"{u['name']} — {u['weight']}% ({num(rate)}/ч)")
    await message.answer("\n".join(lines), parse_mode="HTML")


def shop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🧪 Купить кейс — {num(CASE_COST)} 🪙", callback_data="buy_scientist")
    ]])


@dp.message(Command("shop"))
@dp.message(F.text == BTN_SHOP)
async def cmd_shop(message: Message):
    uid = message.from_user.id
    lines = [
        "🛒 <b>Магазин</b>",
        f"💳 Баланс: <b>{num(get_balance(uid))}</b> 🪙\n",
        f"🧪 <b>Кейс Учёных</b> — {num(CASE_COST)} 🪙",
        "Внутри юнит для пассивного дохода:",
    ]
    for u in SCIENTIST_CASE_POOL:
        rate = FARM_RATES_PER_HOUR[f"{u['rarity_label']} — {u['name']}"]
        lines.append(f"├ {u['name']} — {u['weight']}% · {num(rate)}/ч")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=shop_kb())


async def open_scientist_case(user, target: Message):
    uid = user.id
    if not spend_coins(uid, CASE_COST):
        return False
    unit = random.choices(SCIENTIST_CASE_POOL, weights=[u["weight"] for u in SCIENTIST_CASE_POOL], k=1)[0]
    item = f"{unit['rarity_label']} — {unit['name']}"
    grant_item(uid, item)
    rate = FARM_RATES_PER_HOUR[item]
    caption = (
        f"🧪 <b>Кейс Учёных</b> — {user.mention_html()}\n\n"
        f"Тебе выпал: <b>{unit['name']}</b>\n"
        f"Редкость: <b>{unit['rarity_label']}</b> · шанс <code>{unit['weight']}%</code>\n"
        f"⚡ Доход: {num(rate)} монет/ч\n\n"
        f"💸 Списано: -{num(CASE_COST)}\n"
        f"💳 Баланс: <b>{num(get_balance(uid))}</b>"
    )
    await send_photo_or_text(target, unit.get("photo"), caption)
    return True


@dp.callback_query(F.data == "buy_scientist")
async def cb_buy(cb: CallbackQuery):
    ok = await open_scientist_case(cb.from_user, cb.message)
    if ok:
        await cb.answer()
    else:
        await cb.answer(
            f"Не хватает монет! Нужно {num(CASE_COST)}, у тебя {num(get_balance(cb.from_user.id))}.",
            show_alert=True,
        )


@dp.message(Command("buy_scientist"))
async def cmd_buy(message: Message):
    if not await open_scientist_case(message.from_user, message):
        await message.reply(
            f"❌ Не хватает монет! Нужно <b>{num(CASE_COST)}</b>, у тебя <b>{num(get_balance(message.from_user.id))}</b>.",
            parse_mode="HTML",
        )


def lab_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 Собрать монеты", callback_data="collect_farm")
    ]])


def lab_text(uid, mention):
    rate, sc = farm_rate(uid)
    if sc == 0:
        return (
            f"🧪 <b>Лаборатория</b> — {mention}\n\n"
            f"У тебя нет учёных. Купи <b>Кейс Учёных</b> в магазине ({num(CASE_COST)} 🪙).",
            False,
        )
    return (
        f"🧪 <b>Лаборатория</b> — {mention}\n\n"
        f"👨‍🔬 Учёных: <b>{sc}</b>\n"
        f"⚡ Доход: <b>{num(rate)}</b> монет/ч\n"
        f"📦 Накоплено: <b>{num(farm_pending(uid, rate))}</b> (максимум за {FARM_CAP_HOURS} ч)\n"
        f"💳 Баланс: <b>{num(get_balance(uid))}</b>",
        True,
    )


@dp.message(Command("farm"))
@dp.message(F.text == BTN_LAB)
async def cmd_lab(message: Message):
    text, has = lab_text(message.from_user.id, message.from_user.mention_html())
    await message.answer(text, parse_mode="HTML", reply_markup=lab_kb() if has else None)


@dp.callback_query(F.data == "collect_farm")
async def cb_collect(cb: CallbackQuery):
    uid = cb.from_user.id
    earned = collect_farm(uid)
    await cb.answer(f"+{num(earned)} монет" if earned else "Пока нечего собирать")
    text, has = lab_text(uid, cb.from_user.mention_html())
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=lab_kb() if has else None)
    except Exception:
        pass


def apply_promo(uid, code):
    code = code.strip().upper()
    promo = PROMO_CODES.get(code)
    if not promo:
        return "❌ Такого промокода нет или он просрочен."
    with db() as c:
        cur = c.execute("INSERT OR IGNORE INTO promo_used(user_id, code) VALUES(?, ?)", (uid, code))
        fresh = cur.rowcount > 0
    if not fresh:
        return "❌ Ты уже активировал этот промокод."
    add_coins(uid, promo["coins"])
    if promo["item"]:
        grant_item(uid, promo["item"])
    return f"🎉 Промокод активирован! Получено: +{num(promo['coins'])} 🪙" + (f" и предмет: {promo['item']}" if promo["item"] else "")


@dp.message(Command("promo"))
@dp.message(F.text == BTN_PROMO)
async def cmd_promo_btn(message: Message, command: CommandObject = None):
    uid = message.from_user.id
    arg = command.args if command else None
    if not arg:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            arg = parts[1]
    if not arg:
        awaiting_promo.add(uid)
        await message.answer("🎁 Введи промокод следующим сообщением:", reply_markup=main_menu())
        return
    await message.answer(apply_promo(uid, arg))


@dp.message(F.text & ~F.text.in_(MENU_TEXTS))
async def text_interceptor(message: Message):
    uid = message.from_user.id
    if uid in awaiting_promo:
        awaiting_promo.remove(uid)
        await message.answer
