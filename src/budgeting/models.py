from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class NormalizedTransaction(BaseModel):
    """The contract every parser must produce."""
    transaction_id: str          # deterministic hash
    account_source: str          # 'pnc', 'fidelity', 'amex', 'discover', 'capital_one'
    account_type: str            # 'checking', 'investment', 'credit_card'
    transaction_date: date
    post_date: Optional[date] = None
    description_raw: str
    amount: Decimal              # signed: negative=outflow, positive=inflow
    category_source: Optional[str] = None
    is_pending: bool = False
    raw_payload: dict            # original CSV row as dict, for raw_transactions storage
    source_file: str             # relative path
    row_number: int              # 1-indexed row in source file

    model_config = {"arbitrary_types_allowed": True}
