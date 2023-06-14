# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import copy
import collections
import hashlib
import pprint
import random

from odoo.http import request
from urllib.parse import quote_plus, parse_qsl, parse_qs

from werkzeug import urls

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_vecpay.const import PAYMENT_STATUS_MAPPING
from odoo.addons.payment_vecpay.controllers.main import PaypalController
from datetime import datetime

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # See https://developer.paypal.com/docs/api-basics/notifications/ipn/IPNandPDTVariables/
    # this field has no use in Odoo except for debugging
    paypal_type = fields.Char(string="PayPal Transaction Type")

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Paypal-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'vecpay':
            return res

        base_url = self.provider_id.get_base_url().replace("http://", "https://")
        partner_first_name, partner_last_name = payment_utils.split_partner_name(self.partner_name)
        webhook_url = urls.url_join(base_url, PaypalController._webhook_url)

        webURL = base_url;
		
        itemURL = "user/center/premium";
        lanStr=""
        ignorePayment=""
        ignorePayment += "" if self.provider_id.ecpay_credit else "Credit"
        ignorePayment += "" if self.provider_id.ecpay_webatm else "#WebATM"
        ignorePayment += "" if self.provider_id.ecpay_atm else "#ATM"
        ignorePayment += "" if self.provider_id.ecpay_cvs else "#CVS"
        ignorePayment += "" if self.provider_id.ecpay_barcode else "#BARCODE"
        ignorePayment += "#GooglePay"
        ignorePayment = ignorePayment.lstrip('#')

        ecpay_post = {
            'ChoosePayment': 'ALL',
            'ClientBackURL': webURL + lanStr,
            'CustomField1': self.reference,
            'CustomField2': '',
            'EncryptType': '1',
            'IgnorePayment': ignorePayment,
            'ItemName': f"{self.company_id.name}: {self.reference}",
            'ItemURL': webURL + lanStr + itemURL,
            'MerchantID': self.provider_id._get_ecpay_config().get('MerchantID'),
            'MerchantTradeDate': datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            'MerchantTradeNo': self.reference.replace("-", "v") + "r" + str(random.randrange(1000, 9999)),
            'OrderResultURL': urls.url_join(base_url, PaypalController._return_url),
            'PaymentType': "aio",
            'Remark': '',
            'ReturnURL': webhook_url,
            'StoreID': 'Odoo',
            'TotalAmount': int(self.amount),
            'TradeDesc': 'Odoo付款',
        }
        CheckMacValue = {'CheckMacValue':self.generate_check_value(ecpay_post)}
        #_logger.info("paypal CheckMacValue = " + self.generate_check_value(ecpay_post))
        ecpay_post.update(CheckMacValue)
            

        resultJson = {
            'address1': self.partner_address,
            'amount': self.amount,
            'business': self.provider_id.paypal_email_account,
            'city': self.partner_city,
            'country': self.partner_country_id.code,
            'currency_code': self.currency_id.name,
            'email': self.partner_email,
            'first_name': partner_first_name,
            'handling': self.fees,
            'MerchantID': self.provider_id._get_ecpay_config().get('MerchantID'),
            'item_name': f"{self.company_id.name}: {self.reference}",
            'item_number': self.reference,
            'last_name': partner_last_name,
            'lc': self.partner_lang,
            'notify_url': webhook_url,
            'return_url': urls.url_join(base_url, PaypalController._return_url),
            'state': self.partner_state_id.name,
            'zip_code': self.partner_zip,
            'api_url': self.provider_id._paypal_get_api_url(),
        }
        resultJson.update(ecpay_post)

        return resultJson

    def generate_check_value(self, params):
        # _logger.info("paypal generate_check_value = " + pprint.pformat(params))
        hashKey = self.provider_id._get_ecpay_config().get('HashKey')
        hashIV = self.provider_id._get_ecpay_config().get('HashIV')

        _params = copy.deepcopy(params)

        if _params.get('CheckMacValue'):
            _params.pop('CheckMacValue')

        encrypt_type = int(_params.get('EncryptType', 1))

        ordered_params = collections.OrderedDict(
            sorted(_params.items(), key=lambda k: k[0].lower()))

        encoding_lst = []
        encoding_lst.append('HashKey=%s&' % hashKey)
        encoding_lst.append(''.join(
            ['{}={}&'.format(key, value) for key, value in ordered_params.items()]))
        encoding_lst.append('HashIV=%s' % hashIV)

        safe_characters = '-_.!*()'

        encoding_str = ''.join(encoding_lst)
        encoding_str = quote_plus(
            str(encoding_str), safe=safe_characters).lower()

        check_mac_value = ''
        if encrypt_type == 1:
            check_mac_value = hashlib.sha256(
                encoding_str.encode('utf-8')).hexdigest().upper()
        elif encrypt_type == 0:
            check_mac_value = hashlib.md5(
                encoding_str.encode('utf-8')).hexdigest().upper()

        return check_mac_value

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        _logger.info('paypal _get_tx_from_notification_data:notification_data.reference= %s',
                     notification_data.get('reference'))
        """ Override of payment to find the transaction based on Paypal data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'vecpay' or len(tx) == 1:
            return tx
        _logger.info('vecpay _get_tx_from_notification_data 2:notification_data.reference= %s',
                     notification_data.get('reference'))

        reference = notification_data.get('reference')
        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'vecpay')])
        if not tx:
            raise ValidationError(
                "ecpay: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on dummy data.

        Note: self.ensure_one()

        :param dict notification_data: The dummy notification data
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'vecpay':
            return

        if self.tokenize:
            # The reasons why we immediately tokenize the transaction regardless of the state rather
            # than waiting for the payment method to be validated ('authorized' or 'done') like the
            # other payment providers do are:
            # - To save the simulated state and payment details on the token while we have them.
            # - To allow customers to create tokens whose transactions will always end up in the
            #   said simulated state.
            self._demo_tokenize_from_notification_data(notification_data)

        state = notification_data['simulated_state']
        if state == 'pending':
            self._set_pending()
        elif state == 'done':
            # if self.capture_manually and not notification_data.get('manual_capture'):
            #     self._set_authorized()
            # else:
                self._set_done()
                # Immediately post-process the transaction if it is a refund, as the post-processing
                # will not be triggered by a customer browsing the transaction from the portal.
                if self.operation == 'refund':
                    self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif state == 'cancel':
            self._set_canceled()
        else:  # Simulate an error state.
            self._set_error(_("You selected the following demo payment status: %s", state))
