import csv
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from beancount.core import data
from beancount.core.amount import Amount as BeanAmount
from beangulp import extract, similar, utils
from beangulp.importers.csvbase import Column, CreditOrDebit, Date, Importer, Amount

from beangulp.testing import main as test_main

DIALECT_NAME = "banknorwegian"

csv.register_dialect(DIALECT_NAME, delimiter=",")


class DepositAccountImporter(Importer):
    """
    Importer for Bank Norwegian deposit account CSV statements.

    This importer processes CSV statements from Bank Norwegian in Norway, handling
    Norwegian date and decimal formats, and categorizing transactions based on
    narration patterns.
    """

    # Configure csvbase options
    dialect = DIALECT_NAME
    encoding = "utf-8-sig"  # Handle BOM if present

    # CSV file has a header line
    names = True

    # Configure column mappings
    date = Date("TransactionDate", "%d/%m/%Y")  # Norwegian date format
    narration = Column("Text")

    # Type indicates transaction type (Kjøp, Innbetaling, CreditVoucher, etc.)
    type = Column("Type")

    amount = Amount("Amount",
        subs={
            ",": "."   # Convert decimal separator if needed
        }
    )

    # Additional metadata fields
    currency = Column("Currency")
    merchant_area = Column("Merchant Area")
    merchant_category = Column("Merchant Category")
    book_date = Column("BookDate")
    value_date = Column("ValueDate")

    def __init__(
        self,
        account_name: str,
        currency: str = "NOK",
        narration_to_account_mappings: Optional[Sequence[Tuple[str, str]]] = None,
        from_account_mappings: Optional[Sequence[Tuple[str, str]]] = None,
        to_account_mappings: Optional[Sequence[Tuple[str, str]]] = None,
        dedup_window_days: int = 3,
        dedup_max_date_delta: int = 2,
        dedup_epsilon: Decimal = Decimal("0.05"),
        flag: str = "*",
    ):
        """
        Initialize a Bank Norwegian importer.

        Args:
            account_name: The Beancount account name (e.g., "Assets:Bank:BankNorwegian").
            currency: The currency of the account (default: "NOK").
            narration_to_account_mappings: Optional list of (pattern, account) tuples
                to map narration patterns to accounts for categorization.
            from_account_mappings: Optional list of (pattern, account) tuples
                to map 'from account' patterns to accounts for categorization.
            to_account_mappings: Optional list of (pattern, account) tuples
                to map 'to account' patterns to accounts for categorization.
            flag: Transaction flag (default: "*").
            dedup_window_days: Days to look back for duplicates.
            dedup_max_date_delta: Max days difference for duplicate detection.
            dedup_epsilon: Tolerance for amount differences in duplicates.
        """

        self.narration_to_account_mappings = narration_to_account_mappings or []
        self.from_account_mappings = from_account_mappings or []
        self.to_account_mappings = to_account_mappings or []
        self.dedup_window = datetime.timedelta(days=dedup_window_days)
        self.dedup_max_date_delta = datetime.timedelta(days=dedup_max_date_delta)
        self.dedup_epsilon = dedup_epsilon
        super().__init__(account_name, currency, flag=flag)

    def identify(self, filepath: str) -> bool:
        """
        Identify if the file is a Bank Norwegian CSV statement.

        Args:
            filepath: Path to the file to check.

        Returns:
            True if the file is a matching CSV, False otherwise.
        """

        if not utils.is_mimetype(filepath, "text/csv"):
            return False
        return utils.search_file_regexp(
            filepath,
            "TransactionDate,Text,Type,Currency Amount,Currency Rate,Currency,Amount,Merchant Area,Merchant Category,BookDate,ValueDate",
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
        return f"banknorwegian.{Path(filepath).name}"

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

        # Add additional metadata fields from the CSV
        meta["type"] = getattr(row, "type", "")
        meta["currency"] = getattr(row, "currency", "")
        meta["merchant_area"] = getattr(row, "merchant_area", "")
        meta["merchant_category"] = getattr(row, "merchant_category", "")
        meta["book_date"] = getattr(row, "book_date", "")
        meta["value_date"] = getattr(row, "value_date", "")

        # Filter out empty values to keep metadata clean
        return {k: v for k, v in meta.items() if v != ""}

    def finalize(self, txn: data.Transaction, row: Any) -> Optional[data.Transaction]:
        """
        Post-process the transaction with categorization based on transaction type,
        narration patterns, and account mappings.

        Transaction types:
        - "Kjøp" (Purchase): Negative amount, categorize by narration
        - "Innbetaling" (Deposit): Positive amount, often from another account
        - "CreditVoucher" (Refund/Credit): Positive amount, categorize by narration

        Mapping precedence:
        1. Narration patterns are checked first
        2. From account patterns for deposits
        3. Default categorization based on transaction type

        Args:
            txn: The transaction object to finalize.
            row: The row object from the CSV.

        Returns:
            The modified transaction, or None if invalid.
        """
        if not txn.postings:
            return txn  # No changes if no postings

        # Get transaction type
        transaction_type = getattr(row, "type", "")

        # Check narration patterns first (highest precedence)
        for pattern, account in self.narration_to_account_mappings:
            if pattern in txn.narration:
                opposite_units = BeanAmount(-txn.postings[0].units.number, self.currency)
                balancing_posting = data.Posting(
                    account, opposite_units, None, None, None, None
                )
                return txn._replace(postings=txn.postings + [balancing_posting])

        # Special handling for deposit ("Innbetaling") transactions
        if transaction_type == "Innbetaling":
            # Check from_account mappings for deposits
            for pattern, account in self.from_account_mappings:
                if pattern in txn.narration:
                    opposite_units = BeanAmount(-txn.postings[0].units.number, self.currency)
                    balancing_posting = data.Posting(
                        account, opposite_units, None, None, None, None
                    )
                    return txn._replace(postings=txn.postings + [balancing_posting])

            # Default deposit categorization if no mapping found
            opposite_units = BeanAmount(-txn.postings[0].units.number, self.currency)
            balancing_posting = data.Posting(
                "Income:Unknown", opposite_units, None, None, None, None
            )
            return txn._replace(postings=txn.postings + [balancing_posting])

        # Special handling for refunds/credits ("CreditVoucher")
        elif transaction_type == "CreditVoucher":
            # Refunds usually go to expenses accounts
            opposite_units = BeanAmount(-txn.postings[0].units.number, self.currency)
            balancing_posting = data.Posting(
                "Expenses:Refunds", opposite_units, None, None, None, None
            )
            return txn._replace(postings=txn.postings + [balancing_posting])

        # Default for purchases ("Kjøp") and other types
        else:
            # Default to uncategorized expenses
            opposite_units = BeanAmount(-txn.postings[0].units.number, self.currency)
            balancing_posting = data.Posting(
                "Expenses:Uncategorized", opposite_units, None, None, None, None
            )
            return txn._replace(postings=txn.postings + [balancing_posting])

def main():
    """Entry point for the command-line interface."""
    # This enables the testing CLI commands
    test_main(DepositAccountImporter(
        'Assets:Bank:BankNorwegian:Checking',
        narration_to_account_mappings=[
            ('KIWI', 'Expenses:Groceries'),
            ('MENY', 'Expenses:Groceries'),
            ('VINMONOPOLET', 'Expenses:Alcohol'),
            ('STATOIL', 'Expenses:Transportation:Fuel'),
            ('RUTER', 'Expenses:Transportation:PublicTransport'),
            ('POWER', 'Expenses:Electronics'),
            ('XXL SPORT', 'Expenses:Clothing:SportGear'),
            ('FINN.NO', 'Expenses:Services:Online'),
            ('GET/TELIA', 'Expenses:Utilities:Internet'),
            ('HUSLEIE', 'Expenses:Housing:Rent'),
            ('SKATTEETATEN', 'Income:Government:TaxReturn'),
            ('Lønn', 'Income:Salary'),
            ('OBS BYGG', 'Expenses:HomeImprovement'),
            ('Overføring', 'Assets:Bank:BankNorwegian:Transfer'),
        ],
        from_account_mappings=[
            ('12345678901', 'Assets:Bank:BankNorwegian:Checking')
        ],
        to_account_mappings=[
            ('98712345678', 'Assets:Bank:BankNorwegian:Savings')
        ]
    ))


if __name__ == '__main__':
    main()
