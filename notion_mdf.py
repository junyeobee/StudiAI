from notion_config import headers

import requests
def update_ai_summary_block(block_id: str, summary_text: str):
    url = f"https://api.notion.com/v1/blocks/{block_id}"
    payload = {
        "code": {
            "rich_text": [{
                "text": {
                    "content": summary_text
                }
            }],
            "language": "scss"
        }
    }
    res = requests.patch(url, headers=headers, json=payload)
    print(f"🔁 PATCH 상태: {res.status_code}")
    try:
        print("📄 Notion 응답:", res.json())
    except Exception:
        print("응답 파싱 실패")