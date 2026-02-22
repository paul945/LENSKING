# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """
    擴充租賃訂單模型以支援 LINE Bot
    """
    _inherit = 'sale.order'
    
    # ==================== LINE 整合欄位 ====================
    
    line_user_id = fields.Many2one(
        'line.user',
        string='LINE 用戶',
        help='建立此訂單的 LINE 用戶'
    )
    
    # 訂單來源欄位
    # 如果基礎模組沒有此欄位，我們建立一個新的
    # 如果已存在，則擴充選項
    order_source = fields.Selection(
        selection=[
            ('manual', '人工輸入'),
            ('website', '官網'),
            ('line', 'LINE Bot'),
        ],
        string='訂單來源',
        default='manual',
        help='此訂單的建立來源'
    )
    
    # ==================== 輔助方法 ====================
    
    def send_line_notification(self, message):
        """
        發送 LINE 通知給客戶
        
        Args:
            message: 要發送的訊息內容
        """
        self.ensure_one()
        if not self.line_user_id:
            _logger.warning(f'訂單 {self.name} 沒有關聯的 LINE 用戶')
            return False
        
        try:
            # 透過 LINE Client Service 發送訊息
            line_client = self.env['line.client.service']
            line_client.send_text_message(
                self.line_user_id.line_user_id,
                message
            )
            
            # 記錄對話
            self.env['line.conversation'].log_outgoing_message(
                self.line_user_id,
                'text',
                message,
                self.id
            )
            
            _logger.info(f'已發送 LINE 通知給訂單 {self.name}')
            return True
            
        except Exception as e:
            _logger.error(f'發送 LINE 通知失敗：{str(e)}')
            return False
    
    def action_confirm(self):
        """訂單確認時發送 LINE 通知"""
        result = super(SaleOrder, self).action_confirm()
        
        for order in self:
            if order.line_user_id and order.order_source == 'line':
                message = f"""
✅ 訂單已確認！

訂單編號：{order.name}
金額：NT$ {int(order.amount_total)}

請於租借日期當天前往取件：
📍 {order.company_id.street or '桃園市中壢區義民路一段129號'}

取件時間：12:00-21:30

如有任何問題，歡迎聯絡我們！
                """.strip()
                order.send_line_notification(message)
        
        return result
    
    def write(self, vals):
        """訂單狀態變更時發送通知"""
        result = super(SaleOrder, self).write(vals)
        
        # 付款狀態變更通知
        if 'payment_state' in vals:
            for order in self:
                if order.line_user_id and order.payment_state == 'paid':
                    message = f"""
💰 付款成功！

訂單編號：{order.name}
付款金額：NT$ {int(order.amount_total)}

請於租借日期當天攜帶證件前往取件。

感謝您的付款！
                    """.strip()
                    order.send_line_notification(message)
        
        return result
