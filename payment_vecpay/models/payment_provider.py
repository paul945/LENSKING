# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import hashlib

from odoo import _, api, fields, models

from odoo.addons.payment_vecpay.const import SUPPORTED_CURRENCIES

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('vecpay', "Vector Ecpay")], ondelete={'vecpay': 'set default'})
    paypal_email_account = fields.Char(
        string="Email")
    paypal_seller_account = fields.Char(
        string="Merchant Account ID")
    ecpay_hash_key = fields.Char(
        string="Merchant Hash Key")
    ecpay_hash_iv = fields.Char(
        string="Merchant Hash IV")
    ecpay_credit = fields.Boolean(string="啟用信用卡付款", default=True)
    ecpay_webatm = fields.Boolean(string="啟用網路ATM付款", default=True)
    ecpay_atm = fields.Boolean(string="啟用自動櫃員機付款", default=True)
    ecpay_cvs = fields.Boolean(string="啟用超商代碼付款", default=True)
    ecpay_barcode = fields.Boolean(string="啟用超商條碼付款", default=True)
    is_any_payment_selected = fields.Boolean(string="是否选择付款方式", compute="_compute_is_any_payment_selected", store=True)
    dummy_field = fields.Char(string="請選擇一項付款方式！")

    #=== BUSINESS METHODS ===#
    @api.depends('ecpay_credit', 'ecpay_webatm', 'ecpay_atm', 'ecpay_cvs', 'ecpay_barcode')
    def _compute_is_any_payment_selected(self):
        for record in self:
            record.is_any_payment_selected = any([record.ecpay_credit, record.ecpay_webatm, record.ecpay_atm, record.ecpay_cvs, record.ecpay_barcode])

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, **kwargs):
        """ Override of payment to unlist PayPal providers when the currency is not supported. """
        providers = super()._get_compatible_providers(*args, currency_id=currency_id, **kwargs)

        currency = self.env['res.currency'].browse(currency_id).exists()
        if currency and currency.name not in SUPPORTED_CURRENCIES:
            providers = providers.filtered(lambda p: p.code != 'vecpay')

        return providers



    def _get_ecpay_config(self):
        if self.state == 'enabled':
            return {
                'MerchantID' : self.paypal_seller_account ,
                'HashKey' : self.ecpay_hash_key ,
                'HashIV' : self.ecpay_hash_iv ,
                }
        else:
            return {
                'MerchantID' : '3002607' ,
                'HashKey' : 'pwFHCqoQZGmho4w6' ,
                'HashIV' : 'EkRm7iFT261dpevs' ,
            }

    def _paypal_get_api_url(self):
        if self.state == 'enabled':
            return 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
        else:
            return 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5';

    def _paypal_send_configuration_reminder(self):
        render_template = self.env['ir.qweb']._render(
            'payment_paypal.mail_template_paypal_invite_user_to_configure',
            {'provider': self},
            raise_if_not_found=False,
        )
        if render_template:
            mail_body = self.env['mail.render.mixin']._replace_local_links(render_template)
            mail_values = {
                'body_html': mail_body,
                'subject': _("Add your PayPal account to Odoo"),
                'email_to': self.paypal_email_account,
                'email_from': self.create_uid.email_formatted,
                'author_id': self.create_uid.partner_id.id,
            }
            self.env['mail.mail'].sudo().create(mail_values).send()
