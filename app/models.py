from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class BigExpense(BaseModel):
    name: str
    amount: float
    due_month: str  # YYYY-MM
    priority: int = 1

class MonthPlanRequest(BaseModel):
    month: str  # YYYY-MM
    expected_income_base: float
    expected_income_upside: float = 0
    known_big_expenses: List[BigExpense] = Field(default_factory=list)
    mode: str = "balanced"

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
    type: Literal["income", "expense", "transfer"]
    category: str
    account: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    month: str  # YYYY-MM

class TransactionBatch(BaseModel):
    items: List[Transaction]

class HoldingItem(BaseModel):
    asset_type: Literal["cash","bank","fd","ppf","stock","mf","other"]
    name: str
    qty: float = 0
    avg_cost: float = 0
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
    month: str
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    win_count: int = 0
    loss_count: int = 0
    notes: Optional[str] = None

class NotionUpsertRequest(BaseModel):
    month: str
    notion_parent_page_id: Optional[str] = None
    sheet_url: Optional[str] = None
