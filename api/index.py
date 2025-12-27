import sys
import os
import json
import base64
import time
import uuid
import requests
from datetime import datetime
from flask import Flask, jsonify
import subprocess
import threading

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

# ========== Storage درون‌حافظه (موقت) ==========
# روی Vercel این data از بین می‌ره، ولی برای jobهای کوتاه‌مدت کار می‌کنه
JOBS_STORE = {}

# ========== Cache ==========
TOKEN_CACHE = {"tokens": [], "timestamp": 0}

def load_tokens():
    """بارگذاری توکن‌ها"""
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

def process_visit_batch_sync(job_id, server, uid, total_count):
    """پردازش همزمان کل batch - روی همان request"""
    print(f"🎯 Processing {total_count} visits for job {job_id}")
    
    tokens = load_tokens()
    if not tokens:
        JOBS_STORE[job_id] = {"status": "failed", "error": "No tokens"}
        return
    
    # تنظیم وضعیت
    JOBS_STORE[job_id] = {
        "status": "processing",
        "server": server.upper(),
        "target": uid,
        "total": total_count,
        "processed": 0,
        "success": 0,
        "fail": 0,
        "started_at": datetime.now().isoformat(),
        "progress": 0
    }
    
    try:
        # آماده‌سازی داده
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        start_time = time.time()
        
        # TRICK: پردازش در chunkهای کوچک با timeout protection
        CHUNK_SIZE = 5
        chunks = (total_count + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        for chunk_idx in range(chunks):
            # محاسبه سایز chunk
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min((chunk_idx + 1) * CHUNK_SIZE, total_count)
            chunk_size = chunk_end - chunk_start
            
            # اگر از 8 ثانیه گذشت، partial جواب بده
            if time.time() - start_time > 8:
                print(f"⚠️ Timeout protection at {chunk_start}/{total_count}")
                JOBS_STORE[job_id] = {
                    "status": "partial",
                    "server": server.upper(),
                    "target": uid,
                    "total": total_count,
                    "processed": chunk_start,
                    "success": success,
                    "fail": fail,
                    "success_rate": round((success / chunk_start * 100), 2) if chunk_start > 0 else 0,
                    "execution_time": round(time.time() - start_time, 2),
                    "remaining": total_count - chunk_start,
                    "completed_at": datetime.now().isoformat()
                }
                return
            
            # پردازش chunk
            for i in range(chunk_size):
                token_idx = (chunk_start + i) % len(tokens)
                token = tokens[token_idx]
                
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
                
                # تاخیر بسیار کم
                if i < chunk_size - 1:
                    time.sleep(0.05)
            
            # آپدیت progress
            processed = chunk_end
            progress = (processed / total_count) * 100
            
            JOBS_STORE[job_id]["processed"] = processed
            JOBS_STORE[job_id]["success"] = success
            JOBS_STORE[job_id]["fail"] = fail
            JOBS_STORE[job_id]["progress"] = round(progress, 1)
            
            # تاخیر بین chunkها
            if chunk_idx < chunks - 1:
                time.sleep(0.1)
        
        # اگر همه انجام شد
        end_time = time.time()
        total_time = end_time - start_time
        
        JOBS_STORE[job_id] = {
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "total": total_count,
            "processed": total_count,
            "success": success,
            "fail": fail,
            "success_rate": round((success / total_count * 100), 2),
            "execution_time": round(total_time, 2),
            "avg_time_per_visit": round(total_time / total_count, 3),
            "started_at": JOBS_STORE[job_id]["started_at"],
            "completed_at": datetime.now().isoformat(),
            "performance": "good" if total_time < 5 else "slow"
        }
        
        print(f"✅ Job {job_id} completed: {success}/{total_count}")
        
    except Exception as e:
        JOBS_STORE[job_id] = {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        }

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "ULTIMATE",
        "methods": {
            "normal": "GET /<server>/<uid>/<count> (1-30)",
            "mass": "GET /mass/<server>/<uid>/<count> (1-1000)",
            "results": "GET /results/<job_id>",
            "health": "GET /health"
        }
    })

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "active_jobs": len([j for j in JOBS_STORE.values() if j.get("status") in ["processing", "partial"]]),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/<server>/<int:uid>/<int:count>')
def normal_visits(server, uid, count):
    """عادی - تا 30"""
    if count <= 0 or count > 30:
        return jsonify({"error": "1-30 visits"}), 400
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        start = time.time()
        
        for i in range(count):
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
            "success_rate": round((success / count * 100), 2),
            "time": round(end - start, 2),
            "method": "normal"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mass/<server>/<int:uid>/<int:count>')
def mass_visits(server, uid, count):
    """Mass - تا 1000 (با timeout protection)"""
    if count <= 0 or count > 1000:
        return jsonify({"error": "1-1000 visits"}), 400
    
    # ایجاد job ID
    job_id = str(uuid.uuid4())[:8]
    
    # ذخیره اولیه
    JOBS_STORE[job_id] = {
        "status": "created",
        "server": server.upper(),
        "target": uid,
        "total": count,
        "created_at": datetime.now().isoformat()
    }
    
    # اجرای همزمان در thread جدا
    try:
        thread = threading.Thread(
            target=process_visit_batch_sync,
            args=(job_id, server, uid, count),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "message": f"Processing {count} visits",
            "check_results": f"https://visit-api-pi.vercel.app/results/{job_id}",
            "estimated_max_time": f"{(count * 0.1):.1f} seconds",
            "note": "Large batches may be partially completed due to Vercel timeout"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/results/<job_id>')
def get_results(job_id):
    """دریافت نتایج"""
    if job_id not in JOBS_STORE:
        return jsonify({"error": "Job not found"}), 404
    
    job_data = JOBS_STORE[job_id]
    
    # اگر در حال پردازش است
    if job_data.get("status") == "processing":
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "progress": job_data.get("progress", 0),
            "processed": job_data.get("processed", 0),
            "total": job_data.get("total", 0),
            "success_so_far": job_data.get("success", 0),
            "fail_so_far": job_data.get("fail", 0),
            "started_at": job_data.get("started_at"),
            "last_updated": datetime.now().isoformat()
        })
    
    # اگر partial است (بعضی انجام شد)
    elif job_data.get("status") == "partial":
        return jsonify({
            "job_id": job_id,
            "status": "partial",
            "message": "Partially completed due to timeout",
            "total": job_data["total"],
            "processed": job_data["processed"],
            "successful": job_data["success"],
            "failed": job_data["fail"],
            "success_rate": job_data["success_rate"],
            "remaining": job_data["remaining"],
            "execution_time": job_data["execution_time"],
            "completed_at": job_data["completed_at"],
            "note": "Use multiple smaller requests for remaining visits"
        })
    
    # اگر تموم شده یا failed
    return jsonify(job_data)

# ========== اجرا ==========
if __name__ == "__main__":
    print("🔥 FREE FIRE ULTIMATE API")
    print("🚀 Mass visit support (1-1000)")
    print("⚠️ Large batches may be partially completed")
    print("🌐 http://localhost:8080")
    
    app.run(host="0.0.0.0", port=8080, debug=False)
