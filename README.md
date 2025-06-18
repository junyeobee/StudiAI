<div># StudiAI - MCP 기반 코드 분석 & 문서 자동화 시스템<div>

**📅 개발 기간:** 2025.04.21 ~ 2025.06.16  

---

## ✨ 프로젝트 소개

`StudiAI`는 MCP 서버를 활용하여 프로젝트·학습을 지원하는 **LLM 기반 코드 분석 및 문서 자동화 지원 시스템**입니다.

- GitHub 커밋 분석 및 문서 자동화
- Notion 페이지 자동 분석 및 학습 기록화
- MCP Tools를 통한 학습 보조 기능 제공

**본 프로젝트는 MCP 서버 설치/설정이 완료된 사용자 환경에서 사용 가능합니다.**  
(서버 코드 및 설치법은 별도 제공하지 않음)

---

## 🔍 주요 기능

- ✅ GitHub Webhook → 커밋 단위 분석 → Notion 기록
- ✅ Notion Webhook → 페이지 상태 자동 업데이트
- ✅ 코드 함수 단위 분석 + 자동 문서화
- ✅ MCP Tools 활용 학습 지원 기능 (예: Feedback Tool)

---

## 🚀 사용 방법

### MCP 서버 활용 흐름

1. GitHub 저장소에 커밋 → MCP 서버가 자동으로 코드 분석 후 Notion에 기록
2. Notion 페이지 편집 시 → MCP 서버가 자동으로 상태 반영
3. MCP Tools 제공 API를 통해 학습 지원 기능 사용 가능

---

## 📄 사용 예시

### GitHub 연동 흐름

```text
GitHub Commit → GitHub Webhook → MCP 서버 분석 → Notion 기록
