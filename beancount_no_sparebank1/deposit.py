import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple, Dict, Any

import beangulp
from beancount.core import data
from beancount.core.number import D
from beangulp import mimetypes
from beangulp.importers.csvbase import Importer as CSVImporter
from beangulp.importers.csvbase import Date, Column, Amount, Order

from .deposit_categorizer import DepositCategorizer


class DepositAccountImporter(CSVImporter):
    """Importer for SpareBank 1 deposit account CSV statements using csvbase framework.

    This implementation uses Beangulp's specialized CSV handling which provides
    a more declarative approach to defining column mappings and handling
    Norwegian date and decimal formats.
    """

    # Define CSV structure
    encoding = 'utf-8-sig'  # Handle BOM in SpareBank1 CSVs
    dialect = 'excel'
    delimiter = ';'

    # Define column mappings declaratively
    date = Date('Dato', '%d.%m.%Y')
    narration = Column('Beskrivelse')
    rentedato = Column('Rentedato')
    inn = Amount('Inn', subs={'"': '', '\.': '', ',': '.'})
    ut = Amount('Ut', subs={'"': '', '\.': '', ',': '.'})
    til_konto = Column('Til konto')
    fra_konto = Column('Fra konto')

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
            flag: The flag to use for transactions (default: *).
        """
        super().__init__(account_name, currency, flag)
        self.categorizer = DepositCategorizer(categorization_rules) if categorization_rules else None

    def identify(self, filepath: str) -> bool:
        """Identify if the file is a SpareBank 1 CSV statement."""
        mimetype, encoding = mimetypes.guess_type(filepath)
        if mimetype != "text/csv":
            return False

        # Check for the characteristic header
        with open(filepath, "r", encoding="utf-8-sig") as file:
            header = file.readline().strip()
            expected_header = "Dato;Beskrivelse;Rentedato;Inn;Ut;Til konto;Fra konto;"
            return header == expected_header

    def filename(self, filepath: str) -> str:
        """Generate a meaningful filename."""
        return f"sparebank1.{Path(filepath).name}"

    def metadata(self, filepath: str, lineno: int, row: Any) -> Dict:
        """Build transaction metadata from row data."""
        meta = super().metadata(filepath, lineno, row)

        # Add additional metadata if available
        if row.til_konto:
            meta["to_account"] = row.til_konto.strip('"')
        if row.fra_konto:
            meta["from_account"] = row.fra_konto.strip('"')
        if row.rentedato:
            meta["rentedato"] = row.rentedato.strip('"')

        return meta

    def finalize(self, txn: data.Transaction, row: Any) -> data.Transaction:
        """Post-process the transaction to handle amounts and apply categorization."""
        # Handle the inn/ut columns - we need to combine them since
        # csvbase doesn't have a built-in way to handle this special case
        amount = row.inn if row.inn != D("0") else -row.ut

        # Replace the original posting with one using our combined amount
        if txn.postings:
            units = txn.postings[0].units._replace(number=amount)
            txn.postings[0] = txn.postings[0]._replace(units=units)

        # Apply the categorizer if provided
        if self.categorizer:
            # Convert row to the dict format expected by the categorizer
            row_dict = {
                "Dato": row.date.strftime("%d.%m.%Y"),
                "Beskrivelse": row.narration,
                "Rentedato": row.rentedato,
                "Inn": str(row.inn) if row.inn != D("0") else "",
                "Ut": str(row.ut) if row.ut != D("0") else "",
                "Til konto": row.til_konto,
                "Fra konto": row.fra_konto,
            }
            txn = self.categorizer.categorize(txn, row_dict)

        return txn
