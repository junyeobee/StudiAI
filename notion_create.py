from datetime import datetime, timedelta
import requests
from notion_config import headers
from supa import insert_learning_page, get_learning_database_by_title

# 🔍 AI 요약 블록 ID 추출
def find_ai_summary_block(page_id):
    blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    blocks_res = requests.get(blocks_url, headers=headers)
    if blocks_res.status_code == 200:
        blocks_data = blocks_res.json()
        for block in blocks_data.get("results", []):
            if block.get("type") == "code":
                text = block.get("code", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
                if "[[AI_SUMMARY_BLOCK]]" in text:
                    return block["id"]
    return None

# 📘 학습 페이지 생성 및 Supabase 저장
def create_learning_pages(plans, notion_db_id, learning_db_id):
    for i, plan in enumerate(plans):
        date = (datetime.today() + timedelta(days=i)).strftime("%Y-%m-%d")
        goal_code = "예시)\n" + "\n".join(plan["goal_items"])

        body = {
            "parent": { "database_id": notion_db_id },
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
        if res.status_code == 200:
            page_data = res.json()
            page_id = page_data["id"]
            ai_block_id = find_ai_summary_block(page_id)

            if ai_block_id:
                insert_learning_page(
                    date=date,
                    title=plan["title"],
                    page_id=page_id,
                    ai_block_id=ai_block_id,
                    learning_db_id=learning_db_id
                )
            else:
                print(f"❌ 요약 블록을 찾지 못했습니다: {plan['title']}")
        else:
            print(f"❌ 페이지 생성 실패: {res.status_code}", res.json())

# ▶️ 실행
if __name__ == "__main__":
    title = "React 학습 계획"
    notion_db_id, learning_db_id = get_learning_database_by_title(title)
    if notion_db_id and learning_db_id:
        create_learning_pages(notion_db_id, learning_db_id)
    else:
        print("❌ Supabase에서 학습 DB 정보를 찾을 수 없습니다.")
