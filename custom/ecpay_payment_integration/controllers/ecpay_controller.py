# -*- coding: utf-8 -*-
import logging
import hashlib
from urllib.parse import quote_plus, urlencode
from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ECPayPaymentController(http.Controller):
    """
    綠界付款 Controller
    
    功能：
    1. 接收綠界付款完成通知 (ReturnURL)
    2. 接收 ATM/超商付款通知 (PaymentInfoURL)
    3. 自動更新 Odoo 訂單狀態
    4. 建立會計付款記錄
    """

    def _generate_check_mac_value(self, params, hash_key, hash_iv):
        """
        產生綠界檢查碼 (CheckMacValue)
        
        演算法：
        1. 依照 A-Z 排序參數（忽略 CheckMacValue）
        2. 組合成 key1=value1&key2=value2 格式
        3. 前後加上 HashKey 和 HashIV
        4. URL encode
        5. 轉小寫
        6. SHA256 加密
        7. 轉大寫
        """
        # 移除 CheckMacValue
        params_copy = {k: v for k, v in params.items() if k != 'CheckMacValue'}
        
        # 按照 A-Z 排序
        sorted_params = sorted(params_copy.items())
        
        # 組合字串
        param_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
        
        # 加上 HashKey 和 HashIV
        raw_str = f'HashKey={hash_key}&{param_str}&HashIV={hash_iv}'
        
        # URL encode
        encoded_str = quote_plus(raw_str)
        
        # 轉小寫
        encoded_str = encoded_str.lower()
        
        # SHA256 加密
        check_mac = hashlib.sha256(encoded_str.encode('utf-8')).hexdigest()
        
        # 轉大寫
        return check_mac.upper()

    def _convert_ecpay_datetime(self, ecpay_datetime_str):
        """
        轉換綠界時間格式為 Odoo 格式
        
        綠界格式：2026/02/13 13:15:30
        Odoo 格式：2026-02-13 13:15:30
        
        Args:
            ecpay_datetime_str: 綠界的時間字串
            
        Returns:
            datetime: Python datetime 物件
        """
        try:
            # 綠界格式：yyyy/MM/dd HH:mm:ss
            return datetime.strptime(ecpay_datetime_str, '%Y/%m/%d %H:%M:%S')
        except Exception as e:
            _logger.warning(f'時間轉換失敗：{ecpay_datetime_str}，錯誤：{str(e)}')
            return datetime.now()

    def _convert_payment_method(self, ecpay_payment_type):
        """
        轉換綠界付款方式為 Odoo 選項
        
        綠界付款方式 → Odoo payment_method
        
        Args:
            ecpay_payment_type: 綠界的 PaymentType
            
        Returns:
            str: Odoo 的 payment_method 值
        """
        # 綠界付款方式對照表
        payment_mapping = {
            'Credit_CreditCard': 'credit_card',         # 信用卡
            'Credit': 'credit_card',                    # 信用卡一次付清
            'Credit_Installment': 'credit_installment', # 信用卡分期
            'WebATM': 'web_atm',                        # 網路 ATM
            'ATM': 'atm',                               # ATM 轉帳
            'CVS': 'cvs',                               # 超商代碼
            'BARCODE': 'barcode',                       # 超商條碼
            'ApplePay': 'apple_pay',                    # Apple Pay
            'GooglePay': 'google_pay',                  # Google Pay
            'LINE_Pay': 'line_pay',                     # LINE Pay
        }
        
        # 查找對應值，如果找不到就回傳 credit_card 作為預設
        result = payment_mapping.get(ecpay_payment_type, 'credit_card')
        _logger.info(f'付款方式轉換：{ecpay_payment_type} → {result}')
        return result

    def _verify_ecpay_data(self, post_data):
        """
        驗證綠界回傳資料的檢查碼
        
        Returns:
            bool: True 表示驗證通過
        """
        try:
            # 取得系統參數中的 HashKey 和 HashIV
            IrConfigParameter = request.env['ir.config_parameter'].sudo()
            hash_key = IrConfigParameter.get_param('ecpay.hash_key')
            hash_iv = IrConfigParameter.get_param('ecpay.hash_iv')
            
            if not hash_key or not hash_iv:
                _logger.error('綠界 HashKey 或 HashIV 未設定')
                return False
            
            # 計算檢查碼
            received_mac = post_data.get('CheckMacValue', '')
            calculated_mac = self._generate_check_mac_value(post_data, hash_key, hash_iv)
            
            if received_mac != calculated_mac:
                _logger.error(f'檢查碼驗證失敗！收到：{received_mac}，計算：{calculated_mac}')
                return False
            
            return True
            
        except Exception as e:
            _logger.error(f'驗證綠界資料時發生錯誤：{str(e)}')
            return False

    def _create_payment_record(self, rental_order, payment_data):
        """
        建立會計付款記錄
        
        Args:
            rental_order: 租賃訂單物件
            payment_data: 綠界回傳的付款資料
        """
        try:
            payment_obj = request.env['account.payment'].sudo()
            
            # 建立付款記錄
            payment_vals = {
                'payment_type': 'inbound',  # 收款
                'partner_id': rental_order.partner_id.id,
                'amount': float(payment_data.get('TradeAmt', 0)),
                'currency_id': request.env.company.currency_id.id,
                'date': datetime.now(),
                'ref': f"綠界付款 - {payment_data.get('TradeNo', '')}",
                'journal_id': self._get_payment_journal().id,
            }
            
            payment = payment_obj.create(payment_vals)
            payment.action_post()  # 確認付款
            
            _logger.info(f'已建立付款記錄：{payment.name}，金額：{payment.amount}')
            
            return payment
            
        except Exception as e:
            _logger.error(f'建立付款記錄時發生錯誤：{str(e)}')
            return False

    def _get_payment_journal(self):
        """取得預設的付款日記簿"""
        journal = request.env['account.journal'].sudo().search([
            ('type', '=', 'bank'),
            ('company_id', '=', request.env.company.id)
        ], limit=1)
        
        if not journal:
            # 如果沒有銀行日記簿，使用現金
            journal = request.env['account.journal'].sudo().search([
                ('type', '=', 'cash'),
                ('company_id', '=', request.env.company.id)
            ], limit=1)
        
        return journal

    @http.route('/ecpay/payment/notify', type='http', auth='public', methods=['POST'], csrf=False)
    def ecpay_payment_notify(self, **post):
        """
        接收綠界付款完成通知 (ReturnURL)
        
        支援付款方式：
        - 信用卡
        - WebATM
        - 信用卡分期
        
        流程：
        1. 驗證檢查碼
        2. 查詢訂單
        3. 更新訂單狀態
        4. 建立付款記錄
        5. 觸發自動化動作（通知）
        6. 回傳 1|OK 給綠界
        """
        _logger.info(f'收到綠界付款通知：{post}')
        
        try:
            # 1. 驗證檢查碼
            if not self._verify_ecpay_data(post):
                _logger.error('檢查碼驗證失敗')
                return '0|CheckMacValue Error'
            
            # 2. 取得付款資訊
            merchant_trade_no = post.get('MerchantTradeNo')  # 訂單編號
            trade_no = post.get('TradeNo')  # 綠界交易編號
            rtn_code = post.get('RtnCode')  # 交易狀態（1=成功）
            trade_amt = post.get('TradeAmt')  # 交易金額
            payment_date = post.get('PaymentDate')  # 付款時間
            payment_type = post.get('PaymentType')  # 付款方式
            
            _logger.info(f'訂單編號：{merchant_trade_no}，交易編號：{trade_no}，狀態：{rtn_code}')
            
            # 3. 查詢租賃訂單
            rental_order = request.env['sale.order'].sudo().search([
                ('name', '=', merchant_trade_no)
            ], limit=1)
            
            if not rental_order:
                _logger.error(f'找不到訂單：{merchant_trade_no}')
                return '0|Order Not Found'
            
            # 4. 檢查交易狀態
            if rtn_code != '1':
                # 付款失敗
                rental_order.write({
                    'payment_state': 'failed',
                    'payment_transaction_id': trade_no,
                    'payment_method': payment_type,
                    'payment_note': f"付款失敗：{post.get('RtnMsg', '')}",
                })
                _logger.warning(f'付款失敗：{post.get("RtnMsg", "")}')
                return '1|OK'  # 仍然回傳成功，避免綠界重送
            
            # 5. 更新訂單狀態為「已付款」
            # 轉換綠界時間格式
            payment_datetime = self._convert_ecpay_datetime(payment_date)
            # 轉換付款方式
            payment_method_value = self._convert_payment_method(payment_type)
            
            rental_order.write({
                'payment_state': 'paid',
                'state': 'sale',  # 確認訂單
                'payment_transaction_id': trade_no,
                'payment_date': payment_datetime,
                'payment_method': payment_method_value,
                'payment_auto_registered': True,
                'payment_note': f'綠界自動對帳完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            })
            
            _logger.info(f'訂單 {merchant_trade_no} 已更新為已付款狀態')
            
            # 6. 嘗試建立付款記錄（如果失敗也繼續）
            try:
                self._create_payment_record(rental_order, post)
            except Exception as e:
                _logger.warning(f'建立付款記錄失敗（不影響訂單狀態）：{str(e)}')
            
            # 7. 記錄付款日誌
            rental_order.message_post(
                body=f"""
                <p><strong>✅ 綠界付款成功</strong></p>
                <ul>
                    <li>交易編號：{trade_no}</li>
                    <li>付款金額：NT$ {trade_amt}</li>
                    <li>付款時間：{payment_date}</li>
                    <li>付款方式：{payment_type}</li>
                    <li>自動對帳：是</li>
                </ul>
                """,
                message_type='notification'
            )
            
            # 8. 觸發自動化動作（在 Automated Actions 中設定）
            # - 發送 LINE 通知給客戶
            # - 建立客服待辦事項
            
            # 9. 回傳成功給綠界
            return '1|OK'
            
        except Exception as e:
            _logger.error(f'處理綠界付款通知時發生錯誤：{str(e)}', exc_info=True)
            return '0|System Error'

    @http.route('/ecpay/atm/notify', type='http', auth='public', methods=['POST'], csrf=False)
    def ecpay_atm_notify(self, **post):
        """
        接收 ATM/超商付款通知 (PaymentInfoURL)
        
        流程：
        1. 客戶選擇 ATM 付款時，先收到虛擬帳號（此時訂單狀態為 waiting_payment）
        2. 客戶完成轉帳後，綠界會呼叫這個 API
        3. 更新訂單為已付款
        
        特殊欄位：
        - BankCode: 銀行代碼
        - vAccount: 虛擬帳號
        - ExpireDate: 繳費期限
        """
        _logger.info(f'收到 ATM 付款通知：{post}')
        
        try:
            # 驗證檢查碼
            if not self._verify_ecpay_data(post):
                _logger.error('ATM 付款通知檢查碼驗證失敗')
                return '0|CheckMacValue Error'
            
            merchant_trade_no = post.get('MerchantTradeNo')
            trade_no = post.get('TradeNo')
            rtn_code = post.get('RtnCode')
            trade_amt = post.get('TradeAmt')
            payment_date = post.get('PaymentDate')
            
            # 查詢訂單
            rental_order = request.env['sale.order'].sudo().search([
                ('name', '=', merchant_trade_no)
            ], limit=1)
            
            if not rental_order:
                _logger.error(f'找不到訂單：{merchant_trade_no}')
                return '0|Order Not Found'
            
            # 檢查是否為「取得虛擬帳號」的通知（RtnCode = 2）
            if rtn_code == '2':
                # 更新虛擬帳號資訊
                rental_order.write({
                    'payment_state': 'waiting_payment',
                    'atm_bank_code': post.get('BankCode'),
                    'atm_v_account': post.get('vAccount'),
                    'atm_expire_date': post.get('ExpireDate'),
                    'payment_transaction_id': trade_no,
                })
                
                _logger.info(f'訂單 {merchant_trade_no} 已取得 ATM 虛擬帳號')
                
                # 記錄到訂單
                rental_order.message_post(
                    body=f"""
                    <p><strong>📋 ATM 虛擬帳號已產生</strong></p>
                    <ul>
                        <li>銀行代碼：{post.get('BankCode')}</li>
                        <li>虛擬帳號：{post.get('vAccount')}</li>
                        <li>繳費期限：{post.get('ExpireDate')}</li>
                        <li>應付金額：NT$ {trade_amt}</li>
                    </ul>
                    <p>⚠️ 請在期限內完成轉帳</p>
                    """,
                    message_type='notification'
                )
                
                return '1|OK'
            
            # 檢查是否為「付款完成」的通知（RtnCode = 1）
            if rtn_code == '1':
                # 更新為已付款
                rental_order.write({
                    'payment_state': 'paid',
                    'state': 'sale',
                    'payment_date': payment_date,
                    'payment_method': 'atm',
                    'payment_auto_registered': True,
                    'payment_note': f'ATM 轉帳完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                })
                
                _logger.info(f'訂單 {merchant_trade_no} ATM 付款完成')
                
                # 建立付款記錄
                self._create_payment_record(rental_order, post)
                
                # 記錄到訂單
                rental_order.message_post(
                    body=f"""
                    <p><strong>✅ ATM 付款成功</strong></p>
                    <ul>
                        <li>交易編號：{trade_no}</li>
                        <li>付款金額：NT$ {trade_amt}</li>
                        <li>付款時間：{payment_date}</li>
                        <li>自動對帳：是</li>
                    </ul>
                    """,
                    message_type='notification'
                )
                
                return '1|OK'
            
            # 其他狀態
            _logger.warning(f'ATM 通知未知狀態：{rtn_code}')
            return '1|OK'
            
        except Exception as e:
            _logger.error(f'處理 ATM 付款通知時發生錯誤：{str(e)}', exc_info=True)
            return '0|System Error'

    @http.route('/ecpay/cvs/notify', type='http', auth='public', methods=['POST'], csrf=False)
    def ecpay_cvs_notify(self, **post):
        """
        接收超商代碼付款通知
        
        流程類似 ATM：
        1. 先收到繳費代碼
        2. 客戶繳費後收到付款完成通知
        """
        _logger.info(f'收到超商付款通知：{post}')
        
        try:
            # 驗證檢查碼
            if not self._verify_ecpay_data(post):
                _logger.error('超商付款通知檢查碼驗證失敗')
                return '0|CheckMacValue Error'
            
            merchant_trade_no = post.get('MerchantTradeNo')
            trade_no = post.get('TradeNo')
            rtn_code = post.get('RtnCode')
            trade_amt = post.get('TradeAmt')
            payment_date = post.get('PaymentDate')
            
            # 查詢訂單
            rental_order = request.env['sale.order'].sudo().search([
                ('name', '=', merchant_trade_no)
            ], limit=1)
            
            if not rental_order:
                return '0|Order Not Found'
            
            # 取得繳費代碼（RtnCode = 10100）
            if rtn_code == '10100':
                rental_order.write({
                    'payment_state': 'waiting_payment',
                    'cvs_payment_no': post.get('PaymentNo'),
                    'cvs_expire_date': post.get('ExpireDate'),
                    'payment_transaction_id': trade_no,
                })
                
                _logger.info(f'訂單 {merchant_trade_no} 已取得超商繳費代碼')
                
                rental_order.message_post(
                    body=f"""
                    <p><strong>🏪 超商繳費代碼已產生</strong></p>
                    <ul>
                        <li>繳費代碼：{post.get('PaymentNo')}</li>
                        <li>繳費期限：{post.get('ExpireDate')}</li>
                        <li>應付金額：NT$ {trade_amt}</li>
                    </ul>
                    <p>⚠️ 請至超商完成繳費</p>
                    """,
                    message_type='notification'
                )
                
                return '1|OK'
            
            # 付款完成（RtnCode = 1）
            if rtn_code == '1':
                rental_order.write({
                    'payment_state': 'paid',
                    'state': 'sale',
                    'payment_date': payment_date,
                    'payment_method': 'cvs',
                    'payment_auto_registered': True,
                    'payment_note': f'超商付款完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                })
                
                _logger.info(f'訂單 {merchant_trade_no} 超商付款完成')
                
                # 建立付款記錄
                self._create_payment_record(rental_order, post)
                
                rental_order.message_post(
                    body=f"""
                    <p><strong>✅ 超商付款成功</strong></p>
                    <ul>
                        <li>交易編號：{trade_no}</li>
                        <li>付款金額：NT$ {trade_amt}</li>
                        <li>付款時間：{payment_date}</li>
                        <li>自動對帳：是</li>
                    </ul>
                    """,
                    message_type='notification'
                )
                
                return '1|OK'
            
            return '1|OK'
            
        except Exception as e:
            _logger.error(f'處理超商付款通知時發生錯誤：{str(e)}', exc_info=True)
            return '0|System Error'


class ECPayPaymentPageController(http.Controller):
    """
    綠界付款頁面 Controller
    
    功能：顯示付款頁面，用 POST 表單提交到綠界
    """

    @http.route('/ecpay/payment/page/<int:order_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def ecpay_payment_page(self, order_id, **kwargs):
        """
        顯示付款頁面
        
        這個頁面會：
        1. 準備綠界付款參數
        2. 產生自動提交的 POST 表單
        3. 自動跳轉到綠界付款頁面
        """
        try:
            # 查詢訂單
            sale_order = request.env['sale.order'].sudo().browse(order_id)
            
            if not sale_order.exists():
                return '<h1>訂單不存在</h1>'
            
            # 取得系統參數
            IrConfigParameter = request.env['ir.config_parameter'].sudo()
            merchant_id = IrConfigParameter.get_param('ecpay.merchant_id')
            hash_key = IrConfigParameter.get_param('ecpay.hash_key')
            hash_iv = IrConfigParameter.get_param('ecpay.hash_iv')
            test_mode = IrConfigParameter.get_param('ecpay.test_mode', 'True') == 'True'
            
            if not all([merchant_id, hash_key, hash_iv]):
                return '<h1>綠界設定不完整，請聯絡客服</h1>'
            
            # 設定綠界 API URL
            if test_mode:
                api_url = 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5'
            else:
                api_url = 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
            
            # 準備付款資料
            from datetime import datetime
            
            base_url = 'https://www.lensking.com.tw'
            
            payment_data = {
                'MerchantID': merchant_id,
                'MerchantTradeNo': sale_order.name,
                'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
                'PaymentType': 'aio',
                'TotalAmount': str(int(sale_order.amount_total)),
                'TradeDesc': f'時光幻鏡租借-{sale_order.name}',
                'ItemName': sale_order.name,
                'ReturnURL': f'{base_url}/ecpay/payment/notify',
                'OrderResultURL': f'{base_url}/payment/success',
                'ClientBackURL': base_url,
                'ChoosePayment': 'Credit#WebATM#ATM#ApplePay',  # 信用卡、WebATM、ATM、ApplePay
                'PaymentInfoURL': f'{base_url}/ecpay/atm/notify',
                'NeedExtraPaidInfo': 'Y',
                'EncryptType': '1',
            }
            
            # 產生檢查碼
            check_mac = self._generate_check_mac(payment_data, hash_key, hash_iv)
            payment_data['CheckMacValue'] = check_mac
            
            # 產生 HTML 表單
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>跳轉付款頁面</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                    }}
                    h1 {{
                        color: #333;
                        margin-bottom: 20px;
                    }}
                    .info {{
                        color: #666;
                        margin: 20px 0;
                    }}
                    .spinner {{
                        border: 4px solid #f3f3f3;
                        border-top: 4px solid #667eea;
                        border-radius: 50%;
                        width: 40px;
                        height: 40px;
                        animation: spin 1s linear infinite;
                        margin: 20px auto;
                    }}
                    @keyframes spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔒 安全付款</h1>
                    <div class="spinner"></div>
                    <p class="info">正在跳轉至綠界付款頁面...</p>
                    <p class="info">訂單編號：{sale_order.name}</p>
                    <p class="info">金額：NT$ {int(sale_order.amount_total):,}</p>
                </div>
                
                <form id="ecpayForm" method="post" action="{api_url}">
            """
            
            # 加入所有參數
            for key, value in payment_data.items():
                html += f'    <input type="hidden" name="{key}" value="{value}">\n'
            
            html += """
                </form>
                
                <script>
                    // 自動提交表單
                    document.getElementById('ecpayForm').submit();
                </script>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            _logger.error(f'顯示付款頁面時發生錯誤：{str(e)}', exc_info=True)
            return f'<h1>系統錯誤</h1><p>{str(e)}</p>'
    
    def _generate_check_mac(self, params, hash_key, hash_iv):
        """產生綠界檢查碼"""
        import hashlib
        from urllib.parse import quote_plus
        
        # 移除 CheckMacValue
        params_copy = {k: v for k, v in params.items() if k != 'CheckMacValue'}
        
        # 按照 A-Z 排序
        sorted_params = sorted(params_copy.items())
        
        # 組合字串
        param_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
        
        # 加上 HashKey 和 HashIV
        raw_str = f'HashKey={hash_key}&{param_str}&HashIV={hash_iv}'
        
        # URL encode 並轉小寫
        encoded_str = quote_plus(raw_str).lower()
        
        # SHA256 加密並轉大寫
        return hashlib.sha256(encoded_str.encode('utf-8')).hexdigest().upper()


class ECPaySuccessPageController(http.Controller):
    """
    付款成功頁面 Controller
    """

    @http.route('/payment/success', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def payment_success_page(self, **kwargs):
        """
        顯示付款成功頁面
        """
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>付款成功 - 時光幻鏡</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft JhengHei', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    padding: 20px;
                }
                .container {
                    background: white;
                    border-radius: 20px;
                    padding: 60px 40px;
                    text-align: center;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    max-width: 500px;
                    width: 100%;
                }
                .success-icon {
                    width: 100px;
                    height: 100px;
                    background: #4CAF50;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 30px;
                    animation: scaleIn 0.5s ease-out;
                }
                .success-icon::after {
                    content: '✓';
                    color: white;
                    font-size: 60px;
                    font-weight: bold;
                }
                @keyframes scaleIn {
                    0% {
                        transform: scale(0);
                    }
                    50% {
                        transform: scale(1.1);
                    }
                    100% {
                        transform: scale(1);
                    }
                }
                h1 {
                    color: #333;
                    font-size: 32px;
                    margin-bottom: 15px;
                }
                .message {
                    color: #666;
                    font-size: 18px;
                    margin-bottom: 30px;
                    line-height: 1.6;
                }
                .info-box {
                    background: #f5f5f5;
                    border-radius: 10px;
                    padding: 20px;
                    margin: 30px 0;
                    text-align: left;
                }
                .info-item {
                    display: flex;
                    justify-content: space-between;
                    padding: 10px 0;
                    border-bottom: 1px solid #e0e0e0;
                }
                .info-item:last-child {
                    border-bottom: none;
                }
                .info-label {
                    color: #888;
                    font-size: 14px;
                }
                .info-value {
                    color: #333;
                    font-weight: 600;
                    font-size: 14px;
                }
                .button {
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 15px 40px;
                    border-radius: 25px;
                    text-decoration: none;
                    font-size: 16px;
                    font-weight: 600;
                    transition: transform 0.2s, box-shadow 0.2s;
                    margin-top: 20px;
                }
                .button:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
                }
                .footer {
                    margin-top: 30px;
                    color: #999;
                    font-size: 14px;
                }
                .contact {
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #e0e0e0;
                    color: #666;
                    font-size: 14px;
                }
                .contact a {
                    color: #667eea;
                    text-decoration: none;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon"></div>
                <h1>付款成功！</h1>
                <p class="message">
                    感謝您的付款！<br>
                    我們已收到您的款項，訂單處理中
                </p>
                
                <div class="info-box">
                    <div class="info-item">
                        <span class="info-label">付款狀態</span>
                        <span class="info-value" style="color: #4CAF50;">✓ 已完成</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">處理狀態</span>
                        <span class="info-value">系統自動對帳中</span>
                    </div>
                </div>

                <div class="message">
                    <strong>📅 取件資訊</strong><br>
                    請於租借日期當天前往店面取件<br>
                    <br>
                    <strong>📍 取件地點</strong><br>
                    桃園市中壢區義民路一段129號<br>
                    <br>
                    <strong>📞 聯絡電話</strong><br>
                    0905-527-577
                </div>

                <a href="https://www.lensking.com.tw" class="button">返回首頁</a>

                <div class="contact">
                    如有任何問題，歡迎聯絡我們<br>
                    LINE: <a href="https://line.me/ti/p/@lens-king">@lens-king</a><br>
                    Email: <a href="mailto:lensfantasy@gmail.com">lensfantasy@gmail.com</a>
                </div>

                <div class="footer">
                    © 2026 時光幻鏡攝影器材租借<br>
                    感謝您的支持
                </div>
            </div>
        </body>
        </html>
        """
        return html
