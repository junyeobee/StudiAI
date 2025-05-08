# 페이지 속성
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