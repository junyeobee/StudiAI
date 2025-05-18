import requests

def get_top_level_pages(access_token):
    # API 엔드포인트 및 헤더 설정
    url = "https://api.notion.com/v1/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # 페이지만 검색하도록 필터 설정
    payload = {
        "filter": {
            "value": "page",
            "property": "object"
        }
    }
    
    # API 요청 보내기
    response = requests.post(url, json=payload, headers=headers)
    
    # 응답 처리
    if response.status_code == 200:
        data = response.json()
        # 최상위 페이지만 필터링 (parent.type이 workspace인 것)
        top_level_pages = [
            page for page in data["results"] 
            if page.get("parent", {}).get("type") == "workspace"
        ]
        
        # 결과 출력
        for page in top_level_pages:
            title = page.get("properties", {}).get("title", {}).get("title", [])
            title_text = title[0].get("plain_text") if title else "제목 없음"
            print(f"- {title_text} (ID: {page['id']})")
        
        return top_level_pages
    else:
        print(f"오류: {response.status_code}, {response.text}")
        return []

# 사용 예시
access_token = "ntn_g5832761102v4ymAD7qdZ6MWELYvJFlg4nMqnhnuyVlbNS"
top_level_pages = get_top_level_pages(access_token)