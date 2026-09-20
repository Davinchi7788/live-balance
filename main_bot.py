import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 🔥 ՏԵՂԱԴՐԵՔ ՁԵՐ ՏՎՅԱԼՆԵՐԸ ԱՅՍՏԵՂ 👇
TELEGRAM_TOKEN = "8856804681:AAFxu6Cs-t5VoW41XbHJkU4NbXp4JJYIdZY"
WEB_APP_URL = "https://github.io"
DAILY_INTEREST = 0.01      # Օրական 1% աճ
REFERRAL_REG_BONUS = 60.0  # +60 ֏ ամեն հրավիրած անդամի համար

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Տվյալների բազա
conn = sqlite3.connect("invest_bot_amd.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, referrer_id INTEGER)''')
conn.commit()

# Մենյու
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Իմ Բալանսը (Live ֏)", web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton(text="📥 Ներդրում Անել"), KeyboardButton(text="👥 Ռեֆերալներ")],
        [KeyboardButton(text="📊 Պայմաններ")]
    ], resize_keyboard=True
)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        cursor.execute("INSERT INTO users (user_id, balance, referrer_id) VALUES (?, ?, ?)", (user_id, 0.0, referrer_id))
        conn.commit()
        if referrer_id:
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_REG_BONUS, referrer_id))
            conn.commit()
            try: await bot.send_message(referrer_id, f"👥 Նոր գրանցում Ձեր հղումով: Ձեզ տրվեց **+{REFERRAL_REG_BONUS:.0f} ֏**", parse_mode="Markdown")
            except: pass
    await message.answer("👋 Բարի գալուստ **AMD Capital**:\nՍեղմեք ներքևի կոճակը լայվ բալանսը տեսնելու համար:", reply_markup=main_menu)

@dp.message(lambda message: message.text == "👥 Ռեֆերալներ")
async def referral_menu(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me{bot_info.username}?start={user_id}"
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()[0]
    await message.answer(f"👥 **Ռեֆերալային համակարգ**\n\n🎁 Բոնուս գրանցման համար՝ **+{REFERRAL_REG_BONUS:.0f} ֏** տեղում:\n🔗 Ձեր հղումը՝\n`{ref_link}`\n\n📊 Հրավիրված անդամներ՝ **{ref_count} հոգի**", parse_mode="Markdown")

@dp.message(lambda message: message.text == "📥 Ներդրում Անել")
async def deposit(message: types.Message):
    await message.answer("💳 Գումար ներդնելու կամ քարտով փոխանցում անելու համար կապնվեք ադմինիստրատորի հետ:\n\n*Ադմինի հաշիվը դեռ նշված չէ:*")

@dp.message(lambda message: message.text == "📊 Պայմաններ")
async def show_rules(message: types.Message):
    await message.answer(f"📈 **Պայմաններ՝**\n• Օրական {DAILY_INTEREST*100:.0f}% ավտոմատ աճ բալանսից:\n• +{REFERRAL_REG_BONUS:.0f} ֏ ամեն հրավիրած ընկերոջ համար:")

async def calculate_daily_interest():
    cursor.execute("SELECT user_id, balance FROM users WHERE balance > 0")
    for user_id, balance in cursor.fetchall():
        bonus = balance * DAILY_INTEREST
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, user_id))
        conn.commit()
        try: await bot.send_message(user_id, f"🎉 Ձեր օրական տոկոսը ավելացավ: +{bonus:.2f} ֏:")
        except: pass

async def main():
    scheduler.add_job(calculate_daily_interest, "cron", hour=0, minute=0)
    scheduler.start()
    logging.basicConfig(level=logging.INFO)
    
    import os
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler
    from aiohttp import web
    
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    await site.start()
    
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
