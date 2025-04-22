# notion_config.py
NOTION_TOKEN = "ntn_C58327611023N5xC6lu9H8zMIAuC2rmL225aGylmNQdbC7"
NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}