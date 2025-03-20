# beancount-no-sparebank1

``` python
import beancount_sparebank1

CONFIG = [
    beancount_sparebank1.DepositAccountImporter(
        'Assets:Bank:SpareBank1:Checking',
        currency='NOK',
        categorization_rules=[
            ('GITHUB', 'Expenses:Cloud-Services:Source-Hosting:Github'),
            ('Fedex', 'Expenses:Postage:FedEx'),
        ]
    ),
]
```
