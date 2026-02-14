# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class ConversationHandler(models.AbstractModel):
    """
    對話處理器
    
    負責處理 LINE 用戶的對話邏輯和狀態管理
    """
    _name = 'conversation.handler'
    _description = '對話處理器'
    
    # ==================== 主要處理方法 ====================
    
    def handle_message(self, line_user, message_type, message_text, reply_token):
        """
        處理收到的訊息
        
        Args:
            line_user: LINE 用戶物件
            message_type: 訊息類型
            message_text: 訊息內容
            reply_token: 回覆 Token
        """
        _logger.info(f'處理訊息：用戶={line_user.display_name}, 狀態={line_user.conversation_state}, 內容={message_text}')
        
        # 更新最後互動時間
        line_user.update_last_interaction()
        
        # 記錄收到的訊息
        self.env['line.conversation'].log_incoming_message(
            line_user,
            message_type,
            message_text
        )
        
        # 根據當前狀態處理訊息
        if line_user.conversation_state == 'idle':
            self._handle_idle_state(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'browsing_categories':
            self._handle_browsing_categories(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'browsing_equipment':
            self._handle_browsing_equipment(line_user, message_text, reply_token)
        else:
            # 未知狀態，重置
            line_user.reset_state()
            self._send_main_menu(line_user, reply_token)
    
    # ==================== 狀態處理方法 ====================
    
    def _handle_idle_state(self, line_user, message_text, reply_token):
        """處理閒置狀態"""
        message_lower = message_text.lower().strip()
        
        # 關鍵字辨識
        if any(keyword in message_lower for keyword in ['租借', '租', '器材', '相機', '鏡頭']):
            self._start_browsing(line_user, reply_token)
        elif any(keyword in message_lower for keyword in ['訂單', '查詢', '我的訂單']):
            self._show_user_orders(line_user, reply_token)
        elif any(keyword in message_lower for keyword in ['客服', '聯絡', '問題', '幫助']):
            self._show_contact_info(line_user, reply_token)
        else:
            # 預設顯示主選單
            self._send_main_menu(line_user, reply_token)
    
    def _handle_browsing_categories(self, line_user, message_text, reply_token):
        """處理瀏覽分類狀態"""
        # 檢查是否選擇了分類
        if message_text in ['相機機身', '鏡頭', '閃光燈', '配件']:
            self._show_equipment_list(line_user, message_text, reply_token)
        else:
            self._send_category_menu(line_user, reply_token)
    
    def _handle_browsing_equipment(self, line_user, message_text, reply_token):
        """處理瀏覽器材狀態"""
        # 檢查是否選擇了器材
        if message_text.startswith('租借:'):
            equipment_id = message_text.split(':')[1]
            self._select_equipment(line_user, equipment_id, reply_token)
        else:
            # 返回分類選單
            line_user.conversation_state = 'browsing_categories'
            self._send_category_menu(line_user, reply_token)
    
    # ==================== 功能方法 ====================
    
    def _send_main_menu(self, line_user, reply_token):
        """發送主選單"""
        line_client = self.env['line.client.service']
        
        quick_reply_items = [
            {
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '📷 租借器材',
                    'text': '租借器材'
                }
            },
            {
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '🔍 查詢訂單',
                    'text': '查詢訂單'
                }
            },
            {
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '💬 聯絡客服',
                    'text': '聯絡客服'
                }
            },
        ]
        
        text = f"""👋 您好，{line_user.display_name or '歡迎'}！

我是時光幻鏡租借助手，很高興為您服務！

請選擇您需要的服務："""
        
        messages = [{
            'type': 'text',
            'text': text,
            'quickReply': {
                'items': quick_reply_items
            }
        }]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'quick_reply',
            text
        )
    
    def _start_browsing(self, line_user, reply_token):
        """開始瀏覽器材"""
        line_user.conversation_state = 'browsing_categories'
        self._send_category_menu(line_user, reply_token)
    
    def _send_category_menu(self, line_user, reply_token):
        """發送器材分類選單"""
        line_client = self.env['line.client.service']
        
        # Flex Message - 器材分類卡片
        flex_contents = {
            'type': 'carousel',
            'contents': [
                # 相機機身
                {
                    'type': 'bubble',
                    'hero': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '📷',
                                'size': '5xl',
                                'align': 'center',
                                'color': '#ffffff'
                            }
                        ],
                        'backgroundColor': '#667eea',
                        'paddingAll': '20px'
                    },
                    'body': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '相機機身',
                                'weight': 'bold',
                                'size': 'xl',
                                'align': 'center'
                            },
                            {
                                'type': 'text',
                                'text': 'Canon, Sony 等品牌',
                                'size': 'sm',
                                'color': '#999999',
                                'align': 'center',
                                'margin': 'md'
                            }
                        ]
                    },
                    'footer': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'button',
                                'action': {
                                    'type': 'message',
                                    'label': '查看器材',
                                    'text': '相機機身'
                                },
                                'style': 'primary',
                                'color': '#667eea'
                            }
                        ]
                    }
                },
                # 鏡頭
                {
                    'type': 'bubble',
                    'hero': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '🔭',
                                'size': '5xl',
                                'align': 'center',
                                'color': '#ffffff'
                            }
                        ],
                        'backgroundColor': '#764ba2',
                        'paddingAll': '20px'
                    },
                    'body': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '鏡頭',
                                'weight': 'bold',
                                'size': 'xl',
                                'align': 'center'
                            },
                            {
                                'type': 'text',
                                'text': '廣角、標準、望遠鏡頭',
                                'size': 'sm',
                                'color': '#999999',
                                'align': 'center',
                                'margin': 'md'
                            }
                        ]
                    },
                    'footer': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'button',
                                'action': {
                                    'type': 'message',
                                    'label': '查看器材',
                                    'text': '鏡頭'
                                },
                                'style': 'primary',
                                'color': '#764ba2'
                            }
                        ]
                    }
                },
                # 閃光燈
                {
                    'type': 'bubble',
                    'hero': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '⚡',
                                'size': '5xl',
                                'align': 'center',
                                'color': '#ffffff'
                            }
                        ],
                        'backgroundColor': '#f093fb',
                        'paddingAll': '20px'
                    },
                    'body': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '閃光燈',
                                'weight': 'bold',
                                'size': 'xl',
                                'align': 'center'
                            },
                            {
                                'type': 'text',
                                'text': '機頂閃、棚燈',
                                'size': 'sm',
                                'color': '#999999',
                                'align': 'center',
                                'margin': 'md'
                            }
                        ]
                    },
                    'footer': {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': [
                            {
                                'type': 'button',
                                'action': {
                                    'type': 'message',
                                    'label': '查看器材',
                                    'text': '閃光燈'
                                },
                                'style': 'primary',
                                'color': '#f093fb'
                            }
                        ]
                    }
                },
            ]
        }
        
        messages = [{
            'type': 'flex',
            'altText': '器材分類選單',
            'contents': flex_contents
        }]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'flex',
            '器材分類選單'
        )
    
    def _show_equipment_list(self, line_user, category, reply_token):
        """顯示器材列表（範例資料）"""
        line_user.conversation_state = 'browsing_equipment'
        
        # 儲存選擇的分類
        temp_data = line_user.get_temp_data()
        temp_data['category'] = category
        line_user.set_temp_data(temp_data)
        
        line_client = self.env['line.client.service']
        
        # 範例器材資料
        equipment_data = {
            '相機機身': [
                {'name': 'Canon R6 Mark II', 'price': 1200, 'id': 'camera_001'},
                {'name': 'Sony A7IV', 'price': 1000, 'id': 'camera_002'},
            ],
            '鏡頭': [
                {'name': 'Canon RF 24-70mm F2.8', 'price': 300, 'id': 'lens_001'},
                {'name': 'Sony 24-70mm GM II', 'price': 350, 'id': 'lens_002'},
            ],
            '閃光燈': [
                {'name': 'Godox V1', 'price': 150, 'id': 'flash_001'},
                {'name': 'Profoto A1X', 'price': 200, 'id': 'flash_002'},
            ],
        }
        
        equipment_list = equipment_data.get(category, [])
        
        # 建立器材卡片
        bubbles = []
        for eq in equipment_list:
            bubble = {
                'type': 'bubble',
                'body': {
                    'type': 'box',
                    'layout': 'vertical',
                    'contents': [
                        {
                            'type': 'text',
                            'text': eq['name'],
                            'weight': 'bold',
                            'size': 'lg'
                        },
                        {
                            'type': 'box',
                            'layout': 'baseline',
                            'margin': 'md',
                            'contents': [
                                {
                                    'type': 'text',
                                    'text': f"NT$ {eq['price']}",
                                    'size': 'xl',
                                    'color': '#FF6B6B',
                                    'weight': 'bold'
                                },
                                {
                                    'type': 'text',
                                    'text': '/天',
                                    'size': 'sm',
                                    'color': '#999999'
                                }
                            ]
                        }
                    ]
                },
                'footer': {
                    'type': 'box',
                    'layout': 'vertical',
                    'contents': [
                        {
                            'type': 'button',
                            'action': {
                                'type': 'message',
                                'label': '選擇租借',
                                'text': f"租借:{eq['id']}"
                            },
                            'style': 'primary',
                            'color': '#667eea'
                        }
                    ]
                }
            }
            bubbles.append(bubble)
        
        flex_contents = {
            'type': 'carousel',
            'contents': bubbles
        }
        
        messages = [{
            'type': 'flex',
            'altText': f'{category}器材列表',
            'contents': flex_contents
        }]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'flex',
            f'{category}器材列表'
        )
    
    def _select_equipment(self, line_user, equipment_id, reply_token):
        """選擇器材（簡化版本 - 直接建立訂單）"""
        line_client = self.env['line.client.service']
        
        # 建立簡化的訂單（Phase 2.1 版本）
        # 未來版本會加入日期選擇
        
        try:
            # 確保有 Partner
            if not line_user.partner_id:
                line_user.create_partner()
            
            # 從暫存資料取得分類和器材資訊
            temp_data = line_user.get_temp_data()
            category = temp_data.get('category', '器材')
            
            # 範例器材資料（與前面的對照）
            equipment_data = {
                'camera_001': {'name': 'Canon R6 Mark II', 'price': 1200},
                'camera_002': {'name': 'Sony A7IV', 'price': 1000},
                'lens_001': {'name': 'Canon RF 24-70mm F2.8', 'price': 300},
                'lens_002': {'name': 'Sony 24-70mm GM II', 'price': 350},
                'flash_001': {'name': 'Godox V1', 'price': 150},
                'flash_002': {'name': 'Profoto A1X', 'price': 200},
            }
            
            equipment = equipment_data.get(equipment_id, {'name': '器材租借', 'price': 1000})
            
            # 查找或建立「LINE Bot 租借」產品
            product = self.env['product.product'].sudo().search([
                ('name', '=', equipment['name'])
            ], limit=1)
            
            if not product:
                # 建立通用產品
                product_category = self.env['product.category'].sudo().search([
                    ('name', '=', '租賃商品')
                ], limit=1)
                
                if not product_category:
                    product_category = self.env['product.category'].sudo().create({
                        'name': '租賃商品'
                    })
                
                product = self.env['product.product'].sudo().create({
                    'name': equipment['name'],
                    'list_price': equipment['price'],
                    'type': 'service',
                    'categ_id': product_category.id,
                    'sale_ok': True,
                    'purchase_ok': False,
                })
            
            # 建立訂單（包含產品）
            order_vals = {
                'partner_id': line_user.partner_id.id,
                'line_user_id': line_user.id,
                'order_source': 'line',
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': f'{equipment["name"]} - 租借（1天）',
                    'product_uom_qty': 1,
                    'price_unit': equipment['price'],
                })],
            }
            
            order = self.env['sale.order'].sudo().create(order_vals)
            
            # 產生付款連結
            order.action_send_payment_link()
            
            # 重置狀態
            line_user.reset_state()
            
            # 發送確認訊息
            text = f"""✅ 訂單已建立！

📦 租借器材：{equipment['name']}
💰 金額：NT$ {equipment['price']}

訂單編號：{order.name}

💳 請點選以下連結完成付款：
{order.payment_link}

付款完成後系統將自動確認您的訂單。

如有任何問題，歡迎聯絡我們！
📞 電話：0905-527-577"""
            
            messages = [{
                'type': 'text',
                'text': text
            }]
            
            line_client.reply_message(reply_token, messages)
            
            # 記錄發送的訊息
            self.env['line.conversation'].log_outgoing_message(
                line_user,
                'text',
                text,
                order.id
            )
            
            _logger.info(f'已為 LINE 用戶 {line_user.line_user_id} 建立訂單 {order.name}，包含產品：{equipment["name"]}')
            
        except Exception as e:
            _logger.error(f'建立訂單失敗：{str(e)}', exc_info=True)
            text = '抱歉，建立訂單時發生錯誤。請稍後再試或聯絡客服。'
            messages = [{'type': 'text', 'text': text}]
            line_client.reply_message(reply_token, messages)
    
    def _show_user_orders(self, line_user, reply_token):
        """顯示用戶訂單"""
        line_client = self.env['line.client.service']
        
        orders = self.env['sale.order'].search([
            ('line_user_id', '=', line_user.id)
        ], limit=5, order='create_date desc')
        
        if not orders:
            text = '您目前沒有任何訂單。\n\n點選「租借器材」開始租借！'
        else:
            text = '📋 您的最近訂單：\n\n'
            for order in orders:
                status = dict(order._fields['payment_state'].selection).get(order.payment_state, '未知')
                text += f"訂單：{order.name}\n"
                text += f"狀態：{status}\n"
                text += f"金額：NT$ {int(order.amount_total)}\n"
                text += f"─────────────\n"
        
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'text',
            text
        )
    
    def _show_contact_info(self, line_user, reply_token):
        """顯示聯絡資訊"""
        line_client = self.env['line.client.service']
        
        text = """💬 聯絡我們

📍 地址：
桃園市中壢區義民路一段129號

⏰ 營業時間：
12:00 - 21:30

📞 電話：
0905-527-577

📧 Email：
lensfantasy@gmail.com

🌐 官網：
https://www.lensking.com.tw

歡迎隨時聯絡我們！"""
        
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'text',
            text
        )
