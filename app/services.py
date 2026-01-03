import os, json
import gspread
from google.oauth2.service_account import Credentials
from notion_client import Client as NotionClient

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _get_gspread_client():
    # Store full JSON key in Render env var GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT"]
    info = json.loads(sa_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

def sheets_append_row(tab_name: str, row: list):
    sheet_id = os.environ["SHEET_ID"]
    gc = _get_gspread_client()
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)
    ws.append_row(row, value_input_option="USER_ENTERED")

def notion_client():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        return None
    return NotionClient(auth=token)

def notion_upsert_month_page(month: str, parent_page_id: str, sheet_url: str | None = None):
    notion = notion_client()
    if not notion:
        raise RuntimeError("NOTION_TOKEN not configured")

    title = f"{month} — Plan & Close"

    def text(s: str):
        return [{"type": "text", "text": {"content": s}}]

    children = [
        {"object": "block", "type": "callout", "callout": {
            "icon": {"emoji": "📌"},
            "rich_text": text("Expected income (base/upside): — | Planned invest %: — | Planned savings ₹: — | Goal funding: — | Trading cap: —")
        }},

        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Plan")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Category | % | ₹ | Notes (PocketPilot will fill this)")}},
        {"object": "block", "type": "toggle", "toggle": {
            "rich_text": text("Weekly targets"),
            "children": [
                {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": text("Variable essentials: ₹— / week")}},
                {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": text("Lifestyle: ₹— / week")}},
            ]
        }},

        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Actuals")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Income total: ₹— | Expense total: ₹— | Net cashflow: ₹—")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Category breakdown + Plan vs Actual will go here")}},


        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Performance (Wins/Losses)")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Realized P&L: ₹— | Unrealized P&L: ₹—")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Win count: — | Loss count: — | Win rate: —%")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Notes: what worked / what didn’t —")}},


        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Net Worth Snapshot")}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Assets: ₹— | Liabilities: ₹— | Net worth: ₹—")}},


        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Next Month Adjustments")}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": text("Cut: —")}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": text("Increase: —")}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": text("Rule changes: —")}},


        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": text("Links")}},
    ]

    if sheet_url:
        children.append({"object": "block", "type": "bookmark", "bookmark": {"url": sheet_url}})
    else:
        children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": text("Google Sheet link: —")}})

    page = notion.pages.create(
        parent={"page_id": parent_page_id},
        properties={"title": text(title)},
        children=children
    )

    return {"page_id": page["id"], "page_url": page.get("url")}
