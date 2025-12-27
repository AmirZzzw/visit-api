import sys
import os
import json
import base64
import time
import uuid
import requests
from datetime import datetime
from flask import Flask, jsonify, request
import threading
from queue import Queue
import atexit

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

# ========== سیستم Job ==========
JOBS = {}
ACTIVE_JOBS = {}
JOB_QUEUE = Queue()
WORKERS = []
MAX_CONCURRENT_JOBS = 3

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
                tokens.append({"token": token, "region": "SG"})
        
        TOKEN_CACHE["tokens"] = tokens
        TOKEN_CACHE["timestamp"] = time.time()
        return tokens
    except:
        return TOKEN_CACHE["tokens"] if TOKEN_CACHE["timestamp"] > 0 else []

# ========== Worker System ==========

def process_chunk(job_id, chunk_id, server, uid, chunk_size, tokens):
    """پردازش یک chunk"""
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        success = 0
        fail = 0
        
        for i in range(chunk_size):
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
            
            # NO DELAY - فقط یکم sleep برای جلوگیری از rate limit
            if i % 10 == 0 and i < chunk_size - 1:
                time.sleep(0.05)
        
        return {
            "chunk_id": chunk_id,
            "success": success,
            "fail": fail,
            "completed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "chunk_id": chunk_id,
            "success": 0,
            "fail": chunk_size,
            "error": str(e)
        }

def worker_process_job(job_id, server, uid, total_count):
    """Worker برای پردازش کامل job"""
    print(f"👷 Worker starting job {job_id}: {total_count} visits")
    
    tokens = load_tokens()
    if not tokens:
        JOBS[job_id] = {"status": "failed", "error": "No tokens"}
        return
    
    # تنظیم job
    JOBS[job_id] = {
        "status": "processing",
        "server": server,
        "target": uid,
        "total": total_count,
        "chunks_completed": 0,
        "chunks_total": 0,
        "success": 0,
        "fail": 0,
        "started_at": datetime.now().isoformat()
    }
    
    # تقسیم به chunkهای 10 تایی
    CHUNK_SIZE = 10
    chunks = []
    remaining = total_count
    
    while remaining > 0:
        chunk_size = min(CHUNK_SIZE, remaining)
        chunks.append(chunk_size)
        remaining -= chunk_size
    
    JOBS[job_id]["chunks_total"] = len(chunks)
    
    # پردازش chunkها
    all_results = []
    
    for idx, chunk_size in enumerate(chunks):
        chunk_id = f"{job_id}_chunk_{idx}"
        
        # پردازش chunk
        result = process_chunk(job_id, chunk_id, server, uid, chunk_size, tokens)
        all_results.append(result)
        
        # آپدیت progress
        JOBS[job_id]["chunks_completed"] = idx + 1
        JOBS[job_id]["success"] += result["success"]
        JOBS[job_id]["fail"] += result["fail"]
        
        # Progress هر 10 chunk
        if (idx + 1) % 10 == 0:
            progress = ((idx + 1) / len(chunks)) * 100
            print(f"   Job {job_id}: {progress:.1f}% ({idx+1}/{len(chunks)} chunks)")
        
        # تاخیر خیلی کم بین chunkها
        if idx < len(chunks) - 1:
            time.sleep(0.1)
    
    # تکمیل job
    total_success = sum(r["success"] for r in all_results)
    total_fail = sum(r["fail"] for r in all_results)
    
    JOBS[job_id] = {
        "status": "completed",
        "server": server.upper(),
        "target": uid,
        "total": total_count,
        "success": total_success,
        "fail": total_fail,
        "success_rate": round((total_success / total_count * 100), 2),
        "started_at": JOBS[job_id]["started_at"],
        "completed_at": datetime.now().isoformat(),
        "chunk_results": all_results[:5],  # فقط 5 تا نشون بده
        "processing_time": "auto_calculated"
    }
    
    print(f"✅ Job {job_id} completed: {total_success}/{total_count}")
    
    # حذف از active jobs
    if job_id in ACTIVE_JOBS:
        del ACTIVE_JOBS[job_id]

def worker():
    """Worker اصلی"""
    while True:
        try:
            job_data = JOB_QUEUE.get()
            if job_data is None:
                break
                
            job_id, server, uid, count = job_data
            
            # اگر تعداد jobهای فعال زیاد نیست
            if len(ACTIVE_JOBS) < MAX_CONCURRENT_JOBS:
                ACTIVE_JOBS[job_id] = True
                
                # اجرای job در thread جدید
                thread = threading.Thread(
                    target=worker_process_job,
                    args=(job_id, server, uid, count),
                    daemon=True
                )
                thread.start()
                
                # اجازه بدیم thread ادامه بده (non-blocking)
                time.sleep(0.1)
                
            else:
                # برگردون به صف
                JOB_QUEUE.put(job_data)
                time.sleep(1)
                
            JOB_QUEUE.task_done()
            
        except Exception as e:
            print(f"❌ Worker error: {e}")
            time.sleep(1)

def start_workers():
    """شروع workers"""
    # یک worker شروع کن
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    WORKERS.append(worker_thread)
    print("👷 Worker started")

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Mass Visit API",
        "version": "ULTRA",
        "max_visits": "UNLIMITED (1000+)",
        "methods": {
            "quick": "GET /quick/<server>/<uid>/<count> (max 50)",
            "batch": "POST /batch/<server>/<uid>/<count> (1000+)",
            "results": "GET /results/<job_id>",
            "jobs": "GET /jobs"
        }
    })

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "workers": len(WORKERS),
        "queue_size": JOB_QUEUE.qsize(),
        "active_jobs": len(ACTIVE_JOBS),
        "completed_jobs": len([j for j in JOBS.values() if j.get("status") == "completed"])
    })

@app.route('/quick/<server>/<int:uid>/<int:count>')
def quick_visits(server, uid, count):
    """سریع - تا 50"""
    if count <= 0 or count > 50:
        return jsonify({"error": "Max 50 for quick method"}), 400
    
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
                time.sleep(0.2)
        
        end = time.time()
        
        return jsonify({
            "status": "completed",
            "method": "quick",
            "server": server.upper(),
            "target": uid,
            "requested": count,
            "successful": success,
            "failed": fail,
            "success_rate": round((success / count * 100), 2),
            "time": round(end - start, 2)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/batch/<server>/<int:uid>/<int:count>', methods=['POST', 'GET'])
def batch_visits(server, uid, count):
    """Batch - 1000+ visits"""
    
    # محدودیت منطقی
    if count <= 0:
        return jsonify({"error": "Count must be positive"}), 400
    
    if count > 10000:  # حداکثر 10000
        return jsonify({"error": "Max 10000 visits"}), 400
    
    # ایجاد job ID
    job_id = str(uuid.uuid4())[:8]
    
    # ذخیره اولیه
    JOBS[job_id] = {
        "status": "queued",
        "server": server.upper(),
        "target": uid,
        "total": count,
        "created_at": datetime.now().isoformat(),
        "queue_position": JOB_QUEUE.qsize() + 1
    }
    
    # اضافه به صف
    JOB_QUEUE.put((job_id, server, uid, count))
    
    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": f"Job created for {count} visits",
        "check_results": f"https://visit-api-pi.vercel.app/results/{job_id}",
        "queue_position": JOB_QUEUE.qsize(),
        "estimated_time": f"{(count * 0.1):.1f} seconds",
        "note": "Results available in 30-60 seconds"
    })

@app.route('/results/<job_id>')
def get_results(job_id):
    """دریافت نتایج job"""
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job_data = JOBS[job_id]
    
    # اگر در حال پردازش است
    if job_data.get("status") == "processing":
        chunks_completed = job_data.get("chunks_completed", 0)
        chunks_total = job_data.get("chunks_total", 1)
        progress = (chunks_completed / chunks_total * 100) if chunks_total > 0 else 0
        
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "progress": round(progress, 1),
            "chunks_completed": chunks_completed,
            "chunks_total": chunks_total,
            "success_so_far": job_data.get("success", 0),
            "fail_so_far": job_data.get("fail", 0),
            "estimated_remaining": f"{((100 - progress) * 0.1):.1f}%",
            "last_updated": datetime.now().isoformat()
        })
    
    # اگر در صف است
    elif job_data.get("status") == "queued":
        return jsonify({
            "job_id": job_id,
            "status": "queued",
            "queue_position": job_data.get("queue_position", "unknown"),
            "created_at": job_data.get("created_at"),
            "message": "Waiting in queue"
        })
    
    # اگر تموم شده
    return jsonify(job_data)

@app.route('/jobs')
def list_jobs():
    """لیست jobs"""
    recent_jobs = []
    for job_id, job_data in sorted(
        JOBS.items(), 
        key=lambda x: x[1].get("created_at", ""), 
        reverse=True
    )[:20]:
        recent_jobs.append({
            "job_id": job_id,
            "status": job_data.get("status"),
            "server": job_data.get("server"),
            "target": job_data.get("target"),
            "total": job_data.get("total"),
            "created_at": job_data.get("created_at")
        })
    
    return jsonify({
        "total_jobs": len(JOBS),
        "recent_jobs": recent_jobs
    })

# ========== شروع ==========
if __name__ == "__main__":
    print("🔥 FREE FIRE ULTRA API")
    print("🚀 Supports 1000+ visits")
    print("👷 Starting worker...")
    
    start_workers()
    load_tokens()
    
    print("🌐 Server: http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
    
else:
    # روی Vercel
    print("🚀 Starting on Vercel...")
    start_workers()
    load_tokens()
