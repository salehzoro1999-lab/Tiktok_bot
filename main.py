import os
import tempfile
import shutil
from flask import Flask, request, Response
import telebot
from telebot import types
import yt_dlp

# التوكن ورابط الخدمة
TOKEN = "8360006158:AAGBZ1pDVGBkVV0aHj-DtzHdywHseawTRVo"
WEBHOOK_URL = "https://tiktok-bot-sna5.onrender.com"

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

users_progress = {}  # تقدم التحميل لكل مستخدم
user_stats = {}      # إحصائيات المستخدمين

@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return Response(status=200)

def progress_hook(d, chat_id):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0.0%')
        msg_id = users_progress.get(chat_id)
        try:
            if msg_id:
                bot.edit_message_text(f"جاري التحميل... {percent}", chat_id, msg_id)
        except:
            pass
    elif d['status'] == 'finished':
        users_progress.pop(chat_id, None)
        # تحديث الإحصائيات
        if chat_id in user_stats:
            user_stats[chat_id]['downloads'] += 1

def download_media(url: str, output_dir: str, chat_id: int, only_audio=False, quality=None):
    out_template = os.path.join(output_dir, "%(title).100s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_template,
        "progress_hooks": [lambda d: progress_hook(d, chat_id)],
        "format": quality if quality else "best",
        "noplaylist": True,
    }
    if only_audio:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0"
            }],
        })

    # تحميل الفيديو/الصوت/الصور
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # حفظ الصور إذا موجودة
        if 'thumbnail' in info:
            thumbnail_url = info['thumbnail']
            thumb_path = os.path.join(output_dir, "thumbnail.jpg")
            ydl.download([thumbnail_url])
    
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir)]
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if not files:
        raise RuntimeError("ما نزل أي ملف.")
    return files[0]

def detect_platform(url: str):
    url = url.lower()
    if "tiktok.com" in url or "vt.tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url or "instagr.am" in url:
        return "instagram"
    elif "pinterest." in url:
        return "pinterest"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    else:
        return "unknown"

@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    # إضافة المستخدم للإحصائيات إذا جديد
    if chat_id not in user_stats:
        user_stats[chat_id] = {"downloads": 0}
    text = (
        "هلا! 🙌\n"
        "أرسل لي رابط فيديو من TikTok, YouTube, Instagram, أو Pinterest.\n"
        "تقدر تختار تحميل الفيديو 🎬 أو الصوت 🔊 فقط.\n"
        "تقدر تختار جودة الفيديو قبل التحميل.\n"
        "ملاحظة: ممكن يكون في تأخير بسيط في إرسال الفيديو (حوالي 10 ثواني).\n"
        "استخدم /stats لمشاهدة الإحصائيات."
    )
    bot.send_message(chat_id, text)

@bot.message_handler(commands=["stats"])
def send_stats(message):
    chat_id = message.chat.id
    total_users = len(user_stats)
    downloads = user_stats.get(chat_id, {}).get('downloads', 0)
    bot.send_message(chat_id, f"عدد المستخدمين: {total_users}\nعدد التحميلات لك: {downloads}")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_message(message):
    url = message.text.strip()
    chat_id = message.chat.id

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "أرسل رابط صحيح يبغالها http:// أو https://")
        return

    platform = detect_platform(url)
    if platform == "unknown":
        bot.reply_to(message, "آسف، هذا الموقع غير مدعوم حالياً.")
        return

    if platform in ["tiktok", "youtube"]:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎬 تحميل الفيديو", callback_data=f"download_video|{url}"),
            types.InlineKeyboardButton("🔊 تحميل الصوت فقط", callback_data=f"download_audio|{url}")
        )
        bot.send_message(chat_id, "اختار نوع التحميل:", reply_markup=markup)
    else:
        msg = bot.send_message(chat_id, "جاري تحميل الفيديو، انتظر شوي...")
        users_progress[chat_id] = msg.message_id
        try:
            tmp_dir = tempfile.mkdtemp()
            file_path = download_media(url, tmp_dir, chat_id)
            bot.send_chat_action(chat_id, "upload_video")
            with open(file_path, "rb") as f:
                bot.send_video(chat_id, f)
            bot.edit_message_text("تم إرسال الفيديو ✅", chat_id, msg.message_id)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    action, url = call.data.split("|", 1)
    chat_id = call.message.chat.id
    msg = bot.send_message(chat_id, "جاري التحميل، انتظر شوي...")
    users_progress[chat_id] = msg.message_id
    try:
        tmp_dir = tempfile.mkdtemp()
        # عرض جودة الفيديو قبل التحميل
        quality_markup = types.InlineKeyboardMarkup(row_width=2)
        quality_markup.add(
            types.InlineKeyboardButton("أفضل جودة", callback_data=f"{action}|best|{url}"),
            types.InlineKeyboardButton("جودة 720p", callback_data=f"{action}|[height<=720]|{url}"),
            types.InlineKeyboardButton("جودة 480p", callback_data=f"{action}|[height<=480]|{url}")
        )
        if "|" not in call.data or len(call.data.split("|")) == 2:
            bot.send_message(chat_id, "اختار جودة الفيديو:", reply_markup=quality_markup)
            return

        # إذا تم اختيار الجودة
        parts = call.data.split("|")
        if len(parts) == 3:
            action, quality, url = parts
            only_audio = action == "download_audio"
            file_path = download_media(url, tmp_dir, chat_id, only_audio=only_audio, quality=quality)
            if only_audio:
                bot.send_chat_action(chat_id, "upload_audio")
                with open(file_path, "rb") as f:
                    bot.send_audio(chat_id, f)
            else:
                bot.send_chat_action(chat_id, "upload_video")
                with open(file_path, "rb") as f:
                    bot.send_video(chat_id, f)
            bot.edit_message_text("تم الإرسال ✅", chat_id, msg.message_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        users_progress.pop(chat_id, None)

def set_webhook():
    url = f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
    res = bot.set_webhook(url)
    print(f"نتيجة تعيين webhook: {res}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)