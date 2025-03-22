# beancount-no-sparebank1

A Python library for importing SpareBank 1 (Norway) bank data into Beancount accounting format.

![sb12](https://github.com/user-attachments/assets/e0e90691-1430-4bd1-a29d-e1605e30b857)


## Features

- Import transactions from CSV exports of SpareBank 1 deposit accounts
- Extract balance statements from PDF account statements ("kontoutskrift")
- Flexible transaction categorization with customizable rules

## Quick start

``` python
import beangulp
import beancount_no_sparebank1

importers = [
    beancount_no_sparebank1.deposit.DepositAccountImporter(
        'Assets:Checking',
        currency='NOK',
        narration_to_account_mappings=[
            ('GITHUB', 'Expenses:Cloud-Services:Source-Hosting:Github'),
            ('Fedex', 'Expenses:Postage:FedEx'),
            ('FREMTIND', 'Expenses:Insurance'),
        ]
    ),
    beancount_no_sparebank1.balance.PDFStatementImporter(
        'Assets:Checking',
        currency='NOK'
    ),
]

if __name__ == '__main__':
    ingest = beangulp.Ingest(importers)
    ingest()
```

## See also

- [Automatically balancing Beancount DKB transactions](https://sgoel.dev/posts/automatically-balancing-beancount-dkb-transactions/)
- [siddhantgoel/beancount-dkb](https://github.com/siddhantgoel/beancount-dkb)

