# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Vector 綠界金流模組2',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "Payment Provider: Vector ECPay",
    'depends': ['payment'],
    'images' : ['image/1000x500.png'],
    'author': 'Vector',
    'website': 'https://www.vector.com.tw/',
    'data': [
        'views/payment_paypal_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',

        'data/payment_provider_data.xml',
        'data/payment_paypal_email_data.xml',
    ],
    'application': True,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'price':499,
    'currency':'USD',
}
