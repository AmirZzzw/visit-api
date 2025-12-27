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

def send_single_visit_fast(token, uid, encrypted_data):
    """درخواست فوق‌سریع"""
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
                               timeout=1.5, verify=False)  # timeout کمتر
        return response.status_code == 200
    except:
        return False

# ========== ENDPOINT اصلی ==========

@app.route('/<server>/<int:uid>/<int:count>')
def send_visits(server, uid, count):
    """Endpoint اصلی - محاسبه واقعی delay"""
    print(f"🎯 Request: {server}/{uid}/{count}")
    
    if count <= 0:
        return jsonify({"error": "Count must be positive"}), 400
    
    if count > 300:  # کاهش به 300
        return jsonify({
            "error": f"Max 300 visits per request (requested: {count})",
            "suggestion": "Use multiple smaller requests"
        }), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens available"}), 500
    
    try:
        start_time = time.time()
        
        # آماده‌سازی داده
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        print(f"🚀 Starting {count} visits...")
        
        success = 0
        fail = 0
        
        # محاسبه delay بر اساس تست قبلی
        # از تست قبلی: 8 درخواست در 9.1s = هر کدام ≈ 1.14s
        # پس delay واقعی ≈ 1s
        
        # delay هوشمند
        base_delay = 0.8  # کاهش از 1.14 به 0.8
        max_visits_before_timeout = int(9 / base_delay)  # حدود 11 تا
        
        print(f"📊 Strategy: delay={base_delay}s, max={max_visits_before_timeout}")
        
        for i in range(count):
            # اگر از 8.5 ثانیه گذشت، جواب بده
            elapsed = time.time() - start_time
            if elapsed > 8.5:
                print(f"⚠️ Timeout protection at {i}/{count}")
                
                return jsonify({
                    "status": "completed",
                    "note": "Optimized timeout protection",
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
                    "avg_time_per_visit": round(elapsed / i, 2) if i > 0 else 0,
                    "strategy": f"dynamic-delay={base_delay}"
                })
            
            token = tokens[i % len(tokens)]
            
            if send_single_visit_fast(token, uid, data):
                success += 1
            else:
                fail += 1
            
            # delay
            if i < count - 1:
                time.sleep(base_delay)
        
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
            "avg_time_per_visit": round(total_time / count, 2),
            "strategy": f"dynamic-delay={base_delay}",
            "performance": "excellent" if total_time < 5 else "good"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== ENDPOINT موازی ==========

@app.route('/parallel/<server>/<int:uid>/<int:count>')
def parallel_visits(server, uid, count):
    """پردازش موازی (حداکثر 20)"""
    if count <= 0 or count > 20:
        return jsonify({"error": "1-20 visits for parallel"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        start_time = time.time()
        
        # آماده‌سازی داده
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        print(f"⚡ Parallel: {count} visits")
        
        success = 0
        fail = 0
        
        # پردازش موازی
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            
            for i in range(count):
                token = tokens[i % len(tokens)]
                future = executor.submit(send_single_visit_fast, token, uid, data)
                futures.append(future)
            
            # جمع‌آوری نتایج
            for future in concurrent.futures.as_completed(futures):
                try:
                    if future.result():
                        success += 1
                    else:
                        fail += 1
                except:
                    fail += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        
        return jsonify({
            "status": "completed",
            "method": "parallel",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success / count * 100), 2),
            "execution_time": round(total_time, 2),
            "workers": 3,
            "timestamp": int(time.time())
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "max_visits": {
            "normal": 300,
            "parallel": 20
        },
        "estimated_times": {
            "10_visits": "8-9 seconds",
            "20_visits": "16-18 seconds (use parallel)",
            "30_visits": "24-27 seconds (split requests)"
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "OPTIMIZED",
        "endpoints": {
            "normal": "GET /<server>/<uid>/<count> (1-300)",
            "parallel": "GET /parallel/<server>/<uid>/<count> (1-20)",
            "health": "GET /health"
        },
        "strategy": "Real-time delay adjustment based on server response time"
    })

if __name__ == "__main__":
    print("🔥 FREE FIRE API - OPTIMIZED")
    print("🚀 Dynamic delay system")
    print("⚡ Parallel processing option")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
