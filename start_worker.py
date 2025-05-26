"""
RQ 워커 실행 스크립트 - Windows/Linux 통합 버전
"""
import os
import sys
import argparse
import signal
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worker.tasks import start_worker_with_optimization, get_platform_info
from app.utils.logger import api_logger

def setup_signal_handlers():
    """OS별 시그널 핸들러 설정"""
    def shutdown_handler(signum, frame):
        api_logger.info(f"종료 신호 수신: {signum}")
        sys.exit(0)
    
    if os.name == 'nt':  # Windows
        # Windows에서는 CTRL+C만 처리
        signal.signal(signal.SIGINT, shutdown_handler)
        try:
            signal.signal(signal.SIGTERM, shutdown_handler)
        except AttributeError:
            # Windows에서 SIGTERM이 없는 경우
            pass
    else:  # Linux/Unix
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGQUIT, shutdown_handler)

def check_dependencies():
    """필요 의존성 체크"""
    missing_deps = []
    
    # 기본 의존성
    required_modules = ['redis', 'rq', 'supabase']
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_deps.append(module)
    
    # Windows 특화 의존성 (선택적)
    if os.name == 'nt':
        optional_modules = ['psutil', 'win32evtlog']
        for module in optional_modules:
            try:
                __import__(module)
                api_logger.info(f"Windows 최적화 모듈 사용 가능: {module}")
            except ImportError:
                api_logger.warning(f"Windows 최적화 모듈 없음 (선택적): {module}")
    
    if missing_deps:
        api_logger.error(f"필수 의존성 누락: {missing_deps}")
        print(f"다음 패키지를 설치해주세요: pip install {' '.join(missing_deps)}")
        sys.exit(1)
    
    api_logger.info("의존성 체크 완료")

def setup_environment():
    """환경 설정"""
    # 버퍼링 비활성화
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    # Windows 특화 설정
    if os.name == 'nt':
        # Windows 콘솔 UTF-8 설정
        try:
            os.system('chcp 65001 >nul 2>&1')
        except:
            pass
        
        # Windows에서 SpawnWorker 사용
        os.environ.setdefault("WORKER_MODE", "spawn")
        
        # Windows 타임아웃 증가
        os.environ.setdefault("RQ_WORKER_TIMEOUT", "900")  # 15분
    else:
        # Linux 기본 설정
        os.environ.setdefault("WORKER_MODE", "fork")
        os.environ.setdefault("RQ_WORKER_TIMEOUT", "600")  # 10분
    
    # 공통 환경변수
    os.environ.setdefault("ENABLE_AUTO_SCALING", "true")

def print_startup_info():
    """시작 정보 출력"""
    platform_info = get_platform_info()
    
    print("=" * 60)
    print("🚀 RQ 워커 시작")
    print("=" * 60)
    print(f"플랫폼: {platform_info['platform']}")
    print(f"워커 타입: {platform_info['worker_type']}")
    print(f"최적화 모듈: {platform_info['optimization_module']}")
    print(f"실패 핸들러: {platform_info['failure_handler']}")
    print(f"자동 스케일링: {os.getenv('ENABLE_AUTO_SCALING', 'true')}")
    
    if os.name == 'nt':
        print("🔧 Windows 특화 기능:")
        print("  - SpawnWorker 사용 (fork 대신)")
        print("  - TimerDeathPenalty 적용")
        print("  - 프로세스 핸들 기반 관리")
        print("  - 스레드 풀 기반 재시도")
    else:
        print("🐧 Linux/Unix 특화 기능:")
        print("  - Fork 기반 Worker 사용")
        print("  - Unix 시그널 처리")
        print("  - 표준 프로세스 관리")
    
    print("=" * 60)

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='RQ Worker 시작 (Windows/Linux 통합)')
    parser.add_argument('--mode', choices=['optimized', 'basic'], default='optimized',
                       help='워커 모드 선택')
    parser.add_argument('--scaling', choices=['true', 'false'], default='true',
                       help='자동 스케일링 활성화')
    parser.add_argument('--worker-type', choices=['spawn', 'simple', 'fork'], 
                       help='워커 타입 강제 지정 (Windows: spawn/simple, Linux: fork)')
    
    args = parser.parse_args()
    
    try:
        # 환경 설정
        setup_environment()
        
        # 명령행 인수 적용
        if args.scaling:
            os.environ["ENABLE_AUTO_SCALING"] = args.scaling
            
        if args.worker_type:
            os.environ["WORKER_MODE"] = args.worker_type
        
        # 시작 정보 출력
        print_startup_info()
        
        # 의존성 체크
        check_dependencies()
        
        # 시그널 핸들러 설정
        setup_signal_handlers()
        
        api_logger.info("RQ 워커 시작 준비 완료")
        
        # 워커 시작
        if args.mode == 'optimized':
            start_worker_with_optimization()
        else:
            from worker.tasks import start_worker
            start_worker()
            
    except KeyboardInterrupt:
        api_logger.info("사용자 중단 신호")
        print("\n👋 워커를 정상 종료합니다...")
    except Exception as e:
        api_logger.error(f"워커 시작 실패: {str(e)}")
        print(f"❌ 오류: {str(e)}")
        sys.exit(1)
    finally:
        print("🏁 RQ 워커 종료 완료")

if __name__ == '__main__':
    main()