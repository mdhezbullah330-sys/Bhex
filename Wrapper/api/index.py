from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import requests
import pymongo
import datetime

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = "super_secret_session_encryption_key_999"

# MongoDB Connection
MONGO_URI = "mongodb://benja:hex@ac-4jxadv5-shard-00-00.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-01.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-02.2rtfrua.mongodb.net:27017/?ssl=true&replicaSet=atlas-11c2ax-shard-0&authSource=admin&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["my_api_db"]
keys_collection = db["api_keys"]

TARGET_URL = "http://raw.thug4ff.xyz/check"
ADMIN_PASSWORD = "1nonly_talha"

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    msg = None
    msg_type = "success"

    if request.method == 'POST':
        try:
            new_key = request.form.get('key_name', '').strip()
            days = request.form.get('expiry_days', type=int)
            
            ip_locked = True if request.form.get('ip_locked') == 'on' else False
            manual_ip = request.form.get('manual_ip', '').strip()

            if new_key and days:
                # 🛑 চেক করা হচ্ছে কী-টি অলরেডি ডাটাবেসে আছে কিনা
                existing_key = keys_collection.find_one({"key": new_key})
                if existing_key:
                    msg = f"Error: The key '{new_key}' already exists in the database!"
                    msg_type = "danger"
                else:
                    expiry_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
                    expiry_str = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
                    
                    key_data = {
                        "key": str(new_key), 
                        "expires_at": str(expiry_str),
                        "ip_locked": bool(ip_locked),
                        "locked_ip": manual_ip if manual_ip else None,
                        "last_used": None
                    }
                    
                    keys_collection.insert_one(key_data)
                    msg = f"Key '{new_key}' successfully deployed for {days} days!"
            else:
                msg = "Please fill all fields properly."
                msg_type = "danger"
        except Exception as e:
            msg = f"Backend Error: {str(e)}"
            msg_type = "danger"

    try:
        all_keys = list(keys_collection.find({}, {"_id": 0}))
        return render_template('dashboard.html', msg=msg, msg_type=msg_type, keys=all_keys)
    except Exception as e:
        return f"Template Error: {str(e)}"

@app.route('/delete_key/<string:key_name>', methods=['POST'])
def delete_key(key_name):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    keys_collection.delete_one({"key": key_name})
    return redirect(url_for('dashboard'))

@app.route('/reset_ip/<string:key_name>', methods=['POST'])
def reset_ip(key_name):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    keys_collection.update_one({"key": key_name}, {"$set": {"locked_ip": None}})
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid Password! Try again."
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/check', methods=['GET'])
def check_uid():
    uid = request.args.get('uid')
    user_key = request.args.get('key')
    user_ip = get_client_ip()

    # ⏱️ ডাইনামিক ইউজ ট্র্যাকিং (রিকোয়েস্ট আসা মাত্রই টাইম সবসময় আপডেট হবে)
    if user_key:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + " UTC"
        keys_collection.update_one({"key": user_key}, {"$set": {"last_used": now_str}})

    if not uid or not user_key:
        return jsonify({"error": True, "message": "Missing uid or key parameter"}), 400

    key_data = keys_collection.find_one({"key": user_key})
    if not key_data:
        return jsonify({"error": True, "message": f"Your key '{user_key}' is not valid"}), 401

    expiry_time_str = key_data.get("expires_at")
    if expiry_time_str:
        try:
            expiry_time = datetime.datetime.strptime(expiry_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
            if datetime.datetime.now(datetime.timezone.utc) > expiry_time:
                return jsonify({"error": True, "message": f"Your key '{user_key}' has expired"}), 401
        except Exception:
            pass 

    # 🛡️ IP লক চেকিং
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

@app.route('/')
def home():
    return redirect(url_for('login'))
