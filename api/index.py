import sys
import os
import json
import base64
import time
import requests
import concurrent.futures
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

def send_visit_parallel(token, uid, encrypted_data):
    """درخواست موازی"""
    try:
        url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
        headers = {
            "Authorization": f"Bearer {token['token']}",
            "User-Agent": "Dalvik/2.1.0",
            "Content-Type": "application/octet-stream",
            "ReleaseVersion": "OB51",
            "X-GA": "v1 1"
        }
        
        response = requests.post(url, headers=headers, data=encrypted_data, timeout=3, verify=False)
        return response.status_code == 200
    except:
        return False

def process_batch(tokens, uid, batch_size, batch_num, total_batches):
    """پردازش یک batch"""
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        
        print(f"   Batch {batch_num}/{total_batches}: {batch_size} visits")
        
        for i in range(batch_size):
            token = tokens[i % len(tokens)]
            if send_visit_parallel(token, uid, data):
                success += 1
            else:
                fail += 1
            
            # تاخیر کمتر داخل batch
            if i < batch_size - 1:
                time.sleep(0.2)  # فقط 0.2 ثانیه
        
        return {"success": success, "fail": fail, "batch": batch_num}
        
    except Exception as e:
        return {"success": 0, "fail": batch_size, "batch": batch_num, "error": str(e)}

# ========== ENDPOINT‌های جدید ==========

@app.route('/batch/<server>/<int:uid>/<int:total>')
def batch_send_visits(server, uid, total):
    """سیستم Batch - برای تعداد بالا"""
    print(f"🎯 BATCH Request: {server}/{uid}/{total}")
    
    if total <= 0 or total > 200:  # تا 200
        return jsonify({"error": "Count must be 1-200"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        start_total = time.time()
        
        # محاسبه batchها
        BATCH_SIZE = 10  # هر batch 10 تا
        num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE  # تقسیم به batchهای 10 تایی
        
        print(f"📦 Processing {total} visits in {num_batches} batches of {BATCH_SIZE}")
        
        total_success = 0
        total_fail = 0
        batch_results = []
        
        # پردازش batchها به صورت سریالی (اما داخل هر batch سریع)
        for batch_num in range(num_batches):
            batch_start = time.time()
            
            # محاسبه سایز batch آخر
            current_batch_size = BATCH_SIZE
            if batch_num == num_batches - 1:  # batch آخر
                current_batch_size = total - (batch_num * BATCH_SIZE)
            
            # اگر از 8 ثانیه گذشت، قطع کن
            if time.time() - start_total > 8:
                print("⚠️ Total timeout protection")
                # بقیه رو به عنوان fail حساب کن
                remaining = total - (batch_num * BATCH_SIZE)
                total_fail += remaining
                break
            
            # پردازش batch
            result = process_batch(tokens, uid, current_batch_size, batch_num + 1, num_batches)
            total_success += result["success"]
            total_fail += result["fail"]
            batch_results.append(result)
            
            batch_time = time.time() - batch_start
            print(f"   ✓ Batch {batch_num + 1} completed in {batch_time:.1f}s")
            
            # تاخیر بین batchها
            if batch_num < num_batches - 1:
                time.sleep(0.5)  # تاخیر بین batchها
        
        end_total = time.time()
        total_time = round(end_total - start_total, 2)
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "total_requested": total,
            "total_successful": total_success,
            "total_failed": total_fail,
            "success_rate": round((total_success / total * 100), 2) if total > 0 else 0,
            "total_time": total_time,
            "batch_size": BATCH_SIZE,
            "num_batches": num_batches,
            "batch_results": batch_results,
            "timestamp": int(time.time()),
            "method": "batch_processing"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/parallel/<server>/<int:uid>/<int:count>')
def parallel_send_visits(server, uid, count):
    """Parallel Processing - حداکثر سرعت"""
    print(f"⚡ PARALLEL Request: {server}/{uid}/{count}")
    
    if count <= 0 or count > 50:  # محدود برای parallel
        return jsonify({"error": "Count must be 1-50 for parallel"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        start = time.time()
        
        # آماده‌سازی داده
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        print(f"⚡ Sending {count} visits in parallel...")
        
        success = 0
        fail = 0
        
        # Parallel با ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            
            for i in range(count):
                token = tokens[i % len(tokens)]
                future = executor.submit(send_visit_parallel, token, uid, data)
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
        
        end = time.time()
        exec_time = round(end - start, 2)
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success / count * 100), 2),
            "execution_time": exec_time,
            "method": "parallel",
            "workers": 5,
            "timestamp": int(time.time())
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<server>/<int:uid>/<int:count>')
def normal_send_visits(server, uid, count):
    """روش عادی - برای تعداد کم"""
    print(f"🎯 NORMAL Request: {server}/{uid}/{count}")
    
    if count <= 0 or count > 30:
        return jsonify({"error": "Count must be 1-30"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        success = 0
        fail = 0
        start = time.time()
        
        for i in range(count):
            token = tokens[i % len(tokens)]
            
            if time.time() - start > 8:
                print("⚠️ Timeout protection")
                fail += (count - i)
                break
            
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
                
                response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
                if response.status_code == 200:
                    success += 1
                else:
                    fail += 1
            except:
                fail += 1
            
            if i < count - 1:
                time.sleep(0.3)
        
        end = time.time()
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success/count*100), 2),
            "execution_time": round(end - start, 2),
            "timestamp": int(time.time()),
            "method": "normal"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "methods": [
            "GET /<server>/<uid>/<count> - Normal (max 30)",
            "GET /batch/<server>/<uid>/<count> - Batch (max 200)",
            "GET /parallel/<server>/<uid>/<count> - Parallel (max 50)"
        ],
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    print("🔥 Free Fire API v4.0 (Multi-Method)")
    print("📡 Methods: Normal, Batch, Parallel")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
