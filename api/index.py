import os
import sys

# 將專案根目錄加入 sys.path，確保在 Vercel Serverless 環境下正確載入模組
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import app

# 讓 Vercel WSGI / ASGI 辨識入口點
app = app
