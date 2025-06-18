# 📅 StudiAI 개발 프로젝트 전체 이력

**프로젝트 기간:** 2025.04.21 ~ 2025.06.16  
**전체 커밋 수:** 258 commits  
**프로젝트 개요:** MCP 서버를 활용하여 프로젝트·학습 지원을 위한 LLM 기반 코드 분석 및 문서 자동화 지원 시스템

---

## 프로젝트 이력 상세

| 기간 | 주요 작업 | 비고 |
| --- | --- | --- |
| 2025-04-21 ~ 2025-04-30 | 초기 구조 개발 | Notion/Supabase 통합, AI 요약 블록 설계, 자동 DB 생성 기능 |
| 2025-05-01 ~ 2025-05-10 | MCP 서버 툴 추가, Helper Tool 구성 | Prompt 파싱 방식 구성, Notion 페이지 수정 기능 |
| 2025-05-11 ~ 2025-05-20 | OAuth 인증 모델 구축 | Notion/GitHub OAuth 통합, 토큰 관리, Redis 기반 캐시 설계 |
| 2025-05-21 ~ 2025-05-23 | Code Analysis 1차 구성 | 함수 변경 감지, 버전 추적 로직 |
| 2025-05-24 ~ 2025-05-27 | Redis Cache 설계, Diff 구조 개선 | Commit SHA 기반 변경 감지, 분석 범위 최적화 |
| 2025-05-28 ~ 2025-05-30 | Tree-sitter 기반 파서 전환 | 함수 파싱 정확도 개선, 구조적 파싱 안정화 |
| 2025-05-31 ~ 2025-06-03 | Notion 연동 확장 및 RQ 도입 | RQ 작업 큐 전환, Redis Key 구조 변경 |
| 2025-06-04 ~ 2025-06-07 | CI/CD 파이프라인 구축 | GitHub Actions + Pytest + Docker Build 자동화 |
| 2025-06-08 ~ 2025-06-11 | LLM 로컬 통합 테스트 | Local LLM, Meta-Llama 연동, RQ Task 관리 안정화 |
| 2025-06-12 ~ 2025-06-16 | MCP Tool 확장 및 Feedback Tool 추가 | Redis 구조 재정비, RPC 트랜잭션화, Feedback 수집 기능 추가 |

---

## 프로젝트 주요 구성

- **MCP 서버 기반 분석 및 문서화 자동화 시스템**
- **LLM 기반 코드 분석 및 함수 요약 자동화**
- **GitHub Webhook 기반 커밋 이벤트 감지 및 분석**
- **Notion Webhook 기반 실시간 DB 상태 동기화**
- **Supabase + Redis 기반 상태 관리 및 캐시 설계**
- **자동 문서화 파이프라인 (Markdown → Notion Block 변환)**
- **통합 MCP Tools 설계 및 코드 분석 파이프라인 최적화**

---