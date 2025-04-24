import requests
from notion_config import headers

def list_databases_in_page(parent_page_id):
    """최상위 페이지에 있는 데이터베이스 목록을 조회합니다."""
    blocks_url = f"https://api.notion.com/v1/blocks/{parent_page_id}/children?page_size=100"
    
    response = requests.get(blocks_url, headers=headers)
    if response.status_code != 200:
        return {"error": f"API 호출 실패: {response.status_code}"}
    
    blocks_data = response.json()
    databases = []
    
    for block in blocks_data.get("results", []):
        if block.get("type") == "child_database":
            database_info = {
                "id": block.get("id"),
                "title": block.get("child_database", {}).get("title", "제목 없음")
            }
            databases.append(database_info)
    
    return databases