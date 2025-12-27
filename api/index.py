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

# ========== ENDPOINT هوشمند ==========

@app.route('/<server>/<int:uid>/<int:count>')
def send_visits(server, uid, count):
    """همه‌کاره - تا 500 در یک request"""
    print(f"🎯 Request: {server}/{uid}/{count}")
    
    # محدودیت منطقی
    if count <= 0:
        return jsonify({"error": "Count must be positive"}), 400
    
    if count > 500:
        return jsonify({
            "error": "Max 500 visits per request",
            "suggestion": "Split into multiple requests"
        }), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens available"}), 500
    
    try:
        # زمان شروع
        start_time = time.time()
        
        # آماده‌سازی داده
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        print(f"🚀 Starting {count} visits...")
        
        success = 0
        fail = 0
        
        # محاسبه delay بر اساس تعداد
        if count <= 50:
            delay = 0.3  # برای تعداد کم
        elif count <= 150:
            delay = 0.15  # برای تعداد متوسط
        else:
            delay = 0.05  # برای تعداد زیاد
        
        # پردازش
        for i in range(count):
            # اگر از 9 ثانیه گذشت، فوراً جواب بده
            elapsed = time.time() - start_time
            if elapsed > 9:
                print(f"⚠️ Vercel timeout protection at {i}/{count}")
                
                return jsonify({
                    "status": "completed",
                    "note": "TIMEOUT PROTECTION - Partial results",
                    "server": server.upper(),
                    "target": uid,
                    "requested": count,
                    "processed": i,
                    "successful": success,
                    "failed": fail,
                    "success_rate": round((success / i * 100), 2) if i > 0 else 0,
                    "execution_time": round(elapsed, 2),
                    "timestamp": int(time.time()),
                    "remaining": count - i,
                    "strategy": f"auto-delay={delay}"
                })
            
            token = tokens[i % len(tokens)]
            
            try:
                url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
                headers = {
                    "Authorization": f"Bearer {token['token']}",
                    "User-Agent": "Dalvik/2.1.0",
                    "Content-Type": "application/octet-stream",
                    "ReleaseVersion": "OB51",
                    "X-GA": "v1 1"
                }
                response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
                if response.status_code == 200:
                    success += 1
                else:
                    fail += 1
            except:
                fail += 1
            
            # تاخیر
            if i < count - 1:
                time.sleep(delay)
        
        # اگر همه انجام شد
        end_time = time.time()
        total_time = end_time - start_time
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success / count * 100), 2),
            "execution_time": round(total_time, 2),
            "timestamp": int(time.time()),
            "avg_time_per_visit": round(total_time / count, 3) if count > 0 else 0,
            "strategy": f"auto-delay={delay}",
            "performance": "excellent" if total_time < 5 else "good" if total_time < 9 else "slow"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mass/<server>/<int:uid>/<int:count>')
def mass_visits(server, uid, count):
    """Alias برای backward compatibility"""
    return send_visits(server, uid, count)

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "max_visits_per_request": 500,
        "strategy": "auto-delay based on count",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "FINAL",
        "endpoint": "GET /<server>/<uid>/<count>",
        "max_visits": 500,
        "features": [
            "Auto-delay adjustment",
            "Timeout protection (9s cutoff)",
            "Partial results on timeout",
            "Uses real Free Fire tokens"
        ]
    })

if __name__ == "__main__":
    print("🔥 FREE FIRE API - FINAL VERSION")
    print("🚀 Auto-delay system (0.05s - 0.3s)")
    print("🛡️ 9s timeout protection")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
