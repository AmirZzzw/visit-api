import sys
import os
import json
import base64
import time
import asyncio
import aiohttp
import requests
from datetime import datetime

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
    print(f"❌ Failed to import byte: {e}")
    def encrypt_api(data):
        return "00000000000000000000000000000000"
    def Encrypt_ID(data):
        return "0000000000000000"

try:
    from AccountPersonalShow_pb2 import AccountPersonalShowInfo
    print("✅ AccountPersonalShow_pb2 imported")
except ImportError as e:
    print(f"⚠️ Failed to import protobuf: {e}")
    AccountPersonalShowInfo = None

# ========== ایجاد Flask App ==========
from flask import Flask, jsonify

app = Flask(__name__)

# ========== تنظیمات ==========
GITHUB_TOKEN_URL = "https://raw.githubusercontent.com/AmirZzzw/info-api/main/jwt.json"
TOKEN_CACHE_TTL = 300

# ========== Cache ==========
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
        response = requests.get(GITHUB_TOKEN_URL, timeout=15)
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

async def visit(session, token_info, uid, data):
    url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    headers = {
        "Authorization": f"Bearer {token_info['token']}",
        "User-Agent": "Dalvik/2.1.0",
        "Content-Type": "application/octet-stream",
        "ReleaseVersion": "OB51",
        "X-GA": "v1 1"
    }
    
    try:
        async with session.post(url, headers=headers, data=data, timeout=5, ssl=False) as resp:
            return resp.status == 200
    except:
        return False

async def send_visits_for_tokens(tokens, uid, visit_count):
    success = 0
    fail = 0
    
    try:
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        print(f"🔐 Encrypted UID {uid}")
    except Exception as e:
        print(f"❌ Encryption error: {e}")
        return {"success": 0, "fail": visit_count, "error": str(e)}
    
    async with aiohttp.ClientSession() as session:
        print(f"🚀 Sending {visit_count} visits...")
        
        for i in range(visit_count):
            token = tokens[i % len(tokens)]
            
            if await visit(session, token, uid, data):
                success += 1
            else:
                fail += 1
            
            if i < visit_count - 1:
                await asyncio.sleep(0.5)
            
            if (i + 1) % 20 == 0:
                print(f"   Progress: {i+1}/{visit_count}")
    
    return {"success": success, "fail": fail}

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    return jsonify({
        "service": "Free Fire Visit API",
        "version": "2.0",
        "endpoints": [
            "/<server>/<uid>/<count>",
            "/health",
            "/stats",
            "/test/<index>",
            "/refresh"
        ]
    })

@app.route('/health')
def health():
    tokens = get_cached_tokens()
    return jsonify({
        "status": "healthy",
        "tokens_available": len(tokens) > 0,
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
        "regions": region_counts
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
        return jsonify({"error": "Invalid"}), 400
    
    token = tokens[index-1]
    return jsonify({
        "index": index,
        "region": token["actual_region"],
        "token_preview": token["token"][:30] + "..."
    })

@app.route('/<server>/<int:uid>/<int:count>')
def send_visits(server, uid, count):
    print(f"🎯 Request: {server}/{uid}/{count}")
    
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({"error": "No tokens"}), 500
    
    if count <= 0 or count > 500:
        return jsonify({"error": "Invalid count"}), 400
    
    try:
        start = time.time()
        result = asyncio.run(send_visits_for_tokens(tokens, uid, count))
        end = time.time()
        
        response = {
            "status": "completed",
            "target": uid,
            "requested": count,
            "successful": result["success"],
            "failed": result["fail"],
            "success_rate": round((result["success"] / count * 100), 2) if count > 0 else 0,
            "time": round(end - start, 2)
        }
        
        if "error" in result:
            response["warning"] = result["error"]
        
        print(f"📊 Results: {result['success']}/{count} successful")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/<server>/<int:uid>')
def single_visit(server, uid):
    return send_visits(server, uid, 1)

# ========== VERCEL HANDLER ==========
# این تابع الزامی برای Vercel است
def handler(request, context):
    """Vercel serverless handler"""
    from flask import request as flask_request
    
    # ارسال درخواست به Flask app
    with app.request_context(flask_request.environ):
        try:
            response = app.full_dispatch_request()
            return {
                'statusCode': response.status_code,
                'headers': dict(response.headers),
                'body': response.get_data(as_text=True)
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }

# ========== اجرای محلی ==========
if __name__ == "__main__":
    print("🔥 Free Fire API (Local)")
    print("📡 Tokens from GitHub")
    print("🌐 http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
