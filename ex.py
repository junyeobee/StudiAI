from datetime import datetime, timedelta
import requests

# ✏️ Notion API 키와 DB ID
NOTION_API_KEY = "ntn_C58327611023N5xC6lu9H8zMIAuC2rmL225aGylmNQdbC7"
DATABASE_ID = "1d415ba8-df0e-8182-bf86-ca34bcce11a5"
NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# 📅 학습 계획 정의
learning_plans = [
    {
        "title": "React 개요",
        "goal_items": [
            "- React의 핵심 개념 이해",
            "- Virtual DOM 이해",
            "- 렌더링 방식 이해"
        ],
        "summary": "[[AI_SUMMARY_BLOCK]] (자동으로 요약이 들어오는 공간입니다.)"
    },
    {
        "title": "JSX 문법",
        "goal_items": [
            "- JSX 기본 문법 익히기",
            "- Babel 변환 이해"
        ],
        "summary": "[[AI_SUMMARY_BLOCK]] (자동 정리 예정)"
    },
    {
        "title": "컴포넌트 구조",
        "goal_items": [
            "- 함수형 컴포넌트 이해",
            "- props, state 사용법 익히기"
        ],
        "summary": "[[AI_SUMMARY_BLOCK]] (자동 정리 예정)"
    }
]

# 🔁 각 계획별로 Notion 페이지 생성
for i, plan in enumerate(learning_plans):
    date = (datetime.today() + timedelta(days=i)).strftime("%Y-%m-%d")
    goal_code = "예시)\n" + "\n".join(plan["goal_items"])

    body = {
        "parent": { "database_id": DATABASE_ID },
        "properties": {
            "학습 제목": {
                "title": [{ "text": { "content": plan["title"] } }]
            },
            "날짜": {
                "date": { "start": date }
            },
            "진행 상태": {
                "select": { "name": "시작 전" }
            },
            "복습 여부": {
                "checkbox": False
            }
        },
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{ "text": { "content": "🧠 학습 목표" } }]
                }
            },
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{ "text": { "content": "이 섹션에 학습의 목적이나 계획을 간단히 작성하세요." } }]
                }
            },
            {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{ "text": { "content": goal_code } }],
                    "language": "diff"
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}   
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{ "text": { "content": "🤖 AI 요약 내용" } }]
                }
            },
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{ "text": { "content": "학습 요약 정리를 자동화하거나 수동으로 작성하는 공간입니다." } }]
                }
            },
            {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{ "text": { "content": plan["summary"] } }],
                    "language": "scss"
                }
            }
        ]
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=body)
    print(f"[{i+1}일차] 상태코드: {res.status_code}")
    if res.status_code != 200:
        print(res.json())
    else:
        page_data = res.json()
        page_id = page_data["id"]
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        blocks_res = requests.get(blocks_url, headers=headers)
        if blocks_res.status_code == 200:
            blocks_data = blocks_res.json()
            for block in blocks_data.get("results", []):
                if block.get("type") == "code":
                    text = block.get("code", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                    if "[[AI_SUMMARY_BLOCK]]" in text:
                        ai_summary_block_id = block["id"]
                        print(f"✅ '{plan['title']}' 페이지의 요약 블록 ID: {ai_summary_block_id}")
                        print(text)
                        # 이후 여기에 PATCH 요청으로 AI 응답 텍스트 넣기 가능!
                        break
