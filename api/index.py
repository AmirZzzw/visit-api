import sys
import os
import json
import base64
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
import concurrent.futures

# ========== تنظیم مسیرها ==========
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
lib_dir = os.path.join(parent_dir, 'lib')

sys.path.insert(0, parent_dir)
sys.path.insert(0, lib_dir)

# ========== Import ==========
try:
    from byte import encrypt_api, Encrypt_ID
    print("✅ byte.py imported")
except:
    def encrypt_api(data): return "dummy"
    def Encrypt_ID(data): return "dummy"

app = Flask(__name__)
GITHUB_TOKEN_URL = "https://raw.githubusercontent.com/AmirZzzw/info-api/main/jwt.json"

# ========== Cache ==========
TOKEN_CACHE = {"tokens": [], "timestamp": 0}

def load_tokens():
    try:
        response = requests.get(GITHUB_TOKEN_URL, timeout=10)
        tokens_data = response.json()
        
        tokens = []
        for item in tokens_data:
            token = item.get("token", "")
            if token:
                tokens.append({"token": token})
        
        TOKEN_CACHE["tokens"] = tokens
        TOKEN_CACHE["timestamp"] = time.time()
        return tokens
    except:
        return TOKEN_CACHE["tokens"] if TOKEN_CACHE["timestamp"] > 0 else []

def send_visit_no_delay(token, uid, encrypted_data):
    """درخواست بدون تاخیر اضافه"""
    try:
        url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
        headers = {
            "Authorization": f"Bearer {token['token']}",
            "User-Agent": "Dalvik/2.1.0",
            "Content-Type": "application/octet-stream",
            "ReleaseVersion": "OB51",
            "X-GA": "v1 1"
        }
        response = requests.post(url, headers=headers, data=encrypted_data, 
                               timeout=1.5, verify=False)
        return response.status_code == 200
    except:
        return False

# ========== ENDPOINT عادی ==========

@app.route('/<server>/<int:uid>/<int:count>')
def normal_visits(server, uid, count):
    """عادی - واقع‌بینانه"""
    print(f"🎯 Request: {server}/{uid}/{count}")
    
    if count <= 0 or count > 8:  # حداکثر 8
        return jsonify({
            "error": "1-8 visits per normal request",
            "reason": "Vercel 10s timeout + Free Fire 1.6s per request",
            "suggestion": "Use /parallel/... or multiple requests"
        }), 400
    
    tokens = load_tokens()
    if not tokens:
