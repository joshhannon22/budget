from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator
from budgeting.models import NormalizedTransaction


class BaseParser(ABC):
    """Abstract parser. Each account-specific parser implements parse()."""

    account_source: str = ""     # subclass must set
    account_type: str = ""       # subclass must set

    @abstractmethod
    def parse(self, csv_path: Path) -> Iterator[NormalizedTransaction]:
        """Yield NormalizedTransaction objects, one per CSV row.

        Implementations must:
        - Sign amounts correctly (negative=outflow, positive=inflow)
        - Generate a deterministic transaction_id
        - Preserve the original row as raw_payload (dict)
        - Raise on unrecognized columns or unparseable dates
        """
        ...

    @staticmethod
    def make_transaction_id(
        account_source: str,
        transaction_date: str,
        amount: str,
        description: str,
        occurrence_index: int = 0,
    ) -> str:
        """Stable hash so re-imports are idempotent.

        occurrence_index disambiguates same-day same-amount duplicates
        (e.g. two $5.00 coffees on the same day at the same shop).
        """
        import hashlib
        key = f"{account_source}|{transaction_date}|{amount}|{description}|{occurrence_index}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
