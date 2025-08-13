import os
import tempfile
import shutil
from flask import Flask, request, Response
import telebot
from telebot import types
import subprocess

# هنا حطيت توكن بوتك
TOKEN = "توكن_البوت_حقك"

# رابط خدمتك في Render
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # مثال: "https://yourservice.onrender.com"

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return Response(status=200)

def download_media(url: str, output_dir: str, only_audio=False, quality=None):
    out_template = os.path.join(output_dir, "%(title).100s.%(ext)s")
    cmd = ["yt-dlp", "-o", out_template]
    if only_audio:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    if quality:
        cmd += ["-f", quality]
    cmd.append(url)
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {result.stderr}")
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir)]
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    if not files:
        raise RuntimeError("No files downloaded.")
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

# رسالة /start
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        "هلا والله 👋!\n"
        "هذا البوت لتحميل الفيديوهات من TikTok, Instagram, Pinterest, YouTube.\n"
        "تقدر تختار تحميل الفيديو أو الصوت فقط.\n"
        "ملاحظة: ممكن يكون فيه تأخير 10 ثواني قبل إرسال المقطع."
    )

# استقبال أي رابط
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_message(message):
    url = message.text.strip()
    chat_id = message.chat.id

    if not url.startswith("http"):
        bot.reply_to(message, "أرسل رابط صحيح يبدأ بـ http:// أو https://")
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
        bot.send_message(chat_id, "اختر نوع التحميل:", reply_markup=markup)
    else:
        msg = bot.send_message(chat_id, "جاري تحميل الفيديو، انتظر لحظة...")
        try:
            tmp_dir = tempfile.mkdtemp()
            file_path = download_media(url, tmp_dir)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                bot.edit_message_text(
                    "الملف كبير جدًا لإرساله عبر البوت (>50 ميجابايت).",
                    chat_id,
                    msg.message_id
                )
            else:
                bot.send_chat_action(chat_id, "upload_video")
                with open(file_path, "rb") as f:
                    bot.send_video(chat_id, f)
                bot.edit_message_text("تم إرسال الفيديو ✅", chat_id, msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"حدث خطأ أثناء التحميل: {str(e)}", chat_id, msg.message_id)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

# التعامل مع الضغط على الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        action, url = call.data.split("|", 1)
    except Exception:
        bot.answer_callback_query(call.id, "حدث خطأ في البيانات.")
        return

    chat_id = call.message.chat.id
    msg = bot.send_message(chat_id, "جاري التحميل، انتظر شوي...")
    try:
        tmp_dir = tempfile.mkdtemp()
        if action == "download_audio":
            file_path = download_media(url, tmp_dir, only_audio=True)
            bot.send_chat_action(chat_id, "upload_audio")
            with open(file_path, "rb") as f:
                bot.send_audio(chat_id, f)
            bot.edit_message_text("تم إرسال الصوت ✅", chat_id, msg.message_id)
        elif action == "download_video":
            file_path = download_media(url, tmp_dir, only_audio=False)
            bot.send_chat_action(chat_id, "upload_video")
            with open(file_path, "rb") as f:
                bot.send_video(chat_id, f)
            bot.edit_message_text("تم إرسال الفيديو ✅", chat_id, msg.message_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# تعيين webhook
def set_webhook():
    if not WEBHOOK_URL:
        print("WEBHOOK_URL غير مضبوط، تخطي تعيين webhook")
        return
    url = f"{WEBHOOK_URL.rstrip('/')}/{TOKEN}"
    res = bot.set_webhook(url)
    print(f"نتيجة تعيين webhook: {res}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)