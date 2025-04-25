import requests
import json
import os
from dotenv import load_dotenv
from app.core.config import settings

load_dotenv()

NOTION_VERSION = settings.NOTION_API_VERSION

headers = {
    "Authorization": f"Bearer {settings.NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

def query_database(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    res = requests.post(url, headers=headers)
    print(res.status_code)
    print(res.json())

# 예시: 데이터베이스 생성 (상위 페이지 안에)
def create_database(parent_page_id):
    url = "https://api.notion.com/v1/databases"
    payload = {
        "parent": {
            "type": "page_id",
            "page_id": parent_page_id
        },
        "title": [
            {
                "type": "text",
                "text": {
                    "content": "학습 목표: React"
                }
            }
        ],
        "properties": {
            "날짜": { "date": {} },
            "학습 제목": { "title": {} },
            "복습 여부": { "checkbox": {} },
            "진행 상태": {
                "select": {
                    "options": [
                        { "name": "시작 전", "color": "gray" },
                        { "name": "진행중", "color": "blue" },
                        { "name": "완료", "color": "green" }
                    ]
                }
            }
        }
    }

    res = requests.post(url, headers=headers, data=json.dumps(payload))
    print(res.status_code)
    print(res.json())


query_database("1d215ba8df0e804abe7fd559f7ab6884")
create_database("15415ba8df0e80e4834bcf738689aecc")