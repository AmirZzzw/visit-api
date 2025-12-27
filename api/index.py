# api/index.py - نسخه فوری
import sys
import os
import json
import base64
import time
import requests
from datetime import datetime
from flask import Flask, jsonify

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
        print("📥 Loading tokens...")
        response = requests.get(GITHUB_TOKEN_URL, timeout=10)
        tokens_data = response.json()
        
        tokens = []
        for item in tokens_data:
            token = item.get("token", "")
            if token:
                tokens.append({"token": token, "region": "SG"})
        
        print(f"✅ {len(tokens)} tokens loaded")
        TOKEN_CACHE["tokens"] = tokens
        TOKEN_CACHE["timestamp"] = time.time()
        return tokens
    except Exception as e:
        print(f"❌ Error: {e}")
        return TOKEN_CACHE["tokens"] if TOKEN_CACHE["timestamp"] > 0 else []

def send_visit_fast(token, uid):
    """درخواست بسیار سریع"""
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
        headers = {
            "Authorization": f"Bearer {token['token']}",
            "User-Agent": "Dalvik/2.1.0",
            "Content-Type": "application/octet-stream",
            "ReleaseVersion": "OB51",
            "X-GA": "v1 1"
        }
        
        # timeout خیلی کوتاه
        response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
        return response.status_code == 200
    except:
        return False

# ========== ENDPOINT اصلی ==========

@app.route('/<server>/<int:uid>/<int:count>')
def send_visits(server, uid, count):
    """Endpoint اصلی - بهینه شده برای Vercel"""
    print(f"🎯 Request: {server}/{uid}/{count}")
    
    # محدودیت
    if count <= 0 or count > 30:  # کاهش به 30
        return jsonify({"error": "Count must be 1-30"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        success = 0
        fail = 0
        start = time.time()
        
        print(f"🚀 Sending {count} visits (optimized)...")
        
        for i in range(count):
            token = tokens[i % len(tokens)]
            
            # اگر از 8 ثانیه گذشت، قطع کن
            if time.time() - start > 8:
                print("⚠️ Timeout protection")
                fail += (count - i)
                break
            
            if send_visit_fast(token, uid):
                success += 1
            else:
                fail += 1
            
            # تاخیر کمتر برای سرعت بیشتر
            if i < count - 1:
                time.sleep(0.3)  # 0.3 ثانیه
        
        end = time.time()
        exec_time = round(end - start, 2)
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success/count*100), 2),
            "execution_time": exec_time,
            "timestamp": int(time.time()),
            "optimized": True
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    print("🔥 Free Fire API (Optimized for Vercel)")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
