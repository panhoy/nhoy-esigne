# -*- coding: utf-8 -*-
import logging
import asyncio
import io
import ssl
from datetime import datetime

# OCR Imports
import cv2
import numpy as np
import pytesseract as pty

# Telegram and Web Imports
import aiohttp
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.helpers import escape_markdown
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- CONFIGURATION ---
BOT_TOKEN = "7626608558:AAG2sSmF3awXpk8dbSKoEAb4QDpObyN-kNA"
BOT_2_TOKEN = "7775302991:AAGhN0WzRQ7FNu4z_TJkOTPU6peAPZuMlnU"
ADMIN_CHAT_ID = "1732455712"
BOT_2_ADMIN_CHAT_ID = "1732455712"

# --- OCR CONFIGURATION ---
pty.pytesseract.tesseract_cmd = r"C:\Users\panho\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# --- ASSET URLs ---
START_PHOTO_URL = "https://i.pinimg.com/736x/dd/cb/03/ddcb0341971d4836da7d12c399149675.jpg"
PROCESSING_GIF_URL = "https://i.pinimg.com/originals/fd/5b/d2/fd5bd28732e0345037d301274c8df692.gif"
THANK_YOU_PHOTO_URL = "https://i.pinimg.com/736x/6d/c5/88/6dc58847b0ac6d7bf1f8920286043558.jpg"
PAYMENT_REJECTED_GIF_URL = "https://i.pinimg.com/originals/a5/75/0b/a5750babcf0f417f30e0b4773b29e376.gif" # <-- ADDED THIS LINE
PAYMENT_PHOTOS = {
    "4": "https://i.pinimg.com/736x/37/62/f1/3762f112c8f2179a2663e997c1419619.jpg",
    "7": "https://i.pinimg.com/736x/14/70/c4/1470c436182cf4c4142bfa343b45c844.jpg",
    "12": "https://i.pinimg.com/736x/6a/3d/98/6a3d98a08550c0d823623279e458411a.jpg",
    "16": "https://i.pinimg.com/736x/b5/96/76/b5967687b83a2bc141c8735dc232ca5e.jpg"
}

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- IN-MEMORY USER DATA STORAGE ---
user_data = {}

# --- HELPER FUNCTIONS ---

async def extract_text_from_photo(photo_file) -> str:
    try:
        file_bytes = await photo_file.download_as_bytearray()
        np_array = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        if img is None: return "Error: Could not read image file."
        text = pty.image_to_string(img)
        return text.strip() if text else "No text found in image."
    except Exception as e:
        logger.error(f"Error during OCR processing: {e}")
        return f"Error during text extraction: {e}"

async def send_to_bot_2(order_data: dict) -> bool:
    url = f"https://api.telegram.org/bot{BOT_2_TOKEN}/sendMessage"
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    username = order_data.get('username', 'N/A')
    message = (
        f"🎉 NEW COMPLETED ORDER FROM BOT 1 🎉\n\n"
        f"👤 User: {username}\n"
        f"🆔 User ID: {order_data.get('user_id', 'N/A')}\n"
        f"Esign Amount: ${order_data.get('amount', 'N/A')} USD\n"
        f"📱 UDID: {order_data.get('udid', 'N/A')}\n"
        f"🆔 Payment ID: {order_data.get('payment_id', 'N/A')}\n"
        f"⏰ Order Time: {current_time}\n"
        f"📊 Status: ✅ PAYMENT CONFIRMED"
    )
    payload = {'chat_id': BOT_2_ADMIN_CHAT_ID, 'text': message}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=payload, timeout=15) as response:
                return response.status == 200
        except Exception:
            return False

async def _delete_message_after_delay(message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass # Ignore errors if message is already deleted

async def forward_photo_to_admin(context: ContextTypes.DEFAULT_TYPE, user_message, delete_after_seconds: int = 0):
    if ADMIN_CHAT_ID:
        try:
            forwarded_message = await context.bot.forward_message(
                chat_id=ADMIN_CHAT_ID,
                from_chat_id=user_message.chat_id,
                message_id=user_message.message_id
            )
            if delete_after_seconds > 0:
                asyncio.create_task(_delete_message_after_delay(forwarded_message, delete_after_seconds))
        except Exception as e:
            logger.error(f"Failed to forward photo to admin: {e}")

async def send_text_to_admin(context: ContextTypes.DEFAULT_TYPE, message: str, delete_after_seconds: int = 0):
    if ADMIN_CHAT_ID:
        try:
            sent_message = await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID, text=message, parse_mode='MarkdownV2'
            )
            if delete_after_seconds > 0:
                asyncio.create_task(_delete_message_after_delay(sent_message, delete_after_seconds))
        except Exception as e:
            logger.error(f"Failed to send text to admin: {e}")

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("📱 Download UDID Profile", url="https://udid.tech/download-profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    caption = (
        f"🎉 *Welcome, {user.first_name}\\!* 🎉\n\n"
        "1️⃣ First, download the UDID profile using the button below\\.\n"
        "2️⃣ Install it on your device\\.\n"
        "3️⃣ Copy your unique UDID and send it to me to begin\\."
    )
    await update.message.reply_photo(photo=START_PHOTO_URL, caption=caption, reply_markup=reply_markup, parse_mode='MarkdownV2')

async def handle_udid_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    udid = update.message.text.strip()
    if len(udid) < 20 or ' ' in udid:
        await update.message.reply_text(
            "❌ *Invalid UDID Format*\n\nPlease make sure you copied the entire UDID string\\. It should be a long string of letters and numbers with no spaces\\.\n\nUse /start to get the download link again if you need help\\.",
            parse_mode='MarkdownV2'
        )
        return
    user_data[user_id] = {'udid': udid}
    keyboard = [
        [InlineKeyboardButton("Esign $4", callback_data=f"payment_4_{udid}"), InlineKeyboardButton("Esign $7", callback_data=f"payment_7_{udid}")],
        [InlineKeyboardButton("Esign $12", callback_data=f"payment_12_{udid}"), InlineKeyboardButton("Esign $16", callback_data=f"payment_16_{udid}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ *UDID Received\\!*\n\n📱 *Your UDID:* `{udid}`\n\n"
        f"👇 *Please select your payment plan:*",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )

async def handle_payment_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    action, data = parts[0], parts[1:]
    user_id = query.from_user.id
    if action == 'payment':
        amount = data[0]
        udid = '_'.join(data[1:])
        user_data[user_id] = {'udid': udid, 'pending_amount': amount, 'payment_id': f"PAY-{amount}-{udid[:8]}"}
        payment_photo_url = PAYMENT_PHOTOS.get(amount, START_PHOTO_URL)
        caption = (
            f"💳 *Payment for ${amount} USD*\n\n"
            f"📱 *UDID:* `{udid}`\n"
            f"🆔 *Payment ID:* `{user_data[user_id]['payment_id']}`\n\n"
            f"1️⃣ Make the payment using the QR code in the image\\.\n"
            f"2️⃣ Take a screenshot of the payment confirmation\\.\n"
            f"3️⃣ Send the screenshot back to this chat\\."
        )
        await query.message.reply_photo(photo=payment_photo_url, caption=caption, parse_mode='MarkdownV2')
        await query.edit_message_text(text=f"Instructions sent for ${amount} payment\\. Please check the new message\\.", reply_markup=None)

# --- UPDATED FUNCTION ---
async def handle_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    message = update.message
    
    if user_id not in user_data or 'pending_amount' not in user_data[user_id]:
        await message.reply_text(
            "I wasn't expecting a photo from you\\. Please start the payment process first by sending your UDID\\. Use /start if you need help\\.",
            parse_mode='MarkdownV2'
        )
        return

    processing_message = await message.reply_animation(
        animation=PROCESSING_GIF_URL,
        caption="🔄 *Validating your payment\\.\\.\\. please wait\\.*",
        parse_mode='MarkdownV2'
    )
    photo_file = await message.photo[-1].get_file()
    extracted_text = await extract_text_from_photo(photo_file)
    required_name = "Roeurn Bora"

    if required_name.lower() in extracted_text.lower():
        # --- ORDER OF OPERATIONS ---
        
        # 1. PREPARE ALL DATA
        logger.info(f"Payment validated for user {user_id}. Preparing data.")
        user_info = user_data[user_id]
        username_raw = f"@{user.username}" if user.username else user.first_name
        
        order_data = {
            'username': username_raw,
            'user_id': user_id,
            'amount': user_info.get('pending_amount'),
            'udid': user_info.get('udid'),
            'payment_id': user_info.get('payment_id')
        }

        # 2. SEND DATA TO BOT 2 TO CHECK STATUS FOR USER MESSAGE
        success = await send_to_bot_2(order_data)
        
        # 3. FINISH INTERACTION WITH THE USER
        await processing_message.delete()
        bot_2_status = "✅ Sent for final processing\\." if success else "⚠️ Sent, awaiting confirmation\\."
        confirmation_caption = (
            f"🎉 *Thank You, {user.first_name}\\! Your Order is Confirmed\\!* 🎉\n\n"
            f"We have received and validated your payment proof for *${order_data['amount']}*\\.\n\n"
            f"*Status:* {bot_2_status}\n"
            f"You will receive a notification once the order is complete\\. This usually takes 5\\-10 minutes\\.\n\n"
            "You can start a new order with /start\\."
        )
        await message.reply_photo(photo=THANK_YOU_PHOTO_URL, caption=confirmation_caption, parse_mode='MarkdownV2')
        del user_data[user_id]['pending_amount']
    else:
        # --- THIS IS THE MODIFIED BLOCK ---
        logger.warning(f"Payment REJECTED for user {user_id}. Name '{required_name}' was NOT found.")
        await processing_message.delete()
        
        rejection_caption = (
            "⚠️ *Payment Not Confirmed*\n\n"
            "Sorry, I could not find the name `Roeurn Bora` in the payment screenshot\\. "
            "Please make sure you have sent the correct and complete payment confirmation and try again\\."
        )
        await message.reply_animation(
            animation=PAYMENT_REJECTED_GIF_URL,
            caption=rejection_caption,
            parse_mode='MarkdownV2'
        )
        return

async def handle_other_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.text:
        await handle_udid_input(update, context)
    else:
        await update.message.reply_text("I can only process text and photos. Please send your UDID or a payment screenshot.")

def main() -> None:
    print("🤖 Starting Telegram UDID Payment & OCR Bot...")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_payment_button))
    application.add_handler(MessageHandler(filters.PHOTO, handle_payment_screenshot))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other_messages))
    print("✅ Bot is now running!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()