import os
import json
from datetime import datetime, timezone, date

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

from .models import (
    MonthPlanRequest, MonthPlanResponse, AllocationLine, WeeklyTarget,
    TransactionBatch, HoldingsUpdateRequest, NetWorthSnapshot, MonthCloseRequest,
    NotionUpsertRequest
)
from .services import (
    sheets_append_row_by_header,
    sheets_get_all_records,
    notion_upsert_month_page,
)

load_dotenv()
app = FastAPI(title="PocketPilot Finance API", version="1.0.0")

bearer = HTTPBearer(auto_error=False)

def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    expected = os.environ.get("X_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="X_API_KEY not configured")
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if creds.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid token")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prev_month(yyyy_mm: str) -> str:
    y, m = map(int, yyyy_mm.split("-"))
    if m == 1:
        return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


def parse_date(s: str) -> Optional[date]:
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


@app.get("/profile")
def get_profile(_: None = Depends(require_auth)):
    return {
        "currency": os.getenv("CURRENCY", "INR"),
        "fiscal_year_start_month": int(os.getenv("FISCAL_YEAR_START_MONTH", "4")),
        "ppf_annual_target": float(os.getenv("PPF_ANNUAL_TARGET", "150000")),
        "default_mode": os.getenv("DEFAULT_MODE", "balanced"),
    }


@app.post("/month/plan", response_model=MonthPlanResponse)
def create_month_plan(req: MonthPlanRequest, _: None = Depends(require_auth)):
    now = utc_now_iso()

    income = req.expected_income_base
    fixed_bills = 20000
    variable_essentials = 30000
    lifestyle = 25000

    # naive goal funding
    goal_contrib = 0
    if req.known_big_expenses:
        goal_contrib = 50000

    emergency = 15000
    sinking = 15000
    investing = max(0, income - (fixed_bills + variable_essentials + lifestyle + emergency + sinking + goal_contrib))

    allocations = [
        AllocationLine(category="Fixed bills", percent=round(fixed_bills/income*100, 2), amount=fixed_bills, notes="Rent + utilities buffer"),
        AllocationLine(category="Variable essentials", percent=round(variable_essentials/income*100, 2), amount=variable_essentials),
        AllocationLine(category="Lifestyle", percent=round(lifestyle/income*100, 2), amount=lifestyle),
        AllocationLine(category="Emergency fund", percent=round(emergency/income*100, 2), amount=emergency),
        AllocationLine(category="Sinking fund", percent=round(sinking/income*100, 2), amount=sinking),
        AllocationLine(category="Goal fund", percent=round(goal_contrib/income*100, 2), amount=goal_contrib, notes="Deadline goals (e.g., scooty)"),
        AllocationLine(category="Investing", percent=round(investing/income*100, 2), amount=investing),
    ]

    weekly = [
        WeeklyTarget(category="Variable essentials", weekly_amount=round(variable_essentials / 4, 2)),
        WeeklyTarget(category="Lifestyle", weekly_amount=round(lifestyle / 4, 2)),
    ]

    extra_income_rule = "60% invest, 25% sinking/goals, 15% fun"
    trading_allowed = goal_contrib == 0
    trading_cap = 0 if not trading_allowed else round(investing * 0.05, 2)

    planned_allocations_json = {
        "allocations": [a.model_dump() for a in allocations],
        "weekly_targets": [w.model_dump() for w in weekly],
        "mode": req.mode,
        "big_expenses": [b.model_dump() for b in req.known_big_expenses],
    }

    # ✅ Writes FULL Budget_Monthly schema (aligned to headers)
    sheets_append_row_by_header("Budget_Monthly", {
        "month": req.month,
        "expected_income_base": req.expected_income_base,
        "expected_income_upside": req.expected_income_upside or 0,
        "fixed_bills_amount": fixed_bills,
        "variable_essentials_amount": variable_essentials,
        "lifestyle_amount": lifestyle,
        "emergency_amount": emergency,
        "sinking_amount": sinking,
        "investing_amount": investing,
        "goal_fund_amount": goal_contrib,
        "planned_allocations_json": planned_allocations_json,
        "extra_income_rule": extra_income_rule,
        "trading_allowed": trading_allowed,
        "trading_cap_amount": trading_cap,
        "notes": "",
        "ruleset_used": req.mode,
        "created_at": now,
    })

    return MonthPlanResponse(
        month=req.month,
        allocations=allocations,
        weekly_targets=weekly,
        extra_income_rule=extra_income_rule,
        trading_cap_allowed=trading_allowed,
        trading_cap_amount=trading_cap
    )


@app.post("/transactions")
def add_transactions(batch: TransactionBatch, _: None = Depends(require_auth)):
    now = utc_now_iso()
    for t in batch.items:
        sheets_append_row_by_header("Transactions", {
            "date": t.date,
            "amount": t.amount,
            "type": t.type,
            "category": t.category,
            "subcategory": t.subcategory or "",
            "account": t.account or "",
            "notes": t.notes or "",
            "month": t.month,
            "tags": ",".join(t.tags or []),
            "created_at": now,
        })
    return {"inserted": len(batch.items)}


@app.post("/holdings")
def upsert_holdings(req: HoldingsUpdateRequest, _: None = Depends(require_auth)):
    now = utc_now_iso()
    for h in req.items:
        sheets_append_row_by_header("Holdings", {
            "as_of_date": req.as_of,
            "asset_type": h.asset_type,
            "name_or_ticker": h.name,
            "qty": h.qty if h.qty is not None else "",
            "avg_cost": h.avg_cost if h.avg_cost is not None else "",
            "current_price": h.current_price if h.current_price is not None else "",
            "current_value": h.current_value,
            "account": h.account or "",
            "notes": h.notes or "",
            "updated_at": now,
        })
    return {"updated": len(req.items)}


@app.post("/networth/snapshot")
def add_networth(req: NetWorthSnapshot, _: None = Depends(require_auth)):
    now = utc_now_iso()
    net = (
        (req.cash_bank + req.fd_total + req.ppf_balance + req.equity_value + req.mf_value + req.other_assets)
        - (req.liabilities_cc + req.liabilities_loans)
    )

    sheets_append_row_by_header("NetWorth_Snapshots", {
        "date": req.date,
        "cash_bank": req.cash_bank,
        "fd_total": req.fd_total,
        "ppf_balance": req.ppf_balance,
        "equity_value": req.equity_value,
        "mf_value": req.mf_value,
        "other_assets": req.other_assets,
        "liabilities_cc": req.liabilities_cc,
        "liabilities_loans": req.liabilities_loans,
        "net_worth": net,
        "notes": req.notes or "",
        "created_at": now,
    })
    return {"net_worth": net}


def _get_latest_networth_for_month(month: str) -> Optional[float]:
    rows = sheets_get_all_records("NetWorth_Snapshots")
    best_dt = None
    best_val = None
    for r in rows:
        ds = str(r.get("date", "")).strip()
        if not ds.startswith(month):
            continue
        dt = parse_date(ds)
        if not dt:
            continue
        try:
            nw = float(r.get("net_worth", "") or 0)
        except Exception:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best_val = nw
    return best_val


@app.post("/month/close")
def close_month(req: MonthCloseRequest, _: None = Depends(require_auth)):
    now = utc_now_iso()

    total = req.win_count + req.loss_count
    win_rate = (req.win_count / total * 100) if total else 0.0

    # Try to auto-compute start/end/net_change from NetWorth_Snapshots
    end_nw = _get_latest_networth_for_month(req.month)
    start_nw = _get_latest_networth_for_month(prev_month(req.month))
    net_change = (end_nw - start_nw) if (end_nw is not None and start_nw is not None) else None

    sheets_append_row_by_header("Performance_Monthly", {
        "month": req.month,
        "start_net_worth": start_nw if start_nw is not None else "",
        "end_net_worth": end_nw if end_nw is not None else "",
        "net_change": net_change if net_change is not None else "",
        "realized_pnl": req.realized_pnl,
        "unrealized_pnl": req.unrealized_pnl,
        "win_count": req.win_count,
        "loss_count": req.loss_count,
        "win_rate": win_rate,
        "notes": req.notes or "",
        "closed_at": now,
    })

    return {"month": req.month, "win_rate": win_rate}


@app.post("/notion/month-page")
def upsert_notion_month_page(req: NotionUpsertRequest, _: None = Depends(require_auth)):
    parent_id = req.notion_parent_page_id or os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_id:
        raise HTTPException(status_code=500, detail="NOTION_PARENT_PAGE_ID not configured")

    res = notion_upsert_month_page(req.month, parent_id, sheet_url=req.sheet_url)
    return {"month": req.month, **res}
