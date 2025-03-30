import beangulp
import beancount_no_banknorwegian

importers = [
    beancount_no_banknorwegian.deposit.DepositAccountImporter(
        'Assets:Bank:BankNorwegian:Checking',
        currency='NOK',
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
    ),
    beancount_no_banknorwegian.balance.PDFStatementImporter(
        'Assets:Bank:BankNorwegian:Checking',
        currency='NOK'
    ),
]

if __name__ == '__main__':
    ingest = beangulp.Ingest(importers)
    ingest()
