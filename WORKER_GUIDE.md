# Celery 워커 실행 가이드

## 개요
FastAPI 서버와 분리된 Celery 워커를 통해 코드 분석 작업을 처리합니다.

## 실행 방법

### 1. Redis 서버 실행
```bash
# Redis 서버가 실행 중인지 확인
redis-cli ping
```

### 2. FastAPI 서버 실행 (터미널 1)
```bash
python main.py
```

### 3. Celery 워커 실행 (터미널 2)
```bash
# 방법 1: Python 스크립트로 실행
python start_worker.py

# 방법 2: Celery 명령어로 직접 실행
celery -A worker.tasks worker --loglevel=info --concurrency=4
```

## 작업 흐름

1. **웹훅 수신**: FastAPI 서버가 GitHub 웹훅을 받음
2. **태스크 등록**: `analyze_code_task.delay()`로 Celery 큐에 작업 등록
3. **워커 처리**: Celery 워커가 큐에서 작업을 가져와 코드 분석 실행
4. **결과 저장**: 분석 결과를 Redis와 Notion에 저장

## 모니터링

### Celery 상태 확인
```bash
# 워커 상태 확인
celery -A worker.tasks inspect active

# 큐 상태 확인
celery -A worker.tasks inspect reserved
```

### Redis 큐 확인
```bash
# Redis에서 큐 길이 확인
redis-cli llen celery

# 처리 중인 작업 확인
redis-cli keys "celery-task-meta-*"
```

## 주의사항

- FastAPI 서버와 Celery 워커는 별도 프로세스로 실행
- Redis 서버가 먼저 실행되어야 함
- 환경변수(.env) 설정이 양쪽 모두에 필요
- 워커 재시작 시 처리 중인 작업은 재시도됨

## 트러블슈팅

### 워커가 작업을 받지 않는 경우
1. Redis 연결 확인
2. Celery 브로커 URL 확인
3. 워커 로그 확인

### 메모리 부족 시
```bash
# 동시 실행 수 줄이기
celery -A worker.tasks worker --concurrency=2
``` 