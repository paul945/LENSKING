# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class LineConversation(models.Model):
    """
    LINE 對話記錄模型
    
    記錄所有與 LINE 用戶的對話內容
    """
    _name = 'line.conversation'
    _description = 'LINE 對話記錄'
    _order = 'create_date desc'
    _rec_name = 'create_date'
    
    # ==================== 基本資訊 ====================
    
    line_user_id = fields.Many2one(
        'line.user',
        string='LINE 用戶',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    direction = fields.Selection([
        ('incoming', '收到'),
        ('outgoing', '發送'),
    ], string='方向', required=True, index=True)
    
    message_type = fields.Selection([
        ('text', '文字'),
        ('image', '圖片'),
        ('video', '影片'),
        ('audio', '音訊'),
        ('file', '檔案'),
        ('location', '位置'),
        ('sticker', '貼圖'),
        ('flex', 'Flex Message'),
        ('template', 'Template Message'),
        ('quick_reply', 'Quick Reply'),
    ], string='訊息類型', required=True)
    
    content = fields.Text(
        string='內容',
        help='訊息的文字內容或 JSON 結構'
    )
    
    line_message_id = fields.Char(
        string='LINE Message ID',
        help='LINE 平台的訊息 ID'
    )
    
    create_date = fields.Datetime(
        string='時間',
        default=fields.Datetime.now,
        required=True
    )
    
    # ==================== 狀態資訊 ====================
    
    delivery_status = fields.Selection([
        ('pending', '待發送'),
        ('sent', '已發送'),
        ('delivered', '已送達'),
        ('failed', '發送失敗'),
    ], string='發送狀態', default='pending')
    
    error_message = fields.Text(
        string='錯誤訊息',
        help='發送失敗時的錯誤訊息'
    )
    
    # ==================== 關聯資訊 ====================
    
    related_order_id = fields.Many2one(
        'sale.order',
        string='相關訂單',
        help='此對話相關的訂單'
    )
    
    # ==================== 輔助方法 ====================
    
    @api.model
    def log_incoming_message(self, line_user, message_type, content, message_id=None):
        """記錄收到的訊息"""
        return self.create({
            'line_user_id': line_user.id,
            'direction': 'incoming',
            'message_type': message_type,
            'content': content,
            'line_message_id': message_id,
            'delivery_status': 'delivered',
        })
    
    @api.model
    def log_outgoing_message(self, line_user, message_type, content, order_id=None):
        """記錄發送的訊息"""
        return self.create({
            'line_user_id': line_user.id,
            'direction': 'outgoing',
            'message_type': message_type,
            'content': content,
            'related_order_id': order_id,
            'delivery_status': 'sent',
        })
