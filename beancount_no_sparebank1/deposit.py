import csv
import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import beangulp
from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.number import D
from beangulp import mimetypes
from beangulp import extract, similar

from .deposit_categorizer import DepositCategorizer


class DepositAccountImporter(beangulp.Importer):
    """Importer for SpareBank 1 deposit account CSV statements.

    This importer handles CSV statements from SpareBank 1 in Norway.
    It correctly processes Norwegian date and decimal formats, and categorizes
    transactions based on their descriptions.
    """

    def __init__(
        self,
        account_name: str,
        currency: str = "NOK",
        categorization_rules: Optional[Sequence[Tuple[str, str]]] = None,
        flag: str = "*",
    ):
        """Initialize a SpareBank 1 importer.

        Args:
            account_name: The account to import into (e.g. 'Assets:Bank:SpareBank1:Checking').
            currency: The currency of the account (default: NOK).
            categorization_rules: Optional list of (pattern, account) tuples for automatic categorization.
                Example: [('GITHUB', 'Expenses:Services:Github'), ('Fedex', 'Expenses:Shipping')]
            flag: The flag to use for transactions (default: *).
        """
        self.account_name = account_name
        self.currency = currency
        self.categorizer = DepositCategorizer(categorization_rules) if categorization_rules else None
        self.flag = flag

    def identify(self, filepath: str) -> bool:
        """Identify if the file is a SpareBank 1 CSV statement.

        Args:
            filepath: The path to the file.

        Returns:
            True if this file is a SpareBank 1 CSV statement.
        """
        mimetype, encoding = mimetypes.guess_type(filepath)
        if mimetype != "text/csv":
            return False

        # Check for the characteristic header
        with open(filepath, "r", encoding="utf-8-sig") as file:
            header = file.readline().strip()
            expected_header = "Dato;Beskrivelse;Rentedato;Inn;Ut;Til konto;Fra konto;"
            return header == expected_header

    def account(self, filepath: str) -> str:
        """Return the account for the given file.

        Args:
            filepath: The path to the file.

        Returns:
            The account name.
        """
        return self.account_name

    def filename(self, filepath: str) -> str:
        """Generate a meaningful filename.

        Args:
            filepath: The path to the file.

        Returns:
            A meaningful filename.
        """
        return f"sparebank1.{Path(filepath).name}"

    def date(self, filepath: str) -> Optional[datetime.date]:
        """Extract the statement date.

        Args:
            filepath: The path to the file.

        Returns:
            The most recent transaction date.
        """
        # Try to get the most recent transaction date
        entries = self.extract(filepath, [])
        if entries:
            return max(
                entry.date for entry in entries if isinstance(entry, data.Transaction)
            )
        return None

    def deduplicate(self, entries, existing):
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
            epsilon=Decimal("0.05")                     # 5% tolerance for amount differences
        )

        # Mark duplicates using the function from beangulp.extract (not similar)
        extract.mark_duplicate_entries(entries, existing, window, comparator)

    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse a Norwegian formatted amount.

        Args:
            amount_str: The amount string.

        Returns:
            The decimal amount.
        """
        if not amount_str:
            return D("0")
        # Remove quotes and convert Norwegian decimal format to standard
        clean_str = amount_str.strip('"').replace(".", "").replace(",", ".")
        return D(clean_str)

    def extract(
        self, filepath: str, existing_entries: List[data.Directive]
    ) -> List[data.Directive]:
        """Extract transactions from a SpareBank 1 CSV file.

        Args:
            filepath: The path to the CSV file.
            existing_entries: Existing entries to prevent duplicates.

        Returns:
            A list of beancount directives.
        """
        entries = []

        # Open the CSV file with proper encoding and delimiter
        with open(filepath, "r", encoding="utf-8") as file:
            # Skip the header line
            next(file)

            # Create a CSV reader with semicolon delimiter
            reader = csv.reader(file, delimiter=";")

            for index, row in enumerate(reader, 1):
                # Skip empty rows
                if not row or not row[0]:
                    continue

                # Parse the data from the row
                date_str, description, rentedato, inn, ut, til_konto, fra_konto, _ = row

                date = datetime.datetime.strptime(
                    date_str.strip('"'), "%d.%m.%Y"
                ).date()

                # Parse the description - use it directly as narration
                narration = description.strip('"')

                # Parse both incoming and outgoing amounts
                inn_decimal = self._parse_amount(inn)
                ut_decimal = self._parse_amount(ut)

                # Use inn if present and non-zero, otherwise use ut (with its original sign)
                amount_decimal = inn_decimal if inn_decimal != D("0") else ut_decimal

                # Create metadata
                meta = data.new_metadata(filepath, index)

                # Add additional metadata if available
                if til_konto:
                    meta["to_account"] = til_konto.strip('"')
                if fra_konto:
                    meta["from_account"] = fra_konto.strip('"')
                if rentedato:
                    meta["rentedato"] = rentedato.strip('"')

                # Create the transaction
                amount_obj = Amount(amount_decimal, self.currency)
                posting = data.Posting(self.account_name, amount_obj, None, None, None, None)

                transaction = data.Transaction(
                    meta=meta,
                    date=date,
                    flag=self.flag,
                    payee=None,  # No payee extraction
                    narration=narration,
                    tags=set(),
                    links=set(),
                    postings=[posting],
                )

                # Apply the categorizer if provided
                if self.categorizer:
                    row_dict = {
                        "Dato": date_str,
                        "Beskrivelse": description,
                        "Rentedato": rentedato,
                        "Inn": inn,
                        "Ut": ut,
                        "Til konto": til_konto,
                        "Fra konto": fra_konto,
                    }
                    transaction = self.categorizer.categorize(transaction, row_dict)

                entries.append(transaction)

        return entries

