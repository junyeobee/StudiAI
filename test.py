import asyncio
import httpx
from typing import Dict, Any
import json

# Notion API 설정
NOTION_API_KEY = "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" # 여기에 실제 API 키를 입력하세요
NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_API_VERSION,
    "Content-Type": "application/json"
}

# async def update_notion_page(page_id: str, content: str) -> Dict[str, Any]:
#     """노션 페이지의 속성을 업데이트합니다."""
#     try:
#         json_data = create_page_update_json(content)
#         print(f"요청 데이터: {json.dumps(json_data, ensure_ascii=False)}")
#         async with httpx.AsyncClient() as client:
#             response = await client.patch(
#                 f"{NOTION_BASE_URL}/blocks/{page_id}/children",
#                 headers=HEADERS,
#                 json={"children": [json_data]}
#             )
#             response.raise_for_status()
#             return {"success": True, "message": "페이지 업데이트 성공", "data": response.json()}
#     except Exception as e:
#         return {"success": False, "error": str(e)}

async def update_notion_page(page_id: str, content: str) -> Dict[str, Any]:
    """노션 페이지의 속성을 업데이트합니다."""
    try:
        blocks = create_page_update_json(content)
        print(f"요청 데이터: {json.dumps(blocks, ensure_ascii=False)}")
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{NOTION_BASE_URL}/blocks/{page_id}/children",
                headers=HEADERS,
                json={"children": blocks}  # blocks는 이미 블록 배열이므로 그대로 사용
            )
            response.raise_for_status()
            return {"success": True, "message": "페이지 업데이트 성공", "data": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_page_update_json(content: str) -> dict:
    """노션 페이지 업데이트를 위한 JSON 데이터를 생성합니다."""
    # 헤딩2 블록으로 콘텐츠 추가


    print("start\n\n")

    blocks = []
    lines = content.split("\\n")
    #lines = content.split("\n")  # \\n 대신 \n 사용

    i = 0

    while i < len(lines):
        line = lines[i].strip()
        
        # 빈 줄 건너뛰기
        if not line:
            i += 1
            continue
        
        # H1 제목
        if line.startswith('# '):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                }
            })
        
        # H2 제목
        elif line.startswith('## '):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                }
            })
        
        # H3 제목
        elif line.startswith('### '):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                }
            })
        
        # 리스트 항목
        elif line.startswith('- ') or line.startswith('* '):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                }
            })
        
        # 링크 처리 (URL이 포함된 단순 텍스트 줄)
        elif 'http://' in line or 'https://' in line:
            parts = line.split(': ', 1)
            if len(parts) == 2 and ('http://' in parts[1] or 'https://' in parts[1]):
                label, url = parts
                blocks.append({
                    "object": "block",
                    "type": "bookmark",
                    "bookmark": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{label}: "}},
                            {"type": "text", "text": {"content": url, "link": {"url": url}}}
                        ]
                    }
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })
        
        # 일반 텍스트
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })
        
        i += 1

    print(blocks)


    return blocks
    

    # return {
    #     "object": "block",
    #     "type": "heading_2",
    #     "heading_2": {
    #         "rich_text": [
    #             {
    #                 "type": "text",
    #                 "text": {
    #                     "content": content
    #                 }
    #             }
    #         ]
    #     }
    # }

async def main():
    # 사용자로부터 페이지 ID와 업데이트할 내용 입력 받기
    page_id = "1f15151bc90e80809313d65d8062070b"
    
    content = "# 리액트 중급 - 3주차 학습 계획\\n\\n## 학습 목표\\n- 고급 React Hooks 활용법 학습\\n- Context API를 활용한 전역 상태 관리\\n- React Router를 통한 페이지 라우팅\\n- 다양한 스타일링 기법 익히기\\n- 컴포넌트 성능 최적화 방법 학습\\n- Styled Components\\nhttps://styled-components.com/"
    #content = "# 리액트 중급 - 3주차 학습 계획\n\n## 학습 목표\n- 고급 React Hooks 활용법 학습\n- Context API를 활용한 전역 상태 관리\n- React Router를 통한 페이지 라우팅\n- 다양한 스타일링 기법 익히기\n- 컴포넌트 성능 최적화 방법 학습\n- Styled Components: https://styled-components.com/"


    print(f"노션 페이지 {page_id}를 업데이트합니다...")
    result = await update_notion_page(page_id, content)
    
    if result["success"]:
        print("성공적으로 업데이트되었습니다!")
        print(f"결과: {result['message']}")
    else:
        print(f"업데이트 실패: {result['error']}")

if __name__ == "__main__":
    asyncio.run(main())