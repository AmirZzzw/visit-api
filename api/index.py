import sys
import os
import json
import base64
import time
import asyncio
import aiohttp
import requests
from datetime import datetime
from flask import Flask, jsonify

# ========== تنظیم مسیرها ==========
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
lib_dir = os.path.join(parent_dir, 'lib')

sys.path.insert(0, parent_dir)
sys.path.insert(0, lib_dir)

print("=" * 60)
print("🚀 Free Fire API Starting...")
print(f"📁 Current Dir: {current_dir}")
print(f"📂 Lib Dir: {lib_dir}")
print(f"🔧 Python Path: {sys.path}")
print("=" * 60)

# ========== Import کتابخانه‌ها ==========
try:
    from byte import encrypt_api, Encrypt_ID
    print("✅ byte.py imported successfully")
except ImportError as e:
    print(f"❌ Failed to import byte: {e}")
    # ساخت توابع جایگزین
    def encrypt_api(data):
        return "00000000000000000000000000000000"
    
    def Encrypt_ID(data):
        return "0000000000000000"

try:
    from AccountPersonalShow_pb2 import AccountPersonalShowInfo
    print("✅ AccountPersonalShow_pb2 imported successfully")
except ImportError as e:
    print(f"⚠️ Failed to import protobuf: {e}")
    AccountPersonalShowInfo = None

# ========== ایجاد Flask App ==========
app = Flask(__name__)

# ========== تنظیمات ==========
GITHUB_TOKEN_URL = "https://raw.githubusercontent.com/AmirZzzw/info-api/main/jwt.json"
TOKEN_CACHE_TTL = 300  # 5 دقیقه

# ========== Cache ==========
TOKEN_CACHE = {
    "tokens": [],
    "timestamp": 0,
    "is_valid": False
}

# ========== توابع کمکی ==========
def decode_jwt(token):
    """Decode JWT token to get region"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {"region": "UNKNOWN"}
        
        payload = parts[1]
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)
        
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        return data
    except:
        return {"region": "UNKNOWN"}

def load_tokens_from_github():
    """Load tokens from GitHub raw URL"""
    try:
        print(f"[{datetime.now()}] 📥 Fetching tokens from GitHub...")
        response = requests.get(GITHUB_TOKEN_URL, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        all_tokens = []
        
        for item in data:
            token = item.get("token", "")
            if token and token not in ["", "N/A"]:
                decoded = decode_jwt(token)
                actual_region = decoded.get('lock_region', 'SG')
                if not actual_region:
                    actual_region = decoded.get('noti_region', 'SG')
                
                all_tokens.append({
                    "token": token,
                    "actual_region": actual_region.upper() if actual_region else "SG",
                    "account_id": decoded.get('account_id', 'N/A'),
                    "nickname": decoded.get('nickname', 'N/A')[:20]
                })
        
        print(f"[{datetime.now()}] ✅ Loaded {len(all_tokens)} tokens from GitHub")
        
        # نمایش خلاصه
        region_counts = {}
        for t in all_tokens:
            region = t["actual_region"]
            region_counts[region] = region_counts.get(region, 0) + 1
        
        print(f"\n📊 TOKEN SUMMARY:")
        print(f"   Total tokens: {len(all_tokens)}")
        for region, count in region_counts.items():
            print(f"   {region}: {count} tokens")
        
        # Update cache
        TOKEN_CACHE["tokens"] = all_tokens
        TOKEN_CACHE["timestamp"] = time.time()
        TOKEN_CACHE["is_valid"] = True
        
        return all_tokens
        
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] ❌ Network error: {e}")
        # Fallback to cache if available
        if TOKEN_CACHE["is_valid"] and TOKEN_CACHE["tokens"]:
            print(f"[{datetime.now()}] ⚠️ Using cached tokens")
            return TOKEN_CACHE["tokens"]
        return []
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Error loading from GitHub: {e}")
        return []

def get_cached_tokens():
    """Get tokens with cache mechanism"""
    now = time.time()
    
    # اگر cache معتبر است و منقضی نشده
    if (TOKEN_CACHE["is_valid"] and 
        TOKEN_CACHE["tokens"] and 
        (now - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL):
        return TOKEN_CACHE["tokens"]
    
    # در غیر این صورت از GitHub بارگذاری کن
    return load_tokens_from_github()

def get_url_by_region(region):
    """Get endpoint URL based on token region"""
    region = region.upper()
    return "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"

async def visit(session, token_info, uid, data, token_index, visit_number):
    token = token_info["token"]
    region = token_info["actual_region"]
    url = get_url_by_region(region)
    
    headers = {
        "ReleaseVersion": "OB51",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": url.replace("https://", "").split("/")[0],
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; SM-G973F Build/RP1A.200720.012)",
        "Content-Type": "application/octet-stream",
        "Expect": "100-continue",
        "X-Unity-Version": "2022.3.47f1",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    
    try:
        async with session.post(url, headers=headers, data=data, ssl=False, timeout=10) as resp:
            if resp.status == 200:
                return True, resp.status, region
            else:
                return False, resp.status, region
    except Exception as e:
        return False, str(e), region

async def send_visits_for_tokens(tokens, uid, visit_count):
    """Send multiple visits using available tokens in rotation WITH DELAY"""
    connector = aiohttp.TCPConnector(limit=0, ssl=False)
    
    total_success = 0
    total_fail = 0
    results_by_region = {}
    
    try:
        # رمزگذاری UID (یکبار برای همه)
        encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
        data = bytes.fromhex(encrypted)
        
        print(f"🔐 Encrypted data for UID {uid}: {encrypted[:30]}...")
    except Exception as e:
        print(f"❌ Encryption error: {e}")
        return {
            "total_requests": 0,
            "successful_visits": 0,
            "failed_visits": visit_count,
            "success_rate": 0,
            "results_by_region": {},
            "tokens_used": 0,
            "error": str(e)
        }
    
    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"\n🚀 Sending {visit_count} visits using {len(tokens)} tokens...")
        print(f"   Each token will be used approximately {visit_count // len(tokens)} times")
        print(f"   ⏳ Delay between visits: 0.5 seconds")
        
        # ارسال درخواست‌ها به صورت سریالی با تاخیر
        for i in range(visit_count):
            token_index = i % len(tokens)  # چرخش بین توکن‌ها
            token_info = tokens[token_index]
            
            # شماره درخواست
            visit_number = i + 1
            
            if visit_number % 20 == 0:
                print(f"   📤 Visit {visit_number}/{visit_count}: Token {token_index + 1} ({token_info['actual_region']})")
            
            try:
                success, status, region = await visit(session, token_info, uid, data, token_index + 1, visit_number)
                
                if success:
                    total_success += 1
                    if region not in results_by_region:
                        results_by_region[region] = {"success": 0, "fail": 0}
                    results_by_region[region]["success"] += 1
                else:
                    total_fail += 1
                    if region not in results_by_region:
                        results_by_region[region] = {"success": 0, "fail": 0}
                    results_by_region[region]["fail"] += 1
                    
            except Exception as e:
                total_fail += 1
                print(f"      ❌ Error at visit {visit_number}: {str(e)[:50]}")
            
            # نمایش progress
            if visit_number % 50 == 0 or visit_number == visit_count:
                print(f"   📊 Progress: {visit_number}/{visit_count} | Success: {total_success} | Fail: {total_fail}")
            
            # تاخیر ۰.۵ ثانیه بین درخواست‌ها (به جز آخرین درخواست)
            if visit_number < visit_count:
                await asyncio.sleep(0.5)
    
    success_rate = (total_success / visit_count * 100) if visit_count > 0 else 0
    return {
        "total_requests": visit_count,
        "successful_visits": total_success,
        "failed_visits": total_fail,
        "success_rate": success_rate,
        "results_by_region": results_by_region,
        "tokens_used": len(tokens),
    }

# ========== ENDPOINT ها ==========

@app.route('/')
def home():
    """صفحه اصلی"""
    return jsonify({
        "service": "Free Fire Mass Visit API",
        "version": "2.0",
        "description": "Send visits to Free Fire profiles",
        "github_source": GITHUB_TOKEN_URL,
        "endpoints": {
            "send_visits": "/<server>/<uid>/<count>",
            "health_check": "/health",
            "token_stats": "/stats",
            "refresh_tokens": "/refresh",
            "test_token": "/test/<index>"
        },
        "example": "/IND/4285785816/50"
    })

@app.route('/health')
def health():
    """بررسی سلامت سرویس"""
    tokens = get_cached_tokens()
    return jsonify({
        "status": "healthy" if tokens else "degraded",
        "timestamp": datetime.now().isoformat(),
        "tokens": {
            "available": len(tokens) > 0,
            "count": len(tokens),
            "cache_age": int(time.time() - TOKEN_CACHE["timestamp"])
        },
        "service": "Free Fire Visit API"
    })

@app.route('/stats')
def stats():
    """آمار توکن‌ها"""
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({"error": "No tokens available"}), 400
    
    region_counts = {}
    for token in tokens:
        region = token["actual_region"]
        region_counts[region] = region_counts.get(region, 0) + 1
    
    return jsonify({
        "total_tokens": len(tokens),
        "tokens_by_region": region_counts,
        "cache_info": {
            "is_valid": TOKEN_CACHE["is_valid"],
            "timestamp": TOKEN_CACHE["timestamp"],
            "age_seconds": int(time.time() - TOKEN_CACHE["timestamp"])
        }
    })

@app.route('/refresh')
def refresh_tokens():
    """بارگذاری مجدد توکن‌ها از GitHub"""
    print(f"🔄 Force refreshing tokens from GitHub...")
    tokens = load_tokens_from_github()
    
    if tokens:
        return jsonify({
            "status": "success",
            "message": f"Refreshed {len(tokens)} tokens",
            "cache_updated": True
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to refresh tokens"
        }), 500

@app.route('/test/<int:index>')
def test_token(index):
    """تست یک توکن خاص"""
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({"error": "No tokens available"}), 400
    
    if index < 1 or index > len(tokens):
        return jsonify({"error": f"Invalid index. Valid range: 1-{len(tokens)}"}), 400
    
    token_info = tokens[index-1]
    decoded = decode_jwt(token_info["token"])
    
    return jsonify({
        "token_index": index,
        "total_tokens": len(tokens),
        "region": token_info["actual_region"],
        "account_id": token_info.get("account_id", "N/A"),
        "nickname": token_info.get("nickname", "N/A"),
        "token_preview": token_info["token"][:50] + "...",
        "cache_info": {
            "is_cached": (time.time() - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL,
            "age_seconds": int(time.time() - TOKEN_CACHE["timestamp"])
        }
    })

@app.route('/<string:server>/<int:uid>/<int:count>')
def send_visits(server, uid, count):
    """ارسال بازدید - Endpoint اصلی"""
    print(f"\n" + "="*60)
    print(f"🎯 NEW REQUEST: Server={server}, UID={uid}, Visits={count}")
    print("="*60)
    
    # بارگذاری توکن‌ها
    tokens = get_cached_tokens()
    if not tokens:
        return jsonify({
            "error": "No tokens available!",
            "details": "Cannot load tokens from GitHub repository.",
            "cache_status": TOKEN_CACHE["is_valid"]
        }), 500
    
    if count <= 0:
        return jsonify({"error": "Visit count must be positive"}), 400
    
    if count > 500:
        return jsonify({"error": "Maximum 500 visits allowed per request"}), 400
    
    # اجرای عملیات
    try:
        start_time = time.time()
        result = asyncio.run(send_visits_for_tokens(tokens, uid, count))
        end_time = time.time()
        
        response_data = {
            "status": "completed",
            "server": server.upper(),
            "target_uid": uid,
            "requested_visits": count,
            "successful_visits": result["successful_visits"],
            "failed_visits": result["failed_visits"],
            "success_rate": round(result["success_rate"], 2),
            "tokens_used": result["tokens_used"],
            "execution_time": round(end_time - start_time, 2),
            "timestamp": int(time.time()),
            "cache_info": {
                "used_cache": (time.time() - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL,
                "cache_age_seconds": int(time.time() - TOKEN_CACHE["timestamp"])
            }
        }
        
        if "error" in result:
            response_data["warning"] = result["error"]
        
        print(f"\n" + "="*60)
        print(f"📊 FINAL RESULTS:")
        print(f"   Requested: {count} visits")
        print(f"   Successful: {result['successful_visits']}")
        print(f"   Failed: {result['failed_visits']}")
        print(f"   Success Rate: {result['success_rate']:.2f}%")
        print(f"   Tokens Used: {result['tokens_used']}")
        print(f"   Execution Time: {response_data['execution_time']}s")
        
        for region, stats in result.get("results_by_region", {}).items():
            print(f"   Region {region}: ✅ {stats['success']} | ❌ {stats['fail']}")
        
        print("="*60)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in main function: {e}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e),
            "timestamp": int(time.time())
        }), 500

@app.route('/<string:server>/<int:uid>')
def send_single_visit(server, uid):
    """ارسال یک بازدید (برای backward compatibility)"""
    return send_visits(server, uid, 1)

# ========== برای Vercel ==========
# Vercel به این تابع نیاز داره
def handler(request, context):
    """Handler function for Vercel serverless"""
    print("🔄 Vercel handler called")
    return app

# ========== اجرای محلی ==========
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔥 Free Fire Mass Visit Server v2.0")
    print(f"📡 Using tokens from: {GITHUB_TOKEN_URL}")
    print("⏳ Delay between visits: 0.5 seconds")
    print("📡 Available endpoints:")
    print("  GET /<server>/<uid>/<count>   - Send N visits")
    print("  GET /<server>/<uid>           - Send 1 visit")
    print("  GET /stats                    - Token statistics")
    print("  GET /test/<index>             - Test specific token")
    print("  GET /refresh                  - Refresh tokens")
    print("  GET /health                   - Health check")
    print("  GET /                         - Home page")
    print("="*60)
    
    # بارگذاری اولیه توکن‌ها
    print("\n🔄 Initial token loading...")
    load_tokens_from_github()
    
    app.run(host="0.0.0.0", port=8080, debug=True)
