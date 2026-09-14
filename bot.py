"""
Kino/Video yuboruvchi Telegram bot
-----------------------------------
Ishlash tartibi:
1. Foydalanuvchi botga kino kodini yuboradi (yoki t.me/bot?start=KOD havolasi orqali kiradi)
2. Bot kerakli kanallarga a'zo ekanligini tekshiradi
3. A'zo bo'lmasa -> kanallarga qo'shilish tugmalari + "Tekshirish" tugmasi chiqadi
4. A'zo bo'lgach -> so'ralgan video/kino yuboriladi

O'rnatish:
    pip install python-telegram-bot==21.6

Ishga tushirish:
    python bot.py
"""

import json
import logging
import os

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============ SOZLAMALAR (o'zingizga moslab o'zgartiring) ============

BOT_TOKEN = "8970479229:AAHJWbJ11ucUzXQ0IUApVkr679qvQK_PYr8"          # @BotFather dan olinadi
ADMIN_IDS = [7498238850]                        # Sizning Telegram user ID(lar)ingiz

# Majburiy obuna talab qilinadigan kanallar.
# username bo'lsa "@" bilan, yopiq kanal bo'lsa -100... ko'rinishidagi chat_id bilan yoziladi.
REQUIRED_CHANNELS = [
    {"chat_id": -1004339266904, "title": "Kanalimiz", "url": "https://t.me/+1sYOltdCYZwyNzAy"},
]

MOVIES_DB_FILE = "movies.json"
USERS_DB_FILE = "users.json"
JOIN_REQUESTS_FILE = "join_requests.json"  # {chat_id: [user_id, user_id, ...]}

# ============ Kino bazasi (kod -> file_id) ============

def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


MOVIES = load_json(MOVIES_DB_FILE, {})
USERS = load_json(USERS_DB_FILE, [])  # foydalanuvchi ID'lari ro'yxati
JOIN_REQUESTS = load_json(JOIN_REQUESTS_FILE, {})  # {"kanal_id": [user_id, ...]}


def save_movies():
    save_json(MOVIES_DB_FILE, MOVIES)


def register_user(user_id: int):
    """Yangi foydalanuvchini ro'yxatga oladi (statistika uchun)."""
    if user_id not in USERS:
        USERS.append(user_id)
        save_json(USERS_DB_FILE, USERS)


def register_join_request(chat_id: int, user_id: int):
    """Kimdir yopiq kanalga qo'shilish so'rovi yuborganda shuni eslab qoladi."""
    key = str(chat_id)
    JOIN_REQUESTS.setdefault(key, [])
    if user_id not in JOIN_REQUESTS[key]:
        JOIN_REQUESTS[key].append(user_id)
        save_json(JOIN_REQUESTS_FILE, JOIN_REQUESTS)


def has_pending_join_request(chat_id, user_id: int) -> bool:
    return user_id in JOIN_REQUESTS.get(str(chat_id), [])

# ============ Yordamchi funksiyalar ============

async def get_unsubscribed_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """Foydalanuvchi a'zo bo'lmagan (va so'rov ham yubormagan) kanallar ro'yxatini qaytaradi."""
    not_joined = []
    for ch in REQUIRED_CHANNELS:
        # 1) Avval haqiqiy a'zolikni tekshiramiz
        try:
            member = await context.bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if member.status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ):
                continue  # a'zo ekan, bu kanal bo'yicha muammo yo'q
        except Exception as e:
            logger.warning("Kanalni tekshirishda xato (%s): %s", ch["chat_id"], e)

        # 2) A'zo bo'lmasa, "qo'shilish so'rovi yuborilganmi" tekshiramiz
        if has_pending_join_request(ch["chat_id"], user_id):
            continue  # so'rov yuborilgan, shuning o'zi yetarli

        not_joined.append(ch)
    return not_joined


def build_subscribe_keyboard(not_joined: list, pending_code: str | None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(f"➕ {ch['title']}", url=ch["url"])] for ch in not_joined]
    check_data = f"check:{pending_code}" if pending_code else "check:"
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data=check_data)])
    return InlineKeyboardMarkup(buttons)


async def send_movie(update_or_query, context: ContextTypes.DEFAULT_TYPE, code: str, chat_id: int):
    entry = MOVIES.get(code)
    if not entry:
        await context.bot.send_message(chat_id=chat_id, text="❌ Bunday kod bo'yicha kino topilmadi.")
        return

    file_id = entry["file_id"] if isinstance(entry, dict) else entry
    file_type = entry.get("type", "video") if isinstance(entry, dict) else "video"

    if file_type == "document":
        await context.bot.send_document(chat_id=chat_id, document=file_id, caption=f"🎬 Kod: {code}")
    elif file_type == "video_note":
        await context.bot.send_video_note(chat_id=chat_id, video_note=file_id)
    elif file_type == "photo":
        await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=f"🎬 Kod: {code}")
    else:
        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=f"🎬 Kod: {code}")


# ============ Handlerlar ============

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    args = context.args  # /start KOD orqali kelsa shu yerda bo'ladi
    code = args[0] if args else None

    not_joined = await get_unsubscribed_channels(user_id, context)

    if not_joined:
        text = "SIZ BARCHASIGA A'ZO BO'LMADINGIZ! (Insofing bormi🤨 meni ham tirikchiligimni o'yla ahir)"
        await update.message.reply_text(
            text, reply_markup=build_subscribe_keyboard(not_joined, code)
        )
        return

    if code:
        await send_movie(update, context, code, update.effective_chat.id)
    else:
        await update.message.reply_text(
            "Salom! Kino kodini yuboring, men sizga videoni jo'nataman 🎬"
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi to'g'ridan-to'g'ri kod yozib yuborsa."""
    user_id = update.effective_user.id
    register_user(user_id)
    code = update.message.text.strip()

    not_joined = await get_unsubscribed_channels(user_id, context)
    if not_joined:
        await update.message.reply_text(
            "SIZ BARCHASIGA A'ZO BO'LMADINGIZ! (Insofing bormi🤨 meni ham tirikchiligimni o'yla ahir)",
            reply_markup=build_subscribe_keyboard(not_joined, code),
        )
        return

    await send_movie(update, context, code, update.effective_chat.id)


async def check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'✅ Tekshirish' tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    code = query.data.split("check:", 1)[1] or None

    not_joined = await get_unsubscribed_channels(user_id, context)
    if not_joined:
        await query.answer("SIZ BARCHASIGA A'ZO BO'LMADINGIZ! (Insofing bormi🤨 meni ham tirikchiligimni o'yla ahir)", show_alert=True)
        return

    await query.edit_message_text("✅ Obuna tasdiqlandi!")
    if code:
        await send_movie(update, context, code, update.effective_chat.id)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Endi menga kino kodini yuborishingiz mumkin.",
        )


# ============ Admin uchun: kino qo'shish ============

async def save_movie(message, code: str, admin_message):
    """Video/fayl/rasmni kod bilan saqlaydigan umumiy funksiya."""
    video = message.video or message.document or message.video_note or (
        message.photo[-1] if message.photo else None
    )

    if not video:
        await admin_message.reply_text("❌ Fayl topilmadi. Faylni caption bilan birga yuboring.")
        return

    if message.video:
        file_type = "video"
    elif message.document:
        file_type = "document"
    elif message.video_note:
        file_type = "video_note"
    else:
        file_type = "photo"

    MOVIES[code] = {"file_id": video.file_id, "type": file_type}
    save_movies()
    await admin_message.reply_text(f"✅ Kino saqlandi. Kod: {code}")


async def addmovie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ishlatilishi (1-usul): avval videoni yuboring, keyin unga JAVOB qilib
    (reply) alohida matn xabari sifatida /addmovie KOD deb yozing.
    """
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Foydalanish: video yuboring, unga reply qilib /addmovie KOD yozing")
        return

    code = context.args[0]
    target_message = update.message.reply_to_message or update.message
    await save_movie(target_message, code, update.message)


async def media_with_caption_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ishlatilishi (2-usul): videoni yuborayotganda captioniga to'g'ridan-to'g'ri
    /addmovie KOD deb yozib, birga yuborish.
    """
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    caption = update.message.caption or ""
    if not caption.startswith("/addmovie"):
        return

    parts = caption.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Kod ko'rsatilmadi. Masalan: /addmovie kino1")
        return

    code = parts[1]
    await save_movie(update.message, code, update.message)


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun: /stats — bot statistikasi."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    text = (
        "📊 Bot statistikasi\n\n"
        f"👥 Foydalanuvchilar soni: {len(USERS)}\n"
        f"🎬 Kinolar soni: {len(MOVIES)}\n"
    )
    if MOVIES:
        text += "\nKodlar ro'yxati:\n" + "\n".join(f"• {code}" for code in MOVIES.keys())

    await update.message.reply_text(text)


async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kimdir majburiy kanalga qo'shilish so'rovi yuborganda ishga tushadi."""
    request = update.chat_join_request
    register_join_request(request.chat.id, request.from_user.id)
    logger.info("Yangi qo'shilish so'rovi: kanal=%s, user=%s", request.chat.id, request.from_user.id)


# ============ Botni ishga tushirish ============

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("addmovie", addmovie_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CallbackQueryHandler(check_callback, pattern=r"^check:"))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.ALL | filters.PHOTO | filters.VIDEO_NOTE,
            media_with_caption_handler,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
