import os
import json
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# ---------------- Load .env ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ---------------- Database ----------------
DB_FILE = "database.json"


def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": {},
            "stock": {
                "MLBBbal":
                {},  # {"1000": ["code1", "code2"], "2000": ["code3"]}
                "MLBBph": {},
                "PUPG": {}
            },
            "receipts": {},
            "topup_requests": {},
            "prices": {
                "MLBBbal": {},  # {"1000": 2000, "2000": 4000}
                "MLBBph": {},
                "PUPG": {}
            },
            "payment": {
                "Wave": {
                    "phone": "09673585480",
                    "name": "Nine Nine"
                },
                "KPay": {
                    "phone": "09678786528",
                    "name": "Ma May Phoo Wai"
                }
            },
            "sales_total": 0
        }
    with open(DB_FILE, "r") as f:
        data = json.load(f)

    # Update old structure if needed
    if "stock" in data and isinstance(data["stock"],
                                      dict) and "mlbb" in data["stock"]:
        new_stock = {"MLBBbal": {}, "MLBBph": {}, "PUPG": {}}
        new_prices = {"MLBBbal": {}, "MLBBph": {}, "PUPG": {}}

        # Migrate MLBB codes assuming they are for MLBBbal
        mlbb_codes = data["stock"].get("mlbb", [])
        if mlbb_codes:
            new_stock["MLBBbal"]["1000"] = mlbb_codes
            if "price" in data and data["price"] > 0:
                new_prices["MLBBbal"]["1000"] = data["price"]
            else:
                new_prices["MLBBbal"]["1000"] = 1000

        # Migrate PUBG codes to PUPG
        pubg_codes = data["stock"].get("pubg", [])
        if pubg_codes:
            new_stock["PUPG"]["60"] = pubg_codes
            if "price" in data and data["price"] > 0:
                new_prices["PUPG"]["60"] = data["price"]
            else:
                new_prices["PUPG"]["60"] = 1000

        data["stock"] = new_stock
        data["prices"] = new_prices
        save_db(data)

    # Migrate PUBG to PUPG in existing structure
    if "stock" in data and "PUBG" in data["stock"]:
        data["stock"]["PUPG"] = data["stock"].pop("PUBG")
    if "prices" in data and "PUBG" in data["prices"]:
        data["prices"]["PUPG"] = data["prices"].pop("PUBG")

    # Ensure all expected keys exist
    if "stock" not in data:
        data["stock"] = {"MLBBbal": {}, "MLBBph": {}, "PUPG": {}}
    if "prices" not in data:
        data["prices"] = {"MLBBbal": {}, "MLBBph": {}, "PUPG": {}}
    if "topup_requests" not in data: data["topup_requests"] = {}
    if "users" not in data: data["users"] = {}
    if "payment" not in data:
        data["payment"] = {
            "Wave": {
                "phone": "09673585480",
                "name": "Nine Nine"
            },
            "Kpay": {
                "phone": "09678786528",
                "name": "Ma May Phoo Wai"
            }
        }
    if "sales_total" not in data: data["sales_total"] = 0
    if "pending_registrations" not in data: data["pending_registrations"] = {}

    # Clear old codes from MLBBph and PUPG (one-time cleanup)
    if "cleanup_done" not in data:
        if "MLBBph" in data["stock"]:
            data["stock"]["MLBBph"] = {}
        if "PUPG" in data["stock"]:
            data["stock"]["PUPG"] = {}
        data["cleanup_done"] = True

    return data


def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


db = load_db()


# ---------------- Helpers ----------------
def get_user(uid):
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0, "history": [], "approved": False}
        save_db(db)
    return db["users"][uid]


def is_user_approved(uid):
    return uid in db["users"] and db["users"][uid].get("approved", False)


def generate_receipt_id():
    while True:
        rid = str(random.randint(10000, 999999))
        if rid not in db["receipts"] and rid not in db["topup_requests"]:
            return rid


def validate_receipt_id(rid):
    return rid.isdigit() and 5 <= len(rid) <= 6


def get_available_amounts(game_type):
    """Get available amounts for a game type that have stock"""
    amounts = []
    if game_type in db["stock"]:
        for amount, codes in db["stock"][game_type].items():
            if codes:  # Only include amounts that have codes
                amounts.append(amount)
    return sorted(amounts)


def get_game_display_name(game_type):
    names = {
        "MLBBbal": "Mobile Legends (Bal)",
        "MLBBph": "Mobile Legends (PH)",
        "PUPG": "PUPG Mobile"
    }
    return names.get(game_type, game_type)


# ---------------- User Commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[
        InlineKeyboardButton("📌 အကောင့်ဖွင့်ရန်", callback_data="register")
    ], [InlineKeyboardButton("💰 လက်ကျန်ငွေ", callback_data="balance")],
                [InlineKeyboardButton("💳 ငွေဖြည့်ရန်", callback_data="topup")],
                [InlineKeyboardButton("🛒 ကုဒ်ဝယ်ရန်", callback_data="buy")],
                [InlineKeyboardButton("ℹ️ အကူအညီ", callback_data="help")]]
    if update.message:
        await update.message.reply_text(
            f"👋 မင်္ဂလာပါ {user.first_name}! ကြိုဆိုပါတယ်!",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(
            f"👋 မင်္ဂလာပါ {user.first_name}! ကြိုဆိုပါတယ်!",
            reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "start":
        await start(update, context)
        return

    if data == "register":
        if uid in db["users"] and db["users"][uid].get("approved", False):
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "✅ အကောင့်ဖွင့်ပြီးပါပြီ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return
        elif uid in db["pending_registrations"]:
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "⏳ အကောင့်ဖွင့်တောင်းဆိုမှု စောင့်ဆိုင်းနေပါသည်။ Admin မှ လက်ခံပေးရန် စောင့်ပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Create registration request
        db["pending_registrations"][uid] = {
            "user_id": uid,
            "username": query.from_user.first_name,
            "status": "pending"
        }
        save_db(db)

        # Send to admin
        keyboard = [[
            InlineKeyboardButton("✅ လက်ခံရန်",
                                 callback_data=f"approve_reg_{uid}"),
            InlineKeyboardButton("❌ ငြင်းပယ်ရန်",
                                 callback_data=f"reject_reg_{uid}")
        ]]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 အကောင့်ဖွင့်တောင်းဆိုမှု:\n"
            f"👤 အသုံးပြုသူ ID: {uid}\n"
            f"📝 အမည်: {query.from_user.first_name}\n"
            f"👤 Username: @{query.from_user.username or 'မရှိ'}",
            reply_markup=InlineKeyboardMarkup(keyboard))

        keyboard = [[
            InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
        ]]
        await query.edit_message_text(
            "📝 အကောင့်ဖွင့်တောင်းဆိုမှု Admin ထံပို့ပြီးပါပြီ။ စောင့်ဆိုင်းပါ။",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "balance":
        if not is_user_approved(uid):
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "⚠️ အကောင့်မှ Admin လက်ခံခြင်းမရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        user = get_user(uid)
        keyboard = []
        # Check if user has enough for any available product
        can_buy = False
        for game_type in db["prices"]:
            for amount, price in db["prices"][game_type].items():
                if amount in db["stock"].get(
                        game_type, {}) and db["stock"][game_type][amount]:
                    if user['balance'] >= price:
                        can_buy = True
                        break

        if not can_buy:
            keyboard.append(
                [InlineKeyboardButton("💳 ငွေဖြည့်ရန်", callback_data="topup")])
        keyboard.append(
            [InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")])
        await query.edit_message_text(
            f"💰 လက်ကျန်ငွေ: {user['balance']} MMK",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "topup":
        if not is_user_approved(uid):
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "⚠️ အကောင့်မှ Admin လက်ခံခြင်းမရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        keyboard = [
            [InlineKeyboardButton("📱 Wave", callback_data="topup_wave")],
            [InlineKeyboardButton("📱 Kpay", callback_data="topup_kpay")],
            [InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")]
        ]
        await query.edit_message_text(
            "💳 ငွေဖြည့်မည့်နည်းလမ်းရွေးပါ:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("topup_"):
        payment_method = data.split("_")[1].title()
        payment_info = db["payment"][payment_method]

        context.user_data['topup_method'] = payment_method
        keyboard = [[
            InlineKeyboardButton(f"📋 {payment_info['phone']}",
                                 callback_data=f"copy_{payment_info['phone']}")
        ], [InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="topup")]]

        await query.edit_message_text(
            f"💳 {payment_method} ငွေဖြည့်ရန်:\n\n"
            f"📱 ဖုန်းနံပါတ်: {payment_info['phone']}\n"
            f"👤 အမည်: {payment_info['name']}\n\n"
            f"📋 ဖုန်းနံပါတ်ကူးယူရန် အောက်က ခလုတ်နှိပ်ပါ:\n\n"
            f"💰 လွှဲပြီးရင် ပြေစာပုံအရင်ပို့ပါ။ ပြီးရင်:\n"
            f"• ပြေစာ ID (နောက်ဆုံး ၅လုံး သို့မဟုတ် ၆လုံး)\n"
            f"• လွှဲတဲ့ငွေပမာဏ\n"
            f"ရေးပြီးပို့ပါ။\n\n"
            f"⚠️ သတိပေးချက်: ပြေစာ ID နှင့် ပမာဏမှားရေးမိရင် ငွေဆုံးပါမည်\n\n"
            f"⏰ ငွေလွှဲပြီး ၅မိနစ်အတွင်းပို့ပါ\n"
            f"ℹ️ KPay ငွေလွှဲသူကို မိမိအကောင့်ရဲ့ KPay အမည်ထည့်ရေးပေးပါ",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("copy_"):
        phone_number = data.split("_", 1)[1]
        # Send the phone number as a separate message for easier copying
        await context.bot.send_message(chat_id=query.from_user.id,
                                       text=phone_number)
        await query.answer(
            f"📋 {phone_number} ပို့ပြီးပါပြီ! အပေါ်က ဂဏန်းကို ကူးယူပါ!",
            show_alert=True)

    elif data == "help":
        keyboard = [[
            InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
        ]]
        await query.edit_message_text(
            "ℹ️ အသုံးပြုနည်း:\n\n"
            "1️⃣ အကောင့်ဖွင့်ပါ\n"
            "2️⃣ လက်ကျန်ငွေကြည့်ပါ\n"
            "3️⃣ ငွေဖြည့်ပါ\n"
            "4️⃣ ကုဒ်ဝယ်ယူပါ\n\n"
            "📌 လေ့လာရန်:\n"
            "• Admin မှ လက်ခံပြီးမှ ကုဒ်ရရှိပါမည်\n"
            "• ဝယ်ယူမှုမှတ်တမ်းသိမ်းဆည်းပါမည်\n"
            "• ပြေစာနဲ့ဝယ်ရင် Admin လက်ခံပြီးမှ ကုဒ်ရရှိမည်\n"
            "• လက်ကျန်ငွေနဲ့ဝယ်ရင် ချက်ချင်းရရှိမည်",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "buy":
        if not is_user_approved(uid):
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "⚠️ အကောင့်မှ Admin လက်ခံခြင်းမရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Show available game types
        keyboard = []
        available_games = []

        for game_type in ["MLBBbal", "MLBBph", "PUPG"]:
            amounts = get_available_amounts(game_type)
            if amounts:
                total_codes = sum(
                    len(codes)
                    for codes in db["stock"].get(game_type, {}).values())
                if total_codes > 0:
                    game_name = get_game_display_name(game_type)
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🎮 {game_name} ({total_codes})",
                            callback_data=f"select_{game_type}")
                    ])
                    available_games.append(game_type)

        if not available_games:
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
            ]]
            await query.edit_message_text(
                "⚠️ လောလောဆယ် ကုဒ်မရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        keyboard.append(
            [InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")])
        await query.edit_message_text(
            "🎮 ဂိမ်းအမျိုးအစားရွေးပါ:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("select_"):
        game_type = data.split("_")[1]
        amounts = get_available_amounts(game_type)

        if not amounts:
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="buy")
            ]]
            await query.edit_message_text(
                "⚠️ ဒီဂိမ်းအတွက် ကုဒ်မရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        keyboard = []
        game_name = get_game_display_name(game_type)

        for amount in amounts:
            codes_count = len(db["stock"][game_type][amount])
            price = db["prices"][game_type].get(amount, 0)
            unit = "Coin" if "MLBB" in game_type else "UC"
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 {amount} {unit} - {price} MMK ({codes_count})",
                    callback_data=f"amount_{game_type}_{amount}")
            ])

        keyboard.append(
            [InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="buy")])
        await query.edit_message_text(
            f"🎮 {game_name}\n💎 အရေအတွက်ရွေးပါ:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("amount_"):
        parts = data.split("_")
        game_type = parts[1]
        amount = parts[2]

        if amount not in db["stock"].get(
                game_type, {}) or not db["stock"][game_type][amount]:
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်",
                                     callback_data=f"select_{game_type}")
            ]]
            await query.edit_message_text(
                "⚠️ ဒီပမာဏအတွက် ကုဒ်မရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        price = db["prices"][game_type].get(amount, 0)
        user = get_user(uid)
        max_quantity = len(db["stock"][game_type][amount])

        # Store selection data for text input
        context.user_data['selecting_quantity'] = {
            'game_type': game_type,
            'amount': amount,
            'price': price,
            'max_quantity': max_quantity
        }

        keyboard = [[
            InlineKeyboardButton("🔙 ပြန်သွားရန်",
                                 callback_data=f"select_{game_type}")
        ]]

        game_name = get_game_display_name(game_type)
        unit = "Coin" if "MLBB" in game_type else "UC"
        await query.edit_message_text(
            f"🎮 {game_name}\n"
            f"💎 {amount} {unit}\n"
            f"💰 စျေးနှုန်း: {price} MMK/ကုဒ်\n"
            f"💳 လက်ကျန်ငွေ: {user['balance']} MMK\n"
            f"📦 ရရှိနိုင်သော ကုဒ်: {max_quantity} ခု\n\n"
            f"📝 လိုချင်သော ကုဒ်အရေအတွက် ရေးပို့ပါ (1 to {max_quantity}):",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("quantity_"):
        parts = data.split("_")
        game_type = parts[1]
        amount = parts[2]
        quantity = int(parts[3])

        price = db["prices"][game_type].get(amount, 0)
        total_price = price * quantity
        user = get_user(uid)

        keyboard = []
        if user["balance"] >= total_price:
            keyboard.append([
                InlineKeyboardButton(
                    f"💰 လက်ကျန်ငွေနဲ့ဝယ်ရန် ({total_price} MMK)",
                    callback_data=f"buy_balance_{game_type}_{amount}_{quantity}"
                )
            ])
        else:
            keyboard.append(
                [InlineKeyboardButton("💳 ငွေဖြည့်ရန်", callback_data="topup")])

        keyboard.append([
            InlineKeyboardButton(
                "📄 ပြေစာနဲ့ဝယ်ရန်",
                callback_data=f"buy_receipt_{game_type}_{amount}_{quantity}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 ပြန်သွားရန်",
                                 callback_data=f"amount_{game_type}_{amount}")
        ])

        game_name = get_game_display_name(game_type)
        unit = "Coin" if "MLBB" in game_type else "UC"
        await query.edit_message_text(
            f"🎮 {game_name}\n"
            f"💎 {amount} {unit} x {quantity}\n"
            f"💰 စုစုပေါင်း: {total_price} MMK\n"
            f"💳 လက်ကျန်ငွေ: {user['balance']} MMK\n\n"
            f"💳 ငွေပေးချေမှုနည်းလမ်းရွေးပါ:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_balance_"):
        parts = data.split("_")
        game_type = parts[2]
        amount = parts[3]
        quantity = int(parts[4])

        user = get_user(uid)
        price = db["prices"][game_type].get(amount, 0)
        total_price = price * quantity

        if user["balance"] < total_price:
            keyboard = [[
                InlineKeyboardButton("💳 ငွေဖြည့်ရန်", callback_data="topup")
            ],
                        [
                            InlineKeyboardButton(
                                "🔙 ပြန်သွားရန်",
                                callback_data=
                                f"quantity_{game_type}_{amount}_{quantity}")
                        ]]
            await query.edit_message_text(
                "⚠️ လက်ကျန်ငွေမလုံလောက်ပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if len(db["stock"][game_type][amount]) < quantity:
            keyboard = [[
                InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="buy")
            ]]
            await query.edit_message_text(
                "⚠️ လုံလောက်သော ကုဒ်မရှိပါ။",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Get codes
        codes = []
        for _ in range(quantity):
            if db["stock"][game_type][amount]:
                codes.append(db["stock"][game_type][amount].pop(0))

        user["balance"] -= total_price
        db["sales_total"] += total_price
        game_name = get_game_display_name(game_type)
        unit = "Coin" if "MLBB" in game_type else "UC"

        user["history"].append({
            "type": "balance",
            "codes": codes,
            "game": game_name,
            "amount": amount,
            "quantity": quantity,
            "total_price": total_price
        })
        save_db(db)

        codes_text = "\n".join([f"🔑 {code}" for code in codes])
        keyboard = [[
            InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
        ]]
        await query.edit_message_text(
            f"✅ ဝယ်ယူမှုအောင်မြင်ပါပြီ!\n\n"
            f"🎮 {game_name}\n"
            f"💎 {amount} {unit} x {quantity}\n"
            f"💰 စုစုပေါင်း: {total_price} MMK\n\n"
            f"🔑 ကုဒ်များ:\n{codes_text}\n\n"
            f"💳 လက်ကျန်ငွေ: {user['balance']} MMK",
            reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("buy_receipt_"):
        parts = data.split("_")
        game_type = parts[2]
        amount = parts[3]
        quantity = int(parts[4])

        context.user_data['buying_game'] = game_type
        context.user_data['buying_amount'] = amount
        context.user_data['buying_quantity'] = quantity
        context.user_data['receipt_step'] = 'photo'

        keyboard = [[
            InlineKeyboardButton(
                "🔙 ပြန်သွားရန်",
                callback_data=f"quantity_{game_type}_{amount}_{quantity}")
        ]]
        await query.edit_message_text(
            "📄 ပြေစာနဲ့ဝယ်ယူရန်:\n\n"
            "1️⃣ ပြေစာပုံအရင်ပို့ပါ\n"
            "2️⃣ ပြီးရင် ပြေစာ ID (နောက်ဆုံး ၅လုံး သို့မဟုတ် ၆လုံး) ရေးပို့ပါ\n\n"
            "⚠️ သတိပေးချက်: ပြေစာ ID မှားရေးမိရင် ငွေဆုံးပါမည်",
            reply_markup=InlineKeyboardMarkup(keyboard))

    # Admin approval handlers
    elif data.startswith("message_topup_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        receipt_id = data.split("_")[2]
        if receipt_id not in db["topup_requests"]:
            await query.edit_message_text("⚠️ ငွေဖြည့်တောင်းဆိုမှုမတွေ့ပါ။")
            return

        request = db["topup_requests"][receipt_id]
        user_id = request["user_id"]
        context.user_data['admin_messaging'] = {'user_id': user_id}
        await query.edit_message_text("💬 အသုံးပြုသူထံပို့လိုသောစာကို ရေးပါ:")

    elif data.startswith("message_") and not data.startswith("message_topup_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        receipt_id = data.split("_")[1]
        if receipt_id not in db["receipts"]:
            await query.edit_message_text("⚠️ ပြေစာမတွေ့ပါ။")
            return

        receipt = db["receipts"][receipt_id]
        user_id = receipt["user_id"]
        context.user_data['admin_messaging'] = {'user_id': user_id}
        await query.edit_message_text("💬 အသုံးပြုသူထံပို့လိုသောစာကို ရေးပါ:")

    elif data.startswith("approve_topup_") or data.startswith("reject_topup_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        action, _, receipt_id = data.split("_")
        if receipt_id not in db["topup_requests"]:
            await query.edit_message_text("⚠️ ငွေဖြည့်တောင်းဆိုမှုမတွေ့ပါ။")
            return

        request = db["topup_requests"][receipt_id]
        user_id = request["user_id"]
        amount = request["amount"]
        user = get_user(user_id)

        if action == "approve":
            user["balance"] += amount
            request["status"] = "approved"
            save_db(db)
            await context.bot.send_message(
                user_id,
                f"✅ ငွေဖြည့်မှု လက်ခံပြီးပါပြီ!\n💰 ငွေပမာဏ: {amount} MMK\n💳 လက်ကျန်ငွေ: {user['balance']} MMK"
            )
            await query.edit_message_text(
                f"✅ ငွေဖြည့်မှု {receipt_id} လက်ခံပြီး")
        else:
            request["status"] = "rejected"
            save_db(db)
            await context.bot.send_message(user_id,
                                           "❌ ငွေဖြည့်မှု ငြင်းပယ်ခံရပါသည်။")
            await query.edit_message_text(
                f"❌ ငွေဖြည့်မှု {receipt_id} ငြင်းပယ်ပြီး")

    elif data.startswith("approve_reg_") or data.startswith("reject_reg_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        action, _, user_id = data.split("_")
        user_id = int(user_id)

        if user_id not in db["pending_registrations"]:
            await query.edit_message_text("⚠️ အကောင့်ဖွင့်တောင်းဆိုမှုမတွေ့ပါ။"
                                          )
            return

        if action == "approve":
            # Create approved user account
            db["users"][user_id] = {
                "balance": 0,
                "history": [],
                "approved": True
            }
            del db["pending_registrations"][user_id]
            save_db(db)

            await context.bot.send_message(
                user_id,
                "✅ အကောင့်ဖွင့်မှု လက်ခံပြီးပါပြီ! ယခု bot ကို အသုံးပြုနိုင်ပါပြီ။"
            )
            await query.edit_message_text(
                f"✅ အသုံးပြုသူ {user_id} ၏ အကောင့်ဖွင့်မှု လက်ခံပြီး")
        else:
            del db["pending_registrations"][user_id]
            save_db(db)
            await context.bot.send_message(
                user_id, "❌ အကောင့်ဖွင့်မှု ငြင်းပယ်ခံရပါသည်။")
            await query.edit_message_text(
                f"❌ အသုံးပြုသူ {user_id} ၏ အကောင့်ဖွင့်မှု ငြင်းပယ်ပြီး")

    elif data.startswith("approve_") or data.startswith("reject_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        action, receipt_id = data.split("_")
        if receipt_id not in db["receipts"]:
            await query.edit_message_text("⚠️ ပြေစာမတွေ့ပါ။")
            return

        receipt = db["receipts"][receipt_id]
        user_id = receipt["user_id"]
        game_type = receipt["game_type"]
        amount = receipt["amount"]
        quantity = receipt["quantity"]
        user = get_user(user_id)

        if action == "approve":
            if len(db["stock"][game_type].get(amount, [])) < quantity:
                await query.edit_message_text("⚠️ လုံလောက်သော ကုဒ်မရှိပါ။")
                return

            codes = []
            for _ in range(quantity):
                if db["stock"][game_type][amount]:
                    codes.append(db["stock"][game_type][amount].pop(0))

            total_price = db["prices"][game_type].get(amount, 0) * quantity
            db["sales_total"] += total_price
            game_name = get_game_display_name(game_type)
            unit = "Coin" if "MLBB" in game_type else "UC"

            user["history"].append({
                "type": "receipt",
                "codes": codes,
                "receipt": receipt_id,
                "game": game_name,
                "amount": amount,
                "quantity": quantity
            })
            receipt["status"] = "approved"
            save_db(db)

            codes_text = "\n".join([f"🔑 {code}" for code in codes])
            await context.bot.send_message(
                user_id, f"✅ ပြေစာနဲ့ဝယ်ယူမှု လက်ခံပြီးပါပြီ!\n\n"
                f"🎮 {game_name}\n"
                f"💎 {amount} {unit} x {quantity}\n\n"
                f"🔑 ကုဒ်များ:\n{codes_text}")
            await query.edit_message_text(f"✅ ပြေစာ {receipt_id} လက်ခံပြီး")
        else:
            receipt["status"] = "rejected"
            save_db(db)
            await context.bot.send_message(
                user_id, "❌ ပြေစာနဲ့ဝယ်ယူမှု ငြင်းပယ်ခံရပါသည်။")
            await query.edit_message_text(f"❌ ပြေစာ {receipt_id} ငြင်းပယ်ပြီး")

    # Admin addstock interactive handlers
    elif data.startswith("addstock_"):
        if uid != ADMIN_ID:
            await query.edit_message_text(
                "⚠️ Admin သာလျှင် ဒီအရာကိုလုပ်နိုင်ပါသည်။")
            return

        game_type = data.split("_")[1]
        context.user_data['addstock_game'] = game_type

        keyboard = [[
            InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="start")
        ]]
        game_name = get_game_display_name(game_type)
        unit = "Coin" if "MLBB" in game_type else "UC"
        await query.edit_message_text(
            f"🎮 {game_name} အတွက် ကုဒ်ထည့်ရန်:\n\n"
            f"📝 ဖော်မတ်: <amount> <price> <code1> <code2> ...\n"
            f"ဥပမာ: 1000 2500 CODE123 CODE456\n\n"
            f"💡 {unit} ပမာဏ, စျေးနှုန်း, ပြီးရင် ကုဒ်များပို့ပါ:",
            reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------- Receipt/Image text handler ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    user = get_user(uid)

    # Handle photos
    if update.message.photo:
        # Handle topup photos
        if 'topup_method' in context.user_data:
            context.user_data['topup_photo_sent'] = True
            context.user_data[
                'topup_photo_message_id'] = update.message.message_id

            await update.message.reply_text(
                "📄 ပြေစာပုံရရှိပြီး။ အောက်ပါအချက်အလက်များပို့ပါ:\n\n"
                "📝 ဖော်မတ်: <ပြေစာ ID (နောက်ဆုံး ၅လုံး သို့မဟုတ် ၆လုံး)> <ငွေပမာဏ>\n"
                "ဥပမာ: 123456 50000\n\n"
                "⚠️ သတိပေးချက်: ပြေစာ ID နှင့် ပမာဏမှားရေးမိရင် ငွေဆုံးပါမည်")
            return

        # Handle receipt purchase photos
        elif 'buying_game' in context.user_data and context.user_data.get(
                'receipt_step') == 'photo':
            context.user_data['receipt_photo_sent'] = True
            context.user_data[
                'receipt_photo_message_id'] = update.message.message_id
            context.user_data['receipt_step'] = 'id'

            await update.message.reply_text(
                "📄 ပြေစာပုံရရှိပြီး။ ယခု ပြေစာ ID (နောက်ဆုံး ၅လုံး သို့မဟုတ် ၆လုံး) ရေးပို့ပါ:\n\n"
                "ဥပမာ: 123456\n\n"
                "⚠️ သတိပေးချက်: ပြေစာ ID မှားရေးမိရင် ငွေဆုံးပါမည်")
            return

    # Handle text messages
    if update.message.text:
        text = update.message.text.strip()

        # Handle admin message sending
        if uid == ADMIN_ID and 'admin_messaging' in context.user_data:
            target_user = context.user_data['admin_messaging']['user_id']
            await context.bot.send_message(target_user,
                                           f"📩 Admin မှ စာ:\n{text}")
            await update.message.reply_text(
                f"✅ အသုံးပြုသူ {target_user} ထံ စာပို့ပြီး")
            del context.user_data['admin_messaging']
            return

        # Handle quantity selection
        if 'selecting_quantity' in context.user_data:
            try:
                quantity = int(text)
                selection = context.user_data['selecting_quantity']

                if quantity < 1 or quantity > selection['max_quantity']:
                    await update.message.reply_text(
                        f"⚠️ ကုဒ်အရေအတွက်သည် 1 မှ {selection['max_quantity']} အတွင်းဖြစ်ရမည်။"
                    )
                    return

                game_type = selection['game_type']
                amount = selection['amount']
                price = selection['price']
                total_price = price * quantity
                user = get_user(uid)

                keyboard = []
                if user["balance"] >= total_price:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"💰 လက်ကျန်ငွေနဲ့ဝယ်ရန် ({total_price} MMK)",
                            callback_data=
                            f"buy_balance_{game_type}_{amount}_{quantity}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton("💳 ငွေဖြည့်ရန်",
                                             callback_data="topup")
                    ])

                keyboard.append([
                    InlineKeyboardButton(
                        "📄 ပြေစာနဲ့ဝယ်ရန်",
                        callback_data=
                        f"buy_receipt_{game_type}_{amount}_{quantity}")
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        "🔙 ပြန်သွားရန်",
                        callback_data=f"amount_{game_type}_{amount}")
                ])

                game_name = get_game_display_name(game_type)
                unit = "Coin" if "MLBB" in game_type else "UC"
                await update.message.reply_text(
                    f"🎮 {game_name}\n"
                    f"💎 {amount} {unit} x {quantity}\n"
                    f"💰 စုစုပေါင်း: {total_price} MMK\n"
                    f"💳 လက်ကျန်ငွေ: {user['balance']} MMK\n\n"
                    f"💳 ငွေပေးချေမှုနည်းလမ်းရွေးပါ:",
                    reply_markup=InlineKeyboardMarkup(keyboard))
                del context.user_data['selecting_quantity']
                return
            except ValueError:
                await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ ဂဏန်းသာရေးပါ။")
                return

        # Handle admin addstock
        if uid == ADMIN_ID and 'addstock_game' in context.user_data:
            try:
                parts = text.split()
                if len(parts) < 3:
                    await update.message.reply_text(
                        "⚠️ အနည်းဆုံး: <amount> <price> <code1>")
                    return

                game_type = context.user_data['addstock_game']
                amount = parts[0]
                price = int(parts[1])
                codes = parts[2:]

                # Update stock
                if game_type not in db["stock"]:
                    db["stock"][game_type] = {}
                if amount not in db["stock"][game_type]:
                    db["stock"][game_type][amount] = []
                db["stock"][game_type][amount].extend(codes)

                # Update price
                if game_type not in db["prices"]:
                    db["prices"][game_type] = {}
                db["prices"][game_type][amount] = price

                save_db(db)

                game_name = get_game_display_name(game_type)
                unit = "Coin" if "MLBB" in game_type else "UC"
                await update.message.reply_text(
                    f"✅ {game_name} {amount} {unit}\n"
                    f"💰 စျေးနှုန်း: {price} MMK\n"
                    f"📦 ကုဒ်: {len(codes)} ခု ထည့်ပြီး")
                del context.user_data['addstock_game']
                return
            except ValueError:
                await update.message.reply_text("⚠️ စျေးနှုန်းမှားယွင်းပါသည်။")
                return
            except:
                await update.message.reply_text("⚠️ ဖော်မတ်မှားယွင်းပါသည်။")
                return

        # Handle topup with receipt ID and amount
        if context.user_data.get('topup_photo_sent'):
            try:
                parts = text.split()
                if len(parts) != 2:
                    await update.message.reply_text(
                        "⚠️ ဖော်မတ်: <ပြေစာ ID> <ငွေပမာဏ>")
                    return

                receipt_id = parts[0]
                amount = int(parts[1])

                if not validate_receipt_id(receipt_id):
                    await update.message.reply_text(
                        "⚠️ ပြေစာ ID သည် ၅-၆လုံး ဂဏန်းဖြစ်ရမည်။")
                    return

                if amount < 1000:
                    await update.message.reply_text(
                        "⚠️ ငွေပမာဏမှားယွင်းပါသည်။ အနည်းဆုံး ၁၀၀၀ MMK ဖြစ်ရမည်။"
                    )
                    return

                payment_method = context.user_data['topup_method']
                photo_message_id = context.user_data['topup_photo_message_id']

                db["topup_requests"][receipt_id] = {
                    "user_id": uid,
                    "status": "pending",
                    "amount": amount,
                    "payment_method": payment_method
                }
                save_db(db)

                keyboard = [[
                    InlineKeyboardButton(
                        "✅ လက်ခံရန်",
                        callback_data=f"approve_topup_{receipt_id}"),
                    InlineKeyboardButton(
                        "💬 စာပို့ရန်",
                        callback_data=f"message_topup_{receipt_id}"),
                    InlineKeyboardButton(
                        "❌ ငြင်းပယ်ရန်",
                        callback_data=f"reject_topup_{receipt_id}")
                ]]

                await context.bot.forward_message(
                    chat_id=ADMIN_ID,
                    from_chat_id=update.message.chat.id,
                    message_id=photo_message_id)

                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📥 ငွေဖြည့်တောင်းဆိုမှု:\n"
                    f"👤 အသုံးပြုသူ: {uid}\n"
                    f"💳 နည်းလမ်း: {payment_method}\n"
                    f"📄 ပြေစာ ID: {receipt_id}\n"
                    f"💰 ငွေပမာဏ: {amount} MMK",
                    reply_markup=InlineKeyboardMarkup(keyboard))

                await update.message.reply_text("⏳ Admin မှ စစ်ဆေးနေပါသည်...")

                # Clear user data
                del context.user_data['topup_method']
                del context.user_data['topup_photo_sent']
                del context.user_data['topup_photo_message_id']
                return
            except ValueError:
                await update.message.reply_text("⚠️ ငွေပမာဏမှားယွင်းပါသည်။")
                return
            except:
                await update.message.reply_text("⚠️ ဖော်မတ်မှားယွင်းပါသည်။")
                return

        # Handle receipt purchase with receipt ID
        if 'buying_game' in context.user_data and context.user_data.get(
                'receipt_step') == 'id':
            if not validate_receipt_id(text):
                await update.message.reply_text(
                    "⚠️ ပြေစာ ID သည် ၅-၆လုံး ဂဏန်းဖြစ်ရမည်။")
                return

            game_type = context.user_data['buying_game']
            amount = context.user_data['buying_amount']
            quantity = context.user_data['buying_quantity']
            photo_message_id = context.user_data['receipt_photo_message_id']

            db["receipts"][text] = {
                "user_id": uid,
                "status": "pending",
                "game_type": game_type,
                "amount": amount,
                "quantity": quantity
            }
            save_db(db)

            game_name = get_game_display_name(game_type)
            unit = "Coin" if "MLBB" in game_type else "UC"
            keyboard = [[
                InlineKeyboardButton("✅ လက်ခံရန်",
                                     callback_data=f"approve_{text}"),
                InlineKeyboardButton("💬 စာပို့ရန်",
                                     callback_data=f"message_{text}"),
                InlineKeyboardButton("❌ ငြင်းပယ်ရန်",
                                     callback_data=f"reject_{text}")
            ]]

            await context.bot.forward_message(
                chat_id=ADMIN_ID,
                from_chat_id=update.message.chat.id,
                message_id=photo_message_id)

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📥 ကုဒ်ဝယ်ယူမှု:\n"
                f"👤 အသုံးပြုသူ: {uid}\n"
                f"🎮 ဂိမ်း: {game_name}\n"
                f"💎 {amount} {unit} x {quantity}\n"
                f"📄 ပြေစာ ID: {text}",
                reply_markup=InlineKeyboardMarkup(keyboard))
            await update.message.reply_text("⏳ Admin မှ စစ်ဆေးနေပါသည်...")

            # Clear user data
            del context.user_data['buying_game']
            del context.user_data['buying_amount']
            del context.user_data['buying_quantity']
            del context.user_data['receipt_photo_sent']
            del context.user_data['receipt_photo_message_id']
            del context.user_data['receipt_step']
            return


# ---------------- Admin Commands ----------------
async def setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        args = context.args
        uid = int(args[0])
        amount = int(args[1])
        user = get_user(uid)
        user["balance"] = amount
        save_db(db)
        await update.message.reply_text(
            f"✅ အသုံးပြုသူ {uid} ၏ လက်ကျန်ငွေကို {amount} MMK သတ်မှတ်ပြီး")
    except:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /setbalance <user_id> <amount>")


async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Interactive version
    keyboard = [[
        InlineKeyboardButton("🎮 Mobile Legends (Bal)",
                             callback_data="addstock_MLBBbal")
    ],
                [
                    InlineKeyboardButton("🎮 Mobile Legends (PH)",
                                         callback_data="addstock_MLBBph")
                ],
                [
                    InlineKeyboardButton("🎮 PUPG Mobile",
                                         callback_data="addstock_PUPG")
                ]]
    await update.message.reply_text(
        "🎮 ဂိမ်းအမျိုးအစားရွေးပါ:",
        reply_markup=InlineKeyboardMarkup(keyboard))


async def delstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /delstock <MLBBbal/MLBBph/PUPG> <amount> <code>")
        return

    try:
        game_type = context.args[0]
        amount = context.args[1]
        code_to_delete = context.args[2]

        if game_type not in ["MLBBbal", "MLBBph", "PUPG"]:
            await update.message.reply_text(
                "ဂိမ်းအမျိုးအစား: MLBBbal, MLBBph, သို့မဟုတ် PUPG")
            return

        if game_type not in db["stock"] or amount not in db["stock"][game_type]:
            await update.message.reply_text(
                "⚠️ ဒီဂိမ်းအမျိုးအစား သို့မဟုတ် ပမာဏမရှိပါ။")
            return

        if code_to_delete in db["stock"][game_type][amount]:
            db["stock"][game_type][amount].remove(code_to_delete)
            save_db(db)

            game_name = get_game_display_name(game_type)
            unit = "Coin" if "MLBB" in game_type else "UC"
            await update.message.reply_text(
                f"✅ {game_name} {amount} {unit} မှ ကုဒ် {code_to_delete} ဖျက်ပြီး"
            )
        else:
            await update.message.reply_text("⚠️ ဒီကုဒ်မတွေ့ပါ။")
    except:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /delstock <MLBBbal/MLBBph/PUPG> <amount> <code>")


async def setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /setprice <MLBBbal/MLBBph/PUPG> <amount> <price>")
        return

    try:
        game_type = context.args[0]
        amount = context.args[1]
        price = int(context.args[2])

        if game_type not in ["MLBBbal", "MLBBph", "PUPG"]:
            await update.message.reply_text(
                "ဂိမ်းအမျိုးအစား: MLBBbal, MLBBph, သို့မဟုတ် PUPG")
            return

        if game_type not in db["prices"]:
            db["prices"][game_type] = {}

        db["prices"][game_type][amount] = price
        save_db(db)

        game_name = get_game_display_name(game_type)
        unit = "Coin" if "MLBB" in game_type else "UC"
        await update.message.reply_text(
            f"✅ {game_name} {amount} {unit} ၏ စျေးနှုန်းကို {price} MMK အဖြစ်သတ်မှတ်ပြီး"
        )
    except:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /setprice <MLBBbal/MLBBph/PUPG> <amount> <price>")


async def setpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        method = context.args[0].title()
        phone = context.args[1]
        name = " ".join(context.args[2:])

        if method not in ["Wave", "Kpay"]:
            await update.message.reply_text(
                "ငွေပေးချေမှုနည်းလမ်း: Wave သို့မဟုတ် KPay")
            return

        db["payment"][method] = {"phone": phone, "name": name}
        save_db(db)
        await update.message.reply_text(
            f"✅ {method} ပေးချေမှုအချက်အလက် ပြောင်းလဲပြီး\n📱 ဖုန်း: {phone}\n👤 အမည်: {name}"
        )
    except:
        await update.message.reply_text(
            "အသုံးပြုနည်း: /setpayment <Wave/KPay> <phone> <name>")


async def viewhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        uid = int(context.args[0])
        user = get_user(uid)
        if not user["history"]:
            await update.message.reply_text(
                f"အသုံးပြုသူ {uid} ၏ မှတ်တမ်းမရှိပါ")
            return

        history_text = ""
        for i, h in enumerate(user["history"], 1):
            history_text += f"{i}. {h}\n"

        await update.message.reply_text(
            f"📜 အသုံးပြုသူ {uid} ၏ မှတ်တမ်း:\n{history_text}")
    except:
        await update.message.reply_text("အသုံးပြုနည်း: /viewhistory <user_id>")


async def admhelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Calculate stock counts
    mlbbbal_count = sum(
        len(codes) for codes in db["stock"].get("MLBBbal", {}).values())
    mlbbph_count = sum(
        len(codes) for codes in db["stock"].get("MLBBph", {}).values())
    pupg_count = sum(
        len(codes) for codes in db["stock"].get("PUPG", {}).values())

    # Calculate total orders
    total_orders = 0
    for user_data in db["users"].values():
        total_orders += len(user_data.get("history", []))

    # Calculate total user balance
    total_user_balance = sum(
        user_data.get("balance", 0) for user_data in db["users"].values())

    # Calculate pending counts (only pending status)
    pending_receipts = len(
        [r for r in db["receipts"].values() if r["status"] == "pending"])
    pending_topups = len(
        [r for r in db["topup_requests"].values() if r["status"] == "pending"])
    pending_registrations = len(db.get("pending_registrations", {}))

    help_text = f"""
🔧 Admin Commands:

/setbalance <user_id> <amount> - အသုံးပြုသူလက်ကျန်ငွေသတ်မှတ်ရန်
/addstock - ကုဒ်များထည့်ရန် (အပြန်အလှန်)
/delstock <MLBBbal/MLBBph/PUPG> <amount> <code> - ကုဒ်ဖျက်ရန်
/setprice <MLBBbal/MLBBph/PUPG> <amount> <price> - စျေးနှုန်းသတ်မှတ်ရန်
/setpayment <Wave/Kpay> <phone> <name> - ပေးချေမှုအချက်အလက်ပြောင်းရန်
/viewhistory <user_id> - အသုံးပြုသူမှတ်တမ်းကြည့်ရန်
/admhelp - ဒီအကူအညီစာရင်း

📊 လက်ရှိအခြေအနေ:
🎮 MLBB Bal ကုဒ်: {mlbbbal_count}
🎮 MLBB PH ကုဒ်: {mlbbph_count}
🎮 PUPG ကုဒ်: {pupg_count}
👥 အသုံးပြုသူ: {len(db["users"])}
📦 အော်ဒါစုစုပေါင်း: {total_orders}
💰 အသုံးပြုသူလက်ကျန်ငွေစုစုပေါင်း: {total_user_balance:,} MMK
💵 ရောင်းရငွေစုစုပေါင်း: {db.get('sales_total', 0):,} MMK
⏳ ငံ့ရေးပြေစာ: {pending_receipts}
⏳ ငံ့ရေးငွေဖြည့်: {pending_topups}
⏳ ငံ့ရေးအကောင့်ဖွင့်: {pending_registrations}

💡 ဥပမာများ:
/setprice MLBBbal 1000 2500
/setprice PUPG 60 1500
/delstock MLBBbal 1000 CODE123
/setpayment Kpay 09123456789 John Doe

🔧 အင်္ဂါရပ်များ:
• အကောင့်ဖွင့်မှု Admin လက်ခံမှုလိုအပ်သည်
• ကုဒ်အရေအတွက်ရွေးချယ်မှု စာပို့ခြင်းဖြင့်
• Admin ကို စာပို့နိုင်သည် (💬 ခလုတ်)
    """

    await update.message.reply_text(help_text)


# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbalance", setbalance))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("delstock", delstock))
    app.add_handler(CommandHandler("setprice", setprice))
    app.add_handler(CommandHandler("setpayment", setpayment))
    app.add_handler(CommandHandler("viewhistory", viewhistory))
    app.add_handler(CommandHandler("admhelp", admhelp))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
