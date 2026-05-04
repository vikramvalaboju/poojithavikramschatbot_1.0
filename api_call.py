import os
import time
import threading
import requests
import pytz
from telegram import Update
from datetime import datetime
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters


# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN") 
CHAT_ID = os.getenv("CHAT_ID")
ACCESS_KEY = os.getenv("ACCESS_KEY")
CHECKVISA_URL = "https://app.checkvisaslots.com/slots/v3"
POLL_INTERVAL_SECONDS = 180


# ================= API CALL =================

def fetch_slots():
    headers = {
        "X-Api-Key": ACCESS_KEY,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(CHECKVISA_URL, headers=headers, timeout=30)

    try:
        return response.json()
    except Exception:
        return {
            "status_code": response.status_code,
            "text": response.text
        }


# ================= VALIDATION =================

def needs_login_or_refill(data):
    user_details = data.get("userDetails", {})
    activity = data.get("userActivity", {})

    visa_type = user_details.get("visa_type")
    appointment_type = user_details.get("appointment_type")
    subscription = user_details.get("subscription")

    remaining = activity.get("remaining")
    retrieve = activity.get("retrieve")
    upload = activity.get("upload")

    if (
        visa_type is None
        and appointment_type is None
        and subscription is None
        and remaining is None
        and retrieve is None
        and upload is None
    ):
        return True

    return False


def has_slots_available(data):
    for slot in data.get("slotDetails", []):
        try:
            slots_available = int(slot.get("slots", 0))
        except Exception:
            slots_available = 0

        if slots_available > 0:
            return True

    return False


# ================= FORMAT MESSAGE =================

def format_slots(data):
    try:
        if needs_login_or_refill(data):
            return "login and check for refill entires count"

        slot_details = data.get("slotDetails", [])
        activity = data.get("userActivity", {})
        user_details = data.get("userDetails", {})

        msg = "📊 H4 Regular Slot Status\n\n"
        msg += f"Visa Type: {user_details.get('visa_type')}\n"
        msg += f"Appointment Type: {user_details.get('appointment_type')}\n"
        msg += f"Subscription: {user_details.get('subscription')}\n\n"

        for slot in slot_details:
            created_on = slot.get("createdon")
            location = slot.get("visa_location")
            slots_available = slot.get("slots", 0)

            utc_time = datetime.strptime(created_on, "%a, %d %b %Y %H:%M:%S GMT")
            utc_time = utc_time.replace(tzinfo=pytz.utc)

            est_time = utc_time.astimezone(pytz.timezone("US/Eastern"))
            ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
            available_date = slot.get("start_date", "N/A")
            msg += (
                f"📍 {location}\n"
                f"Slots Available: {slots_available}\n"
                f"Available Date: {available_date}\n"
                f"Snapshot EST: {est_time.strftime('%Y-%m-%d %I:%M:%S %p')}\n"
                f"Snapshot IST: {ist_time.strftime('%Y-%m-%d %I:%M:%S %p')}\n\n"
            )
        
        msg += "Usage Summary\n"
        msg += f"Remaining: {activity.get('remaining')}\n"
        msg += f"Retrieve: {activity.get('retrieve')}\n"
        msg += f"Upload: {activity.get('upload')}\n"

        return msg

    except Exception as e:
        return f"Error formatting data: {e}\n\nRaw data:\n{data}"


# ================= COMMON CHECK =================

def run_check():
    data = fetch_slots()
    message = format_slots(data)

    if len(message) > 4000:
        message = message[:4000] + "\n\n...response trimmed"

    return data, message


# ================= TELEGRAM SEND =================

def send_telegram_direct(message):
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=30
    )

    print("Telegram send status:", response.status_code, flush=True)


# ================= AUTO CHECK LOOP =================

def auto_check_loop():
    print("Auto check loop started.", flush=True)
    print("Sleep time: 3 minutes", flush=True)

    while True:
        try:
            print("Auto check running now...", flush=True)

            data, message = run_check()

            if needs_login_or_refill(data):
                send_telegram_direct("login and check for refill entires count")
                print("Login/refill message sent.", flush=True)

            elif has_slots_available(data):
                send_telegram_direct("🚨 Slot Available!\n\n" + message)
                print("Slot available. Telegram alert sent.", flush=True)

            else:
                print("No slot available. No Telegram message sent.", flush=True)

        except Exception as e:
            print("Auto check error:", e, flush=True)

        print(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...", flush=True)
        time.sleep(POLL_INTERVAL_SECONDS)


# ================= TELEGRAM HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot started.\n\nSend only 'check' to check slots manually.\nAuto check runs every 3 minutes."
    )


async def check_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text != "check":
        await update.message.reply_text("Only 'check' is allowed.")
        return

    await update.message.reply_text("Checking slots...")

    try:
        data, message = run_check()
        await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(f"Error while checking: {e}")


# ================= MAIN =================

def main():
    thread = threading.Thread(target=auto_check_loop, daemon=True)
    thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_on_message))

    print("Telegram bot running.", flush=True)
    print("Manual command allowed: check", flush=True)
    print("Auto check sleep time: 3 minutes", flush=True)

    app.run_polling()


if __name__ == "__main__":
    main()
