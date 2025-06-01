# 페이지 속성
def extract_text_from_rich_text(rich_text: list[dict]) -> str:
    """rich_text 배열에서 순수 텍스트 추출"""
    if not rich_text:
        return ""
    
    text_parts = []
    for text_obj in rich_text:
        if text_obj.get("type") == "text":
            text_parts.append(text_obj.get("text", {}).get("content", ""))
    
    return "".join(text_parts)

async def get_toggle_content(toggle_block_id: str, make_request_func) -> str:
    """토글 블록의 하위 내용을 텍스트로 변환하여 반환"""
    try:
        content_parts = []
        cursor = None
        
        while True:
            resp = await make_request_func(
                "GET",
                f"blocks/{toggle_block_id}/children",
                params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            )
            
            blocks = resp.get("results", [])
            for block in blocks:
                block_text = await convert_block_to_markdown(block, make_request_func)
                if block_text:
                    content_parts.append(block_text)
            
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        
        return "\n".join(content_parts)
        
    except Exception as e:
        # 로깅은 호출하는 쪽에서 처리
        return ""

async def convert_block_to_markdown(block: dict, make_request_func) -> str:
    """Notion 블록을 마크다운 텍스트로 변환"""
    block_type = block.get("type")
    
    if block_type == "paragraph":
        return extract_text_from_rich_text(block.get("paragraph", {}).get("rich_text", []))
    
    elif block_type == "heading_1":
        text = extract_text_from_rich_text(block.get("heading_1", {}).get("rich_text", []))
        return f"# {text}"
    
    elif block_type == "heading_2":
        text = extract_text_from_rich_text(block.get("heading_2", {}).get("rich_text", []))
        return f"## {text}"
    
    elif block_type == "heading_3":
        text = extract_text_from_rich_text(block.get("heading_3", {}).get("rich_text", []))
        return f"### {text}"
    
    elif block_type == "bulleted_list_item":
        text = extract_text_from_rich_text(block.get("bulleted_list_item", {}).get("rich_text", []))
        return f"• {text}"
    
    elif block_type == "numbered_list_item":
        text = extract_text_from_rich_text(block.get("numbered_list_item", {}).get("rich_text", []))
        return f"1. {text}"
    
    elif block_type == "code":
        text = extract_text_from_rich_text(block.get("code", {}).get("rich_text", []))
        language = block.get("code", {}).get("language", "")
        return f"```{language}\n{text}\n```"
    
    elif block_type == "quote":
        text = extract_text_from_rich_text(block.get("quote", {}).get("rich_text", []))
        return f"> {text}"
    
    elif block_type == "callout":
        text = extract_text_from_rich_text(block.get("callout", {}).get("rich_text", []))
        emoji = block.get("callout", {}).get("icon", {}).get("emoji", "💡")
        return f"{emoji} {text}"
    
    elif block_type == "divider":
        return "---"
    
    # 하위 블록이 있는 경우 재귀 처리
    if block.get("has_children"):
        current_text = extract_text_from_rich_text(
            block.get(block_type, {}).get("rich_text", [])
        )
        children_text = await get_toggle_content(block["id"], make_request_func)
        return f"{current_text}\n{children_text}" if current_text else children_text
    
    return ""

def serialize_page_props(props: dict) -> dict:
    r = {}
    if "title" in props:
        r["학습 제목"] = {
            "title": [{"text": {"content": props["title"]}}]
        }
    if "date" in props:
        r["날짜"] = {
            "date": {"start": props["date"]}  # ISO 문자열
        }
    if "status" in props:
        r["진행 상태"] = {
            "select": {"name": props["status"]}
        }
    if "revisit" in props:
        r["복습 여부"] = {
            "checkbox": props["revisit"]
        }
    return r

# 페이지 컨텐츠 중 필요한 부분만 추려내기
def block_content(block: dict) -> dict:
    btype = block["type"]
    base = {"id": block["id"], "type": btype, "children": block["has_children"]}
    match btype:
        case "heading_2" | "heading_3" | "heading_1":
            base["text"] = block[btype]["rich_text"][0]["text"]["content"]
        case "quote":
            base["text"] = block["quote"]["rich_text"][0]["text"]["content"]
        case "to_do":
            base["text"] = block["to_do"]["rich_text"][0]["text"]["content"]
            base["checked"] = block["to_do"]["checked"]
        case "code":
            base["text"] = block["code"]["rich_text"][0]["text"]["content"]
            base["lang"] = block["code"]["language"]
        case _:
            base["text"] = ""
    return base

def _process_markdown_line(line: str) -> dict | None:
    """
    단일 마크다운 라인을 Notion 블록으로 변환합니다.
    
    Args:
        line: 처리할 마크다운 라인
        
    Returns:
        Notion 블록 딕셔너리 또는 None
    """
    if not line.strip():
        return None
    
    # 라인 시작 패턴으로 블록 타입 결정
    match line:
        # 헤딩 처리 (### 가장 먼저 체크)
        case s if s.startswith('### '):
            return {
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": s[4:]}}]
                }
            }
        case s if s.startswith('## '):
            return {
                "object": "block", 
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": s[3:]}}]
                }
            }
        case s if s.startswith('# '):
            return {
                "object": "block",
                "type": "heading_1", 
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": s[2:]}}]
                }
            }
        
        # 인용문 처리
        case s if s.startswith('> '):
            return {
                "object": "block",
                "type": "quote", 
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": s[2:]}}]
                }
            }
        
        # 체크리스트 처리 (- [ ], - [x]) - 일반 리스트보다 먼저 체크
        case s if s.startswith('- [') and len(s) > 4 and s[3] in ' x' and s[4] == ']':
            is_checked = s[3] == 'x'
            content = s[6:] if len(s) > 6 else ""
            return {
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": content}}],
                    "checked": is_checked
                }
            }
        
        # 번호 리스트 처리
        case s if len(s) > 2 and s[0].isdigit() and s[1:3] == '. ':
            return {
                "object": "block", 
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": s[3:]}}]
                }
            }
        
        # 리스트 + URL 처리 (- 라벨: URL 형태)
        case s if (s.startswith('- ') or s.startswith('* ')) and ('http://' in s or 'https://' in s):
            content = s[2:]  # '- ' 제거
            return _process_list_with_url(content)
        
        # 일반 리스트 처리
        case s if s.startswith('- ') or s.startswith('* '):
            return {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": s[2:]}}]
                }
            }
        
        # URL만 있는 라인 처리 (리스트가 아닌 경우)
        case s if 'http://' in s or 'https://' in s:
            return _process_url_line(s)
        
        # 일반 텍스트
        case _:
            return _process_complex_text(line)


def _normalize_language(language: str) -> str:
    """
    코드 블록 언어를 Notion API에서 지원하는 언어로 변환합니다.
    """
    language_mapping = {
        'jsx': 'javascript',
        'ts': 'typescript',
        'js': 'javascript',
        'py': 'python',
        'rb': 'ruby',
        'sh': 'shell',
        'bash': 'shell',
        'zsh': 'shell',
        'yml': 'yaml',
        'vue': 'html',
        'svelte': 'html',
        'md': 'markdown',
        'dockerfile': 'docker'
    }
    
    return language_mapping.get(language.lower(), language.lower())


# Markdown을 Notion 블록으로 변환
def markdown_to_notion_blocks(content: str) -> list[dict]:
    """
    Markdown 텍스트를 Notion API 블록 구조로 변환합니다.
    
    지원하는 Markdown 구문:
    - # H1 제목
    - ## H2 제목 
    - ### H3 제목
    - - 또는 * 불릿 리스트
    - 1. 번호 리스트
    - \n\n → divider 블록
    - URL이 포함된 텍스트 (bookmark 블록으로 변환)
    - 코드 블록, 인용문
    - 일반 텍스트 (paragraph 블록)
    
    Args:
        content: Markdown 형식의 텍스트 문자열
        
    Returns:
        Notion API 블록 구조의 리스트
    """
    blocks = []
    
    # \n\n을 구분선으로 처리하기 위해 먼저 분할
    sections = content.split('\n\n')
    
    for section_idx, section in enumerate(sections):
        if not section.strip():
            continue
            
        # 각 섹션을 라인별로 처리
        lines = section.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 빈 줄 건너뛰기
            if not line:
                i += 1
                continue
            
            # 코드 블록 특별 처리 (여러 라인)
            if line.startswith('```'):
                language = line[3:].strip() or "plain text"
                # 언어 정규화
                language = _normalize_language(language)
                
                code_lines = []
                i += 1
                
                # 코드 블록 끝까지 읽기
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                code_content = '\n'.join(code_lines)
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code_content}}],
                        "language": language
                    }
                })
                i += 1  # ``` 닫는 라인 건너뛰기
                continue
            
            # 일반 라인 처리
            block = _process_markdown_line(line)
            if block is not None:
                blocks.append(block)
            
            i += 1
        
        # 섹션 간 구분선 추가 (마지막 섹션 제외)
        if section_idx < len(sections) - 1 and section.strip():
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
    
    return blocks


def _process_list_with_url(content: str) -> dict:
    """리스트 항목 중 URL이 포함된 경우를 bookmark 블록으로 처리합니다."""
    import re
    
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, content)
    
    if urls:
        url = urls[0].strip()
        # "라벨: URL" 형태에서 라벨 추출
        colon_patterns = [': ', ' : ', ':']
        for pattern in colon_patterns:
            if pattern in content:
                parts = content.split(pattern, 1)
                if len(parts) == 2 and url in parts[1]:
                    label = parts[0].strip()
                    # bookmark 블록으로 생성
                    return {
                        "object": "block",
                        "type": "bookmark",
                        "bookmark": {
                            "url": url,
                            "caption": [{"type": "text", "text": {"content": label}}] if label else []
                        }
                    }
        
        # 콜론 패턴이 없으면 URL 앞부분을 라벨로 사용
        url_start = content.find(url)
        if url_start > 0:
            label = content[:url_start].strip()
            return {
                "object": "block",
                "type": "bookmark", 
                "bookmark": {
                    "url": url,
                    "caption": [{"type": "text", "text": {"content": label}}] if label else []
                }
            }
    
    # URL이 없으면 일반 리스트로 처리
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": content}}]
        }
    }


def _process_url_line(line: str) -> dict:
    """URL이 포함된 라인을 bookmark 블록으로 처리합니다."""
    import re
    
    # URL 패턴 매칭 (http:// 또는 https://)
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, line)
    
    if urls:
        # URL이 발견된 경우 - 첫 번째 URL 사용
        url = urls[0].strip()
        
        # "라벨: URL" 또는 "라벨 : URL" 형식 체크
        colon_patterns = [': ', ' : ', ':']
        for pattern in colon_patterns:
            if pattern in line:
                parts = line.split(pattern, 1)
                if len(parts) == 2 and url in parts[1]:
                    label = parts[0].strip()
                    return {
                        "object": "block",
                        "type": "bookmark",
                        "bookmark": {
                            "url": url,
                            "caption": [{"type": "text", "text": {"content": label}}] if label else []
                        }
                    }
        
        # 콜론 패턴이 없으면 URL 앞부분을 라벨로 사용
        url_start = line.find(url)
        if url_start > 0:
            label = line[:url_start].strip().rstrip(':').strip()
            return {
                "object": "block",
                "type": "bookmark",
                "bookmark": {
                    "url": url,
                    "caption": [{"type": "text", "text": {"content": label}}] if label else []
                }
            }
        else:
            # URL이 맨 앞에 있는 경우 - 라벨 없이 bookmark만
            return {
                "object": "block",
                "type": "bookmark",
                "bookmark": {
                    "url": url,
                    "caption": []
                }
            }
    
    # URL이 없으면 일반 텍스트로 처리 (fallback)
    return {
        "object": "block",
        "type": "paragraph", 
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": line}}]
        }
    }


def _process_complex_text(line: str) -> dict:
    """
    일반 텍스트를 paragraph 블록으로 변환합니다.
    
    Args:
        line: 처리할 텍스트 라인
        
    Returns:
        Notion paragraph 블록
    """
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": line}}]
        }
    }