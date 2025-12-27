from flask import Flask, jsonify
import aiohttp
import asyncio
import json
import base64
from byte import encrypt_api, Encrypt_ID
from AccountPersonalShow_pb2 import AccountPersonalShowInfo
import time
import requests
from datetime import datetime

app = Flask(__name__)

# ========== CONFIGURATION ==========
GITHUB_TOKEN_URL = "https://raw.githubusercontent.com/AmirZzzw/info-api/main/jwt.json"
TOKEN_CACHE_TTL = 300  # 5 دقیقه
# ===================================

# Cache برای توکن‌ها
TOKEN_CACHE = {
    "tokens": [],
    "timestamp": 0,
    "is_valid": False
}

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
                # گرفتن region از خود JWT
                decoded = decode_jwt(token)
                # استفاده از lock_region از JWT
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
    
    # رمزگذاری UID (یکبار برای همه)
    encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
    data = bytes.fromhex(encrypted)
    
    print(f"🔐 Encrypted data for UID {uid}: {encrypted[:30]}...")
    
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
            
            print(f"   📤 Visit {visit_number}/{visit_count}: Token {token_index + 1} ({token_info['actual_region']})")
            
            try:
                success, status, region = await visit(session, token_info, uid, data, token_index + 1, visit_number)
                
                if success:
                    total_success += 1
                    if region not in results_by_region:
                        results_by_region[region] = {"success": 0, "fail": 0}
                    results_by_region[region]["success"] += 1
                    print(f"      ✅ Success")
                else:
                    total_fail += 1
                    if region not in results_by_region:
                        results_by_region[region] = {"success": 0, "fail": 0}
                    results_by_region[region]["fail"] += 1
                    print(f"      ❌ Failed (Status: {status})")
                    
            except Exception as e:
                total_fail += 1
                print(f"      ❌ Error: {str(e)[:50]}...")
            
            # نمایش progress
            if visit_number % 10 == 0 or visit_number == visit_count:
                print(f"   📊 Progress: {visit_number}/{visit_count} | Success: {total_success} | Fail: {total_fail}")
            
            # تاخیر ۰.۵ ثانیه بین درخواست‌ها (به جز آخرین درخواست)
            if visit_number < visit_count:
                await asyncio.sleep(0.5)
    
    return {
        "total_requests": visit_count,
        "successful_visits": total_success,
        "failed_visits": total_fail,
        "success_rate": (total_success / visit_count * 100) if visit_count > 0 else 0,
        "results_by_region": results_by_region,
        "tokens_used": len(tokens),
    }

@app.route('/<string:server>/<int:accid>/<int:visitcount>', methods=['GET'])
def send_visits_with_count(server, accid, visitcount):
    """Endpoint جدید: /IND/4285785816/50"""
    server = server.upper()
    
    print(f"\n" + "="*60)
    print(f"🎯 NEW REQUEST: Server={server}, UID={accid}, Visits={visitcount}")
    print("="*60)
    
    # بارگذاری توکن‌ها از GitHub (با cache)
    all_tokens = get_cached_tokens()
    
    if not all_tokens:
        return jsonify({
            "error": "❌ No tokens available!",
            "details": "Cannot load tokens from GitHub repository.",
            "cache_status": TOKEN_CACHE["is_valid"],
            "timestamp": TOKEN_CACHE["timestamp"]
        }), 500
    
    if visitcount <= 0:
        return jsonify({"error": "❌ Visit count must be positive"}), 400
    
    if visitcount > 500:  # محدودیت برای جلوگیری از abuse
        return jsonify({"error": "❌ Maximum 500 visits allowed per request"}), 400
    
    # اجرای عملیات
    start_time = time.time()
    result = asyncio.run(send_visits_for_tokens(all_tokens, accid, visitcount))
    end_time = time.time()
    
    # ساخت response
    response_data = {
        "status": "completed",
        "server": server,
        "target_uid": accid,
        "requested_visits": visitcount,
        "actual_requests": result["total_requests"],
        "successful_visits": result["successful_visits"],
        "failed_visits": result["failed_visits"],
        "success_rate": round(result["success_rate"], 2),
        "tokens_used": result["tokens_used"],
        "results_by_region": result["results_by_region"],
        "execution_time": round(end_time - start_time, 2),
        "estimated_time_with_delay": round(visitcount * 0.5 + (end_time - start_time), 2),
        "timestamp": int(time.time()),
        "cache_info": {
            "used_cache": (time.time() - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL,
            "cache_age_seconds": int(time.time() - TOKEN_CACHE["timestamp"]),
            "tokens_source": "GitHub Repository"
        }
    }
    
    # نمایش خلاصه
    print(f"\n" + "="*60)
    print(f"📊 FINAL RESULTS:")
    print(f"   Requested: {visitcount} visits")
    print(f"   Successful: {result['successful_visits']}")
    print(f"   Failed: {result['failed_visits']}")
    print(f"   Success Rate: {result['success_rate']:.2f}%")
    print(f"   Tokens Used: {result['tokens_used']}")
    print(f"   Execution Time: {response_data['execution_time']}s")
    
    for region, stats in result["results_by_region"].items():
        print(f"   Region {region}: ✅ {stats['success']} | ❌ {stats['fail']}")
    
    print("="*60)
    
    return jsonify(response_data), 200

@app.route('/<string:server>/<int:accid>', methods=['GET'])
def send_visits_default(server, accid):
    """Endpoint قدیمی برای backward compatibility"""
    return send_visits_with_count(server, accid, 1)

@app.route('/refresh-tokens', methods=['GET'])
def refresh_tokens():
    """Force refresh tokens from GitHub"""
    print(f"\n🔄 Force refreshing tokens from GitHub...")
    tokens = load_tokens_from_github()
    
    if tokens:
        return jsonify({
            "status": "success",
            "message": f"Refreshed {len(tokens)} tokens",
            "regions": {t["actual_region"] for t in tokens},
            "cache_timestamp": TOKEN_CACHE["timestamp"],
            "cache_age": int(time.time() - TOKEN_CACHE["timestamp"])
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to refresh tokens",
            "cache_status": TOKEN_CACHE
        }), 500

@app.route('/test/token/<int:index>', methods=['GET'])
def test_token(index):
    """تست یک توکن خاص"""
    all_tokens = get_cached_tokens()
    
    if not all_tokens:
        return jsonify({"error": "No tokens available"}), 400
    
    if index < 1 or index > len(all_tokens):
        return jsonify({"error": f"Invalid index. Valid range: 1-{len(all_tokens)}"}), 400
    
    token_info = all_tokens[index-1]
    decoded = decode_jwt(token_info["token"])
    
    return jsonify({
        "token_index": index,
        "total_tokens": len(all_tokens),
        "region": token_info["actual_region"],
        "account_id": token_info.get("account_id", "N/A"),
        "nickname": token_info.get("nickname", "N/A"),
        "endpoint": get_url_by_region(token_info["actual_region"]),
        "token_preview": token_info["token"][:50] + "...",
        "cache_info": {
            "is_cached": (time.time() - TOKEN_CACHE["timestamp"]) < TOKEN_CACHE_TTL,
            "age_seconds": int(time.time() - TOKEN_CACHE["timestamp"])
        }
    }), 200

@app.route('/stats', methods=['GET'])
def get_stats():
    """آمار کلی توکن‌ها"""
    all_tokens = get_cached_tokens()
    
    if not all_tokens:
        return jsonify({"error": "No tokens available"}), 400
    
    region_counts = {}
    for token in all_tokens:
        region = token["actual_region"]
        region_counts[region] = region_counts.get(region, 0) + 1
    
    return jsonify({
        "total_tokens": len(all_tokens),
        "tokens_by_region": region_counts,
        "available_regions": list(region_counts.keys()),
        "cache_info": {
            "is_valid": TOKEN_CACHE["is_valid"],
            "timestamp": TOKEN_CACHE["timestamp"],
            "age_seconds": int(time.time() - TOKEN_CACHE["timestamp"]),
            "source": "GitHub Repository"
        }
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    all_tokens = get_cached_tokens()
    
    return jsonify({
        "status": "healthy" if all_tokens else "degraded",
        "service": "Free Fire Visit Server",
        "version": "2.0",
        "description": "Using tokens from GitHub repository",
        "tokens_status": {
            "available": len(all_tokens) > 0,
            "count": len(all_tokens),
            "source": "GitHub",
            "cache_age": int(time.time() - TOKEN_CACHE["timestamp"])
        },
        "configuration": {
            "delay_between_visits": "0.5 seconds",
            "max_visits_per_request": 500,
            "token_cache_ttl": f"{TOKEN_CACHE_TTL} seconds"
        },
        "endpoints": [
            "GET /<server>/<uid>/<count> - Send N visits with 0.5s delay",
            "GET /<server>/<uid> - Send 1 visit",
            "GET /stats - Token statistics",
            "GET /test/token/<index> - Test specific token",
            "GET /refresh-tokens - Force refresh tokens",
            "GET /health - Health check"
        ]
    }), 200

if __name__ == "__main__":
    print("🔥 Free Fire Mass Visit Server v2.0 (GitHub Edition)")
    print(f"📡 Using tokens from: {GITHUB_TOKEN_URL}")
    print(f"💾 Token Cache TTL: {TOKEN_CACHE_TTL} seconds")
    print("⏳ Delay between visits: 0.5 seconds")
    print("\n📡 Available endpoints:")
    print("  GET /<server>/<uid>/<count>   - Send N visits with 0.5s delay")
    print("  GET /<server>/<uid>           - Send 1 visit")
    print("  GET /stats                    - Token statistics")
    print("  GET /test/token/<index>       - Test specific token")
    print("  GET /refresh-tokens           - Force refresh tokens")
    print("  GET /health                   - Health check")
    print("\n" + "="*60)
    
    # بارگذاری اولیه توکن‌ها
    print("\n🔄 Initial token loading from GitHub...")
    load_tokens_from_github()
    
    app.run(host="0.0.0.0", port=5200, debug=True)