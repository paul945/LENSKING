# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """
    擴充租賃訂單模型
    
    新增欄位：
    1. 付款狀態追蹤
    2. 綠界交易資訊
    3. ATM/超商付款資訊
    4. LINE 整合欄位
    """
    _inherit = 'sale.order'

    # ==================== 付款狀態欄位 ====================
    
    payment_state = fields.Selection([
        ('not_paid', '未付款'),
        ('pending', '處理中'),
        ('waiting_payment', '等待付款'),  # ATM/超商已取得代碼，等待繳費
        ('paid', '已付款'),
        ('failed', '付款失敗'),
        ('refunded', '已退款'),
    ], string='付款狀態', default='not_paid', tracking=True,
       help='訂單的付款狀態')

    # ==================== 綠界交易資訊 ====================
    
    payment_transaction_id = fields.Char(
        string='綠界交易編號',
        readonly=True,
        help='綠界回傳的 TradeNo'
    )
    
    payment_date = fields.Datetime(
        string='付款時間',
        readonly=True,
        help='客戶完成付款的時間'
    )
    
    payment_method = fields.Selection([
        ('credit_card', '信用卡'),
        ('credit_installment', '信用卡分期'),
        ('web_atm', '網路 ATM'),
        ('atm', 'ATM 轉帳'),
        ('cvs', '超商代碼'),
        ('barcode', '超商條碼'),
        ('apple_pay', 'Apple Pay'),
        ('google_pay', 'Google Pay'),
        ('line_pay', 'LINE Pay'),
    ], string='付款方式', readonly=True)
    
    payment_auto_registered = fields.Boolean(
        string='自動登記',
        default=False,
        help='是否由系統自動登記付款（非人工）'
    )
    
    payment_manual_verified = fields.Boolean(
        string='人工覆核',
        default=False,
        help='是否已經過人工覆核確認'
    )
    
    payment_note = fields.Text(
        string='付款備註',
        help='付款相關備註或錯誤訊息'
    )

    # ==================== ATM 付款資訊 ====================
    
    atm_bank_code = fields.Char(
        string='ATM 銀行代碼',
        readonly=True,
        help='虛擬帳號的銀行代碼'
    )
    
    atm_v_account = fields.Char(
        string='ATM 虛擬帳號',
        readonly=True,
        help='客戶需要轉帳的虛擬帳號'
    )
    
    atm_expire_date = fields.Datetime(
        string='ATM 繳費期限',
        readonly=True,
        help='虛擬帳號的繳費期限'
    )

    # ==================== 超商付款資訊 ====================
    
    cvs_payment_no = fields.Char(
        string='超商繳費代碼',
        readonly=True,
        help='客戶需要在超商繳費的代碼'
    )
    
    cvs_expire_date = fields.Datetime(
        string='超商繳費期限',
        readonly=True,
        help='超商繳費代碼的期限'
    )

    # ==================== 付款連結欄位 ====================
    
    payment_link = fields.Char(
        string='付款連結',
        readonly=True,
        help='產生的付款連結，客戶可以點擊此連結進行付款'
    )

    # ==================== LINE 整合欄位 ====================
    
    line_user_id = fields.Char(
        string='LINE User ID',
        help='客戶的 LINE User ID，用於發送通知'
    )
    
    source_channel = fields.Selection([
        ('manual', '人工建單'),
        ('line_bot', 'LINE Bot'),
        ('website', '官方網站'),
        ('phone', '電話預約'),
    ], string='訂單來源', default='manual',
       help='此訂單是從哪個管道建立的')

    # ==================== 計算欄位 ====================
    
    @api.depends('payment_state')
    def _compute_payment_status_color(self):
        """計算付款狀態的顏色標記"""
        for order in self:
            if order.payment_state == 'paid':
                order.payment_status_color = 'success'
            elif order.payment_state == 'failed':
                order.payment_status_color = 'danger'
            elif order.payment_state == 'waiting_payment':
                order.payment_status_color = 'warning'
            else:
                order.payment_status_color = 'muted'
    
    payment_status_color = fields.Char(
        string='狀態顏色',
        compute='_compute_payment_status_color',
        store=False
    )

    # ==================== 產生綠界付款連結 ====================
    
    def action_generate_ecpay_payment_link(self):
        """
        產生綠界付款連結
        
        功能：
        1. 產生綠界付款連結
        2. 可以透過 LINE Bot 發送給客戶
        3. 或顯示在 Odoo 訂單頁面
        
        Returns:
            dict: 包含付款連結的字典
        """
        self.ensure_one()
        
        # 取得系統參數
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        merchant_id = IrConfigParameter.get_param('ecpay.merchant_id')
        hash_key = IrConfigParameter.get_param('ecpay.hash_key')
        hash_iv = IrConfigParameter.get_param('ecpay.hash_iv')
        test_mode = IrConfigParameter.get_param('ecpay.test_mode', 'True') == 'True'
        
        if not all([merchant_id, hash_key, hash_iv]):
            raise ValueError('綠界設定不完整，請先在系統參數中設定')
        
        # 設定綠界 API URL
        if test_mode:
            api_url = 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5'
        else:
            api_url = 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
        
        # 取得網站基礎 URL
        # 使用固定的官方網域，避免取到錯誤的網址
        base_url = 'https://www.lensking.com.tw'
        
        # 準備付款資料
        from datetime import datetime
        import hashlib
        from urllib.parse import quote_plus
        
        payment_data = {
            'MerchantID': merchant_id,
            'MerchantTradeNo': self.name,  # 訂單編號
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': str(int(self.amount_total)),  # 金額（整數）
            'TradeDesc': f'時光幻鏡租借-{self.name}',
            'ItemName': self.name,
            
            # 回調網址
            'ReturnURL': f'{base_url}/ecpay/payment/notify',
            'OrderResultURL': f'{base_url}/payment/success',
            'ClientBackURL': 'https://www.lensking.com.tw',
            
            # 付款方式（ALL = 全部）
            'ChoosePayment': 'ALL',
            
            # ATM 專用回調
            'PaymentInfoURL': f'{base_url}/ecpay/atm/notify',
            
            # 額外參數
            'NeedExtraPaidInfo': 'Y',
            'EncryptType': '1',  # SHA256
        }
        
        # 產生檢查碼
        check_mac = self._generate_ecpay_check_mac(payment_data, hash_key, hash_iv)
        payment_data['CheckMacValue'] = check_mac
        
        # 組合完整 URL
        from urllib.parse import urlencode
        payment_url = f"{api_url}?{urlencode(payment_data)}"
        
        _logger.info(f'已產生付款連結：{payment_url}')
        
        # 更新訂單狀態
        self.write({
            'payment_state': 'pending',
        })
        
        return {
            'payment_url': payment_url,
            'order_no': self.name,
            'amount': self.amount_total,
        }
    
    def _generate_ecpay_check_mac(self, params, hash_key, hash_iv):
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

    # ==================== 訂單動作按鈕 ====================
    
    def action_send_payment_link(self):
        """
        產生付款連結並儲存
        
        功能：
        1. 產生綠界付款頁面 URL
        2. 儲存在 payment_link 欄位
        3. 可以透過 LINE Bot 發送給客戶
        4. 或顯示在 Odoo 訂單頁面供複製
        
        Returns:
            dict: 包含付款連結的字典
        """
        self.ensure_one()
        
        # 產生付款頁面 URL（指向 Odoo 自己的付款頁面）
        base_url = 'https://www.lensking.com.tw'
        payment_url = f'{base_url}/ecpay/payment/page/{self.id}'
        
        # 更新訂單狀態和付款連結
        self.write({
            'payment_state': 'pending',
            'payment_link': payment_url,
        })
        
        _logger.info(f'已產生付款連結：{payment_url}')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '付款連結已產生',
                'message': f'付款連結已儲存在「付款連結」欄位中，可隨時複製使用',
                'type': 'success',
                'sticky': True,  # 不自動消失
            }
        }
    
    def action_verify_payment_manually(self):
        """人工覆核付款"""
        self.ensure_one()
        
        self.write({
            'payment_manual_verified': True,
        })
        
        self.message_post(
            body=f"<p>✅ 人工覆核確認付款無誤</p>",
            message_type='notification'
        )
        
        return True
