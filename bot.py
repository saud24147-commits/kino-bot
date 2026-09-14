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


def save_movies():
    save_json(MOVIES_DB_FILE, MOVIES)


def register_user(user_id: int):
    """Yangi foydalanuvchini ro'yxatga oladi (statistika uchun)."""
    if user_id not in USERS:
        USERS.append(user_id)
        save_json(USERS_DB_FILE, USERS)

# ============ Yordamchi funksiyalar ============

async def get_unsubscribed_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """Foydalanuvchi a'zo bo'lmagan kanallar ro'yxatini qaytaradi."""
    not_joined = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch["chat_id"], user_id=user_id)
            if member.status not in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ):
                not_joined.append(ch)
        except Exception as e:
            # Bot kanalda admin bo'lmasa yoki kanal noto'g'ri bo'lsa shu yerga tushadi
            logger.warning("Kanalni tekshirishda xato (%s): %s", ch["chat_id"], e)
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
        text = "🔒 Kinoni olishdan oldin quyidagi kanallarga a'zo bo'ling:"
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
            "🔒 Kinoni olishdan oldin quyidagi kanallarga a'zo bo'ling:",
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
        await query.answer("❗ Siz hali barcha kanallarga a'zo bo'lmadingiz.", show_alert=True)
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

async def addmovie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ishlatilishi: video/kinoni botga yuboring va caption qismiga
    /addmovie KOD deb yozing (masalan: /addmovie kino1)
    """
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Foydalanish: video yuboring, captionga /addmovie KOD yozing")
        return

    code = context.args[0]
    msg = update.message.reply_to_message or update.message
    video = msg.video or msg.document or msg.video_note or (msg.photo[-1] if msg.photo else None)

    if not video:
        await update.message.reply_text("❌ Fayl topilmadi. Faylni caption bilan birga yuboring.")
        return

    if msg.video:
        file_type = "video"
    elif msg.document:
        file_type = "document"
    elif msg.video_note:
        file_type = "video_note"
    else:
        file_type = "photo"

    MOVIES[code] = {"file_id": video.file_id, "type": file_type}
    save_movies()
    await update.message.reply_text(f"✅ Kino saqlandi. Kod: {code}")


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


# ============ Botni ishga tushirish ============

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("addmovie", addmovie_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CallbackQueryHandler(check_callback, pattern=r"^check:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
