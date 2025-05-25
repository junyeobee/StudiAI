# RQ 워커 실행 가이드

## 개요
FastAPI 서버와 분리된 RQ(Redis Queue) 워커를 통해 코드 분석 작업을 처리합니다.
## 실행 방법

### 1. Redis 서버 실행
```bash
# Redis 서버가 실행 중인지 확인
redis-cli ping
```

### 2. RQ 패키지 설치
```bash
pip install rq
```

### 3. FastAPI 서버 실행 (터미널 1)
```bash
python main.py
```

### 4. RQ 워커 실행 (터미널 2)
```bash
# 방법 1: Python 스크립트로 실행
python start_worker.py

# 방법 2: RQ 명령어로 직접 실행
rq worker code_analysis --url redis://:{password}@{server_url}:{port}/0
```

## 작업 흐름

1. **웹훅 수신**: FastAPI 서버가 GitHub 웹훅을 받음
2. **태스크 등록**: `task_queue.enqueue()`로 RQ 큐에 작업 등록
3. **워커 처리**: RQ 워커가 큐에서 작업을 가져와 코드 분석 실행
4. **결과 저장**: 분석 결과를 Redis와 Notion에 저장

## 모니터링

### RQ 상태 확인
```bash
# 큐 상태 확인
rq info --url redis://:{password}@{server_url}:{port}/0

# 워커 상태 확인
rq info --url redis://:{password}@{server_url}:{port}/0 --interval 1
```

### Redis 큐 확인
```bash
# Redis에서 큐 길이 확인
redis-cli -h localhost -p 9091 -a {password} llen rq:queue:code_analysis

# 처리 중인 작업 확인
redis-cli -h localhost -p 9091 -a {password} keys "rq:job:*"
```

## 주요 변경사항 (Fastapi 내부 비동기 큐 → RQ)

- **API 서버 부하 분산** : LLM분석, 대용량 파일 파싱 등 무거운 작업들을 워커 프로세스가 처리
- **쉬운 모니터링**: RQ 대시보드 사용 가능
- **빠른 시작**: 설정 오류 최소화

## 주의사항

- FastAPI 서버와 RQ 워커는 별도 프로세스로 실행
- Redis 서버가 먼저 실행되어야 함
- 환경변수(.env) 설정
- 워커 재시작 시 처리 중인 작업은 재시도됨

## 트러블슈팅

### 워커가 작업을 받지 않는 경우
1. Redis 연결 확인
2. 큐 이름 확인 (`code_analysis`)
3. 워커 로그 확인

### 메모리 부족 시
```bash
# 단일 워커로 실행
python start_worker.py
```

### RQ 대시보드 사용 (선택사항)
```bash
pip install rq-dashboard
rq-dashboard --redis-url redis://:{password}@{server_url}:{port}/0
``` 