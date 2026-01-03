import os
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials
from notion_client import Client as NotionClient

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_gspread_client():
    """
    Render env var expected:
      GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT = full JSON string
    """
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT"]
    info = json.loads(sa_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@lru_cache(maxsize=1)
def _open_sheet():
    sheet_id = os.environ["SHEET_ID"]
    gc = _get_gspread_client()
    return gc.open_by_key(sheet_id)


def _worksheet(tab_name: str):
    sh = _open_sheet()
    return sh.worksheet(tab_name)


@lru_cache(maxsize=64)
def _sheet_headers(tab_name: str) -> List[str]:
    ws = _worksheet(tab_name)
    headers = ws.row_values(1)
    if not headers:
        raise RuntimeError(f"Sheet '{tab_name}' has no header row in row 1")
    return headers


def sheets_append_row_by_header(tab_name: str, row_dict: Dict[str, Any]):
    """
    Appends a row aligned to the header row (Row 1) of the given worksheet.
    Any missing header keys are written as blank.
    Any extra keys in row_dict are ignored.
    """
    ws = _worksheet(tab_name)
    headers = _sheet_headers(tab_name)

    row = []
    for h in headers:
        v = row_dict.get(h, "")
        # Convert lists/dicts to JSON strings for *_json columns
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        row.append(v)

    ws.append_row(row, value_input_option="USER_ENTERED")


def sheets_get_all_records(tab_name: str) -> List[Dict[str, Any]]:
    """
    Reads all rows as dicts, using Row 1 as headers.
    """
    ws = _worksheet(tab_name)
    # gspread returns "" for empty cells
    return ws.get_all_records()


def notion_client() -> NotionClient:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN not configured")
    return NotionClient(auth=token)


def notion_upsert_month_page(month: str, parent_page_id: str, sheet_url: Optional[str] = None):
    """
    Creates a month page under parent page. (Simple create for now; no true upsert.)
    """
    notion = notion_client()
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

from typing import Any, Dict, List, Optional

def _col_to_a1(col_idx_1based: int) -> str:
    """1-based column index -> Excel column letters (1=A, 27=AA)."""
    col = col_idx_1based
    s = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        s = chr(65 + rem) + s
    return s


def sheets_update_row_by_header(tab_name: str, row_number_1based: int, row_dict: Dict[str, Any]):
    """
    Updates a specific row number (e.g., row 2 for singleton Settings) aligned to headers.
    Missing keys become blank.
    """
    ws = _worksheet(tab_name)
    headers = _sheet_headers(tab_name)

    row = []
    for h in headers:
        v = row_dict.get(h, "")
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        row.append(v)

    end_col = _col_to_a1(len(headers))
    rng = f"A{row_number_1based}:{end_col}{row_number_1based}"
    ws.update(rng, [row], value_input_option="USER_ENTERED")


def sheets_upsert_row_by_key(tab_name: str, key_column: str, key_value: str, row_dict: Dict[str, Any]):
    """
    Upsert a row in a tab using a unique key column value.
    - If key exists: updates that row
    - Else: appends a new row
    """
    ws = _worksheet(tab_name)
    headers = _sheet_headers(tab_name)

    if key_column not in headers:
        raise RuntimeError(f"'{key_column}' not found in header row for tab '{tab_name}'")

    key_col_idx = headers.index(key_column) + 1  # 1-based
    col_vals = ws.col_values(key_col_idx)  # includes header in row 1

    # Find existing row (skip header)
    target_row = None
    for i, v in enumerate(col_vals[1:], start=2):  # start at row 2
        if str(v).strip() == str(key_value).strip():
            target_row = i
            break

    if target_row:
        sheets_update_row_by_header(tab_name, target_row, row_dict)
        return {"action": "updated", "row": target_row}

    # append if not found
    sheets_append_row_by_header(tab_name, row_dict)
    return {"action": "inserted"}

