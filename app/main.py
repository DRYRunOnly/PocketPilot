import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

from .models import (
    MonthPlanRequest, MonthPlanResponse, AllocationLine, WeeklyTarget,
    TransactionBatch, HoldingsUpdateRequest, NetWorthSnapshot, MonthCloseRequest,
    NotionUpsertRequest
)
from .services import sheets_append_row, notion_upsert_month_page

load_dotenv()

app = FastAPI(title="PocketPilot Finance API", version="1.0.0")

# Proper Bearer auth (adds "Authorize" button in /docs and correct OpenAPI security schema)
bearer = HTTPBearer(auto_error=False)

def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """
    Expects: Authorization: Bearer <token>
    Token must match env var X_API_KEY
    """
    expected = os.environ.get("X_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="X_API_KEY not configured")

    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    if creds.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid token")


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
    income = req.expected_income_base

    # Simple balanced allocation (you can refine later)
    fixed_bills = 20000
    variable_essentials = 30000
    lifestyle = 25000

    # goals due soon (sum any big expenses due this month or next month, but keep it simple)
    goal_fund = 0
    for g in req.known_big_expenses:
        # naive: if due is within next 2 months, start funding
        if g.due_month <= req.month or g.due_month[:7] == req.month:
            goal_fund += g.amount

    # For now: allocate a flat goal contribution if any big expense exists
    goal_contrib = 0
    if req.known_big_expenses:
        goal_contrib = 50000  # you can compute properly later

    emergency = 15000
    sinking = 15000
    investing = max(0, income - (fixed_bills + variable_essentials + lifestyle + emergency + sinking + goal_contrib))

    allocations = [
        AllocationLine(category="Fixed bills", percent=round(fixed_bills/income*100, 2), amount=fixed_bills,
                       notes="Rent + utilities buffer"),
        AllocationLine(category="Variable essentials", percent=round(variable_essentials/income*100, 2),
                       amount=variable_essentials),
        AllocationLine(category="Lifestyle", percent=round(lifestyle/income*100, 2), amount=lifestyle),
        AllocationLine(category="Emergency fund", percent=round(emergency/income*100, 2), amount=emergency),
        AllocationLine(category="Sinking fund", percent=round(sinking/income*100, 2), amount=sinking),
        AllocationLine(category="Goal fund", percent=round(goal_contrib/income*100, 2), amount=goal_contrib,
                       notes="Deadline goals (e.g., scooty)"),
        AllocationLine(category="Investing", percent=round(investing/income*100, 2), amount=investing),
    ]

    weekly = [
        WeeklyTarget(category="Variable essentials", weekly_amount=round(variable_essentials / 4, 2)),
        WeeklyTarget(category="Lifestyle", weekly_amount=round(lifestyle / 4, 2)),
    ]

    # Trading policy: not allowed if goal funding active
    trading_allowed = goal_contrib == 0
    trading_cap = 0 if not trading_allowed else round(investing * 0.05, 2)

    # Persist to sheet
    sheets_append_row("Budget_Monthly", [
        req.month, req.expected_income_base, req.expected_income_upside,
        fixed_bills, variable_essentials, lifestyle, emergency, sinking, investing, goal_contrib, req.mode
    ])

    return MonthPlanResponse(
        month=req.month,
        allocations=allocations,
        weekly_targets=weekly,
        extra_income_rule="60% invest, 25% sinking/goals, 15% fun",
        trading_cap_allowed=trading_allowed,
        trading_cap_amount=trading_cap
    )


@app.post("/transactions")
def add_transactions(batch: TransactionBatch, _: None = Depends(require_auth)):
    for t in batch.items:
        sheets_append_row("Transactions", [
            t.date, t.amount, t.type, t.category, t.account or "", t.notes or "", t.month, ",".join(t.tags)
        ])
    return {"inserted": len(batch.items)}


@app.post("/holdings")
def upsert_holdings(req: HoldingsUpdateRequest, _: None = Depends(require_auth)):
    for h in req.items:
        sheets_append_row("Holdings", [
            req.as_of, h.asset_type, h.name, h.qty, h.avg_cost, h.current_value, h.account or "", h.notes or ""
        ])
    return {"updated": len(req.items)}


@app.post("/networth/snapshot")
def add_networth(req: NetWorthSnapshot, _: None = Depends(require_auth)):
    net = (
        (req.cash_bank + req.fd_total + req.ppf_balance + req.equity_value + req.mf_value + req.other_assets)
        - (req.liabilities_cc + req.liabilities_loans)
    )
    sheets_append_row("NetWorth_Snapshots", [
        req.date, req.cash_bank, req.fd_total, req.ppf_balance, req.equity_value, req.mf_value, req.other_assets,
        req.liabilities_cc, req.liabilities_loans, net, req.notes or ""
    ])
    return {"net_worth": net}


@app.post("/month/close")
def close_month(req: MonthCloseRequest, _: None = Depends(require_auth)):
    total = req.win_count + req.loss_count
    win_rate = (req.win_count / total * 100) if total else 0.0
    sheets_append_row("Performance_Monthly", [
        req.month, req.realized_pnl, req.unrealized_pnl, req.win_count, req.loss_count, win_rate, req.notes or ""
    ])
    return {"month": req.month, "win_rate": win_rate}


@app.post("/notion/month-page")
def upsert_notion_month_page(req: NotionUpsertRequest, _: None = Depends(require_auth)):
    parent_id = req.notion_parent_page_id or os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_id:
        raise HTTPException(status_code=500, detail="NOTION_PARENT_PAGE_ID not configured")

    try:
        res = notion_upsert_month_page(req.month, parent_id, sheet_url=req.sheet_url)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"month": req.month, **res}
