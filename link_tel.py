import telebot
from telebot import types
import jdatetime, random, string, time, asyncio

# =========================
# توکن ربات تلگرام
# =========================
TOKEN = "8367127956:AAHAR6zf2m4_hNJOw4cesM_3ExsNacvWxUU"

# =========================
# دیتابیس‌های داخلی ربات
# =========================
FILE_DB = {}      # نگهداری اطلاعات فایل‌ها
USER_ACCESS = {}  # محدود کردن دریافت تکراری فایل
SENT_FILES = {}   # جلوگیری از ارسال فایل تکراری برای هر کاربر
LAST_SEND = {}    # زمان آخرین ارسال فایل (آنتی اسپم)
ANTI_SPAM_TIME = 120  # مدت زمان محدودیت اسپم (ثانیه)

# =========================
# توابع کمکی
# =========================
def format_remaining(seconds: float) -> str:
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
    return jdatetime.datetime.fromtimestamp(t).strftime("%Y/%m/%d - %H:%M:%S")

def generate_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=20))

# =========================
# پاکسازی خودکار فایل‌های منقضی شده
# =========================
def auto_cleanup():
    while True:
        time.sleep(10)
        now = time.time()
        expired = [c for c, (_, e, *_) in FILE_DB.items() if now > e]
        for code in expired:
            file_id, _, _, chat_id, msg_id, sent = FILE_DB.pop(code, (None,)*6)

            # حذف پیام اصلی فایل
            try: bot.delete_message(chat_id, msg_id)
            except: pass

            # حذف پیام‌های اطلاعاتی ارسال شده به کاربر
            for ch, mid in sent:
                try: bot.delete_message(ch, mid)
                except: pass

            # ارسال پیام هشدار به کاربر درباره انقضا فایل
            try:
                bot.send_message(chat_id, "فایل شما منقضی شد. لطفاً دوباره ارسال کنید.")
            except: pass

            USER_ACCESS.pop(code, None)

            # پاک کردن کد فایل از SENT_FILES
            for u, files in SENT_FILES.items():
                if code in files: files.remove(code)

            # پاک کردن زمان آخرین ارسال اگر کاربر دیگر فایلی ندارد
            for u in list(LAST_SEND.keys()):
                if u in SENT_FILES and not SENT_FILES[u]:
                    LAST_SEND.pop(u, None)

# =========================
# ایجاد نمونه ربات
# =========================
bot = telebot.TeleBot(TOKEN)

# =========================
# مدیریت کلیک روی دکمه دریافت فایل
# =========================
@bot.callback_query_handler(func=lambda call: True)
def button_click(call):
    code = call.data
    user = call.from_user.id

    if code not in FILE_DB:
        return bot.answer_callback_query(call.id, "لینک منقضی یا اشتباه!", show_alert=True)

    file_id, expire, ftype, chat_id, msg_id, sent = FILE_DB[code]

    # بررسی انقضای لینک
    if time.time() > expire:
        return bot.answer_callback_query(call.id, "لینک منقضی شد!", show_alert=True)

    # جلوگیری از دریافت چندباره فایل توسط یک کاربر در ۶ ساعت
    USER_ACCESS.setdefault(code, {})
    if user in USER_ACCESS[code] and time.time() - USER_ACCESS[code][user] < 6*3600:
        warn = bot.send_message(call.message.chat.id,
            "امکان دریافت فایل تکراری بیش از یکبار در هر 6 ساعت وجود ندارد.")
        sent.append((warn.chat.id, warn.message_id))
        FILE_DB[code] = (file_id, expire, ftype, chat_id, msg_id, sent)
        return bot.answer_callback_query(call.id, "امکان دریافت تکراری نیست!", show_alert=True)

    USER_ACCESS[code][user] = time.time()
    remaining = format_remaining(expire - time.time())

    # ارسال فایل بر اساس نوع آن
    try:
        if ftype == "photo":
            msg = bot.send_photo(call.message.chat.id, file_id)
        elif ftype == "video":
            msg = bot.send_video(call.message.chat.id, file_id)
        elif ftype == "audio":
            msg = bot.send_audio(call.message.chat.id, file_id)
        else:
            msg = bot.send_document(call.message.chat.id, file_id)
    except:
        return bot.answer_callback_query(call.id, "خطا در ارسال فایل!", show_alert=True)

    # ارسال پیام اطلاعات انقضا
    info = bot.reply_to(msg, f"تاریخ انقضا:\n`{to_shamsi(expire)}`\n{remaining}", parse_mode="Markdown")
    sent += [(msg.chat.id, msg.message_id), (info.chat.id, info.message_id)]
    FILE_DB[code] = (file_id, expire, ftype, chat_id, msg_id, sent)
    bot.answer_callback_query(call.id, "فایل ارسال شد!")

# =========================
# دستور /start
# =========================
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith("file_"):
        return bot.reply_to(message,
            "LinkBolt Pro\n\nفایل بفرست → لینک ۶۰ ثانیه‌ای با دکمه شیشه‌ای\n"
            "همه می‌تونن بگیرن\nبعد ۱ دقیقه می‌سوزه!\n\nبفرست و کپی کن!",
            parse_mode="Markdown", disable_web_page_preview=True
        )

    code = args[1][5:]
    if code not in FILE_DB or time.time() > FILE_DB[code][1]:
        return bot.reply_to(message, "لینک منقضی شد!")

    expire = FILE_DB[code][1]
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("دریافت فایل", callback_data=code))

    bot.reply_to(message,
        f"لینک آماده است!\n\nتاریخ انقضا:\n`{to_shamsi(expire)}`\n"
        f"{format_remaining(expire - time.time())} باقی مونده\n\nدکمه زیر رو بزن!",
        parse_mode="Markdown", reply_markup=keyboard
    )

# =========================
# مدیریت فایل‌های ارسالی توسط کاربر
# =========================
@bot.message_handler(content_types=['photo', 'video', 'document', 'audio'])
def handle_file(message):
    msg = bot.reply_to(message, "در حال ساخت...")
    file_id = ftype = name = None

    # شناسایی نوع فایل و دریافت file_id و نام فایل
    if message.photo:
        file_id = message.photo[-1].file_id
        ftype, name = "photo", "عکس.jpg"
    elif message.video:
        file_id = message.video.file_id
        ftype, name = "video", message.video.file_name or "ویدیو.mp4"
    elif message.document:
        file_id = message.document.file_id
        ftype, name = "document", message.document.file_name or "فایل"
    elif message.audio:
        file_id = message.audio.file_id
        ftype, name = "audio", message.audio.file_name or "آهنگ.mp3"
    else:
        return bot.edit_message_text("فقط عکس، ویدیو، فایل یا آهنگ!", msg.chat.id, msg.message_id)

    user = message.from_user.id
    now = time.time()

    # بررسی آنتی اسپم
    if user in LAST_SEND and now - LAST_SEND[user] < ANTI_SPAM_TIME:
        remaining = ANTI_SPAM_TIME - (now - LAST_SEND[user])
        m = int(remaining) // 60
        s = int(remaining) % 60
        countdown = f"{m} دقیقه و {s} ثانیه" if m else f"{s} ثانیه"
        return bot.edit_message_text(f"از اسپم کردن خودداری کنید!\nزمان باقی‌مانده تا ارسال بعدی: {countdown}", 
                                   msg.chat.id, msg.message_id)

    # بررسی فایل تکراری
    active_files = SENT_FILES.get(user, [])
    for code, info in FILE_DB.items():
        if info[0] == file_id and code in active_files:
            return bot.edit_message_text("فایل تکراری است.", msg.chat.id, msg.message_id)

    # تولید کد و لینک فایل
    code = generate_code()
    expire = now + 60
    link = f"https://t.me/{bot.get_me().username}?start=file_{code}"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("دریافت فایل", callback_data=code))

    # ارسال پیام نهایی به کاربر
    bot.edit_message_text(
        f"لینک ۶۰ ثانیه‌ای آماده شد!\n\n**نام:** `{name}`\n**انقضا:** `{to_shamsi(expire)}`\n"
        f"{format_remaining(expire - now)} باقی مونده\n\n`{link}`\n\nکپی کن و بفرست!",
        msg.chat.id, msg.message_id,
        parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True
    )

    # ثبت اطلاعات فایل در دیتابیس
    FILE_DB[code] = (file_id, expire, ftype, msg.chat.id, msg.message_id, [])
    SENT_FILES.setdefault(user, []).append(code)
    LAST_SEND[user] = now

# =========================
# اجرای ربات
# =========================
if __name__ == '__main__':
    print("LinkBolt Pro روشن شد! | زمان هوشمند فعال | ضد اسپم فعال")
    
    # اجرای پاکسازی در یک thread جداگانه
    import threading
    cleanup_thread = threading.Thread(target=auto_cleanup, daemon=True)
    cleanup_thread.start()
    
    bot.infinity_polling()