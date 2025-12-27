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

# ========== Progress System ==========
PROGRESS_STORE = {}  # job_id -> progress data
ACTIVE_JOBS = set()

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

def send_visit_chunk(tokens, uid, chunk_start, chunk_end):
    """ارسال یک chunk از بازدیدها"""
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        chunk_success = 0
        chunk_fail = 0
        
        for i in range(chunk_start, chunk_end):
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
                    chunk_success += 1
                else:
                    chunk_fail += 1
            except:
                chunk_fail += 1
            
            # تاخیر بسیار کم داخل chunk
            if i < chunk_end - 1:
                time.sleep(0.05)
        
        return {"success": chunk_success, "fail": chunk_fail}
        
    except Exception as e:
        return {"success": 0, "fail": chunk_end - chunk_start, "error": str(e)}

def process_large_batch(job_id, server, uid, total_count):
    """پردازش batch بزرگ در chunkهای 5 تایی"""
    print(f"🚀 Processing job {job_id}: {total_count} visits")
    
    tokens = load_tokens()
    if not tokens:
        PROGRESS_STORE[job_id] = {
            "status": "failed",
            "error": "No tokens available",
            "created_at": datetime.now().isoformat()
        }
        return
    
    # بروزرسانی وضعیت به "processing"
    PROGRESS_STORE[job_id]["status"] = "processing"
    PROGRESS_STORE[job_id]["started_at"] = datetime.now().isoformat()
    PROGRESS_STORE[job_id]["last_update"] = datetime.now().isoformat()
    
    # تنظیم progress اولیه
    PROGRESS_STORE[job_id].update({
        "server": server.upper(),
        "target": uid,
        "total": total_count,
        "completed": 0,
        "success": 0,
        "fail": 0,
        "current_chunk": 0,
        "total_chunks": (total_count + 4) // 5,  # chunkهای 5 تایی
    })
    
    # پردازش chunkهای 5 تایی
    CHUNK_SIZE = 5
    
    for chunk_num in range(0, total_count, CHUNK_SIZE):
        chunk_start = chunk_num
        chunk_end = min(chunk_num + CHUNK_SIZE, total_count)
        
        # پردازش chunk
        chunk_result = send_visit_chunk(tokens, uid, chunk_start, chunk_end)
        
        # آپدیت progress
        PROGRESS_STORE[job_id]["completed"] = chunk_end
        PROGRESS_STORE[job_id]["success"] += chunk_result["success"]
        PROGRESS_STORE[job_id]["fail"] += chunk_result["fail"]
        PROGRESS_STORE[job_id]["current_chunk"] = chunk_num // CHUNK_SIZE + 1
        PROGRESS_STORE[job_id]["last_update"] = datetime.now().isoformat()
        
        # progress هر 10 chunk
        if (chunk_num // CHUNK_SIZE + 1) % 10 == 0:
            progress = (chunk_end / total_count) * 100
            print(f"   Job {job_id}: {progress:.1f}% ({chunk_end}/{total_count})")
        
        # تاخیر بین chunkها
        if chunk_end < total_count:
            time.sleep(0.2)  # 0.2 ثانیه بین chunkها
    
    # تکمیل job
    PROGRESS_STORE[job_id] = {
        "status": "completed",
        "server": server.upper(),
        "target": uid,
        "total": total_count,
        "success": PROGRESS_STORE[job_id]["success"],
        "fail": PROGRESS_STORE[job_id]["fail"],
        "success_rate": round((PROGRESS_STORE[job_id]["success"] / total_count * 100), 2),
        "started_at": PROGRESS_STORE[job_id]["started_at"],
        "completed_at": datetime.now().isoformat(),
        "chunk_size": CHUNK_SIZE,
        "total_chunks": PROGRESS_STORE[job_id]["total_chunks"],
        "job_id": job_id
    }
    
    print(f"✅ Job {job_id} completed")
    ACTIVE_JOBS.discard(job_id)

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "PROGRESS SYSTEM",
        "endpoints": {
            "progress": "POST /progress/<server>/<uid>/<count> (1-1000+)",
            "status": "GET /status/<job_id>",
            "quick": "GET /<server>/<uid>/<count> (1-8)",
            "health": "GET /health",
            "cleanup": "GET /cleanup",
            "jobs": "GET /jobs"
        }
    })

@app.route('/health')
def health():
    tokens = load_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "tokens": len(tokens),
        "active_jobs": len(ACTIVE_JOBS),
        "completed_jobs": len([j for j in PROGRESS_STORE.values() if j.get("status") == "completed"]),
        "queued_jobs": len([j for j in PROGRESS_STORE.values() if j.get("status") == "queued"]),
        "processing_jobs": len([j for j in PROGRESS_STORE.values() if j.get("status") == "processing"]),
        "chunk_size": 5,
        "max_per_request": 1000
    })

@app.route('/<server>/<int:uid>/<int:count>')
def quick_visits(server, uid, count):
    """سریع - تا 8"""
    if count <= 0 or count > 8:
        return jsonify({
            "error": "1-8 visits for quick method",
            "use_progress": "Use /progress/... for larger requests"
        }), 400
    
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
                time.sleep(0.05)
        
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

@app.route('/progress/<server>/<int:uid>/<int:count>', methods=['POST', 'GET'])
def progress_visits(server, uid, count):
    """Progress System - 5 تا 5 تا می‌زنه"""
    if count <= 0 or count > 1000:
        return jsonify({"error": "1-1000 visits"}), 400
    
    # ایجاد job ID
    job_id = str(uuid.uuid4())[:8]
    
    # ذخیره اولیه
    PROGRESS_STORE[job_id] = {
        "status": "queued",
        "server": server.upper(),
        "target": uid,
        "total": count,
        "job_id": job_id,
        "created_at": datetime.now().isoformat()
    }
    
    ACTIVE_JOBS.add(job_id)
    
    # شروع پردازش در background thread
    try:
        thread = threading.Thread(
            target=process_large_batch,
            args=(job_id, server, uid, count),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "started",
            "message": f"Processing {count} visits in chunks of 5",
            "check_progress": f"https://visit-api-pi.vercel.app/status/{job_id}",
            "check_progress_local": f"/status/{job_id}",
            "total_chunks": (count + 4) // 5,
            "estimated_time": f"{(count * 0.35):.1f} seconds",
            "created_at": datetime.now().isoformat(),
            "note": "Job will continue processing even if this request ends"
        })
        
    except Exception as e:
        PROGRESS_STORE[job_id]["status"] = "failed"
        PROGRESS_STORE[job_id]["error"] = str(e)
        return jsonify({"error": str(e)}), 500

@app.route('/status/<job_id>')
def get_job_status(job_id):
    """بررسی status و progress"""
    if job_id not in PROGRESS_STORE:
        return jsonify({"error": "Job not found"}), 404
    
    job_data = PROGRESS_STORE[job_id]
    
    if job_data.get("status") == "processing":
        completed = job_data.get("completed", 0)
        total = job_data.get("total", 1)
        progress = (completed / total) * 100
        
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "progress": round(progress, 1),
            "completed": completed,
            "total": total,
            "success_so_far": job_data.get("success", 0),
            "fail_so_far": job_data.get("fail", 0),
            "current_chunk": job_data.get("current_chunk", 0),
            "total_chunks": job_data.get("total_chunks", 0),
            "started_at": job_data.get("started_at"),
            "last_update": job_data.get("last_update"),
            "estimated_remaining_chunks": job_data.get("total_chunks", 0) - job_data.get("current_chunk", 0),
            "estimated_remaining_time": f"{(job_data.get('total_chunks', 0) - job_data.get('current_chunk', 0)) * 0.35:.1f} seconds"
        })
    
    elif job_data.get("status") == "queued":
        return jsonify({
            "job_id": job_id,
            "status": "queued",
            "message": "Job is in queue, will start soon",
            "created_at": job_data.get("created_at"),
            "position_in_queue": len([j for j in PROGRESS_STORE.values() if j.get("status") == "queued"])
        })
    
    # اگر completed یا failed
    response = dict(job_data)
    if job_data.get("status") == "completed":
        response["success_rate"] = f"{response.get('success_rate', 0)}%"
        response["estimated_time_used"] = f"{(response.get('total', 0) * 0.35):.1f} seconds"
    
    return jsonify(response)

@app.route('/jobs')
def list_all_jobs():
    """لیست همه jobs"""
    jobs_list = []
    for job_id, job_data in PROGRESS_STORE.items():
        jobs_list.append({
            "job_id": job_id,
            "status": job_data.get("status"),
            "target": job_data.get("target"),
            "total": job_data.get("total"),
            "progress": f"{job_data.get('completed', 0)}/{job_data.get('total', 0)}" if job_data.get("status") == "processing" else "N/A",
            "created_at": job_data.get("created_at", job_data.get("started_at")),
            "last_update": job_data.get("last_update", "N/A")
        })
    
    jobs_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return jsonify({
        "total_jobs": len(PROGRESS_STORE),
        "jobs": jobs_list[:20]  # آخرین 20 تا
    })

# ========== Cleanup ==========
@app.route('/cleanup')
def cleanup_old_jobs():
    """پاک کردن jobs قدیمی"""
    now = time.time()
    old_jobs = []
    
    for job_id in list(PROGRESS_STORE.keys()):
        job_data = PROGRESS_STORE[job_id]
        created_time = job_data.get("created_at") or job_data.get("started_at")
        
        # اگر بیشتر از 1 ساعت گذشته
        if created_time:
            try:
                created_dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                if (datetime.now() - created_dt).total_seconds() > 3600:
                    old_jobs.append(job_id)
            except:
                pass
    
    cleaned_count = 0
    for job_id in old_jobs:
        if job_id in PROGRESS_STORE:
            del PROGRESS_STORE[job_id]
            ACTIVE_JOBS.discard(job_id)
            cleaned_count += 1
    
    return jsonify({
        "cleaned": cleaned_count,
        "remaining": len(PROGRESS_STORE),
        "active_jobs": len(ACTIVE_JOBS)
    })

if __name__ == "__main__":
    print("🔥 FREE FIRE PROGRESS API")
    print("🚀 Chunk System (5 visits per chunk)")
    print("📊 Real-time progress tracking")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080)
