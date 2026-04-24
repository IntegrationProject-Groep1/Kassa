# -*- coding: utf-8 -*-
{
    'name': 'Kassa POS Custom',
    'version': '1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Customizations for the Kassa POS',
    'description': """
        Customizations for the Desideriushogeschool Kassa Integratie:
        - Story 9: Badge scanning & auto-select customer via bus
        - Story 17: Age restriction pop-ups (alcohol)
        - Story 19: Blocking anonymous Badge Wallet transactions
        - Story 21: Auto-update and auto-select registration customers
    """,
    'author': 'IntegrationProject-Groep1',
    'depends': ['point_of_sale', 'bus'],
    'data': [],
    'assets': {
        # Odoo 16/17 uses point_of_sale._assets_pos for POS frontend code
        'point_of_sale._assets_pos': [
            'kassa_pos_custom/static/src/js/pos_custom.js',
            'kassa_pos_custom/static/src/xml/pos_custom.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
