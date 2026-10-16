import os
from threading import Thread
from flask import Flask

app = Flask("")


@app.route("/")
def home():
  return "Бот работает 24/7!"


def run():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = Thread(target=run)
  t.daemon = True
  t.start()
import asyncio
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "8828163971:AAFcyWMENFCzFHJkKO6CQfygpsjReLE3AR0"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# КД = 0 секунд для тестирования
COOLDOWN_TIME = 0
user_cooldowns = {}
user_inventory = {}  # {user_id: { "Название": count }}
user_balances = {}  # {user_id: coins}
user_last_farm_time = {}  # {user_id: timestamp}

# Награды в монетах за базовые редкости (х2)
REWARD_COINS = {
    "⚪ Обычный": 10,
    "🔵 Редкий": 30,
    "🟣 Эпический": 70,
    "🟡 Легендарный": 160,
    "🔴 МИФИЧЕСКИЙ": 400,
}

# Доход ученых в час (за 1 шт.)
FARM_RATES_PER_HOUR = {
    "✨ Эксклюзивный — Обычный Камерамен Учёный": 200,
    "✨ Эксклюзивный — Большой Камерамен Учёный": 1000,
    "✨ Эксклюзивный — Инженер Камерамен": 5000,
}

# Награды при выпадении из кейса ученых
SCIENTIST_REWARDS = {
    "Обычный Камерамен Учёный": 20,
    "Большой Камерамен Учёный": 100,
    "Инженер Камерамен": 500,
}

# Базовый пул персонажей (/spin)
GACHA_POOL = {
    "⚪ Обычный": [
        {
            "name": "Обычный Камерамен",
            "photo": "AgACAgIAAxkBAAM2atF_9oFMTdxTRDAl5TfLaJKKlSgAAvIeaxtpKohKAaYNEMymzUMBAAMCAAN4AAM9BA",
        },
        {
            "name": "Обычный Спикермен",
            "photo": "AgACAgIAAxkBAAMwatF_IJKMqqiR41a3ucnaaftJ39EAAvUeaxtpKohKVZx6eWMZMZIBAAMCAAN4AAM9BA",
        },
    ],
    "🔵 Редкий": [
        {
            "name": "Большой Спикермен",
            "photo": "AgACAgIAAxkBAANMatGJQ6tVvCpJG3OrctfOW9IOl6AAAgUfaxtpKohK5TL8RmFMXUgBAAMCAAN4AAM9BA",
        },
        {
            "name": "Большой Камерамен",
            "photo": "AgACAgIAAxkBAANSatGJyzGYl0XWuPVoekp2cIPS3bcAAgsfaxtpKohKWHToAAEHYHRAAQADAgADeAADPQQ",
        },
        {
            "name": "ТВ-мен",
            "photo": "AgACAgIAAxkBAAM4atGAGEyuP2vFGkW2ui9tSYGb5wgAAvYeaxtpKohKe6f0E2Xan8EBAAMCAAN4AAM9BA",
        },
        {
            "name": "Симп Камерамен",
            "photo": "AgACAgIAAxkBAANIatGIsqrRjfHYayRoPjhL4b_ZfiIAAgQfaxtpKohKCk20eMwsUJEBAAMCAAN4AAM9BA",
        },
    ],
    "🟣 Эпический": [
        {
            "name": "Вантузмен",
            "photo": "AgACAgIAAxkBAANQatGJw_bAopEqVKLtpGEhhNzeB7MAAgofaxtpKohKTBU12Qqf0wEBAAMCAAN4AAM9BA",
        },
        {
            "name": "Большой ТВ-мен 1.0",
            "photo": "AgACAgIAAxkBAANOatGJa0NJxx8aIpda5XKs2T9FpbkAAgkfaxtpKohK60yeE-mvaIsBAAMCAAN4AAM9BA",
        },
    ],
    "🟡 Легендарный": [
        {
            "name": "Камера-Титан 1.0",
            "photo": "AgACAgIAAxkBAANUatGJzglJG5MUxaopP_9EAAEr-lb9AAIMH2sbaSqISkd82X8HEDFhAQADAgADeAADPQQ",
        },
        {
            "name": "Спикер-Титан 1.0",
            "photo": "AgACAgIAAxkBAANYatGJ1PdbUQZKSbjs4EgOuOjMRmsAAg4faxtpKohK5T1sYjzRVVUBAAMCAAN4AAM9BA",
        },
        {
            "name": "ТВ-Титан 1.0",
            "photo": "AgACAgIAAxkBAANWatGJ0Y9efUDfjCY3ThWixV7M9X0AAg0faxtpKohKVjPouIIhOUMBAAMCAAN4AAM9BA",
        },
        {
            "name": "Спикервумен",
            "photo": "AgACAgIAAxkBAANaatGJ2KRexMgi6IiYc1FIeojQDtsAAg8faxtpKohKeF7f-8vHJMIBAAMCAAN4AAM9BA",
        },
    ],
    "🔴 МИФИЧЕСКИЙ": [
        {
            "name": "Камерамен Титан 2.0",
            "photo": "AgACAgIAAxkBAANcatGJ29AeApFutaztCK8lG0mvusEAAhAfaxtpKohK4hGQ5luQ_pYBAAMCAAN4AAM9BA",
        },
        {
            "name": "Спикермен Титан 2.0",
            "photo": "AgACAgIAAxkBAANeatGJ3niIOvupuuEzkhmq0CuFe8YAAhEfaxtpKohKFuZWZzxokp4BAAMCAAN4AAM9BA",
        },
    ],
}

RARITY_WEIGHTS = {
    "⚪ Обычный": 70.1,
    "🔵 Редкий": 25,
    "🟣 Эпический": 4,
    "🟡 Легендарный": 1.0,
    "🔴 МИФИЧЕСКИЙ": 0.1,
}

# Пул и шансы Кейса Учёных с добавленными фото
SCIENTIST_CASE_POOL = [
    {
        "name": "Обычный Камерамен Учёный",
        "rarity_label": "✨ Эксклюзивный",
        "weight": 93.0,
        "photo": "AgACAgIAAxkBAANhatGLYm7M7u2dDlU-oXLBG9hCuUsAAhIfaxtpKohKY3U7gy9B2o0BAAMCAAN4AAM9BA",
    },
    {
        "name": "Большой Камерамен Учёный",
        "rarity_label": "✨ Эксклюзивный",
        "weight": 6.0,
        "photo": "AgACAgIAAxkBAANiatGLZ2VMe_Yw3e7TWu5ktNgcqzwAAhMfaxtpKohKgfRhBNwh6FsBAAMCAAN4AAM9BA",
    },
    {
        "name": "Инженер Камерамен",
        "rarity_label": "✨ Эксклюзивный",
        "weight": 1.0,
        "photo": "AgACAgIAAxkBAANjatGLasg7RHfLLR5RBrg_adHxankAAhQfaxtpKohKBX_reeD_jHQBAAMCAAN4AAM9BA",
    },
]


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  await message.answer(
      "🛸 **Skibidi Gacha Bot запущен!**\n\n"
      "- `/spin` — Бесплатная крутка\n"
      "- `/shop` — Магазин кейсов\n"
      "- `/farm` — Ферма монет (нужны Учёные)\n"
      "- `/inventory` — Твоя коллекция\n"
      "- `/balance` — Проверить монеты",
      parse_mode="Markdown",
  )


@dp.message(Command("spin"))
async def cmd_spin(message: types.Message):
  user_id = message.from_user.id
  current_time = time.time()

  if user_id in user_cooldowns:
    time_passed = current_time - user_cooldowns[user_id]
    if time_passed < COOLDOWN_TIME:
      remaining_sec = int(COOLDOWN_TIME - time_passed)
      await message.reply(
          f"⏳ Кейс на перезарядке! Жди {remaining_sec // 60} мин."
          f" {remaining_sec % 60} сек."
      )
      return

  user_cooldowns[user_id] = current_time
  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )

  rarities = list(RARITY_WEIGHTS.keys())
  weights = list(RARITY_WEIGHTS.values())
  chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
  character_data = random.choice(GACHA_POOL[chosen_rarity])

  char_name = character_data["name"]
  char_photo = character_data.get("photo")
  chance_val = RARITY_WEIGHTS[chosen_rarity]

  coins_earned = REWARD_COINS[chosen_rarity]
  user_balances[user_id] = user_balances.get(user_id, 0) + coins_earned
  total_coins = user_balances[user_id]

  if user_id not in user_inventory:
    user_inventory[user_id] = {}

  item_key = f"{chosen_rarity} — {char_name}"
  user_inventory[user_id][item_key] = (
      user_inventory[user_id].get(item_key, 0) + 1
  )

  caption = (
      f"👤 Игрок: {user_mention}\n\n"
      f"🌀 **Открытие кейса...**\n\n"
      f"Тебе выпал: **{char_name}**!\n"
      f"Редкость: **{chosen_rarity}**\n"
      f"Шанс выпадения: `{chance_val}%`\n\n"
      f"💰 **Награда:** +{coins_earned} монет (Всего: {total_coins})"
  )

  if char_photo:
    try:
      await message.reply_photo(
          photo=char_photo, caption=caption, parse_mode="Markdown"
      )
      return
    except Exception as e:
      print(f"Ошибка отправки фото персонажа: {e}")

  await message.reply(caption, parse_mode="Markdown")


@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
  user_id = message.from_user.id
  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )
  balance = user_balances.get(user_id, 0)

  text = (
      f"🛒 **Магазин кейсов** ({user_mention})\n"
      f"💳 Твой баланс: **{balance}** монет\n\n"
      f"🧪 **Кейс Учёных** — `3000` монет\n"
      f"Редкость юнитов: **✨ Эксклюзивный**\n"
      f"├ ⚪ Обычный Камерамен Учёный — **93%** (доход 200/ч)\n"
      f"├ 🔵 Большой Камерамен Учёный — **6%** (доход 1000/ч)\n"
      f"└ 🟡 Инженер Камерамен — **1%** (доход 5000/ч)\n\n"
      f"👉 Купить кейс: `/buy_scientist`\n"
      f"🚜 Собрать фарм: `/farm`"
  )
  await message.reply(text, parse_mode="Markdown")


@dp.message(Command("buy_scientist"))
async def cmd_buy_scientist(message: types.Message):
  user_id = message.from_user.id
  cost = 3000
  balance = user_balances.get(user_id, 0)

  if balance < cost:
    await message.reply(
        f"❌ Недостаточно монет! Кейс Учёных стоит **{cost}** монет (у тебя"
        f" **{balance}**).",
        parse_mode="Markdown",
    )
    return

  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )

  weights = [item["weight"] for item in SCIENTIST_CASE_POOL]
  chosen_unit = random.choices(SCIENTIST_CASE_POOL, weights=weights, k=1)[0]

  char_name = chosen_unit["name"]
  rarity_label = chosen_unit["rarity_label"]
  chance_val = chosen_unit["weight"]
  char_photo = chosen_unit.get("photo")

  coins_earned = SCIENTIST_REWARDS.get(char_name, 0)
  user_balances[user_id] = balance - cost + coins_earned
  total_coins = user_balances[user_id]

  if user_id not in user_inventory:
    user_inventory[user_id] = {}

  item_key = f"{rarity_label} — {char_name}"
  user_inventory[user_id][item_key] = (
      user_inventory[user_id].get(item_key, 0) + 1
  )

  caption = (
      f"🧪 **Открытие Кейса Учёных...** ({user_mention})\n\n"
      f"Тебе выпал: **{char_name}**!\n"
      f"Редкость: **{rarity_label}**\n"
      f"Шанс выпадения: `{chance_val}%`\n\n"
      f"💸 **Списано:** -{cost} монет\n"
      f"💰 **Возврат:** +{coins_earned} монет\n"
      f"💳 **Текущий баланс:** {total_coins} монет\n\n"
      f"🚜 *Этот юнит теперь автоматически приносит доход в `/farm`!*"
  )

  if char_photo:
    try:
      await message.reply_photo(
          photo=char_photo, caption=caption, parse_mode="Markdown"
      )
      return
    except Exception as e:
      print(f"Ошибка отправки фото персонажа: {e}")

  await message.reply(caption, parse_mode="Markdown")


@dp.message(Command("farm"))
async def cmd_farm(message: types.Message):
  user_id = message.from_user.id
  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )
  items = user_inventory.get(user_id, {})

  hourly_rate = 0
  scientist_count = 0

  for item_key, rate in FARM_RATES_PER_HOUR.items():
    count = items.get(item_key, 0)
    if count > 0:
      hourly_rate += rate * count
      scientist_count += count

  if scientist_count == 0:
    await message.reply(
        f"⚙️ {user_mention}, у тебя нет учёных для работы фермы!\n\n"
        f"Купи **Кейс Учёных** в `/shop` (`/buy_scientist`), чтобы запустить"
        f" пассивный доход.",
        parse_mode="Markdown",
    )
    return

  current_time = time.time()
  last_time = user_last_farm_time.get(user_id, current_time)

  elapsed_seconds = current_time - last_time
  earned_coins = int((hourly_rate / 3600) * elapsed_seconds)

  user_last_farm_time[user_id] = current_time

  if earned_coins > 0:
    user_balances[user_id] = user_balances.get(user_id, 0) + earned_coins

  total_coins = user_balances.get(user_id, 0)

  await message.reply(
      f"🚜 **Лабораторная Ферма** ({user_mention})\n\n"
      f"👨‍🔬 Работающих учёных: **{scientist_count} шт.**\n"
      f"⚡ Общий доход: **{hourly_rate} монет/час**\n\n"
      f"💰 **Собрано монет:** +{earned_coins}\n"
      f"💳 **Твой баланс:** {total_coins} монет",
      parse_mode="Markdown",
  )


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
  user_id = message.from_user.id
  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )
  balance = user_balances.get(user_id, 0)
  await message.reply(
      f"🪙 {user_mention}, твой баланс: **{balance}** монет.",
      parse_mode="Markdown",
  )


@dp.message(Command("inventory"))
async def cmd_inventory(message: types.Message):
  user_id = message.from_user.id
  user_mention = message.from_user.mention_markdown(
      message.from_user.first_name
  )
  items = user_inventory.get(user_id, {})

  if not items:
    await message.reply(
        f"🎒 {user_mention}, твой инвентарь пуст!", parse_mode="Markdown"
    )
    return

  inventory_list = []
  for item, count in items.items():
    if count > 1:
      inventory_list.append(f"{item} **[x{count}]**")
    else:
      inventory_list.append(item)

  await message.reply(
      f"🎒 **Коллекция {user_mention}:**\n\n" + "\n".join(inventory_list[-20:]),
      parse_mode="Markdown",
  )


async def main():
  print(
      "✅ Бот запущен! Все учёные на месте, скрипт сбора фото удалён."
  )
  await dp.start_polling(bot)


if __name__ == "__main__":
  keep_alive()
  try:
    asyncio.run(main())
  except (KeyboardInterrupt, SystemExit):
    print("🔴 Бот остановлен.")
