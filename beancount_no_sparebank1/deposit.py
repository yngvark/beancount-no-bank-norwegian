from beangulp.importers import csvbase
import csv
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence, Tuple, Dict, Any, List

from beancount.core import data
from beancount.core.amount import Amount
from beangulp import extract, similar


class SpareBank1Importer(csvbase.Importer):
    """Importer for SpareBank 1 deposit account CSV statements using csvbase.

    This importer handles CSV statements from SpareBank 1 in Norway.
    It correctly processes Norwegian date and decimal formats, and categorizes
    transactions based on their descriptions.
    """

    # Define a custom dialect for Norwegian CSV format
    class NorwegianDialect(csv.Dialect):
        delimiter = ';'
        quotechar = '"'
        doublequote = True
        skipinitialspace = True
        lineterminator = '\r\n'
        quoting = csv.QUOTE_MINIMAL

    # Configure csvbase options
    dialect = NorwegianDialect
    encoding = 'utf-8-sig'  # Handle BOM if present

    # CSV file has a header line
    names = True

    # Configure column mappings
    date = csvbase.Date('Dato', '%d.%m.%Y')  # Norwegian date format
    narration = csvbase.Column('Beskrivelse')

    # Handle both Inn (credit) and Ut (debit) columns, convert comma to period
    amount = csvbase.CreditOrDebit('Inn', 'Ut', subs={',': '.'})

    # Map the metadata fields
    rentedato = csvbase.Column('Rentedato')
    til_konto = csvbase.Column('Til konto')
    fra_konto = csvbase.Column('Fra konto')

    def __init__(self, account_name: str, currency: str = "NOK",
                 categorization_rules: Optional[Sequence[Tuple[str, str]]] = None,
                 flag: str = "*"):
        """Initialize a SpareBank 1 importer.

        Args:
            account_name: The account to import into (e.g. 'Assets:Bank:SpareBank1:Checking').
            currency: The currency of the account (default: NOK).
            categorization_rules: Optional list of (pattern, account) tuples for automatic categorization.
                Example: [('GITHUB', 'Expenses:Services:Github'), ('Fedex', 'Expenses:Shipping')]
            flag: The flag to use for transactions (default: *).
        """
        self.categorization_rules = categorization_rules or []
        super().__init__(account_name, currency, flag=flag)

    def identify(self, filepath: str) -> bool:
        """Identify if the file is a SpareBank 1 CSV statement."""
        try:
            with open(filepath, encoding=self.encoding) as fd:
                header_line = fd.readline().strip()
                return header_line == "Dato;Beskrivelse;Rentedato;Inn;Ut;Til konto;Fra konto;"
        except:
            return False

    def filename(self, filepath: str) -> str:
        """Generate a meaningful filename."""
        return f"sparebank1.{Path(filepath).name}"

    def deduplicate(self, entries: List[data.Directive], existing: List[data.Directive]) -> None:
        """Mark duplicate entries.

        Args:
            entries: List of entries extracted from the current file
            existing: List of existing entries from the ledger
        """
        # Define a window of days to look for duplicates
        window = datetime.timedelta(days=3)

        # Create the comparator directly with desired settings
        comparator = similar.heuristic_comparator(
            max_date_delta=datetime.timedelta(days=2),  # Tolerance for date differences
            epsilon=Decimal("0.05"),  # 5% tolerance for amount differences
        )

        # Mark duplicates using the function from beangulp.extract
        extract.mark_duplicate_entries(entries, existing, window, comparator)

    def metadata(self, filepath: str, lineno: int, row: Any) -> Dict[str, Any]:
        """Build transaction metadata dictionary."""
        meta = super().metadata(filepath, lineno, row)

        # Add additional metadata if available
        if hasattr(row, 'rentedato') and row.rentedato:
            meta["rentedato"] = row.rentedato
        if hasattr(row, 'til_konto') and row.til_konto:
            meta["to_account"] = row.til_konto
        if hasattr(row, 'fra_konto') and row.fra_konto:
            meta["from_account"] = row.fra_konto

        return meta

    def finalize(self, txn: data.Transaction, row: Any) -> Optional[data.Transaction]:
        """Post-process the transaction with categorization."""
        # If no categorization rules, return transaction unchanged
        if not self.categorization_rules:
            return txn

        # Get the description from the transaction narration
        description = txn.narration

        # Apply first matching categorization rule
        for pattern, account in self.categorization_rules:
            if pattern in description:
                # Create a balancing posting with the opposite amount
                opposite_units = Amount(-txn.postings[0].units.number, self.currency)
                balancing_posting = data.Posting(
                    account, opposite_units, None, None, None, None
                )

                # Add the new posting to the transaction
                txn = txn._replace(postings=txn.postings + [balancing_posting])
                break

        return txn
