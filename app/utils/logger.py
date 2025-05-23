"""
로깅 설정
"""
import logging
from logging.handlers import RotatingFileHandler
import os
from app.core.config import settings
from datetime import datetime

# 로그 디렉토리 생성
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 현재 날짜로 로그 파일명 생성
current_date = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join(log_dir, f"app_{current_date}.log")

# 로깅 포맷 설정
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

# API 로거 설정
api_logger = logging.getLogger("api")
api_logger.setLevel(logging.INFO)
api_handler = logging.FileHandler(log_file, encoding='utf-8')
api_handler.setFormatter(logging.Formatter(log_format, date_format))
api_logger.addHandler(api_handler)
api_logger.propagate = False

# 웹훅 로거 설정
webhook_logger = logging.getLogger("webhook")
webhook_logger.setLevel(logging.INFO)
webhook_handler = logging.FileHandler(log_file, encoding='utf-8')
webhook_handler.setFormatter(logging.Formatter(log_format, date_format))
webhook_logger.addHandler(webhook_handler)
webhook_logger.propagate = False

# Notion 로거 설정
notion_logger = logging.getLogger("notion")
notion_logger.setLevel(logging.INFO)
notion_handler = logging.FileHandler(log_file, encoding='utf-8')
notion_handler.setFormatter(logging.Formatter(log_format, date_format))
notion_logger.addHandler(notion_handler)
notion_logger.propagate = False
# Github 로거 설정
github_logger = logging.getLogger("github")
github_logger.setLevel(logging.INFO)
github_handler = logging.FileHandler(log_file, encoding='utf-8')
github_handler.setFormatter(logging.Formatter(log_format, date_format))
github_logger.addHandler(github_handler)
github_logger.propagate = False

def setup_logging():
    """로깅 설정을 초기화합니다."""
    # 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # 모든 로거에 콘솔 핸들러 추가
    for logger in [api_logger, webhook_logger, notion_logger]:
        logger.addHandler(console_handler)

# 로깅 설정 초기화
setup_logging() 