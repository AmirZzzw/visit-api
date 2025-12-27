# این فایل باید در پوشه /api/index.py باشد
import sys
import os

# تنظیم مسیرها
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import app اصلی
from app import app

# Vercel از این تابع استفاده می‌کند
def handler(request, context):
    return app