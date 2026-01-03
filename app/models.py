from typing import List, Optional
from pydantic import BaseModel


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
