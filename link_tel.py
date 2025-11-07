from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import jdatetime, random, string, time, asyncio

# =========================
# توکن ربات تلگرام
# =========================
TOKEN = "8058467026:AAG29hMthzO7q39Vowgv-0yBDX-SbhB8t1M"

# =========================
# دیتابیس‌های داخلی ربات
# =========================
FILE_DB = {}      # نگهداری اطلاعات فایل‌ها
# ساختار: code → (file_id, expire, ftype, chat_id, message_id, [sent_msgs])
USER_ACCESS = {}  # محدود کردن دریافت تکراری فایل
# ساختار: code → {user_id: last_click_time}
SENT_FILES = {}   # جلوگیری از ارسال فایل تکراری برای هر کاربر
# ساختار: user_id → لیست کد فایل‌های فعال
LAST_SEND = {}    # زمان آخرین ارسال فایل (آنتی اسپم)
# ساختار: user_id → timestamp آخرین ارسال
ANTI_SPAM_TIME = 120  # مدت زمان محدودیت اسپم (ثانیه)

# =========================
# توابع کمکی
# =========================
def format_remaining(seconds: float) -> str:
    """
    تبدیل زمان باقی‌مانده به رشته قابل فهم
    مثال: 1 ساعت و 2 دقیقه و 3 ثانیه باقی مونده
    """
    seconds = int(seconds)
    if seconds <= 0: return "منقضی شده!"
    parts = []
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s: parts.append(f"{s} ثانیه")
    if len(parts) == 1: return parts[0] + " باقی مونده"
    if len(parts) == 2: return f"{parts[0]} و {parts[1]} باقی مونده"
    return f"{parts[0]} و {parts[1]} و {parts[2]} باقی مونده"

def to_shamsi(t):
    """تبدیل timestamp به تاریخ و زمان شمسی"""
    return jdatetime.datetime.fromtimestamp(t).strftime("%Y/%m/%d - %H:%M:%S")

def generate_code():
    """تولید کد تصادفی ۲۰ کاراکتری برای لینک فایل"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=20))

# =========================
# پاکسازی خودکار فایل‌های منقضی شده
# =========================
async def auto_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """
    این تابع هر ۱۰ ثانیه اجرا می‌شود
    و فایل‌های منقضی شده را پاک کرده و پیام‌های مربوطه را حذف می‌کند.
    """
    while True:
        await asyncio.sleep(10)
        now = time.time()
        expired = [c for c, (_, e, *_) in FILE_DB.items() if now > e]
        for code in expired:
            file_id, _, _, chat_id, msg_id, sent = FILE_DB.pop(code, (None,)*6)

            # حذف پیام اصلی فایل
            try: await context.bot.delete_message(chat_id, msg_id)
            except: pass

            # حذف پیام‌های اطلاعاتی ارسال شده به کاربر
            for ch, mid in sent:
                try: await context.bot.delete_message(ch, mid)
                except: pass

            # ارسال پیام هشدار به کاربر درباره انقضا فایل
            try:
                await context.bot.send_message(chat_id, "فایل شما منقضی شد. لطفاً دوباره ارسال کنید.")
            except: pass

            USER_ACCESS.pop(code, None)  # پاک کردن دسترسی کاربران برای این کد

            # پاک کردن کد فایل از SENT_FILES
            for u, files in SENT_FILES.items():
                if code in files: files.remove(code)

            # پاک کردن زمان آخرین ارسال اگر کاربر دیگر فایلی ندارد
            for u in list(LAST_SEND.keys()):
                if u in SENT_FILES and not SENT_FILES[u]:
                    LAST_SEND.pop(u, None)

# =========================
# مدیریت کلیک روی دکمه دریافت فایل
# =========================
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    وقتی کاربر روی دکمه دریافت فایل کلیک می‌کند، این تابع اجرا می‌شود
    - بررسی می‌کند لینک معتبر است یا منقضی شده
    - محدودیت دریافت تکراری هر 6 ساعت
    - ارسال فایل به کاربر
    - ارسال اطلاعات انقضا فایل
    """
    q = update.callback_query
    await q.answer()
    code = q.data
    user = q.from_user.id

    if code not in FILE_DB:
        return await q.edit_message_text("لینک منقضی یا اشتباه!")

    file_id, expire, ftype, chat_id, msg_id, sent = FILE_DB[code]

    # بررسی انقضای لینک
    if time.time() > expire:
        return await q.edit_message_text("لینک منقضی شد!")

    # جلوگیری از دریافت چندباره فایل توسط یک کاربر در ۶ ساعت
    USER_ACCESS.setdefault(code, {})
    if user in USER_ACCESS[code] and time.time() - USER_ACCESS[code][user] < 6*3600:
        warn = await context.bot.send_message(q.message.chat_id,
            "امکان دریافت فایل تکراری بیش از یکبار در هر 6 ساعت وجود ندارد.")
        sent.append((warn.chat_id, warn.message_id))
        FILE_DB[code] = (file_id, expire, ftype, chat_id, msg_id, sent)
        return

    USER_ACCESS[code][user] = time.time()
    remaining = format_remaining(expire - time.time())

    # ارسال فایل بر اساس نوع آن
    try:
        func = {"photo": context.bot.send_photo,
                "video": context.bot.send_video,
                "audio": context.bot.send_audio}.get(ftype, context.bot.send_document)
        msg = await func(q.message.chat_id, file_id)
    except:
        return await q.edit_message_text("خطا در ارسال فایل!")

    # ارسال پیام اطلاعات انقضا
    info = await msg.reply_text(f"تاریخ انقضا:\n`{to_shamsi(expire)}`\n{remaining}", parse_mode="Markdown")
    sent += [(msg.chat_id, msg.message_id), (info.chat_id, info.message_id)]
    FILE_DB[code] = (file_id, expire, ftype, chat_id, msg_id, sent)

# =========================
# دستور /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دستور /start
    اگر کاربر لینک فایل را با start فرستاده باشد، لینک آماده و دکمه نمایش داده می‌شود
    در غیر این صورت، پیام راهنما ارسال می‌شود
    """
    args = context.args
    if not args or not args[0].startswith("file_"):
        return await update.message.reply_text(
            "LinkBolt Pro\n\nفایل بفرست → لینک ۶۰ ثانیه‌ای با دکمه شیشه‌ای\n"
            "همه می‌تونن بگیرن\nبعد ۱ دقیقه می‌سوزه!\n\nبفرست و کپی کن!",
            parse_mode="Markdown", disable_web_page_preview=True
        )

    code = args[0][5:]
    if code not in FILE_DB or time.time() > FILE_DB[code][1]:
        return await update.message.reply_text("لینک منقضی شد!")

    expire = FILE_DB[code][1]
    keyboard = [[InlineKeyboardButton("دریافت فایل", callback_data=code)]]

    await update.message.reply_text(
        f"لینک آماده است!\n\nتاریخ انقضا:\n`{to_shamsi(expire)}`\n"
        f"{format_remaining(expire - time.time())} باقی مونده\n\nدکمه زیر رو بزن!",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================
# مدیریت فایل‌های ارسالی توسط کاربر
# =========================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    وقتی کاربر فایلی ارسال می‌کند، این تابع اجرا می‌شود
    - بررسی آنتی اسپم (ارسال فایل جدید قبل از 120 ثانیه محدود است)
    - جلوگیری از ارسال فایل تکراری
    - ساخت لینک ۶۰ ثانیه‌ای
    - ارسال پیام حاوی لینک و اطلاعات فایل
    """
    msg = await update.message.reply_text("در حال ساخت...")
    file_id = ftype = name = None

    # شناسایی نوع فایل و دریافت file_id و نام فایل
    if update.message.photo:
        file_id = update.message.photo[-1].file_id; ftype, name = "photo", "عکس.jpg"
    elif update.message.video:
        file_id = update.message.video.file_id; ftype, name = "video", update.message.video.file_name or "ویدیو.mp4"
    elif update.message.document:
        file_id = update.message.document.file_id; ftype, name = "document", update.message.document.file_name or "فایل"
    elif update.message.audio:
        file_id = update.message.audio.file_id; ftype, name = "audio", update.message.audio.file_name or "آهنگ.mp3"
    else:
        return await msg.edit_text("فقط عکس، ویدیو، فایل یا آهنگ!")

    user = update.message.from_user.id
    now = time.time()

    # بررسی آنتی اسپم
    if user in LAST_SEND and now - LAST_SEND[user] < ANTI_SPAM_TIME:
        remaining = ANTI_SPAM_TIME - (now - LAST_SEND[user])
        m = int(remaining) // 60
        s = int(remaining) % 60
        countdown = f"{m} دقیقه و {s} ثانیه" if m else f"{s} ثانیه"
        return await msg.edit_text(f"از اسپم کردن خودداری کنید!\nزمان باقی‌مانده تا ارسال بعدی: {countdown}")

    # بررسی فایل تکراری
    active_files = SENT_FILES.get(user, [])
    for code, info in FILE_DB.items():
        if info[0] == file_id and code in active_files:
            return await msg.edit_text("فایل تکراری است.")

    # تولید کد و لینک فایل
    code = generate_code()
    expire = now + 60
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=file_{code}"
    keyboard = [[InlineKeyboardButton("دریافت فایل", callback_data=code)]]

    # ارسال پیام نهایی به کاربر
    await msg.edit_text(
        f"لینک ۶۰ ثانیه‌ای آماده شد!\n\n**نام:** `{name}`\n**انقضا:** `{to_shamsi(expire)}`\n"
        f"{format_remaining(expire - now)} باقی مونده\n\n`{link}`\n\nکپی کن و بفرست!",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True
    )

    # ثبت اطلاعات فایل در دیتابیس
    FILE_DB[code] = (file_id, expire, ftype, msg.chat_id, msg.message_id, [])
    SENT_FILES.setdefault(user, []).append(code)
    LAST_SEND[user] = now  # ثبت زمان آخرین ارسال برای آنتی اسپم

# =========================
# راه‌اندازی خودکار هنگام اجرای ربات
# =========================
async def post_init(app):
    asyncio.create_task(auto_cleanup(app))

# =========================
# اجرای ربات
# =========================
def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO, handle_file))
    app.add_handler(CallbackQueryHandler(button_click))
    print("LinkBolt Pro روشن شد! | زمان هوشمند فعال | ضد اسپم فعال")
    app.run_polling()

if __name__ == '__main__':
    main()