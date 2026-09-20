import logging
import asyncio
import sqlite3
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from aiocryptopay import CryptoPay, Networks
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 🔥 1. ԿԱՐԳԱՎՈՐՈՒՄՆԵՐ (Ամեն ինչ արդեն լրացված է Ձեր տվյալներով)
TELEGRAM_TOKEN = "8856804681:AAFxu6Cs-t5VoW41XbHJkU4NbXp4JJYIdZY" # Ձեր BotFather-ի տոկենը կթարմացվի Render-ում
CRYPTO_TOKEN = "636509:AAtznSvL2z8ia8xsOwgM9ENA0RAryY3EIs3"
USDT_RATE = 400.0          # 1 USDT = 400 AMD
DAILY_INTEREST = 0.01      # Օրական 1% աճ
REFERRAL_REG_BONUS = 60.0  # +60 ֏ ամեն հրավիրած անդամի համար
WEB_APP_URL = "https://github.io"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
crypto = CryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)

class WithdrawState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_address = State()

# Տվյալների բազա
conn = sqlite3.connect("invest_bot_amd.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, referrer_id INTEGER)''')
conn.commit()

# Մենյու
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Իմ Բալանսը (Live ֏)", web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton(text="📥 Ավտոմատ Լիցքավորում"), KeyboardButton(text="💸 Ավտոմատ Կանխիկացում")],
        [KeyboardButton(text="👥 Ռեֆերալներ"), KeyboardButton(text="📊 Պայմաններ")]
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

# 📥 ԱՎՏՈՄԱՏ ԼԻՑՔԱՎՈՐՈՒՄ (USDT -> AMD)
@dp.message(lambda message: message.text == "📥 Ավտոմատ Լիցքավորում")
async def deposit_cmd(message: types.Message):
    await message.answer("💡 Լիցքավորման նվազագույն չափը **1 USDT (400 ֏)** է։\nՍեղմեք ստորև գտնվող կոճակը վճարման հաշիվ ստեղծելու համար․")
    invoice = await crypto.create_invoice(asset='USDT', amount=1.0) # Ստեղծում ենք թեստային 1 USDT հաշիվ
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Վճարել `@CryptoBot`-ով", url=invoice.pay_url)],
        [InlineKeyboardButton(text="🔄 Ստուգել Վճարումը", callback_data=f"check_{invoice.invoice_id}")]
    ])
    await message.answer("Ձեր հաշիվը պատրաստ է․", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("check_"))
async def check_invoice_callback(callback: types.CallbackQuery):
    invoice_id = int(callback.data.split("_")[1])
    invoices = await crypto.get_invoices(invoice_ids=invoice_id)
    if invoices and invoices[0].status == 'paid':
        user_id = callback.from_user.id
        amd_amount = float(invoices[0].amount) * USDT_RATE
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amd_amount, user_id))
        conn.commit()
        await callback.message.answer(f"✅ Վճարումը հաստատվեց։ Ձեր հաշվեկշռին ավելացավ **+{amd_amount:.0f} ֏**")
    else:
        await callback.answer("❌ Վճարումը դեռ չի կատարվել։", show_alert=True)

# 💸 ԱՎՏՈՄԱՏ ԿԱՆԽԻԿԱՑՈՒՄ (AMD -> USDT)
@dp.message(lambda message: message.text == "💸 Ավտոմատ Կանխիկացում")
async def withdraw_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0.0
    if balance < 400:
        await message.answer("⚠️ Կանխիկացման նվազագույն գումարը **400 ֏ (1 USDT)** է։")
        return
    await state.update_data(balance=balance)
    await message.answer(f"💰 Ձեր բալանսը՝ **{balance:.2f} ֏**\nԳրեք, թե ինչքան դրամ եք ցանկանում կանխիկացնել․")
    await state.set_state(WithdrawState.waiting_for_amount)

@dp.message(WithdrawState.waiting_for_amount)
async def withdraw_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Խնդրում եմ գրեք միայն թիվ (օրինակ՝ 400)․")
        return
    amount = float(message.text)
    data = await state.get_data()
    if amount < 400 or amount > data['balance']:
        await message.answer("⚠️ Գումարը սխալ է կամ գերազանցում է Ձեր բալանսը։")
        return
    await state.update_data(withdraw_amount=amount)
    await message.answer("📬 Այժմ ուղարկեք Ձեր **USDT (TRC-20 կամ TON)** դրամապանակի հասցեն `@CryptoBot`-ից․")
    await state.set_state(WithdrawState.waiting_for_address)

@dp.message(WithdrawState.waiting_for_address)
async def withdraw_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    data = await state.get_data()
    amount_amd = data['withdraw_amount']
    amount_usdt = amount_amd / USDT_RATE
    user_id = message.from_user.id
    await state.clear()
    
    # Ավտոմատ փոխանցում Crypto Pay API-ով
    try:
        # Փորձում ենք կատարել ավտոմատ ելքը սերվերով
        transfer = await crypto.transfer(user_id=user_id, asset='USDT', amount=amount_usdt, spend_id=os.urandom(8).hex())
        if transfer:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount_amd, user_id))
            conn.commit()
            await message.answer(f"✅ Կանխիկացումը հաջողվեց։ **{amount_usdt:.2f} USDT ({amount_amd:.0f} ֏)** ավտոմատ ուղարկվեց Ձեր դրամապանակին։")
    except Exception as e:
        await message.answer("⚠️ Ավտոմատ փոխանցման սխալ։ Հնարավոր է սերվերի բալանսը դատարկ է կամ հասցեն սխալ է։ Կապնվեք ադմինի հետ։")

@dp.message(lambda message: message.text == "📊 Պայմաններ")
async def show_rules(message: types.Message):
    await message.answer(f"📈 **Պայմաններ՝**\n• Օրական {DAILY_INTEREST*100:.0f}% ավտոմատ աճ բալանսից:\n• +{REFERRAL_REG_BONUS:.0f} ֏ ամեն հրավիրած ընկերոջ համար:\n• 1 USDT = {USDT_RATE:.0f} ֏")

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
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
