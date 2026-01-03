from typing import Optional, List, Any, Dict
from pydantic import BaseModel

class SettingsUpdateRequest(BaseModel):
    currency: Optional[str] = None
    fiscal_year_start_month: Optional[int] = None
    risk_mode: Optional[str] = None  # e.g. balanced
    default_allocations_json: Optional[Dict[str, Any]] = None
    ppf_annual_target: Optional[float] = None
    goal_priorities_json: Optional[Dict[str, Any]] = None


class GoalItem(BaseModel):
    goal_name: str
    target_amount: float
    target_date: str  # YYYY-MM or YYYY-MM-DD (you decide)
    priority: int = 1
    current_saved: float = 0
    monthly_required: Optional[float] = None
    status: str = "active"  # active/paused/done
    notes: Optional[str] = None


class GoalsUpsertRequest(BaseModel):
    items: List[GoalItem]


class PlanYearUpdateRequest(BaseModel):
    fy: str  # e.g. FY2026 or 2025-26
    ppf_target: Optional[float] = None
    ppf_monthly: Optional[float] = None
    total_invest_target: Optional[float] = None
    emergency_target: Optional[float] = None
    big_purchases_json: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class BigExpense(BaseModel):
    name: str
    amount: float
    due_month: str
    priority: Optional[int] = 1


class MonthPlanRequest(BaseModel):
    month: str  # YYYY-MM
    expected_income_base: float
    expected_income_upside: Optional[float] = 0
    known_big_expenses: List[BigExpense] = []
    mode: Optional[str] = "balanced"


class AllocationLine(BaseModel):
    category: str
    percent: float
    amount: float
    notes: Optional[str] = None


class WeeklyTarget(BaseModel):
    category: str
    weekly_amount: float
    notes: Optional[str] = None


class MonthPlanResponse(BaseModel):
    month: str
    allocations: List[AllocationLine]
    weekly_targets: List[WeeklyTarget]
    extra_income_rule: str
    trading_cap_allowed: bool
    trading_cap_amount: float


class Transaction(BaseModel):
    date: str
    amount: float
    type: str  # income/expense/transfer
    category: str
    subcategory: Optional[str] = None
    account: Optional[str] = None
    notes: Optional[str] = None
    month: str
    tags: List[str] = []


class TransactionBatch(BaseModel):
    items: List[Transaction]


class HoldingItem(BaseModel):
    asset_type: str  # cash/bank/fd/ppf/stock/mf/other
    name: str
    qty: Optional[float] = None
    avg_cost: Optional[float] = None
    current_price: Optional[float] = None
    current_value: float
    account: Optional[str] = None
    notes: Optional[str] = None


class HoldingsUpdateRequest(BaseModel):
    as_of: str  # YYYY-MM-DD
    items: List[HoldingItem]


class NetWorthSnapshot(BaseModel):
    date: str  # YYYY-MM-DD
    cash_bank: float = 0
    fd_total: float = 0
    ppf_balance: float = 0
    equity_value: float = 0
    mf_value: float = 0
    other_assets: float = 0
    liabilities_cc: float = 0
    liabilities_loans: float = 0
    notes: Optional[str] = None


class MonthCloseRequest(BaseModel):
    month: str  # YYYY-MM
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    win_count: int = 0
    loss_count: int = 0
    notes: Optional[str] = None


class NotionUpsertRequest(BaseModel):
    month: str
    notion_parent_page_id: Optional[str] = None
    sheet_url: Optional[str] = None
