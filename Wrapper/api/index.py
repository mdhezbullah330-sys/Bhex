from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import requests
import pymongo
import datetime
import re

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = "super_secret_session_encryption_key_999"

# MongoDB Connection
MONGO_URI = "mongodb://benja:hex@ac-4jxadv5-shard-00-00.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-01.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-02.2rtfrua.mongodb.net:27017/?ssl=true&replicaSet=atlas-11c2ax-shard-0&authSource=admin&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["my_api_db"]
keys_collection = db["api_keys"]
banned_ips_collection = db["banned_ips"]
ip_history_collection = db["ip_history"] # ট্র্যাক রাখবে কোন কী কোন IP ও ডিভাইস দিয়ে ইউজ হয়েছে

TARGET_URL = "http://raw.thug4ff.xyz/check"
ADMIN_PASSWORDS = ["1nonly_talha", "hyceanx", "benjahexofficialx", "duryabx", "deeshanx"]

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def parse_user_agent(ua_string):
    if not ua_string:
        return "Unknown Script"
    ua = ua_string.lower()
    if "mozilla" in ua or "chrome" in ua or "safari" in ua or "opera" in ua:
        # Browser detect tracking
        if "android" in ua: return "Mobile Browser"
        if "iphone" in ua: return "iPhone Browser"
        return "Desktop Browser"
    if "curl" in ua: return "cURL Command"
    if "python-requests" in ua or "aiohttp" in ua: return "Python Script"
    if "node-fetch" in ua or "axios" in ua: return "Node.js App"
    if "vps" in ua or "cloud" in ua or "go-http-client" in ua: return "VPS/Hosting Server"
    return "External Request"

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    msg, msg_type = None, "success"

    if request.method == 'POST':
        # নতুন কী তৈরি করার মেকানিজম
        try:
            new_key = request.form.get('key_name', '').strip()
            expiry_type = request.form.get('expiry_type') # 'days', 'date', 'unlimited'
            
            ip_locked = True if request.form.get('ip_locked') == 'on' else False
            manual_ip = request.form.get('manual_ip', '').strip()

            if new_key:
                if keys_collection.find_one({"key": new_key}):
                    msg, msg_type = f"Error: '{new_key}' already exists!", "danger"
                else:
                    if expiry_type == 'unlimited':
                        expiry_str = "UNLIMITED"
                    elif expiry_type == 'date':
                        custom_date = request.form.get('custom_date') # YYYY-MM-DDTHH:MM
                        if custom_date:
                            expiry_str = custom_date.replace("T", " ") + ":00"
                        else:
                            expiry_str = "UNLIMITED"
                    else:
                        days = request.form.get('expiry_days', type=int) or 30
                        expiry_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
                        expiry_str = expiry_date.strftime('%Y-%m-%d %H:%M:%S')

                    keys_collection.insert_one({
                        "key": str(new_key), 
                        "expires_at": expiry_str,
                        "ip_locked": bool(ip_locked),
                        "locked_ip": manual_ip if manual_ip else None,
                        "last_used": None,
                        "last_agent": None,
                        "is_active": True
                    })
                    msg = f"Key '{new_key}' deployed successfully!"
        except Exception as e:
            msg, msg_type = f"Backend Error: {str(e)}", "danger"

    return render_template('dashboard.html', msg=msg, msg_type=msg_type)

# ---- API ENDPOINTS FOR LIVE SYNC ----

@app.route('/api/live_data', methods=['GET'])
def live_data():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    
    keys = list(keys_collection.find({}, {"_id": 0}))
    banned_ips = list(banned_ips_collection.find({}, {"_id": 0}))
    
    # কারেন্ট টাইম UTC স্ট্রিং পাস করা হচ্ছে কাউন্টডাউনের সুবিধার জন্য
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({"keys": keys, "banned_ips": banned_ips, "server_time": now_str})

@app.route('/api/key_history/<string:key_name>', methods=['GET'])
def key_history(key_name):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    history = list(ip_history_collection.find({"key": key_name}, {"_id": 0}).sort("timestamp", -1).limit(50))
    return jsonify(history)

@app.route('/api/edit_key', methods=['POST'])
def edit_key():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    key_name = data.get('key')
    expiry_type = data.get('type') # 'unlimited' or 'date'
    new_val = data.get('value')
    
    if expiry_type == 'unlimited':
        final_expiry = "UNLIMITED"
    else:
        final_expiry = new_val.replace("T", " ") + ":00" if "T" in new_val else new_val
        
    keys_collection.update_one({"key": key_name}, {"$set": {"expires_at": final_expiry}})
    return jsonify({"success": True})

@app.route('/api/ban_ip', methods=['POST'])
def ban_ip():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ip = data.get('ip', '').strip()
    duration_type = data.get('type') # 'permanent' or 'custom'
    end_val = data.get('value') # date string or none
    
    if not ip: return jsonify({"error": "IP required"}), 400
    
    ban_expiry = "PERMANENT"
    if duration_type == 'custom' and end_val:
        ban_expiry = end_val.replace("T", " ") + ":00" if "T" in end_val else end_val

    banned_ips_collection.update_one(
        {"ip": ip},
        {"$set": {"ip": ip, "ban_expiry": ban_expiry, "agent": data.get('agent', 'Manual Entry')}},
        upsert=True
    )
    return jsonify({"success": True})

@app.route('/api/unban_ip/<string:ip>', methods=['POST'])
def unban_ip(ip):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    banned_ips_collection.delete_one({"ip": ip})
    return jsonify({"success": True})

@app.route('/delete_key/<string:key_name>', methods=['POST'])
def delete_key(key_name):
    if session.get('logged_in'): keys_collection.delete_one({"key": key_name})
    return redirect(url_for('dashboard'))

@app.route('/toggle_pause/<string:key_name>', methods=['POST'])
def toggle_pause(key_name):
    if session.get('logged_in'):
        k = keys_collection.find_one({"key": key_name})
        if k: keys_collection.update_one({"key": key_name}, {"$set": {"is_active": not k.get("is_active", True)}})
    return redirect(url_for('dashboard'))

@app.route('/reset_ip/<string:key_name>', methods=['POST'])
def reset_ip(key_name):
    if session.get('logged_in'): keys_collection.update_one({"key": key_name}, {"$set": {"locked_ip": None}})
    return redirect(url_for('dashboard'))

# ---- CORE VERIFICATION GATEWAY WITH LIVE BAN CHECK ----

@app.route('/check', methods=['GET'])
def check_uid():
    uid = request.args.get('uid')
    user_key = request.args.get('key')
    user_ip = get_client_ip()
    user_agent_raw = request.headers.get('User-Agent', '')
    parsed_agent = parse_user_agent(user_agent_raw)

    # 🛑 1. গ্লোবাল IP ব্যান চেক ফিল্টার
    ban_record = banned_ips_collection.find_one({"ip": user_ip})
    if ban_record:
        expiry_limit = ban_record.get("ban_expiry", "PERMANENT")
        if expiry_limit != "PERMANENT":
            try:
                exp_time = datetime.datetime.strptime(expiry_limit, '%Y-%m-%d %H:%M:%S')
                if datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) > exp_time:
                    # ব্যানের মেয়াদ শেষ, অটো রিলিজ
                    banned_ips_collection.delete_one({"ip": user_ip})
                    ban_record = None
            except: pass
            
        if ban_record:
            return jsonify({
                "error": True, 
                "message": "You are banned from accessing this API Matrix Node!",
                "ban_expiry": expiry_limit
            }), 403

    # ট্র্যাকিং ও হিস্ট্রি অ্যাড
    if user_key:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + " UTC"
        keys_collection.update_one(
            {"key": user_key}, 
            {"$set": {"last_used": now_str, "last_agent": parsed_agent}}
        )
        # হিস্ট্রি ডাটাবেসে সেভ
        ip_history_collection.insert_one({
            "key": user_key,
            "ip": user_ip,
            "agent": parsed_agent,
            "timestamp": now_str
        })

    if not uid or not user_key:
        return jsonify({"error": True, "message": "Missing uid or key parameter"}), 400

    key_data = keys_collection.find_one({"key": user_key})
    if not key_data:
        return jsonify({"error": True, "message": f"Your key '{user_key}' is not valid"}), 401

    if not key_data.get("is_active", True):
        return jsonify({"error": True, "message": f"Your access key '{user_key}' has been paused or temporarily suspended by admin"}), 403

    expiry_time_str = key_data.get("expires_at")
    if expiry_time_str and expiry_time_str != "UNLIMITED":
        try:
            expiry_time = datetime.datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S')
            if datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) > expiry_time:
                return jsonify({"error": True, "message": f"Your key '{user_key}' has expired"}), 401
        except Exception: pass 

    if key_data.get("ip_locked"):
        current_locked_ip = key_data.get("locked_ip")
        if not current_locked_ip:
            keys_collection.update_one({"key": user_key}, {"$set": {"locked_ip": user_ip}})
            current_locked_ip = user_ip
        if user_ip != current_locked_ip:
            return jsonify({"error": True, "message": "You are not whitelisted! IP mismatch."}), 403

    try:
        response = requests.get(f"{TARGET_URL}?uid={uid}&key=great", timeout=60)
        api_res = response.json()
    except Exception:
        return jsonify({"error": True, "message": "Main API took too long to respond or is down"}), 500

    if isinstance(api_res, dict):
        api_res.pop("credit", None)
        custom_credit = {
            "developer": "BENJA HEX",
            "discord": "https://discord.gg/TKdd5GNhxq",
            "youtube": "https://youtube.com/@benjahexofficial?si=DVyAs57DGUBe7jw7"
        }
        api_res = {**{"credit": custom_credit}, **api_res}

    return jsonify(api_res), response.status_code

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') in ADMIN_PASSWORDS:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid Password!"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def home():
    return redirect(url_for('login'))
