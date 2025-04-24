import requests
from notion_config import headers

## 노션 페이지 안의 모든 DB 조회
def list_databases_in_page(parent_page_id):
    """
    Notion 페이지에 있는 모든 DB 목록 조회
    
    Args:
        parent_page_id: Notion 페이지 ID
    """
    url = f"https://api.notion.com/v1/blocks/{parent_page_id}/children?page_size=100"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return {"error": f"API 요청 실패: {response.status_code}"}
    
    data = response.json()
    databases = []
    
    # 블록 중에서 데이터베이스 타입 찾기
    for block in data.get("results", []):
        if block.get("type") == "child_database":
            db_info = {
                "id": block["id"],
                "title": block.get("child_database", {}).get("title", "제목 없음")
            }
            databases.append(db_info)
    
    return databases

def get_notion_database_info(db_id):
    """Notion DB 정보 조회"""
    url = f"https://api.notion.com/v1/databases/{db_id}"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    return {
        "id": data["id"],
        "title": data["title"][0]["plain_text"] if data["title"] else "제목 없음",
        "properties": data["properties"]
    }

