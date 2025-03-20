# beancount-no-sparebank1

``` python
import beangulp
import beancount_no_sparebank1

importers = [
    beancount_no_sparebank1.deposit.DepositAccountImporter(
        'Assets:Checking',
        currency='NOK',
        categorization_rules=[
            ('GITHUB', 'Expenses:Cloud-Services:Source-Hosting:Github'),
            ('Fedex', 'Expenses:Postage:FedEx'),
            ('FREMTIND', 'Expenses:Insurance'),
        ]
    ),
]

if __name__ == '__main__':
    ingest = beangulp.Ingest(importers)
    ingest()
```
