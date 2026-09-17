import os
import re
import time
import json
import threading
import requests
from html import unescape
from dotenv import load_dotenv
import telebot

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN not found in .env")
    print("Create .env file with: BOT_TOKEN=your_token")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============== ADMIN & SUBSCRIPTION ==============
# Yahan apna Telegram User ID daalo (number)
# ID kaise pata karein: @userinfobot ko message bhejo
ADMIN_ID = 7145835109  # <-- YAHAN APNA TELEGRAM ID DAALO

SUBSCRIBERS_FILE = "subscribers.json"

# chat_id -> {"username": str, "last_status": str, "active": bool}
monitors = {}
lock = threading.Lock()


def load_subscribers() -> set:
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, "r") as f:
                data = json.load(f)
                return set(data)
    except Exception:
        pass
    return set()


def save_subscribers(subs: set):
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subs), f)
    except Exception as e:
        print(f"Failed to save subscribers: {e}")


subscribers = load_subscribers()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_allowed(user_id: int) -> bool:
    return is_admin(user_id) or user_id in subscribers


def not_allowed_message(message):
    bot.reply_to(
        message,
        "❌ <b>Access Denied</b>\n\n"
        "You don't have an active subscription.\n"
        "Contact admin to get access.",
        parse_mode="HTML"
    )


# ============== INSTAGRAM CHECK ==============

def decode_html_entities(text: str) -> str:
    """Exact same as server.js decodeHTMLEntities"""
    if not text:
        return ""
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return unescape(text)


def check_instagram(username: str) -> dict:
    """Exact logic from server.js /api/check"""
    if not username:
        return {"exists": False, "status": "BANNED"}

    username = username.strip().lower().replace("@", "")

    # Method 1
    try:
        headers = {
            "x-ig-app-id": "936619743392459",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Referer": "https://www.instagram.com/"
        }

        response = requests.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers=headers,
            timeout=12
        )

        if response.status_code == 200:
            data = response.json()
            user = data.get("data", {}).get("user")
            if user:
                return {
                    "exists": True,
                    "status": "ACTIVE",
                    "user": {
                        "full_name": user.get("full_name") or username,
                        "username": user.get("username"),
                        "biography": user.get("biography") or "",
                        "followers": user.get("edge_followed_by", {}).get("count", 0),
                        "following": user.get("edge_follow", {}).get("count", 0),
                        "posts": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
                        "profile_pic": user.get("profile_pic_url_hd") or user.get("profile_pic_url") or ""
                    }
                }
    except Exception:
        pass

    # Method 2 - Public page
    try:
        page_res = requests.get(
            f"https://www.instagram.com/{username}/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=12
        )

        html = page_res.text

        if "og:title" in html or f'"username":"{username}"' in html:
            full_name = username
            biography = ""
            profile_pic = ""
            followers = following = posts = "—"

            title_match = re.search(r'property="og:title" content="([^"]+)"', html, re.I)
            if title_match:
                full_name = decode_html_entities(title_match.group(1).split("(")[0].strip())

            desc_match = re.search(r'property="og:description" content="([^"]+)"', html, re.I)
            if desc_match:
                raw = decode_html_entities(desc_match.group(1))
                raw = raw.split(" - See Instagram")[0].strip()
                biography = raw

                nums = re.search(
                    r"([\d,.]+[KMB]?)\s+Followers.*?([\d,.]+[KMB]?)\s+Following.*?([\d,.]+[KMB]?)\s+Posts",
                    raw, re.I
                )
                if nums:
                    followers = nums.group(1)
                    following = nums.group(2)
                    posts = nums.group(3)

            pic_match = re.search(r'property="og:image" content="([^"]+)"', html, re.I)
            if pic_match:
                profile_pic = pic_match.group(1)

            return {
                "exists": True,
                "status": "ACTIVE",
                "user": {
                    "full_name": full_name,
                    "username": username,
                    "biography": biography,
                    "followers": followers,
                    "following": following,
                    "posts": posts,
                    "profile_pic": profile_pic
                }
            }
    except Exception:
        pass

    return {"exists": False, "status": "BANNED"}


def format_profile(data: dict) -> str:
    if not data.get("exists") or not data.get("user"):
        return "❌ Account not found or <b>BANNED</b>"

    u = data["user"]
    return (
        f"✅ <b>ACTIVE</b>\n\n"
        f"👤 <b>{u.get('full_name', '')}</b>\n"
        f"🔗 @{u.get('username', '')}\n"
        f"📝 {u.get('biography') or 'No bio'}\n\n"
        f"👥 Followers: <b>{u.get('followers', '—')}</b>\n"
        f"➡️ Following: <b>{u.get('following', '—')}</b>\n"
        f"📸 Posts: <b>{u.get('posts', '—')}</b>"
    )


# ============== BOT COMMANDS ==============

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        # ===== YAHAN APNA WELCOME TEXT DAALO =====
        "👋 <b>YOUR WELCOME TEXT HERE</b>\n\n"
        "YOUR DESCRIPTION / INTRO TEXT HERE...\n\n"
        # ==========================================
        "📋 <b>Commands:</b>\n"
        "/check &lt;username&gt; — Check once\n"
        "/monitor &lt;username&gt; — Start monitoring\n"
        "/stop — Stop monitoring\n"
        "/status — Current monitor status\n\n"
        "Example:\n"
        "<code>/monitor cristiano</code>\n"
        "<code>/check instagram</code>"
    )
    bot.reply_to(message, text, parse_mode="HTML")


# ---------- ADMIN COMMANDS ----------

@bot.message_handler(commands=["adduser"])
def cmd_adduser(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only command.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /adduser &lt;chat_id&gt;\nExample: /adduser 123456789", parse_mode="HTML")
        return

    try:
        chat_id = int(args[1].strip())
    except ValueError:
        bot.reply_to(message, "❌ Invalid chat_id. It should be a number.")
        return

    if chat_id in subscribers:
        bot.reply_to(message, f"⚠️ User <code>{chat_id}</code> is already subscribed.", parse_mode="HTML")
        return

    subscribers.add(chat_id)
    save_subscribers(subscribers)
    bot.reply_to(message, f"✅ User <code>{chat_id}</code> added successfully.", parse_mode="HTML")


@bot.message_handler(commands=["removeuser"])
def cmd_removeuser(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only command.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /removeuser &lt;chat_id&gt;\nExample: /removeuser 123456789", parse_mode="HTML")
        return

    try:
        chat_id = int(args[1].strip())
    except ValueError:
        bot.reply_to(message, "❌ Invalid chat_id. It should be a number.")
        return

    if chat_id not in subscribers:
        bot.reply_to(message, f"⚠️ User <code>{chat_id}</code> is not in subscribers.", parse_mode="HTML")
        return

    subscribers.discard(chat_id)
    save_subscribers(subscribers)

    # Agar wo monitor kar raha tha toh stop bhi kar do
    with lock:
        if chat_id in monitors:
            del monitors[chat_id]

    bot.reply_to(message, f"🔴 User <code>{chat_id}</code> removed.", parse_mode="HTML")


@bot.message_handler(commands=["listusers"])
def cmd_listusers(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only command.")
        return

    if not subscribers:
        bot.reply_to(message, "📭 No subscribers yet.")
        return

    lines = [f"• <code>{uid}</code>" for uid in sorted(subscribers)]
    text = f"👥 <b>Subscribers ({len(subscribers)}):</b>\n\n" + "\n".join(lines)
    bot.reply_to(message, text, parse_mode="HTML")


# ---------- USER COMMANDS (subscription required) ----------

@bot.message_handler(commands=["check"])
def cmd_check(message):
    if not is_allowed(message.from_user.id):
        not_allowed_message(message)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /check &lt;username&gt;", parse_mode="HTML")
        return

    username = args[1].strip().replace("@", "")
    # ===== YAHAN CHECK KE UPAR KA TEXT DAALO =====
    msg = bot.reply_to(message, f"🔍 YOUR CHECKING TEXT HERE @{username}...")
    # =============================================

    data = check_instagram(username)
    bot.edit_message_text(
        format_profile(data),
        chat_id=msg.chat.id,
        message_id=msg.message_id,
        parse_mode="HTML"
    )


@bot.message_handler(commands=["monitor"])
def cmd_monitor(message):
    if not is_allowed(message.from_user.id):
        not_allowed_message(message)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Usage: /monitor &lt;username&gt;", parse_mode="HTML")
        return

    username = args[1].strip().lower().replace("@", "")
    chat_id = message.chat.id

    with lock:
        monitors[chat_id] = {
            "username": username,
            "last_status": None,
            "active": True
        }

    # ===== YAHAN MONITOR START KA TEXT DAALO =====
    bot.reply_to(
        message,
        f"🟢 YOUR MONITOR START TEXT HERE <b>@{username}</b>\n"
        f"YOUR NOTIFICATION / INFO TEXT HERE...\n\n"
        f"Use /stop to stop monitoring.",
        parse_mode="HTML"
    )
    # =============================================

    # Immediate first check
    data = check_instagram(username)
    status = data.get("status", "BANNED")
    with lock:
        if chat_id in monitors:
            monitors[chat_id]["last_status"] = status

    # ===== YAHAN INITIAL STATUS KE UPAR KA TEXT DAALO =====
    bot.send_message(
        chat_id,
        f"YOUR INITIAL STATUS TEXT HERE @{username}:\n\n{format_profile(data)}",
        parse_mode="HTML"
    )
    # ======================================================


@bot.message_handler(commands=["stop"])
def cmd_stop(message):
    if not is_allowed(message.from_user.id):
        not_allowed_message(message)
        return

    chat_id = message.chat.id
    with lock:
        if chat_id in monitors and monitors[chat_id]["active"]:
            username = monitors[chat_id]["username"]
            monitors[chat_id]["active"] = False
            del monitors[chat_id]
            # ===== YAHAN STOP KA TEXT DAALO =====
            bot.reply_to(message, f"🔴 YOUR STOP TEXT HERE @{username}")
            # ====================================
        else:
            # ===== YAHAN NO MONITOR TEXT DAALO =====
            bot.reply_to(message, "YOUR NO ACTIVE MONITOR TEXT HERE")
            # =======================================


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not is_allowed(message.from_user.id):
        not_allowed_message(message)
        return

    chat_id = message.chat.id
    with lock:
        if chat_id in monitors and monitors[chat_id]["active"]:
            m = monitors[chat_id]
            # ===== YAHAN STATUS TEXT DAALO =====
            bot.reply_to(
                message,
                f"📡 YOUR STATUS TEXT HERE: <b>@{m['username']}</b>\n"
                f"Last known status: <b>{m['last_status'] or '—'}</b>",
                parse_mode="HTML"
            )
            # ===================================
        else:
            # ===== YAHAN NO MONITOR TEXT DAALO =====
            bot.reply_to(message, "YOUR NO ACTIVE MONITOR TEXT HERE\nUse /monitor &lt;username&gt;", parse_mode="HTML")
            # =======================================


# ============== BACKGROUND MONITOR ==============

def monitor_loop():
    """Background thread - checks every 2 seconds"""
    while True:
        try:
            with lock:
                items = list(monitors.items())

            for chat_id, info in items:
                if not info.get("active"):
                    continue

                username = info["username"]
                data = check_instagram(username)
                new_status = data.get("status", "BANNED")
                old_status = info.get("last_status")

                if old_status is not None and new_status != old_status:
                    emoji = "✅" if new_status == "ACTIVE" else "🚫"
                    # ===== YAHAN STATUS CHANGE NOTIFICATION TEXT DAALO =====
                    text = (
                        f"{emoji} <b>YOUR STATUS CHANGE TITLE HERE</b>\n\n"
                        f"@{username} is now <b>{new_status}</b>\n\n"
                        f"{format_profile(data)}"
                    )
                    # =======================================================
                    try:
                        bot.send_message(chat_id, text, parse_mode="HTML")
                    except Exception as e:
                        print(f"Failed to notify {chat_id}: {e}")

                with lock:
                    if chat_id in monitors:
                        monitors[chat_id]["last_status"] = new_status

        except Exception as e:
            print(f"Monitor loop error: {e}")

        time.sleep(2)


if __name__ == "__main__":
    print("🚀 Instagram Ban Monitor Bot starting...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"👥 Loaded subscribers: {len(subscribers)}")
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    print("✅ Monitor thread started")
    print("✅ Bot is running... (Ctrl+C to stop)")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
