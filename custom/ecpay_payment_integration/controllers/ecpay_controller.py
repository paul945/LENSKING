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
            rental_order.write({
                'payment_state': 'paid',
                'state': 'sale',  # 確認訂單
                'payment_transaction_id': trade_no,
                'payment_date': payment_date,
                'payment_method': payment_type,
                'payment_auto_registered': True,
                'payment_note': f'綠界自動對帳完成 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            })
            
            _logger.info(f'訂單 {merchant_trade_no} 已更新為已付款狀態')
            
            # 6. 建立付款記錄
            self._create_payment_record(rental_order, post)
            
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
