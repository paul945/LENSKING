# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import json

_logger = logging.getLogger(__name__)


class LineUser(models.Model):
    """
    LINE 用戶模型
    
    儲存 LINE 用戶的基本資訊和對話狀態
    """
    _name = 'line.user'
    _description = 'LINE 用戶'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'
    _order = 'last_interaction desc'
    
    # ==================== 基本資訊 ====================
    
    line_user_id = fields.Char(
        string='LINE User ID',
        required=True,
        index=True,
        help='LINE 平台的用戶唯一識別碼'
    )
    
    display_name = fields.Char(
        string='顯示名稱',
        help='用戶在 LINE 上的顯示名稱'
    )
    
    picture_url = fields.Char(
        string='頭像網址',
        help='用戶的 LINE 頭像圖片網址'
    )
    
    status_message = fields.Char(
        string='狀態訊息',
        help='用戶的 LINE 狀態訊息'
    )
    
    # ==================== Odoo 整合 ====================
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Odoo 客戶',
        help='關聯的 Odoo 客戶記錄'
    )
    
    # ==================== 對話狀態 ====================
    
    conversation_state = fields.Selection([
        ('idle', '閒置'),
        ('browsing_categories', '瀏覽分類'),
        ('browsing_equipment', '瀏覽器材'),
        ('selecting_dates', '選擇日期'),
        ('confirming_order', '確認訂單'),
        ('waiting_payment', '等待付款'),
    ], string='對話狀態', default='idle', index=True,
       help='用戶目前在對話流程中的狀態')
    
    temp_data = fields.Text(
        string='暫存資料',
        help='JSON 格式儲存對話中的臨時資料（如：已選擇的器材、日期等）'
    )
    
    last_interaction = fields.Datetime(
        string='最後互動時間',
        default=fields.Datetime.now,
        index=True,
        help='用戶最後一次發送訊息的時間'
    )
    
    # ==================== 統計資訊 ====================
    
    conversation_ids = fields.One2many(
        'line.conversation',
        'line_user_id',
        string='對話記錄'
    )
    
    conversation_count = fields.Integer(
        string='對話次數',
        compute='_compute_conversation_count',
        store=True
    )
    
    order_ids = fields.One2many(
        'sale.order',
        'line_user_id',
        string='訂單記錄'
    )
    
    order_count = fields.Integer(
        string='訂單數量',
        compute='_compute_order_count',
        store=True
    )
    
    # ==================== 計算欄位 ====================
    
    @api.depends('conversation_ids')
    def _compute_conversation_count(self):
        for record in self:
            record.conversation_count = len(record.conversation_ids)
    
    @api.depends('order_ids')
    def _compute_order_count(self):
        for record in self:
            record.order_count = len(record.order_ids)
    
    # ==================== 輔助方法 ====================
    
    def get_temp_data(self):
        """取得暫存資料（JSON → dict）"""
        self.ensure_one()
        if self.temp_data:
            try:
                return json.loads(self.temp_data)
            except:
                return {}
        return {}
    
    def set_temp_data(self, data):
        """設定暫存資料（dict → JSON）"""
        self.ensure_one()
        self.temp_data = json.dumps(data, ensure_ascii=False)
    
    def clear_temp_data(self):
        """清除暫存資料"""
        self.ensure_one()
        self.temp_data = False
    
    def reset_state(self):
        """重置對話狀態"""
        self.ensure_one()
        self.write({
            'conversation_state': 'idle',
            'temp_data': False,
        })
        _logger.info(f'用戶 {self.display_name} ({self.line_user_id}) 狀態已重置')
    
    def update_last_interaction(self):
        """更新最後互動時間"""
        self.ensure_one()
        self.last_interaction = fields.Datetime.now()
    
    # ==================== 客戶關聯 ====================
    
    def link_to_partner(self, partner_id):
        """關聯到 Odoo 客戶"""
        self.ensure_one()
        self.partner_id = partner_id
        _logger.info(f'LINE 用戶 {self.line_user_id} 已關聯到客戶 {partner_id}')
    
    def create_partner(self):
        """建立新的 Odoo 客戶"""
        self.ensure_one()
        if self.partner_id:
            _logger.warning(f'LINE 用戶 {self.line_user_id} 已有關聯客戶')
            return self.partner_id
        
        partner = self.env['res.partner'].create({
            'name': self.display_name or f'LINE_{self.line_user_id[:8]}',
            'comment': f'透過 LINE Bot 註冊\nLINE User ID: {self.line_user_id}',
        })
        
        self.partner_id = partner.id
        _logger.info(f'為 LINE 用戶 {self.line_user_id} 建立新客戶 {partner.id}')
        return partner
