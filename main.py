import os, json, time, random, threading, asyncio
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
import aiohttp

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = "admin123"  # 🔥 change karo

# In-memory data – tu JSON file bhi use kar sakta hai
DATA = {
    "owners": [8978106847],
    "admins": [],
    "banned": [],
    "users": {},
    "firebases": [],
    "redeem_codes": {},
    "stats": {"total_sent": 0, "total_failed": 0},
    "videos": []
}

# Firebase device cache (same as bot)
CACHED_DEVICES = []
LAST_SCAN_TIME = 0
SCANNING = False

def load_data():
    global DATA
    if os.path.exists("data.json"):
        with open("data.json", "r") as f:
            DATA.update(json.load(f))

def save_data():
    with open("data.json", "w") as f:
        json.dump(DATA, f, indent=2)

load_data()

# ---------------- Helper functions (copy from bot) ----------------
# Firebase scanning, sending SMS, etc. (same as bot code)
# We'll provide simplified versions for brevity.

async def get_all_online_devices():
    # same as bot's get_all_online_devices
    # ... (implement using aiohttp)
    return []  # placeholder

def get_user_credits(uid):
    return DATA["users"].get(str(uid), {}).get("credits", 0)

def add_credits(uid, amount):
    uid = str(uid)
    if uid not in DATA["users"]:
        DATA["users"][uid] = {"credits": 0}
    DATA["users"][uid]["credits"] = DATA["users"][uid].get("credits", 0) + amount
    save_data()

def deduct_credits(uid, amount):
    uid = str(uid)
    if uid in DATA["users"] and DATA["users"][uid].get("credits", 0) >= amount:
        DATA["users"][uid]["credits"] -= amount
        save_data()
        return True
    return False

def is_owner(uid):
    return uid in DATA["owners"]

def is_admin(uid):
    return uid in DATA["admins"] or is_owner(uid)

def is_banned(uid):
    return uid in DATA["banned"]

# ---------------- API Endpoints ----------------

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('uid')
    if not uid:
        return jsonify({"error": "UID required"}), 400
    uid = int(uid)
    if is_banned(uid):
        return jsonify({"status": "banned"})
    if is_owner(uid):
        role = "owner"
    elif is_admin(uid):
        role = "admin"
    else:
        role = "user"
    credits = get_user_credits(uid)
    return jsonify({"status": "ok", "role": role, "credits": credits})

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.json
    uid = data.get('uid')
    password = data.get('password')
    if not uid or not password:
        return jsonify({"error": "UID and password required"}), 400
    uid = int(uid)
    if password != ADMIN_PASSWORD:
        return jsonify({"error": "Invalid admin password"}), 403
    if is_banned(uid):
        return jsonify({"status": "banned"})
    if not (is_owner(uid) or is_admin(uid)):
        return jsonify({"error": "User not admin"}), 403
    role = "owner" if is_owner(uid) else "admin"
    credits = get_user_credits(uid)
    return jsonify({"status": "ok", "role": role, "credits": credits})

@app.route('/send_sms', methods=['POST'])
def send_sms():
    data = request.json
    uid = data.get('uid')
    number = data.get('number')
    message = data.get('message')
    count = data.get('count', 1)
    speed = data.get('speed', 0.2)
    if not uid or not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid)
    if is_banned(uid):
        return jsonify({"error": "User banned"}), 403
    # Deduct credits
    if not is_admin(uid):
        if not deduct_credits(uid, count):
            return jsonify({"error": "Insufficient credits"}), 400

    # Get online devices
    devices = asyncio.run(get_all_online_devices())
    if not devices:
        return jsonify({"error": "No online devices"}), 503

    # Send SMS (simplified: send sequentially with speed)
    sent = 0
    failed = 0
    for i in range(min(count, len(devices)*3)):
        device = devices[i % len(devices)]
        # Use asyncio to actually send
        # For simplicity, just simulate
        sent += 1
        time.sleep(speed)
    # Update stats
    DATA["stats"]["total_sent"] = DATA["stats"].get("total_sent", 0) + sent
    DATA["stats"]["total_failed"] = DATA["stats"].get("total_failed", 0) + failed
    save_data()
    return jsonify({"sent": sent, "failed": failed})

@app.route('/get_credits', methods=['GET'])
def get_credits():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "UID required"}), 400
    uid = int(uid)
    credits = get_user_credits(uid)
    return jsonify({"credits": credits})

@app.route('/redeem', methods=['POST'])
def redeem():
    data = request.json
    uid = data.get('uid')
    code = data.get('code')
    if not uid or not code:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid)
    codes = DATA.get("redeem_codes", {})
    if code not in codes:
        return jsonify({"error": "Invalid code"}), 400
    cdata = codes[code]
    if cdata.get("uses_left", 0) <= 0:
        return jsonify({"error": "Code expired"}), 400
    if uid in cdata.get("used_by", []):
        return jsonify({"error": "Already used"}), 400
    cdata["uses_left"] -= 1
    cdata.setdefault("used_by", []).append(uid)
    add_credits(uid, cdata["credits"])
    save_data()
    return jsonify({"status": "ok", "credits_added": cdata["credits"]})

@app.route('/get_users', methods=['GET'])
def get_users():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "UID required"}), 400
    uid = int(uid)
    if not is_admin(uid):
        return jsonify({"error": "Admin only"}), 403
    users = []
    for uid_str, udata in DATA["users"].items():
        users.append({
            "uid": int(uid_str),
            "name": udata.get("name", "Unknown"),
            "credits": udata.get("credits", 0),
            "uses": udata.get("uses", 0)
        })
    return jsonify({"users": users})

@app.route('/ban', methods=['POST'])
def ban_user():
    data = request.json
    uid = data.get('uid')
    target = data.get('target_uid')
    if not uid or not target:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid); target = int(target)
    if not is_admin(uid):
        return jsonify({"error": "Admin only"}), 403
    if is_owner(target) or target in DATA["admins"]:
        return jsonify({"error": "Cannot ban admin/owner"}), 403
    if target not in DATA["banned"]:
        DATA["banned"].append(target)
        save_data()
    return jsonify({"status": "ok"})

@app.route('/unban', methods=['POST'])
def unban_user():
    data = request.json
    uid = data.get('uid')
    target = data.get('target_uid')
    if not uid or not target:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid); target = int(target)
    if not is_admin(uid):
        return jsonify({"error": "Admin only"}), 403
    if target in DATA["banned"]:
        DATA["banned"].remove(target)
        save_data()
    return jsonify({"status": "ok"})

@app.route('/add_credits', methods=['POST'])
def add_credits_endpoint():
    data = request.json
    uid = data.get('uid')
    target = data.get('target_uid')
    amount = data.get('amount')
    if not uid or not target or amount is None:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid); target = int(target); amount = int(amount)
    if not is_admin(uid):
        return jsonify({"error": "Admin only"}), 403
    add_credits(target, amount)
    return jsonify({"status": "ok", "new_balance": get_user_credits(target)})

@app.route('/add_firebase', methods=['POST'])
def add_firebase():
    uid = request.form.get('uid')
    if not uid:
        return jsonify({"error": "UID required"}), 400
    uid = int(uid)
    if not is_owner(uid):
        return jsonify({"error": "Owner only"}), 403
    file = request.files.get('file')
    if not file or not file.filename.endswith('.txt'):
        return jsonify({"error": "Upload a .txt file"}), 400
    content = file.read().decode('utf-8')
    lines = content.splitlines()
    added = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        if '|' in line:
            label, url = line.split('|', 1)
            label = label.strip()
            url = url.strip()
        else:
            url = line
            label = url.replace('https://', '').split('.')[0][:20]
        if not url.startswith('http'): continue
        url = url.rstrip('/')
        if any(fb['url'] == url for fb in DATA['firebases']):
            continue
        DATA['firebases'].append({
            "id": str(int(time.time()*1000) + random.randint(1,999)),
            "url": url,
            "label": label,
            "added_at": int(time.time())
        })
        added += 1
    save_data()
    return jsonify({"status": "ok", "added": added})

@app.route('/broadcast', methods=['POST'])
def broadcast():
    data = request.json
    uid = data.get('uid')
    message = data.get('message')
    if not uid or not message:
        return jsonify({"error": "Missing fields"}), 400
    uid = int(uid)
    if not is_admin(uid):
        return jsonify({"error": "Admin only"}), 403
    # Send to all users (simulate)
    count = len(DATA["users"])
    # In real implementation, you'd use bot.send_message
    return jsonify({"status": "ok", "delivered": count})

@app.route('/get_videos', methods=['GET'])
def get_videos():
    return jsonify({"videos": DATA.get("videos", [])})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
