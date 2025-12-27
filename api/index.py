import sys
import os
import json
import base64
import time
import uuid
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from queue import Queue
import atexit

# ========== تنظیم مسیرها ==========
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
lib_dir = os.path.join(parent_dir, 'lib')

sys.path.insert(0, parent_dir)
sys.path.insert(0, lib_dir)

# ========== Import کتابخانه‌ها ==========
try:
    from byte import encrypt_api, Encrypt_ID
    print("✅ byte.py imported")
except ImportError as e:
    print(f"⚠️ byte.py import failed: {e}")
    def encrypt_api(data):
        return "00000000000000000000000000000000"
    def Encrypt_ID(data):
        return "0000000000000000"

# ========== Flask App ==========
app = Flask(__name__)

# ========== تنظیمات ==========
GITHUB_TOKEN_URL = "https://raw.githubusercontent.com/AmirZzzw/info-api/main/jwt.json"
TOKEN_CACHE_TTL = 300
MAX_VISITS = 500  # حداکثر 500 بازدید

# ========== سیستم Job ==========
JOBS = {}  # ذخیره نتایج jobs
JOB_QUEUE = Queue()  # صف jobs
WORKER_THREAD = None

# ========== Cache توکن‌ها ==========
TOKEN_CACHE = {
    "tokens": [],
    "timestamp": 0,
    "is_valid": False
}

# ========== توابع کمکی ==========
def decode_jwt(token):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {"region": "UNKNOWN"}
        
        payload = parts[1]
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)
        
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except:
        return {"region": "UNKNOWN"}

def load_tokens_from_github():
    try:
        print("📥 Fetching tokens from GitHub...")
        response = requests.get(GITHUB_TOKEN_URL, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        all_tokens = []
        
        for item in data:
            token = item.get("token", "")
            if token and token not in ["", "N/A"]:
                decoded = decode_jwt(token)
                actual_region = decoded.get('lock_region', 'SG') or decoded.get('noti_region', 'SG')
                
                all_tokens.append({
                    "token": token,
                    "actual_region": actual_region.upper() if actual_region else "SG"
                })
        
        print(f"✅ Loaded {len(all_tokens)} tokens")
        
        TOKEN_CACHE["tokens"] = all_tokens
        TOKEN_CACHE["timestamp"] = time.time()
        TOKEN_CACHE["is_valid"] = True
        
        return all_tokens
        
    except Exception as e:
        print(f"❌ Error loading from GitHub: {e}")
        if TOKEN_CACHE["is_valid"] and TOKEN_CACHE["tokens"]:
            print("⚠️ Using cached tokens")
            return TOKEN_CACHE["tokens"]
        return []

def get_cached_tokens():
    now = time.time()
    
    if (TOKEN_CACHE["is_valid"] and 
        TOKEN_CACHE["tokens"] and 
        (now - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL):
        return TOKEN_CACHE["tokens"]
    
    return load_tokens_from_github()

def send_single_visit(token_info, uid, encrypted_data):
    """ارسال یک بازدید"""
    url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    headers = {
        "Authorization": f"Bearer {token_info['token']}",
        "User-Agent": "Dalvik/2.1.0",
        "Content-Type": "application/octet-stream",
        "ReleaseVersion": "OB51",
        "X-GA": "v1 1"
    }
    
    try:
        response = requests.post(url, headers=headers, data=encrypted_data, 
                               timeout=3, verify=False)
        return response.status_code == 200
    except:
        return False

def process_visits(job_id, server, uid, count):
    """پردازش بازدیدها در background"""
    print(f"🎯 Processing job {job_id}: {server}/{uid}/{count}")
    
    tokens = get_cached_tokens()
    if not tokens:
        JOBS[job_id] = {
            "status": "failed",
            "error": "No tokens available",
            "completed_at": datetime.now().isoformat()
        }
        return
    
    try:
        # رمزگذاری UID
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        start_time = time.time()
        
        print(f"🚀 Sending {count} visits for job {job_id}")
        
        for i in range(count):
            token = tokens[i % len(tokens)]
            
            if send_single_visit(token, uid, data):
                success += 1
            else:
                fail += 1
            
            # تاخیر 0.5 ثانیه
            if i < count - 1:
                time.sleep(0.5)
            
            # آپدیت progress هر 10 تا
            if (i + 1) % 10 == 0:
                progress = (i + 1) / count * 100
                JOBS[job_id]["progress"] = round(progress, 1)
                print(f"   Job {job_id}: {i+1}/{count} ({progress:.1f}%)")
        
        end_time = time.time()
        execution_time = round(end_time - start_time, 2)
        success_rate = round((success / count * 100), 2) if count > 0 else 0
        
        JOBS[job_id] = {
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": success_rate,
            "execution_time": execution_time,
            "started_at": datetime.fromtimestamp(start_time).isoformat(),
            "completed_at": datetime.fromtimestamp(end_time).isoformat(),
            "processing_time": execution_time
        }
        
        print(f"✅ Job {job_id} completed: {success}/{count} successful")
        
    except Exception as e:
        JOBS[job_id] = {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        }
        print(f"❌ Job {job_id} failed: {e}")

def worker():
    """Worker thread برای پردازش jobs"""
    while True:
        try:
            job_data = JOB_QUEUE.get()
            if job_data is None:  # سیگنال توقف
                break
                
            job_id, server, uid, count = job_data
            process_visits(job_id, server, uid, count)
            JOB_QUEUE.task_done()
            
        except Exception as e:
            print(f"❌ Worker error: {e}")
            time.sleep(1)

# ========== شروع Worker Thread ==========
def start_worker():
    """شروع worker thread"""
    global WORKER_THREAD
    if WORKER_THREAD is None or not WORKER_THREAD.is_alive():
        WORKER_THREAD = threading.Thread(target=worker, daemon=True)
        WORKER_THREAD.start()
        print("👷 Worker thread started")

def stop_worker():
    """توقف worker thread"""
    JOB_QUEUE.put(None)
    print("🛑 Worker thread stopped")

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "3.0 (Background Jobs)",
        "max_visits": MAX_VISITS,
        "endpoints": {
            "create_job": "POST /<server>/<uid>/<count>",
            "get_results": "GET /results/<job_id>",
            "health": "GET /health",
            "stats": "GET /stats",
            "test": "GET /test/<index>",
            "refresh": "GET /refresh"
        },
        "note": "Uses background processing to avoid timeout"
    })

@app.route('/health')
def health():
    tokens = get_cached_tokens()
    worker_alive = WORKER_THREAD is not None and WORKER_THREAD.is_alive()
    
    return jsonify({
        "status": "healthy",
        "tokens_available": len(tokens) > 0,
        "worker_running": worker_alive,
        "queue_size": JOB_QUEUE.qsize(),
        "active_jobs": len([j for j in JOBS.values() if j.get("status") == "processing"]),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/stats')
def stats():
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 400
    
    region_counts = {}
    for token in tokens:
        region = token["actual_region"]
        region_counts[region] = region_counts.get(region, 0) + 1
    
    return jsonify({
        "total_tokens": len(tokens),
        "regions": region_counts,
        "jobs": {
            "total": len(JOBS),
            "completed": len([j for j in JOBS.values() if j.get("status") == "completed"]),
            "processing": len([j for j in JOBS.values() if j.get("status") == "processing"]),
            "failed": len([j for j in JOBS.values() if j.get("status") == "failed"])
        }
    })

@app.route('/refresh')
def refresh_tokens():
    tokens = load_tokens_from_github()
    return jsonify({
        "refreshed": len(tokens),
        "status": "success" if tokens else "error"
    })

@app.route('/test/<int:index>')
def test_token(index):
    tokens = get_cached_tokens()
    if not tokens or index < 1 or index > len(tokens):
        return jsonify({"error": "Invalid index"}), 400
    
    token = tokens[index-1]
    return jsonify({
        "index": index,
        "region": token["actual_region"],
        "token_preview": token["token"][:30] + "..."
    })

# ========== سیستم Job ==========

@app.route('/<server>/<int:uid>/<int:count>', methods=['POST', 'GET'])
def create_visit_job(server, uid, count):
    """ایجاد job جدید برای پردازش بازدیدها"""
    
    # برای GET هم پشتیبانی کن
    if request.method == 'GET':
        count = min(count, MAX_VISITS)
    
    if count <= 0:
        return jsonify({"error": "Count must be positive"}), 400
    
    if count > MAX_VISITS:
        return jsonify({
            "error": f"Maximum {MAX_VISITS} visits allowed",
            "requested": count,
            "allowed": MAX_VISITS
        }), 400
    
    # ایجاد job ID
    job_id = str(uuid.uuid4())[:8]
    
    # ذخیره job اولیه
    JOBS[job_id] = {
        "status": "processing",
        "server": server.upper(),
        "target": uid,
        "requested": count,
        "created_at": datetime.now().isoformat(),
        "progress": 0
    }
    
    # اضافه کردن به صف
    JOB_QUEUE.put((job_id, server, uid, count))
    
    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Job created and queued for processing",
        "check_results": f"/results/{job_id}",
        "estimated_time": f"{(count * 0.5):.1f} seconds",
        "queue_position": JOB_QUEUE.qsize(),
        "created_at": datetime.now().isoformat()
    })

@app.route('/results/<job_id>')
def get_job_results(job_id):
    """دریافت نتایج job"""
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job_data = JOBS[job_id]
    
    # اگر در حال پردازش هست، progress رو برگردون
    if job_data.get("status") == "processing":
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "progress": job_data.get("progress", 0),
            "estimated_remaining": "calculating...",
            "last_updated": datetime.now().isoformat()
        })
    
    # اگر تموم شده، نتایج کامل رو برگردون
    return jsonify(job_data)

@app.route('/jobs')
def list_jobs():
    """لیست همه jobs"""
    job_list = []
    for job_id, job_data in list(JOBS.items())[-20:]:  # آخرین 20 job
        job_list.append({
            "job_id": job_id,
            "status": job_data.get("status"),
            "server": job_data.get("server"),
            "target": job_data.get("target"),
            "requested": job_data.get("requested"),
            "created_at": job_data.get("created_at")
        })
    
    return jsonify({
        "total_jobs": len(JOBS),
        "recent_jobs": job_list
    })

# ========== اجرای سریع (بدون queue) برای تعداد کم ==========
@app.route('/quick/<server>/<int:uid>/<int:count>')
def quick_visit(server, uid, count):
    """اجرای سریع برای تعداد کم (کمتر از 10)"""
    if count > 10:
        return jsonify({
            "error": "Use POST method for more than 10 visits",
            "max_quick": 10,
            "alternative": "POST /<server>/<uid>/<count>"
        }), 400
    
    # اجرای مستقیم
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({"error": "No tokens available"}), 500
    
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        start = time.time()
        
        for i in range(count):
            token = tokens[i % len(tokens)]
            if send_single_visit(token, uid, data):
                success += 1
            else:
                fail += 1
            
            if i < count - 1:
                time.sleep(0.5)
        
        end = time.time()
        
        return jsonify({
            "status": "completed",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success / count * 100), 2),
            "execution_time": round(end - start, 2),
            "timestamp": int(time.time()),
            "mode": "quick"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== شروع برنامه ==========
if __name__ == "__main__":
    print("🔥 Free Fire API v3.0 (Background Jobs)")
    print(f"📡 Max visits per job: {MAX_VISITS}")
    print(f"📡 Tokens from: {GITHUB_TOKEN_URL}")
    
    # شروع worker
    start_worker()
    
    # بارگذاری توکن‌ها
    load_tokens_from_github()
    
    print("🌐 Server: http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
    
else:
    # روی Vercel
    print("🚀 Starting on Vercel with background jobs...")
    start_worker()
    load_tokens_from_github()
