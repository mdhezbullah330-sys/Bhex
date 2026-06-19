from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import requests
import pymongo
from datetime import datetime, timedelta

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = "super_secret_session_encryption_key_999"

# MongoDB Connection
MONGO_URI = "mongodb://benja:hex@ac-4jxadv5-shard-00-00.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-01.2rtfrua.mongodb.net:27017,ac-4jxadv5-shard-00-02.2rtfrua.mongodb.net:27017/?ssl=true&replicaSet=atlas-11c2ax-shard-0&authSource=admin&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["my_api_db"]
keys_collection = db["api_keys"]

TARGET_URL = "http://raw.thug4ff.xyz/check"
ADMIN_PASSWORD = "1nonly_talha"

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    msg = None
    msg_type = "success"

    if request.method == 'POST':
        new_key = request.form.get('key_name')
        days = request.form.get('expiry_days', type=int)

        if new_key and days:
            expiry_date = datetime.utcnow() + timedelta(days=days)
            keys_collection.update_one(
                {"key": new_key},
                {"$set": {"key": new_key, "expires_at": expiry_date}},
                upsert=True
            )
            msg = f"Key '{new_key}' successfully added for {days} days!"
        else:
            msg = "Please fill all fields properly."
            msg_type = "danger"

    all_keys = list(keys_collection.find({}, {"_id": 0}))
    return render_template('dashboard.html', msg=msg, msg_type=msg_type, keys=all_keys)

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

    if not uid or not user_key:
        return jsonify({"error": True, "message": "Missing uid or key parameter"}), 400

    key_data = keys_collection.find_one({"key": user_key})
    if not key_data:
        return jsonify({"error": True, "message": f"Your key '{user_key}' is not valid"}), 401

    expiry_time = key_data.get("expires_at")
    if expiry_time and datetime.utcnow() > expiry_time:
        return jsonify({"error": True, "message": f"Your key '{user_key}' has expired"}), 401

    try:
        response = requests.get(f"{TARGET_URL}?uid={uid}&key=great", timeout=60)
        api_res = response.json()
    except Exception:
        return jsonify({"error": True, "message": "API is unreachable"}), 500

    if isinstance(api_res, dict):
        api_res.pop("credit", None)

    return jsonify(api_res), response.status_code

@app.route('/')
def home():
    return redirect(url_for('login'))