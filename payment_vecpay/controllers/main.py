# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

import requests
from werkzeug import urls
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PaypalController(http.Controller):
    _return_url = '/payment/vecpay/return/'
    _webhook_url = '/payment/vecpay/webhook/'

    @http.route(
        _return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False,
        save_session=False
    )
    def paypal_return_from_checkout(self, **payData):
        """ Process the PDT notification sent by PayPal after redirection from checkout.

        The PDT (Payment Data Transfer) notification contains the parameters necessary to verify the
        origin of the notification and retrieve the actual notification data, if PDT is enabled on
        the account. See https://developer.paypal.com/api/nvp-soap/payment-data-transfer/.

        If PDT is not enabled on the account, the origin of the notification cannot be verified and
        the latter directly contains the notification data that must be processed.

        The route accepts both GET and POST requests because PayPal seems to switch between the two
        depending on whether PDT is enabled, whether the customer pays anonymously (without logging
        in on PayPal), whether the customer cancels the payment, whether they click on "Return to
        Merchant" after paying, etc.

        The route is flagged with `save_session=False` to prevent Odoo from assigning a new session
        to the user if they are redirected to this route with a POST request. Indeed, as the session
        cookie is created without a `SameSite` attribute, some browsers that don't implement the
        recommended default `SameSite=Lax` behavior will not include the cookie in the redirection
        request from the payment provider to Odoo. As the redirection to the '/payment/status' page
        will satisfy any specification of the `SameSite` attribute, the session of the user will be
        retrieved and with it the transaction which will be immediately post-processed.
        """
        _logger.info("handling redirection from PayPal with data:\n%s", pprint.pformat(payData))
        odooData = {
            'reference':payData.get('CustomField1')
        }
        if not payData:  # The customer has canceled or paid then clicked on "Return to Merchant"
            pass  # Redirect them to the status page to browse the (currently) draft transaction
        else:
            # Check the origin of the notification
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'vecpay', odooData
            )

            RtnCode = int(payData.get('RtnCode'))

            if RtnCode != 1:
                raise ValidationError(payData.get('RtnMsg'));


            CheckMacValue = payData.get('CheckMacValue');
            if CheckMacValue != tx_sudo.generate_check_value(payData):
                _logger.error(
                    "PayPal did not confirm the origin of the notification with data:\n%s",
                    pprint.pformat(payData),
                )
                pass

            # try:
            #     notification_data = self._verify_pdt_notification_origin(pdt_data, tx_sudo)
            # except Forbidden:
            #     _logger.exception("could not verify the origin of the PDT; discarding it")
            # else:
            #     # Handle the notification data
            # notification_data = {'reference': pdt_data.get('CustomField1'), 'simulated_state': 'done'}
            # tx_sudo._handle_notification_data('vecpay', notification_data)

        return request.redirect('/payment/status')

    def _verify_pdt_notification_origin(self, pdt_data, tx_sudo):
        """ Validate the authenticity of a PDT and return the retrieved notification data.

        The validation is done in four steps:

        1. Make a POST request to Paypal with the `tx`, the GET param received with the PDT,
           and the two other required params `cmd` and `at`.
        2. PayPal sends back a response text starting with either 'SUCCESS' or 'FAIL'. If the
           validation was a success, the notification data are appended to the response text as a
           string formatted as follows: 'SUCCESS\nparam1=value1\nparam2=value2\n...'
        3. Extract the notification data and process these instead of the PDT.
        4. Return an empty HTTP 200 response (done at the end of the route controller).

        See https://developer.paypal.com/docs/api-basics/notifications/payment-data-transfer/.

        :param dict pdt_data: The PDT whose authenticity must be checked.
        :param recordset tx_sudo: The sudoed transaction referenced in the PDT, as a
                                  `payment.transaction` record
        :return: The retrieved notification data
        :raise :class:`werkzeug.exceptions.Forbidden`: if the notification origin can't be verified
        """
        if 'tx' not in pdt_data:  # We did not receive a PDT but directly notification data
            # When PDT is not enabled, PayPal sends directly the notification data instead. We can't
            # verify them but we can process them as is.
            notification_data = pdt_data
        else:
            if not tx_sudo.provider_id.paypal_pdt_token:  # We received PDT but can't verify them
                raise Forbidden("PayPal: The PDT token is not set; cannot verify data origin")
            else:  # The PayPal account is configured to receive PDTs, and the PDT token is set
                # Request a PDT authenticity check and the notification data to PayPal
                url = tx_sudo.provider_id._paypal_get_api_url()
                payload = {
                    'cmd': '_notify-synch',
                    'tx': pdt_data['tx'],
                    'at': tx_sudo.provider_id.paypal_pdt_token,
                }
                try:
                    response = requests.post(url, data=payload, timeout=10)
                    response.raise_for_status()
                except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError):
                    raise Forbidden("PayPal: Encountered an error when verifying PDT origin")
                else:
                    notification_data = self._parse_pdt_validation_response(response.text)
                    if notification_data is None:
                        raise Forbidden("PayPal: The PDT origin was not verified by PayPal")

        return notification_data

    @staticmethod
    def _parse_pdt_validation_response(response_content):
        """ Parse the PDT validation request response and return the parsed notification data.

        :param str response_content: The PDT validation request response
        :return: The parsed notification data
        :rtype: dict
        """
        response_items = response_content.splitlines()
        if response_items[0] == 'SUCCESS':
            notification_data = {}
            for notification_data_param in response_items[1:]:
                key, raw_value = notification_data_param.split('=', 1)
                notification_data[key] = urls.url_unquote_plus(raw_value)
            return notification_data
        return None

    @http.route(_webhook_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def paypal_webhook(self, **payData):
        """ Process the notification data (IPN) sent by PayPal to the webhook.

        The "Instant Payment Notification" is a classical webhook notification.
        See https://developer.paypal.com/api/nvp-soap/ipn/.

        :param dict data: The notification data
        :return: An empty string to acknowledge the notification
        :rtype: str
        """
        _logger.info("notification received from PayPal with data:\n%s", pprint.pformat(payData))
        odooData = {
            'reference':payData.get('CustomField1'),
            'simulated_state': 'done'
        }
        try:
            # Check the origin and integrity of the notification
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'vecpay', odooData
            )
            self._verify_webhook_notification_origin(payData, tx_sudo)

            # Handle the notification data
            tx_sudo._handle_notification_data('vecpay', odooData)
        except ValidationError:  # Acknowledge the notification to avoid getting spammed
            _logger.exception("unable to handle the notification data; skipping to acknowledge")
            odooData.update(simulated_state = 'cancel')
            tx_sudo._handle_notification_data('vecpay', odooData)
        return '1|OK'

    @staticmethod
    def _verify_webhook_notification_origin(payData, tx_sudo):
        """ Check that the notification was sent by PayPal.

        The verification is done in three steps:

        1. POST the complete message back to Paypal with the additional param
           `cmd=_notify-validate`, in the same encoding.
        2. PayPal sends back either 'VERIFIED' or 'INVALID'.
        3. Return an empty HTTP 200 response if the notification origin is verified by PayPal, raise
           an HTTP 403 otherwise.

        See https://developer.paypal.com/docs/api-basics/notifications/ipn/IPNIntro/.

        :param dict notification_data: The notification data
        :param recordset tx_sudo: The sudoed transaction referenced in the notification data, as a
                                        `payment.transaction` record
        :return: None
        :raise: :class:`werkzeug.exceptions.Forbidden` if the notification origin can't be verified
        """
        # Request PayPal for an authenticity check
        # url = tx_sudo.provider_id._paypal_get_api_url()
        # payload = dict(notification_data, cmd='_notify-validate')
        # try:
            # response = requests.post(url, payload, timeout=60)
            # response.raise_for_status()
        # except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as error:
        #     _logger.exception(
        #         "could not verify notification origin at %(url)s with data: %(data)s:\n%(error)s",
        #         {
        #             'url': url,
        #             'data': pprint.pformat(notification_data),
        #             'error': pprint.pformat(error.response.text),
        #         },
        #     )
        #     raise Forbidden()
        # else:
        # 將 POST data 計算驗證是否相符
        CheckMacValue = payData.get('CheckMacValue');
        if CheckMacValue != tx_sudo.generate_check_value(payData):
            _logger.error(
                "PayPal did not confirm the origin of the notification with data:\n%s",
                pprint.pformat(payData),
            )
            raise Forbidden()


        RtnCode = int(payData.get('RtnCode'))

        if RtnCode != 1:
            raise ValidationError(payData.get('RtnMsg'));
