from flask import Flask, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient

import re
import certifi
import os
import threading
import time
import serial
import subprocess
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from werkzeug.utils import secure_filename

# Import your existing agents (NO CHANGES NEEDED)
from agents.chat_agent import model_col, ChatAgent
from agents.requir_recommender_agent import RecommenderAgent
from agents.pricing_agent import PricingAgent
from agents.report_agent import ReportAgent

# ✅ Load .env variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
app.config["SESSION_TYPE"] = "filesystem"
CORS(app)

# ✅ MongoDB Configuration
mongo_uri = os.getenv("MONGO_URI")
user_db_name = os.getenv("USER_DB_NAME")
users_collection_name = os.getenv("USERS_COLLECTION_NAME", "users")
chats_collection_name = os.getenv("CHATS_COLLECTION_NAME", "chats")

mongo_client = MongoClient(
    mongo_uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=20000
)
user_db = mongo_client[user_db_name]
users_col = user_db[users_collection_name]
chats_col = user_db[chats_collection_name]
final_model_col = user_db["final_models"]

# ✅ Azure OpenAI Setup
gpt_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-05-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    default_headers={"azure-openai-deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")}
)
az_key = os.getenv("AZURE_OPENAI_KEY")
az_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
assistant_id = os.getenv("AZURE_OPENAI_ASSISTANT_ID")

# 🔒 SECURE Multi-Platform Configuration (phone numbers from environment variables)
WHATSAPP_FRIENDS = os.getenv("WHATSAPP_FRIENDS", "").split(",") if os.getenv("WHATSAPP_FRIENDS") else []
WHATSAPP_FRIENDS = [phone.strip() for phone in WHATSAPP_FRIENDS if phone.strip()]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USB_MODEM_PORT = os.getenv("USB_MODEM_PORT", "/dev/ttyUSB0")
ANDROID_DEVICE_ID = os.getenv("ANDROID_DEVICE_ID")

# 🆕 Keep-alive for Render (prevents sleeping)
def keep_alive():
    """Ping self every 10 minutes to prevent Render from sleeping"""
    if os.getenv("RENDER"):
        while True:
            try:
                time.sleep(600)  # 10 minutes
                requests.get(f"http://localhost:5000/platform-status", timeout=30)
                print("🏓 Keep-alive ping sent")
            except Exception as e:
                print(f"Keep-alive error: {e}")

# Start keep-alive in background
if os.getenv("RENDER"):
    threading.Thread(target=keep_alive, daemon=True).start()

# 🆕 Platform identification helper
def identify_platform(email):
    """Identify which platform the user is from"""
    if email.startswith("91") and len(email) == 12:
        return "whatsapp"
    elif email.startswith("telegram_"):
        return "telegram"
    elif email.startswith("sms_"):
        return "sms"
    elif "@" in email:
        return "web"
    else:
        return "unknown"

# 🆕 Auto-registration for messaging platforms
def auto_register_user(email, username, platform="unknown"):
    """Auto-register users from messaging platforms"""
    existing_user = users_col.find_one({"email": email})
    
    if not existing_user:
        user_data = {
            "username": username,
            "email": email,
            "password": "auto_generated",
            "platform": platform,
            "created_at": datetime.now()
        }
        users_col.insert_one(user_data)
        print(f"✅ Auto-registered {platform} user: {email}")
        return user_data
    
    return existing_user

# 🆕 Clean phone number helper
def clean_phone_number(phone):
    """Clean and format Indian phone numbers"""
    phone = re.sub(r'\D', '', str(phone))
    
    if phone.startswith('91') and len(phone) == 12:
        return phone[2:]
    elif phone.startswith('0') and len(phone) == 11:
        return phone[1:]
    elif len(phone) == 10:
        return phone
    else:
        return None

# 🆕 Format message for different platforms
def format_for_platform(message, platform):
    """Format AI response for different platforms"""
    if platform == "sms":
        # SMS: Plain text, 160 char limit
        clean_text = re.sub(r'\*\*\*.*?\*\*\*', lambda m: m.group(0).replace('***', ''), message)
        clean_text = re.sub(r'[📝💡🤖✨👋🎯🔄⚠️😊]', '', clean_text)
        clean_text = re.sub(r'[•◦]', '-', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) <= 160:
            return clean_text
        else:
            return clean_text[:155] + "..."
    
    elif platform == "whatsapp":
        # WhatsApp: Supports some formatting
        formatted = message.replace('***', '*').replace('***', '*')
        formatted = formatted.replace('• ', '• ')
        formatted = formatted.replace('  ◦ ', '    ◦ ')
        return formatted
    
    elif platform == "telegram":
        # Telegram: HTML formatting
        formatted = message.replace('***', '<b><i>').replace('***', '</i></b>')
        formatted = formatted.replace('• ', '• ')
        formatted = formatted.replace('  ◦ ', '    ◦ ')
        return formatted
    
    else:
        # Web: Return as-is
        return message

# ==================== EXISTING WEB ENDPOINTS (UNCHANGED) ====================

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        return jsonify({"status": "fail", "message": "All fields are required"}), 400

    if users_col.find_one({"email": email}):
        return jsonify({"status": "fail", "message": "Email already registered"}), 409

    users_col.insert_one({
        "username": name,
        "email": email,
        "password": password,
        "platform": "web",
        "created_at": datetime.now()
    })

    return jsonify({"status": "success", "message": "User registered successfully"})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    print("🎯 Login API hit")

    if not email or not password:
        return jsonify({"status": "fail", "message": "Both email and password are required"}), 400

    existing_user = users_col.find_one({"email": email})
    if not existing_user:
        return jsonify({"status": "fail", "message": "User not found. Please sign up."}), 404

    if existing_user["password"] != password:
        return jsonify({"status": "fail", "message": "Incorrect password"}), 401
    
    session[f"chat_session_{existing_user['email']}"] = {
        "shortlisted_models": [],
        "current_model": None,
        "rejected_models": [],
        "original_requirement": "",
        "username": existing_user["email"]
    }
    
    print("✅ Login successful for:", email)
    return jsonify({"status": "success", "email": existing_user["email"]})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    email = data.get("email")
    message = data.get("message")
    return process_chat_message(email, message, "web")

# 🆕 Core chat processing function
def process_chat_message(email, message, platform="web"):
    """Core chat processing that works for all platforms"""
    
    try:
        chat_agent = ChatAgent(gpt_client)
        
        session_key = f"chat_session_{email}"
        session_data = session.get(session_key, {
            "email": email,
            "shortlisted_models": [],
            "current_model": None,
            "rejected_models": [],
            "original_requirement": ""
        })

        chat_response = chat_agent.process_web_input(message, session_data, username=email)

        if not chat_response or not chat_response["proceed"]:
            response = chat_response["message"] if chat_response else "Could not process your request. Please try again."
        else:
            action = chat_response.get("action")

            if action == "NewRequirement":
                recommender = RecommenderAgent(gpt_client)
                recommended = recommender.recommend_models(
                    analyzed_user_input=message,
                    username=email,
                    is_new_requirement=1
                )

                pricing_agent = PricingAgent(assistant_id, az_key, az_endpoint)
                pricing_info = pricing_agent.analyze_pricing(recommended)

                session_data["original_requirement"] = message
                print("👀 Saving for email:", email)

                report_agent = ReportAgent(gpt_client)
                report = report_agent.generate_report(email, message, recommended, pricing_info)

                session_data["shortlisted_models"] = recommended
                session_data["current_model"] = recommended[0] if recommended else None
                session_data["rejected_models"] = []

                response = report

            elif action == "FollowUp":
                response = chat_response["message"]

            elif action == "ModelRejection":
                recommender = RecommenderAgent(gpt_client)
                original_requirement = chat_response.get("requirement", "")
                rejected_models = session_data.get("rejected_models", [])

                recommended = recommender.recommend_models(
                    analyzed_user_input=original_requirement,
                    username=email,
                    is_new_requirement=0
                )

                if not recommended:
                    response = "No more suitable models found. Would you like to try a different approach or modify your requirements?"
                else:
                    pricing_agent = PricingAgent(assistant_id, az_key, az_endpoint)
                    pricing_info = pricing_agent.analyze_pricing(recommended)

                    report_agent = ReportAgent(gpt_client)
                    report = report_agent.generate_report(email, original_requirement, recommended, pricing_info)

                    session_data["shortlisted_models"] = recommended
                    session_data["current_model"] = recommended[0] if recommended else None

                    response = report

            else:
                response = "I'm here to help with AI model recommendations. Could you please clarify what you need?"

        session[session_key] = session_data
        print(f"✅ Stored session for: {email} ({platform})")

        chats_col.insert_one({
            "email": email, 
            "message": message, 
            "response": response, 
            "platform": platform,
            "timestamp": datetime.now()
        })
        
        formatted_response = format_for_platform(response, platform)
        
        if platform == "web":
            return jsonify({
                "response": formatted_response,
                "current_model": session_data.get("current_model")
            })
        else:
            return {
                "response": formatted_response,
                "current_model": session_data.get("current_model")
            }
            
    except Exception as e:
        print(f"❌ Error processing chat message: {e}")
        error_response = "Sorry, I'm having trouble processing your request right now. Please try again."
        
        if platform == "web":
            return jsonify({"response": error_response, "current_model": None})
        else:
            return {"response": error_response, "current_model": None}

# ==================== WHATSAPP INTEGRATION ====================

@app.route("/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        data = request.get_json()
        print(f"📱 WhatsApp webhook received: {data}")
        
        phone_number = data.get("from", data.get("From", "")).replace("+", "").replace(" ", "")
        message_text = data.get("message", data.get("text", data.get("body", "")))
        
        clean_phone = clean_phone_number(phone_number)
        
        if not clean_phone or not message_text:
            print(f"❌ Invalid WhatsApp data: phone={phone_number}, message={message_text}")
            return jsonify({"status": "error", "message": "Missing phone or message"}), 400
        
        full_phone = f"91{clean_phone}"
        if full_phone not in WHATSAPP_FRIENDS:
            print(f"❌ Unauthorized WhatsApp user: {full_phone}")
            return jsonify({"status": "unauthorized", "message": "Not authorized"}), 403
        
        auto_register_user(
            email=full_phone,
            username=f"WhatsApp_{clean_phone}",
            platform="whatsapp"
        )
        
        result = process_chat_message(full_phone, message_text, "whatsapp")
        
        print(f"✅ WhatsApp response sent to {phone_number}")
        return jsonify({
            "status": "success",
            "response": result["response"],
            "to": phone_number
        })
        
    except Exception as e:
        print(f"❌ WhatsApp webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== TELEGRAM INTEGRATION ====================

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram messages"""
    try:
        data = request.get_json()
        print(f"🤖 Telegram webhook received: {data}")
        
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_text = message.get("text", "")
        user_info = message.get("from", {})
        username = user_info.get("username", user_info.get("first_name", "TelegramUser"))
        
        if not chat_id or not message_text:
            print(f"❌ Invalid Telegram data: chat_id={chat_id}, message={message_text}")
            return jsonify({"status": "error", "message": "Missing chat_id or message"}), 400
        
        if message_text.startswith("/"):
            return handle_telegram_command(chat_id, message_text, username)
        
        telegram_email = f"telegram_{chat_id}"
        
        auto_register_user(
            email=telegram_email,
            username=f"Telegram_{username}",
            platform="telegram"
        )
        
        result = process_chat_message(telegram_email, message_text, "telegram")
        
        send_telegram_message(chat_id, result["response"])
        
        print(f"✅ Telegram response sent to {chat_id}")
        return jsonify({"status": "success"})
        
    except Exception as e:
        print(f"❌ Telegram webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_telegram_command(chat_id, command, username):
    """Handle Telegram bot commands"""
    try:
        if command == "/start":
            welcome_msg = f"""🤖 Welcome to AI Model Selector Bot, {username}!

I help you find the perfect AI model for your needs.

💡 Just describe what you want to do:
• "I need AI for image recognition"
• "Help me with text summarization" 
• "I want to build a chatbot"

🚀 What AI task can I help you with today?"""
            
            send_telegram_message(chat_id, welcome_msg)
            
        elif command == "/help":
            help_msg = """🆘 How to use AI Model Selector:

1️⃣ Describe your AI need
2️⃣ Get personalized recommendations  
3️⃣ Ask follow-up questions about models

💭 Example questions:
• "What's the best model for document analysis?"
• "I need real-time image processing"
• "Help me choose between GPT models"

Need help? Just ask! 😊"""
            
            send_telegram_message(chat_id, help_msg)
            
        else:
            send_telegram_message(chat_id, "Unknown command. Type /help for assistance.")
        
        return jsonify({"status": "success"})
        
    except Exception as e:
        print(f"❌ Telegram command error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def send_telegram_message(chat_id, message):
    """Send message to Telegram user"""
    try:
        if not TELEGRAM_BOT_TOKEN:
            print("❌ Telegram bot token not configured")
            return False
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Telegram message sent to {chat_id}")
            return True
        else:
            print(f"❌ Telegram send failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Telegram send error: {e}")
        return False

# ==================== SMS INTEGRATION ====================

@app.route("/sms-webhook", methods=["POST"])
def sms_webhook():
    """Handle incoming SMS messages"""
    try:
        data = request.get_json() or request.form.to_dict()
        print(f"📞 SMS webhook received: {data}")
        
        phone_number = data.get("from", data.get("From", data.get("mobile", "")))
        message_text = data.get("body", data.get("Body", data.get("text", "")))
        
        clean_phone = clean_phone_number(phone_number)
        
        if not clean_phone or not message_text:
            print(f"❌ Invalid SMS data: phone={phone_number}, message={message_text}")
            return jsonify({"status": "error", "message": "Missing phone or message"}), 400
        
        full_phone = f"91{clean_phone}"
        sms_email = f"sms_{full_phone}"
        
        auto_register_user(
            email=sms_email,
            username=f"SMS_{clean_phone}",
            platform="sms"
        )
        
        result = process_chat_message(sms_email, message_text, "sms")
        
        send_sms_response(full_phone, result["response"])
        
        print(f"✅ SMS response sent to {phone_number}")
        return jsonify({"status": "success"})
        
    except Exception as e:
        print(f"❌ SMS webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def send_sms_response(phone_number, message):
    """Send SMS response using available methods"""
    try:
        print(f"📱 SMS to {phone_number}: {message}")
        
        if USB_MODEM_PORT and os.path.exists(USB_MODEM_PORT):
            return send_sms_via_usb_modem(phone_number, message)
        elif ANDROID_DEVICE_ID:
            return send_sms_via_android_adb(phone_number, message)
        else:
            print(f"📱 SMS would be sent to {phone_number}: {message}")
            return True
            
    except Exception as e:
        print(f"❌ SMS send error: {e}")
        return False

def send_sms_via_usb_modem(phone_number, message):
    """Send SMS using USB modem"""
    try:
        modem = serial.Serial(USB_MODEM_PORT, 9600, timeout=5)
        time.sleep(2)
        
        modem.write(b'AT\r\n')
        response = modem.read(100)
        
        if b'OK' not in response:
            return False
        
        modem.write(b'AT+CMGF=1\r\n')
        time.sleep(1)
        
        sms_cmd = f'AT+CMGS="{phone_number}"\r\n'
        modem.write(sms_cmd.encode())
        time.sleep(1)
        
        modem.write(message.encode() + b'\x1A')
        time.sleep(5)
        response = modem.read(200)
        
        modem.close()
        
        return b'OK' in response or b'+CMGS' in response
        
    except Exception as e:
        print(f"❌ USB modem error: {e}")
        return False

def send_sms_via_android_adb(phone_number, message):
    """Send SMS using Android phone via ADB"""
    try:
        adb_command = [
            'adb', '-s', ANDROID_DEVICE_ID, 'shell',
            'am', 'start', '-a', 'android.intent.action.SENDTO',
            '-d', f'sms:{phone_number}',
            '--es', 'sms_body', message,
            '--ez', 'exit_on_sent', 'true'
        ]
        
        result = subprocess.run(adb_command, capture_output=True, text=True)
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Android ADB error: {e}")
        return False

# ==================== UTILITY ENDPOINTS ====================

@app.route("/platform-status", methods=["GET"])
def platform_status():
    """Get status of all platforms - used by UptimeRobot"""
    try:
        web_users = users_col.count_documents({"platform": "web"})
        whatsapp_users = users_col.count_documents({"platform": "whatsapp"})
        telegram_users = users_col.count_documents({"platform": "telegram"})
        sms_users = users_col.count_documents({"platform": "sms"})
        total_chats = chats_col.count_documents({})
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "platforms": {
                "web": {"status": "active", "users": web_users},
                "whatsapp": {"status": "active", "users": whatsapp_users, "friends": len(WHATSAPP_FRIENDS)},
                "telegram": {"status": "active", "users": telegram_users, "bot_configured": bool(TELEGRAM_BOT_TOKEN)},
                "sms": {"status": "active", "users": sms_users}
            },
            "total_users": web_users + whatsapp_users + telegram_users + sms_users,
            "total_chats": total_chats,
            "environment": "production" if os.getenv("RENDER") else "development"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/set-telegram-webhook", methods=["POST"])
def set_telegram_webhook():
    """Set Telegram webhook URL"""
    try:
        if not TELEGRAM_BOT_TOKEN:
            return jsonify({"status": "error", "message": "Telegram bot token not configured"}), 400
        
        webhook_url = request.json.get("webhook_url")
        if not webhook_url:
            return jsonify({"status": "error", "message": "webhook_url required"}), 400
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
        data = {"url": f"{webhook_url}/telegram-webhook"}
        
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            return jsonify({"status": "success", "webhook_set": webhook_url})
        else:
            return jsonify({"status": "error", "message": response.text}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== EXISTING ENDPOINTS (UNCHANGED) ====================

@app.route("/history/<username>", methods=["GET"])
def history(username):
    try:
        chats = chats_col.find({"email": username}).sort("timestamp", 1)
        result = []
        for c in chats:
            result.append({"email": username, "message": c["message"], "timestamp": c.get("timestamp")})
            if "response" in c:
                result.append({"username": "Agent", "message": c["response"], "timestamp": c.get("timestamp")})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("file")
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join("uploads", filename)
            os.makedirs("uploads", exist_ok=True)
            file.save(filepath)
            return jsonify({"status": "success", "file": filename})
        return jsonify({"status": "fail", "message": "No file provided"}), 400
    except Exception as e:
        return jsonify({"status": "fail", "message": str(e)}), 400

@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    try:
        email = request.get_json().get("username")
        deleted = chats_col.delete_many({"email": email})
        return jsonify({"status": "cleared", "deleted_count": deleted.deleted_count})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/logout", methods=["POST", "OPTIONS"])
def logout_user():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode("utf-8"))

        email = data.get("email")
        print(f"🔐 Logout request received for: {email}")

        deleted_chats = chats_col.delete_many({"email": email})
        deleted_models = final_model_col.delete_many({"email": email})

        print(f"🧹 Deleted {deleted_chats.deleted_count} chats.")
        print(f"🧹 Deleted {deleted_models.deleted_count} final models.")

        return jsonify({
            "status": "success",
            "message": f"Data cleared for {email}",
            "deleted_chats": deleted_chats.deleted_count,
            "deleted_models": deleted_models.deleted_count
        }), 200

    except Exception as e:
        print("❌ Error during logout:", str(e))
        return jsonify({"status": "fail", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Basic health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "AI Model Selector",
        "platforms": ["web", "whatsapp", "telegram", "sms"],
        "timestamp": datetime.now().isoformat()
    })

@app.route("/", methods=["GET"])
def root():
    """Root endpoint"""
    return jsonify({
        "message": "AI Model Selector Multi-Platform API",
        "status": "running",
        "platforms": {
            "web": "Active",
            "whatsapp": f"Configured for {len(WHATSAPP_FRIENDS)} friends",
            "telegram": "Configured" if TELEGRAM_BOT_TOKEN else "Not configured",
            "sms": "Available"
        },
        "endpoints": {
            "web_chat": "/chat",
            "whatsapp_webhook": "/whatsapp-webhook", 
            "telegram_webhook": "/telegram-webhook",
            "sms_webhook": "/sms-webhook",
            "platform_status": "/platform-status"
        }
    })

if __name__ == "__main__":
    print("🚀 Starting Multi-Platform AI Model Selector...")
    print("=" * 50)
    print("📱 Platforms:")
    print(f"   • Web: Active")
    print(f"   • WhatsApp: {len(WHATSAPP_FRIENDS)} friends configured")
    print(f"   • Telegram: {'Configured' if TELEGRAM_BOT_TOKEN else 'Not configured'}")
    print(f"   • SMS: Available")
    print("=" * 50)
    print("🔗 Webhook URLs (replace with your Render URL):")
    print("   • WhatsApp: https://your-app.onrender.com/whatsapp-webhook")
    print("   • Telegram: https://your-app.onrender.com/telegram-webhook")
    print("   • SMS: https://your-app.onrender.com/sms-webhook")
    print("=" * 50)
    print("🔧 Environment Check:")
    print(f"   • MongoDB: {'Connected' if mongo_uri else 'Not configured'}")
    print(f"   • Azure OpenAI: {'Connected' if az_key else 'Not configured'}")
    print(f"   • Telegram Bot: {'Configured' if TELEGRAM_BOT_TOKEN else 'Not configured'}")
    print(f"   • WhatsApp Friends: {len(WHATSAPP_FRIENDS)} configured")
    print(f"   • USB Modem: {'Available' if USB_MODEM_PORT and os.path.exists(USB_MODEM_PORT) else 'Not available'}")
    print(f"   • Android ADB: {'Configured' if ANDROID_DEVICE_ID else 'Not configured'}")
    print("=" * 50)
    print("🎯 Next Steps:")
    print("   1. Set environment variable: WHATSAPP_FRIENDS=919876543210,919876543211")
    print("   2. Deploy to Render")
    print("   3. Set up Telegram webhook")
    print("   4. Add UptimeRobot monitoring")
    print("   5. Test with friends!")
    print("=" * 50)
    
    # Start the Flask app
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)