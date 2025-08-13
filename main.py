import os
import tempfile
import shutil
import subprocess
import json
from flask import Flask, request, Response
import telebot
from telebot import types

# --------------------------
# التوكن ورابط الخدمة
# --------------------------
TOKEN = "8360006158:AAGBZ1pDVGBkVV0aHj-DtzHdywHseawTRVo"
WEBHOOK_URL = "https://tiktok-bot-1-t64c.onrender.com"
PORT = 10000

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# --------------------------
# الإحصائيات
# --------------------------
STATS_FILE = "stats.json"
if not os.path.exists(STATS_FILE):
    stats = {"users": {}, "total_downloads": 0}
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)
else:
    with open(STATS_FILE, "r") as f:
        stats = json.load(f)

def save_stats():
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

def add_user(chat_id):
    if str(chat_id) not in stats["users"]:
        stats["users"][str(chat_id)] = {"downloads": 0}
        save_stats()

def increment_download(chat_id):
    stats["total_downloads"] += 1
    if str(chat_id) in stats["users"]:
        stats["users"][str(chat_id)]["downloads"] += 1
    save_stats()

# --------------------------
# وظائف التحميل
# --------------------------
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

def download_media(url: str, output_dir: str, only_audio=False, quality=None):
    out_template = os.path.join(output_dir, "%(title).100s.%(ext)s")
    cmd = ["yt-dlp", "-o", out_template]
    if only_audio:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    if quality:
        cmd += ["-f", quality]
    cmd.append(url)
    # تشغيل التحميل
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {result.stderr}")
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir)]
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if not files:
        raise RuntimeError("ما تم تنزيل أي ملف.")
    return files[0]

# --------------------------
# وظائف البوت
# --------------------------
@app.route("/", methods=["GET"])
def health_check():
    return "البوت شغال 🟢", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return Response(status=200)

@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    add_user(chat_id)
    welcome_text = (
        "هلا والله! 🤠\n"
        "أنا بوت التحميل حق الفيديوهات من TikTok, YouTube, Instagram, Pinterest.\n"
        "أرسل لي رابط الفيديو وراح أعطيك خيارات التحميل.\n"
        "⚠️ البوت أحياناً يأخر شوي في إرسال المقطع (حوالي 10 ثواني) حسب حجم الفيديو.\n\n"
        "الأوامر المتوفرة:\n"
        "/start - عرض هالرسالة\n"
        "/stats - إحصائياتك وعدد التحميلات\n"
    )
    bot.send_message(chat_id, welcome_text)

@bot.message_handler(commands=["stats"])
def send_stats(message):
    chat_id = message.chat.id
    user_data = stats["users"].get(str(chat_id), {"downloads": 0})
    total = stats["total_downloads"]
    bot.send_message(chat_id, f"🧾 إحصائياتك:\nعدد تحميلاتك: {user_data['downloads']}\nإجمالي التحميلات: {total}")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_message(message):
    url = message.text.strip()
    chat_id = message.chat.id

    if not url.startswith("http://") and not url.startswith("https://"):
        bot.reply_to(message, "يبي رابط صحيح يبدأ بـ http:// أو https://")
        return

    platform = detect_platform(url)
    if platform == "unknown":
        bot.reply_to(message, "هالموقع غير مدعوم حالياً.")
        return

    add_user(chat_id)

    if platform in ["tiktok", "youtube"]:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎬 تحميل الفيديو", callback_data=f"download_video|{url}"),
            types.InlineKeyboardButton("🔊 تحميل الصوت", callback_data=f"download_audio|{url}")
        )
        bot.send_message(chat_id, "اختار التحميل:", reply_markup=markup)
    else:
        msg = bot.send_message(chat_id, "جاري تحميل الفيديو، انتظر شوي...")
        try:
            tmp_dir = tempfile.mkdtemp()
            file_path = download_media(url, tmp_dir, only_audio=False)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                bot.edit_message_text(
                    "الملف كبير جدًا للإرسال عبر البوت (>50 ميجابايت). جرب رابط ثاني أو جودة أقل.",
                    chat_id, msg.message_id
                )
            else:
                bot.send_chat_action(chat_id, "upload_video")
                with open(file_path, "rb") as f:
                    bot.send_video(chat_id, f)
                bot.edit_message_text("تم إرسال الفيديو ✅", chat_id, msg.message_id)
                increment_download(chat_id)
        except Exception as e:
            bot.edit_message_text(f"صارت مشكلة أثناء التحميل: {str(e)}", chat_id, msg.message_id)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        action, url = call.data.split("|", 1)
    except Exception:
        bot.answer_callback_query(call.id, "صارت مشكلة في البيانات.")
        return

    chat_id = call.message.chat.id
    msg = bot.send_message(chat_id, "جاري التحميل، انتظر شوي...")
    try:
        tmp_dir = tempfile.mkdtemp()
        if action == "download_audio":
            file_path = download_media(url, tmp_dir, only_audio=True)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                bot.edit_message_text("ملف الصوت كبير جداً للإرسال.", chat_id, msg.message_id)
            else:
                bot.send_chat_action(chat_id, "upload_audio")
                with open(file_path, "rb") as f:
                    bot.send_audio(chat_id, f)
                bot.edit_message_text("تم إرسال الصوت ✅", chat_id, msg.message_id)
                increment_download(chat_id)
        elif action == "download_video":
            file_path = download_media(url, tmp_dir, only_audio=False)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                bot.edit_message_text(
                    "الملف كبير جداً للإرسال. جرب رابط ثاني أو جودة أقل.",
                    chat_id, msg.message_id
                )
            else:
                bot.send_chat_action(chat_id, "upload_video")
                with open(file_path, "rb") as f:
                    bot.send_video(chat_id, f)
                bot.edit_message_text("تم إرسال الفيديو ✅", chat_id, msg.message_id)
                increment_download(chat_id)
        else:
            bot.edit_message_text("نوع التحميل غير معروف.", chat_id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"فشل التحميل: {str(e)}", chat_id, msg.message_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# --------------------------
# تعيين Webhook
# --------------------------
def set_webhook():
    url = f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
    res = bot.set_webhook(url)
    print(f"نتيجة تعيين webhook: {res}")

# --------------------------
# تشغيل البوت
# --------------------------
if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)