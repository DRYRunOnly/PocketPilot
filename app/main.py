import os
import json
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

from .models import (
    MonthPlanRequest, MonthPlanResponse, AllocationLine, WeeklyTarget,
    TransactionBatch, HoldingsUpdateRequest, NetWorthSnapshot, MonthCloseRequest,
    NotionUpsertRequest, SettingsUpdateRequest, GoalsUpsertRequest, PlanYearUpdateRequest
)
from .services import (
    sheets_append_row_by_header,
    sheets_get_all_records,
    notion_upsert_month_page,
    sheets_append_row_by_header, 
    sheets_get_all_records, 
    sheets_update_row_by_header, 
    sheets_upsert_row_by_key, 
    notion_upsert_month_page
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

@app.get("/settings")
def get_settings(_: None = Depends(require_auth)):
    # Expect settings in row 2 (singleton). If empty, return env defaults.
    rows = sheets_get_all_records("Settings")
    if rows and isinstance(rows, list):
        # get_all_records() returns list of dicts starting from row2
        # if user has one row, it will be rows[0]
        if len(rows) >= 1:
            return rows[0]

    return {
        "currency": os.getenv("CURRENCY", "INR"),
        "fiscal_year_start_month": int(os.getenv("FISCAL_YEAR_START_MONTH", "4")),
        "risk_mode": os.getenv("DEFAULT_MODE", "balanced"),
        "default_allocations_json": {},
        "ppf_annual_target": float(os.getenv("PPF_ANNUAL_TARGET", "150000")),
        "goal_priorities_json": {},
    }


@app.post("/settings")
def update_settings(req: SettingsUpdateRequest, _: None = Depends(require_auth)):
    # Merge existing row (if any) with new values, then write to row 2
    existing = {}
    rows = sheets_get_all_records("Settings")
    if rows and len(rows) >= 1:
        existing = rows[0] or {}

    # Only overwrite fields provided
    merged = dict(existing)
    payload = req.model_dump(exclude_none=True)

    merged.update(payload)

    # Ensure required-ish defaults exist if still missing
    merged.setdefault("currency", os.getenv("CURRENCY", "INR"))
    merged.setdefault("fiscal_year_start_month", int(os.getenv("FISCAL_YEAR_START_MONTH", "4")))
    merged.setdefault("risk_mode", os.getenv("DEFAULT_MODE", "balanced"))
    merged.setdefault("ppf_annual_target", float(os.getenv("PPF_ANNUAL_TARGET", "150000")))
    merged.setdefault("default_allocations_json", {})
    merged.setdefault("goal_priorities_json", {})

    sheets_update_row_by_header("Settings", 2, merged)
    return {"ok": True, "settings": merged}


@app.get("/goals")
def list_goals(_: None = Depends(require_auth)):
    return {"items": sheets_get_all_records("Goals")}


@app.post("/goals/upsert")
def upsert_goals(req: GoalsUpsertRequest, _: None = Depends(require_auth)):
    now = utc_now_iso()

    existing_rows = sheets_get_all_records("Goals")
    existing_created_at = {}
    for r in existing_rows:
        name = str(r.get("goal_name", "")).strip()
        if name:
            existing_created_at[name] = r.get("created_at", "") or ""

    results = []
    for g in req.items:
        created_at = existing_created_at.get(g.goal_name, "") or now
        monthly_required = g.monthly_required if g.monthly_required is not None else ""

        row_dict = {
            "goal_name": g.goal_name,
            "target_amount": g.target_amount,
            "target_date": g.target_date,
            "priority": g.priority,
            "current_saved": g.current_saved,
            "monthly_required": monthly_required,
            "status": g.status,
            "notes": g.notes or "",
            "created_at": created_at,
            "updated_at": now,
        }

        res = sheets_upsert_row_by_key("Goals", "goal_name", g.goal_name, row_dict)
        results.append({"goal_name": g.goal_name, **res})

    return {"ok": True, "results": results}


@app.get("/plan/year")
def get_plan_year(fy: str, _: None = Depends(require_auth)):
    rows = sheets_get_all_records("Plan_Year")
    for r in rows:
        if str(r.get("fy", "")).strip() == fy.strip():
            return r
    return {"fy": fy}


@app.post("/plan/year/upsert")
def upsert_plan_year(req: PlanYearUpdateRequest, _: None = Depends(require_auth)):
    now = utc_now_iso()

    existing_rows = sheets_get_all_records("Plan_Year")
    existing_created_at = {}
    for r in existing_rows:
        fy = str(r.get("fy", "")).strip()
        if fy:
            existing_created_at[fy] = r.get("created_at", "") or ""

    created_at = existing_created_at.get(req.fy, "") or now

    row_dict = {
        "fy": req.fy,
        "ppf_target": req.ppf_target if req.ppf_target is not None else "",
        "ppf_monthly": req.ppf_monthly if req.ppf_monthly is not None else "",
        "total_invest_target": req.total_invest_target if req.total_invest_target is not None else "",
        "emergency_target": req.emergency_target if req.emergency_target is not None else "",
        "big_purchases_json": req.big_purchases_json if req.big_purchases_json is not None else {},
        "notes": req.notes or "",
        "created_at": created_at,
    }

    res = sheets_upsert_row_by_key("Plan_Year", "fy", req.fy, row_dict)
    return {"ok": True, **res}

