import csv
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from beancount.core import data
from beancount.core.amount import Amount
from beangulp import extract, similar, utils
from beangulp.importers.csvbase import Column, CreditOrDebit, Date, Importer

DIALECT_NAME = "sparebank1"

csv.register_dialect(DIALECT_NAME, delimiter=";")


class DepositAccountImporter(Importer):
    """
    Importer for SpareBank 1 deposit account CSV statements.

    This importer processes CSV statements from SpareBank 1 in Norway, handling
    Norwegian date and decimal formats, and categorizing transactions based on
    narration patterns.
    """

    # Configure csvbase options
    dialect = DIALECT_NAME
    encoding = "utf-8-sig"  # Handle BOM if present

    # CSV file has a header line
    names = True

    # Configure column mappings
    date = Date("Dato", "%d.%m.%Y")  # Norwegian date format
    narration = Column("Beskrivelse")

    # Handle both Inn (credit) and Ut (debit) columns, convert comma to period
    amount = CreditOrDebit("Inn", "Ut", subs={",": "."})

    # Map the metadata fields
    rentedato = Column("Rentedato")
    til_konto = Column("Til konto")
    fra_konto = Column("Fra konto")

    def __init__(
        self,
        account_name: str,
        currency: str = "NOK",
        narration_to_account_mappings: Optional[Sequence[Tuple[str, str]]] = None,
        dedup_window_days: int = 3,
        dedup_max_date_delta: int = 2,
        dedup_epsilon: Decimal = Decimal("0.05"),
        flag: str = "*",
    ):
        """
        Initialize a SpareBank 1 importer.

        Args:
            account_name: The Beancount account name (e.g., "Assets:Bank:SpareBank1").
            currency: The currency of the account (default: "NOK").
            narration_to_account_mappings: Optional list of (pattern, account) tuples
                to map narration patterns to accounts for categorization.
            flag: Transaction flag (default: "*").
            dedup_window_days: Days to look back for duplicates.
            dedup_max_date_delta: Max days difference for duplicate detection.
            dedup_epsilon: Tolerance for amount differences in duplicates.
        """

        self.narration_to_account_mappings = narration_to_account_mappings or []
        self.dedup_window = datetime.timedelta(days=dedup_window_days)
        self.dedup_max_date_delta = datetime.timedelta(days=dedup_max_date_delta)
        self.dedup_epsilon = dedup_epsilon
        super().__init__(account_name, currency, flag=flag)

    def identify(self, filepath: str) -> bool:
        """
        Identify if the file is a SpareBank 1 CSV statement.

        Args:
            filepath: Path to the file to check.

        Returns:
            True if the file is a matching CSV, False otherwise.
        """

        if not utils.is_mimetype(filepath, "text/csv"):
            return False
        return utils.search_file_regexp(
            filepath,
            "Dato;Beskrivelse;Rentedato;Inn;Ut;Til konto;Fra konto",
            encoding=self.encoding,
        )

    def filename(self, filepath: str) -> str:
        """
        Generate a descriptive filename.

        Args:
            filepath: Original file path.

        Returns:
            A string with account name and original filename.
        """
        return f"sparebank1.{Path(filepath).name}"

    def deduplicate(
        self, entries: List[data.Directive], existing: List[data.Directive]
    ) -> None:
        """
        Mark duplicate entries based on configurable parameters.

        Args:
            entries: List of new entries to check for duplicates.
            existing: List of existing entries to compare against.
        """

        comparator = similar.heuristic_comparator(
            max_date_delta=self.dedup_max_date_delta,
            epsilon=self.dedup_epsilon,
        )

        extract.mark_duplicate_entries(entries, existing, self.dedup_window, comparator)

    def metadata(self, filepath: str, lineno: int, row: Any) -> Dict[str, Any]:
        """
        Build transaction metadata dictionary from row data.

        Args:
            filepath: Path to the CSV file.
            lineno: Line number in the file.
            row: Row object containing parsed CSV data.

        Returns:
            Dictionary of metadata key-value pairs.
        """

        meta = super().metadata(filepath, lineno, row)

        meta["rentedato"] = getattr(row, "rentedato", "")
        meta["to_account"] = getattr(row, "til_konto", "")
        meta["from_account"] = getattr(row, "fra_konto", "")

        # Filter out None values to keep metadata clean
        return {k: v for k, v in meta.items() if v != ""}

    def finalize(self, txn: data.Transaction, row: Any) -> Optional[data.Transaction]:
        """
        Post-process the transaction with categorization based on narration.

        Args:
            txn: The transaction object to finalize.
            row: The row object from the CSV.

        Returns:
            The modified transaction, or None if invalid.
        """

        # If no categorization rules, return transaction unchanged
        if not self.narration_to_account_mappings or not txn.postings:
            return txn  # No changes if no mappings or postings

        for pattern, account in self.narration_to_account_mappings:
            if pattern in txn.narration:
                # Create a balancing posting with the opposite amount
                opposite_units = Amount(-txn.postings[0].units.number, self.currency)
                balancing_posting = data.Posting(
                    account, opposite_units, None, None, None, None
                )
                # Append the new posting
                return txn._replace(postings=txn.postings + [balancing_posting])
        return txn  # Return unchanged if no patterns match
