import re
from typing import Sequence, Tuple, Optional

from beancount.core import data


class DepositCategorizer:
    """Categorizer for SpareBank 1 deposit account transactions.

    This categorizer allows automatic classification of transactions based on
    regular expression patterns matched against transaction descriptions.
    """

    def __init__(self, rules: Optional[Sequence[Tuple[str, str]]] = None):
        """Initialize with optional categorization rules.

        Args:
            rules: Optional sequence of (pattern, account) tuples.
                Example: [('GITHUB', 'Expenses:Services:Github')]
        """
        self.patterns = []
        if rules is not None:
            for pattern, account in rules:
                self.add(pattern, account)

    def add(self, pattern: str, account: str) -> None:
        """Add a pattern to match transactions against.

        Args:
            pattern: Regular expression to match transaction descriptions.
            account: Account to use for matched transactions.
        """
        self.patterns.append((re.compile(pattern), account))

    def categorize(self, transaction, row_dict):
        """Categorize a transaction based on patterns.

        Args:
            transaction: The transaction to categorize.
            row_dict: The original row data dictionary.

        Returns:
            The categorized transaction with additional postings if matched.
        """
        description = row_dict.get('Beskrivelse', '')

        for pattern, account in self.patterns:
            if re.search(pattern, description):
                # Add a posting to the matched account
                new_postings = list(transaction.postings) + [
                    data.Posting(account, None, None, None, None, None)
                ]

                transaction = data.Transaction(
                    meta=transaction.meta,
                    date=transaction.date,
                    flag=transaction.flag,
                    payee=transaction.payee,
                    narration=transaction.narration,
                    tags=transaction.tags,
                    links=transaction.links,
                    postings=new_postings
                )

                break

        return transaction
