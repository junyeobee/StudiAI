# 에러 수집 시스템 가이드

FastAPI 애플리케이션에 구현된 체계적인 에러 수집 및 분석 시스템 사용법입니다.

## 🎯 목적

- 모든 예외를 종류별로 분류하여 체계적으로 관리
- 에러 정보를 Supabase에 구조화된 형태로 저장
- Git 버전별 에러 트렌드 분석
- 운영 환경에서의 안정적인 에러 처리

## 📊 시스템 구조

### 1. 커스텀 예외 클래스들
```python
# app/core/exceptions.py
- NotionAPIError: Notion API 통신 오류
- DatabaseError: 데이터베이스 처리 오류  
- WebhookError: 웹훅 처리 오류
- ValidationError: 입력값 검증 오류
- LearningError: 학습 관련 오류
- RedisError: Redis 캐시 오류
- GithubAPIError: GitHub API 통신 오류
- WebhookOperationError: 웹훅 작업 오류
```

### 2. 에러 로그 테이블 스키마
```sql
-- Supabase error_logs 테이블
CREATE TABLE public.error_logs (
  id             UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  timestamp      TIMESTAMPTZ NOT NULL,     -- 에러 발생 시각 (UTC)
  version_tag    TEXT NOT NULL,            -- Git 태그/커밋 해시
  endpoint       TEXT NOT NULL,            -- 요청된 경로
  method         TEXT NOT NULL,            -- HTTP 메서드
  exception_type TEXT NOT NULL,            -- 예외 클래스명
  detail         TEXT,                     -- 예외 메시지
  stack_trace    TEXT,                     -- 스택 트레이스
  user_id        TEXT,                     -- 사용자 ID
  inserted_at    TIMESTAMPTZ DEFAULT NOW() -- 레코드 생성 시각
);
```

## 🔧 환경 설정

### 필수 환경 변수
```bash
# 버전 추적용 (CI/CD에서 자동 설정 권장)
APP_VERSION=v1.2.0  # 또는 커밋 해시

# 환경 구분용 (테스트 엔드포인트 제어)
ENVIRONMENT=development  # development | staging | production
```

## 📱 API 엔드포인트

### 1. 에러 통계 조회 (관리자용)
```http
GET /api/v1/admin/error-statistics?version_tag=v1.2.0&limit=100
Authorization: Bearer {api_key}
```

**응답 예시:**
```json
{
  "status": "success",
  "data": {
    "total_errors": 45,
    "error_type_counts": {
      "DatabaseError": 20,
      "NotionAPIError": 15,
      "ValidationError": 10
    },
    "endpoint_counts": {
      "/api/v1/databases": 15,
      "/api/v1/learning": 10
    },
    "version_tag": "v1.2.0"
  },
  "message": "에러 통계 조회 완료"
}
```

### 2. 시스템 건강성 체크
```http
GET /api/v1/admin/health/error-logging
Authorization: Bearer {api_key}
```

### 3. 테스트용 예외 발생 (개발 환경만)
```http
POST /api/v1/admin/test/trigger-error/database
Authorization: Bearer {api_key}
```

## 💻 개발 가이드

### 1. 서비스 레이어에서 예외 발생
```python
# app/services/some_service.py
from app.core.exceptions import DatabaseError

async def create_something(data: dict, supabase: AsyncClient):
    try:
        result = await supabase.table("table_name").insert(data).execute()
        return result.data
    except Exception as e:
        # 원본 예외를 커스텀 예외로 래핑
        raise DatabaseError(f"생성 실패: {str(e)}")
```

### 2. 엔드포인트에서는 최소한의 처리
```python
# app/api/v1/endpoints/some_endpoint.py
from app.services.some_service import create_something
from app.core.exceptions import DatabaseError

@router.post("/")
async def create_endpoint(data: CreateRequest):
    try:
        result = await create_something(data.dict(), supabase)
        return {"status": "success", "data": result}
    except DatabaseError as e:
        # 커스텀 예외는 전역 핸들러가 자동 처리
        raise  # 그냥 다시 던지면 됨
    # 또는 아예 try/except 없이 두어도 전역 핸들러가 처리
```

### 3. 전역 핸들러가 자동 처리
- 에러 로그를 Supabase에 저장
- 스택 트레이스를 콘솔에 출력  
- 사용자에게는 안전한 메시지만 반환

## 📈 운영 활용

### 1. 버전별 에러 분석
```bash
# 특정 버전의 에러만 조회
curl -H "Authorization: Bearer {key}" \
  "https://api.example.com/admin/error-statistics?version_tag=v1.2.0"

# 최근 모든 에러 조회  
curl -H "Authorization: Bearer {key}" \
  "https://api.example.com/admin/error-statistics?limit=500"
```

### 2. 대시보드 구축
- `error_logs` 테이블을 기반으로 Grafana/Superset 대시보드 구축
- 시간대별/엔드포인트별/예외 유형별 차트 생성
- 알림 규칙 설정 (특정 에러 임계값 초과 시)

### 3. CI/CD 연동
```yaml
# GitHub Actions 예시
- name: Deploy
  env:
    APP_VERSION: ${{ github.ref_name }}  # Git 태그
  run: |
    export APP_VERSION
    docker-compose up -d
```

## 🛡️ 보안 고려사항

### 1. 민감 정보 필터링
- 스택 트레이스에 API 키나 비밀번호가 노출되지 않도록 주의
- 필요시 `detail` 필드에서 민감 정보 마스킹

### 2. 관리자 권한
```python
# TODO: 실제 구현 예시
async def is_admin_user(user_id: str, supabase: AsyncClient) -> bool:
    # 관리자 권한 체크 로직
    pass
```

### 3. 로그 보존 정책
```sql
-- 90일 이후 오래된 로그 삭제 (크론잡 권장)
DELETE FROM error_logs 
WHERE inserted_at < NOW() - INTERVAL '90 days';
```

## 🧪 테스트 방법

### 1. 개발 환경에서 테스트
```bash
# 다양한 예외 유형 테스트
curl -X POST -H "Authorization: Bearer {key}" \
  "http://localhost:8000/api/v1/admin/test/trigger-error/database"

curl -X POST -H "Authorization: Bearer {key}" \
  "http://localhost:8000/api/v1/admin/test/trigger-error/notion_api"
```

### 2. 로그 확인
```bash
# Supabase에서 저장된 로그 확인
SELECT * FROM error_logs ORDER BY timestamp DESC LIMIT 10;
```

## 🔄 향후 개선 방향

1. **알림 시스템**: 중요 에러 발생 시 Slack/Email 알림
2. **AI 분석**: 에러 패턴 분석 및 자동 해결 제안
3. **성능 최적화**: 에러 로그 저장 시 비동기 큐 활용
4. **상세 분석**: 사용자별/지역별/디바이스별 에러 분포 분석

---

> 💡 **팁**: 개발 초기부터 이 시스템을 활용하면, 서비스 안정성과 사용자 경험을 크게 향상시킬 수 있습니다. 