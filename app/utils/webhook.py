"""
웹훅 관련 유틸리티 함수
"""
from datetime import datetime
from typing import Optional
from app.utils.logger import webhook_logger

def log_webhook_operation(
    db_id: str,
    operation_type: str,
    status: str,
    error_message: Optional[str] = None,
    webhook_id: Optional[str] = None
) -> None:
    """
    웹훅 작업 로그를 기록합니다.
    
    Args:
        db_id (str): 데이터베이스 ID
        operation_type (str): 작업 유형 (create, delete, update 등)
        status (str): 작업 상태 (success, failed, pending 등)
        error_message (Optional[str]): 에러 메시지 (실패한 경우)
        webhook_id (Optional[str]): 웹훅 ID
    """
    try:
        # 로그 메시지 구성
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "db_id": db_id,
            "operation_type": operation_type,
            "status": status,
            "webhook_id": webhook_id,
            "error_message": error_message
        }
        
        # 상태에 따른 로깅 레벨 결정
        if status == "success":
            webhook_logger.info(f"Webhook operation successful: {log_data}")
        elif status == "failed":
            webhook_logger.error(f"Webhook operation failed: {log_data}")
        else:
            webhook_logger.warning(f"Webhook operation {status}: {log_data}")
            
    except Exception as e:
        webhook_logger.error(f"Failed to log webhook operation: {str(e)}") 