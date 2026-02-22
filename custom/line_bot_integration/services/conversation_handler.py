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
        
        # 特殊指令處理（任何狀態都可用）
        if message_text.lower().strip() in ['購物車', '查看購物車', 'cart']:
            self._show_cart(line_user, reply_token)
            return
        elif message_text.lower().strip() in ['清空購物車', 'clear cart']:
            self._clear_cart(line_user, reply_token)
            return
        
        # 根據當前狀態處理訊息
        if line_user.conversation_state == 'idle':
            self._handle_idle_state(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'browsing_categories':
            self._handle_browsing_categories(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'browsing_equipment':
            self._handle_browsing_equipment(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'viewing_cart':
            self._handle_viewing_cart(line_user, message_text, reply_token)
        elif line_user.conversation_state == 'confirming_order':
            self._handle_confirming_order(line_user, message_text, reply_token)
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
    # 檢查是否選擇了分類（使用分類 ID）
    if message_text.startswith('category:'):
        category_id = int(message_text.split(':')[1])
        self._show_equipment_list_by_category_id(line_user, category_id, reply_token)
    else:
        # 返回主選單
        self._send_main_menu(line_user, reply_token)
    def _show_equipment_list_by_category_id(self, line_user, category_id, reply_token):
    """顯示器材列表（從 Odoo 讀取，使用分類 ID）"""
    line_user.conversation_state = 'browsing_equipment'
    
    # 儲存選擇的分類 ID
    temp_data = line_user.get_temp_data()
    temp_data['category_id'] = category_id
    line_user.set_temp_data(temp_data)
    
    line_client = self.env['line.client.service']
    product_service = self.env['odoo.product.service']
    
    # 從 Odoo 讀取產品
    equipment_list = product_service.get_products_by_category(category_id, limit=20)
    
    if not equipment_list:
        text = '抱歉，此分類目前沒有可租借的器材。'
        quick_reply_items = [{
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '◀️ 返回分類',
                'text': '租借器材'
            }
        }]
        messages = [{
            'type': 'text',
            'text': text,
            'quickReply': {'items': quick_reply_items}
        }]
        line_client.reply_message(reply_token, messages)
        return
    
    # 建立器材卡片（含圖片）
    bubbles = []
    for eq in equipment_list:
        # 判斷庫存狀態
        has_stock = eq['qty'] > 0
        stock_text = f"庫存：{int(eq['qty'])} 台" if has_stock else "暫無庫存"
        stock_color = '#999999' if has_stock else '#FF6B6B'
        
        bubble = {
            'type': 'bubble',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': []
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'button',
                        'action': {
                            'type': 'message',
                            'label': '🛒 加入購物車' if has_stock else '暫無庫存',
                            'text': f"加入購物車:{eq['id']}"
                        },
                        'style': 'primary',
                        'color': '#667eea' if has_stock else '#CCCCCC'
                    }
                ]
            }
        }
        
        # 如果有圖片，加入 hero
        if eq.get('image_url'):
            bubble['hero'] = {
                'type': 'image',
                'url': eq['image_url'],
                'size': 'full',
                'aspectRatio': '20:13',
                'aspectMode': 'cover'
            }
        
        # 產品資訊
        bubble['body']['contents'] = [
            {
                'type': 'text',
                'text': eq['name'],
                'weight': 'bold',
                'size': 'md',
                'wrap': True
            },
            {
                'type': 'box',
                'layout': 'baseline',
                'margin': 'md',
                'contents': [
                    {
                        'type': 'text',
                        'text': f"NT$ {int(eq['price'])}",
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
            },
            {
                'type': 'text',
                'text': stock_text,
                'size': 'sm',
                'color': stock_color,
                'margin': 'md'
            }
        ]
        
        bubbles.append(bubble)
    
    # 限制 Carousel 最多 10 個 bubble
    if len(bubbles) > 10:
        bubbles = bubbles[:10]
    
    flex_contents = {
        'type': 'carousel',
        'contents': bubbles
    }
    
    # 取得目前購物車數量
    cart_items = temp_data.get('cart', [])
    cart_count = len(cart_items)
    
    # 建立快速回覆按鈕
    quick_reply_items = [
        {
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '🛒 查看購物車' + (f' ({cart_count})' if cart_count > 0 else ''),
                'text': '查看購物車'
            }
        },
        {
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '◀️ 返回分類',
                'text': '租借器材'
            }
        }
    ]
    
    # 取得分類名稱
    category = self.env['product.category'].sudo().browse(category_id)
    category_name = category.name if category.exists() else '器材'
    
    messages = [
        {
            'type': 'flex',
            'altText': f'{category_name}列表',
            'contents': flex_contents
        },
        {
            'type': 'text',
            'text': f'📦 {category_name}',
            'quickReply': {
                'items': quick_reply_items
            }
        }
    ]
    
    line_client.reply_message(reply_token, messages)
    
    # 記錄發送的訊息
    self.env['line.conversation'].log_outgoing_message(
        line_user,
        'flex',
        f'{category_name}器材列表'
    )
    
    def _handle_browsing_equipment(self, line_user, message_text, reply_token):
        """處理瀏覽器材狀態"""
        # 檢查是否選擇了器材（加入購物車）
        if message_text.startswith('加入購物車:'):
            equipment_id = message_text.split(':')[1]
            self._add_to_cart(line_user, equipment_id, reply_token)
        elif message_text == '查看購物車':
            self._show_cart(line_user, reply_token)
        elif message_text == '返回分類':
            line_user.conversation_state = 'browsing_categories'
            self._send_category_menu(line_user, reply_token)
        else:
            # 可能是重新選擇分類
            if message_text in ['相機機身', '鏡頭', '閃光燈', '配件']:
                self._show_equipment_list(line_user, message_text, reply_token)
            else:
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
    """發送器材分類選單（從 Odoo 動態讀取）"""
    line_user.conversation_state = 'browsing_categories'
    
    line_client = self.env['line.client.service']
    product_service = self.env['odoo.product.service']
    
    # 從 Odoo 取得主要分類
    categories = product_service.get_main_categories()
    
    if not categories:
        # 如果沒有分類，顯示錯誤訊息
        text = '抱歉，目前系統無法載入器材分類。請稍後再試。'
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        return
    
    # 定義分類的 emoji 和顏色
    category_styles = {
        'Canon 相機': {'emoji': '📷', 'color': '#667eea'},
        'Canon 鏡頭': {'emoji': '🔭', 'color': '#764ba2'},
        'Sony 無反相機': {'emoji': '📸', 'color': '#f093fb'},
        'Sony 鏡頭': {'emoji': '🎯', 'color': '#4facfe'},
        '儲存與電力': {'emoji': '🔋', 'color': '#43e97b'},
    }
    
    # 建立分類卡片
    bubbles = []
    colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#43e97b', '#fa709a']
    
    for idx, cat in enumerate(categories):
        category_name = cat['name']
        style = category_styles.get(category_name, {
            'emoji': '📦',
            'color': colors[idx % len(colors)]
        })
        
        bubble = {
            'type': 'bubble',
            'size': 'micro',
            'hero': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': style['emoji'],
                        'size': '4xl',
                        'align': 'center',
                        'margin': 'md'
                    }
                ],
                'backgroundColor': style['color'],
                'paddingAll': '20px'
            },
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': category_name,
                        'weight': 'bold',
                        'size': 'md',
                        'wrap': True,
                        'align': 'center'
                    }
                ],
                'spacing': 'sm',
                'paddingAll': '13px'
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'button',
                        'action': {
                            'type': 'message',
                            'label': '查看',
                            'text': f"category:{cat['id']}"  # 使用分類 ID
                        },
                        'style': 'primary',
                        'color': style['color']
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
        'altText': '器材分類',
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
                                'label': '🛒 加入購物車',
                                'text': f"加入購物車:{eq['id']}"
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
        
        # 取得目前購物車數量
        cart_items = temp_data.get('cart', [])
        cart_count = len(cart_items)
        
        # 建立快速回覆按鈕
        quick_reply_items = [
            {
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '🛒 查看購物車' + (f' ({cart_count})' if cart_count > 0 else ''),
                    'text': '查看購物車'
                }
            },
            {
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '◀️ 返回分類',
                    'text': '返回分類'
                }
            }
        ]
        
        messages = [
            {
                'type': 'flex',
                'altText': f'{category}器材列表',
                'contents': flex_contents
            },
            {
                'type': 'text',
                'text': f'📦 {category}',
                'quickReply': {
                    'items': quick_reply_items
                }
            }
        ]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'flex',
            f'{category}器材列表'
        )
    
    def _add_to_cart(self, line_user, equipment_id, reply_token):
    """加入購物車（使用真實產品 ID）"""
    line_client = self.env['line.client.service']
    product_service = self.env['odoo.product.service']
    
    # 從 Odoo 讀取產品
    equipment = product_service.get_product_by_id(int(equipment_id))
    
    if not equipment:
        text = '抱歉，找不到此器材。'
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        return
    
    # 檢查庫存
    if equipment['qty'] <= 0:
        text = f'抱歉，{equipment["name"]} 目前沒有庫存。'
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        return
    
    # 取得購物車
    temp_data = line_user.get_temp_data()
    cart = temp_data.get('cart', [])
    
    # 檢查是否已在購物車中
    existing_item = next((item for item in cart if item['id'] == equipment_id), None)
    
    if existing_item:
        # 已存在，增加數量
        existing_item['quantity'] += 1
        action_text = '已增加數量'
    else:
        # 新增到購物車
        cart.append({
            'id': equipment_id,
            'name': equipment['name'],
            'price': equipment['price'],
            'quantity': 1
        })
        action_text = '已加入購物車'
    
    temp_data['cart'] = cart
    line_user.set_temp_data(temp_data)
    
    # 計算總價
    total = sum(item['price'] * item['quantity'] for item in cart)
    
    # 發送確認訊息
    quick_reply_items = [
        {
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '🛒 查看購物車',
                'text': '查看購物車'
            }
        },
        {
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '➕ 繼續選購',
                'text': '租借器材'
            }
        }
    ]
    
    text = f"""✅ {action_text}！

📦 {equipment['name']}
💰 NT$ {int(equipment['price'])}/天

🛒 購物車：{len(cart)} 項商品
💵 小計：NT$ {int(total)}"""
    
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
        'text',
        text
    )

    def _show_cart(self, line_user, reply_token):
        """顯示購物車"""
        line_client = self.env['line.client.service']
        temp_data = line_user.get_temp_data()
        cart = temp_data.get('cart', [])
        
        if not cart:
            text = '🛒 購物車是空的\n\n請先選擇要租借的器材！'
            quick_reply_items = [{
                'type': 'action',
                'action': {
                    'type': 'message',
                    'label': '📷 租借器材',
                    'text': '租借器材'
                }
            }]
            messages = [{
                'type': 'text',
                'text': text,
                'quickReply': {'items': quick_reply_items}
            }]
            line_client.reply_message(reply_token, messages)
            return
        
        # 建立購物車 Flex Message
        total = sum(item['price'] * item['quantity'] for item in cart)
        
        # 購物車項目
        cart_items_contents = []
        for idx, item in enumerate(cart):
            item_content = {
                'type': 'box',
                'layout': 'horizontal',
                'contents': [
                    {
                        'type': 'text',
                        'text': f"{item['quantity']}x",
                        'size': 'sm',
                        'color': '#999999',
                        'flex': 1
                    },
                    {
                        'type': 'text',
                        'text': item['name'],
                        'size': 'sm',
                        'wrap': True,
                        'flex': 4
                    },
                    {
                        'type': 'text',
                        'text': f"NT$ {item['price'] * item['quantity']}",
                        'size': 'sm',
                        'align': 'end',
                        'flex': 2
                    }
                ],
                'margin': 'md' if idx > 0 else 'none'
            }
            cart_items_contents.append(item_content)
        
        flex_contents = {
            'type': 'bubble',
            'header': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': '🛒 購物車',
                        'weight': 'bold',
                        'size': 'xl',
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
                        'text': '租借清單',
                        'size': 'md',
                        'weight': 'bold',
                        'margin': 'none'
                    },
                    {
                        'type': 'separator',
                        'margin': 'md'
                    },
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'contents': cart_items_contents,
                        'margin': 'lg'
                    },
                    {
                        'type': 'separator',
                        'margin': 'lg'
                    },
                    {
                        'type': 'box',
                        'layout': 'horizontal',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '小計',
                                'size': 'lg',
                                'weight': 'bold'
                            },
                            {
                                'type': 'text',
                                'text': f'NT$ {total}',
                                'size': 'lg',
                                'weight': 'bold',
                                'color': '#FF6B6B',
                                'align': 'end'
                            }
                        ],
                        'margin': 'lg'
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
                            'label': '✅ 確認訂單',
                            'text': '確認訂單'
                        },
                        'style': 'primary',
                        'color': '#4CAF50'
                    },
                    {
                        'type': 'button',
                        'action': {
                            'type': 'message',
                            'label': '➕ 繼續選購',
                            'text': '租借器材'
                        },
                        'style': 'secondary',
                        'margin': 'sm'
                    },
                    {
                        'type': 'button',
                        'action': {
                            'type': 'message',
                            'label': '🗑️ 清空購物車',
                            'text': '清空購物車'
                        },
                        'style': 'secondary',
                        'margin': 'sm'
                    }
                ]
            }
        }
        
        line_user.conversation_state = 'viewing_cart'
        
        messages = [{
            'type': 'flex',
            'altText': '購物車',
            'contents': flex_contents
        }]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'flex',
            '購物車'
        )
    
    def _clear_cart(self, line_user, reply_token):
        """清空購物車"""
        line_client = self.env['line.client.service']
        
        temp_data = line_user.get_temp_data()
        temp_data['cart'] = []
        line_user.set_temp_data(temp_data)
        line_user.conversation_state = 'idle'
        
        text = '🗑️ 購物車已清空'
        quick_reply_items = [{
            'type': 'action',
            'action': {
                'type': 'message',
                'label': '📷 重新選擇',
                'text': '租借器材'
            }
        }]
        
        messages = [{
            'type': 'text',
            'text': text,
            'quickReply': {'items': quick_reply_items}
        }]
        
        line_client.reply_message(reply_token, messages)
        
        # 記錄發送的訊息
        self.env['line.conversation'].log_outgoing_message(
            line_user,
            'text',
            text
        )
    
    def _handle_viewing_cart(self, line_user, message_text, reply_token):
        """處理查看購物車狀態"""
        if message_text == '確認訂單':
            self._confirm_and_create_order(line_user, reply_token)
        elif message_text == '繼續選購' or message_text == '租借器材':
            line_user.conversation_state = 'browsing_categories'
            self._send_category_menu(line_user, reply_token)
        elif message_text == '清空購物車':
            self._clear_cart(line_user, reply_token)
        else:
            # 預設重新顯示購物車
            self._show_cart(line_user, reply_token)
    
    def _handle_confirming_order(self, line_user, message_text, reply_token):
        """處理確認訂單狀態"""
        if message_text == '確定建立':
            self._create_order_from_cart(line_user, reply_token)
        elif message_text == '返回購物車':
            self._show_cart(line_user, reply_token)
        else:
            line_user.reset_state()
            self._send_main_menu(line_user, reply_token)
    
    def _confirm_and_create_order(self, line_user, reply_token):
        """確認並建立訂單"""
        line_client = self.env['line.client.service']
        
        temp_data = line_user.get_temp_data()
        cart = temp_data.get('cart', [])
        
        if not cart:
            text = '購物車是空的，無法建立訂單。'
            messages = [{'type': 'text', 'text': text}]
            line_client.reply_message(reply_token, messages)
            return
        
        # 直接建立訂單（簡化版本）
        self._create_order_from_cart(line_user, reply_token)
    
    def _create_order_from_cart(self, line_user, reply_token):
        """從購物車建立訂單"""
        line_client = self.env['line.client.service']
        
        try:
            # 確保有 Partner
            if not line_user.partner_id:
                line_user.create_partner()
            
            # 取得購物車
            temp_data = line_user.get_temp_data()
            cart = temp_data.get('cart', [])
            
            if not cart:
                text = '購物車是空的，無法建立訂單。'
                messages = [{'type': 'text', 'text': text}]
                line_client.reply_message(reply_token, messages)
                return
            
            # 取得租借日期（未來會實作 LIFF 日期選擇，目前使用預設值）
            # 預設：今天取件，明天歸還
            from datetime import datetime, timedelta
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            
            # 營業時間：12:00 - 21:30
            pickup_datetime = today.replace(hour=14, minute=0, second=0, microsecond=0)
            return_datetime = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
            
            # 建立訂單明細
            order_lines = []
            total_amount = 0
            
            for item in cart:
                # 查找或建立產品
                product = self.env['product.product'].sudo().search([
                    ('name', '=', item['name'])
                ], limit=1)
                
                if not product:
                    # 建立產品
                    product_category = self.env['product.category'].sudo().search([
                        ('name', '=', '租賃商品')
                    ], limit=1)
                    
                    if not product_category:
                        product_category = self.env['product.category'].sudo().create({
                            'name': '租賃商品'
                        })
                    
                    product = self.env['product.product'].sudo().create({
                        'name': item['name'],
                        'list_price': item['price'],
                        'type': 'service',
                        'categ_id': product_category.id,
                        'sale_ok': True,
                        'purchase_ok': False,
                        'rent_ok': True,  # ⭐ 標記為可租借
                    })
                
                # 加入訂單明細（包含租賃資訊）
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': f"{item['name']} - 租借（{item['quantity']}天）",
                    'product_uom_qty': item['quantity'],
                    'price_unit': item['price'],
                    'is_rental': True,  # ⭐ 標記為租賃訂單明細
                    'start_date': pickup_datetime.strftime('%Y-%m-%d %H:%M:%S'),  # ⭐ 取件時間
                    'return_date': return_datetime.strftime('%Y-%m-%d %H:%M:%S'),  # ⭐ 歸還時間
                }))
                
                total_amount += item['price'] * item['quantity']
            
            # 建立訂單（包含租賃標記）
            order_vals = {
                'partner_id': line_user.partner_id.id,
                'line_user_id': line_user.id,
                'order_source': 'line',
                'is_rental_order': True,  # ⭐ 正確的欄位名稱
                'rental_status': 'pickup',  # ⭐ 租賃狀態：待取件
                'order_line': order_lines,
            }
            
            order = self.env['sale.order'].sudo().create(order_vals)
            
            # 產生付款連結
            order.action_send_payment_link()
            
            # 清空購物車並重置狀態
            temp_data['cart'] = []
            line_user.set_temp_data(temp_data)
            line_user.reset_state()
            
            # 建立訂單摘要文字
            items_text = '\n'.join([f"• {item['quantity']}x {item['name']} - NT$ {item['price'] * item['quantity']}" 
                                   for item in cart])
            
            # 格式化日期時間
            pickup_str = pickup_datetime.strftime('%m/%d %H:%M')
            return_str = return_datetime.strftime('%m/%d %H:%M')
            
            # 發送確認訊息
            text = f"""✅ 訂單已建立！

📦 租借器材：
{items_text}

📅 租借期間：
取件：{pickup_str}
歸還：{return_str}

💰 總金額：NT$ {total_amount}

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
            
            _logger.info(f'已為 LINE 用戶 {line_user.line_user_id} 建立租賃訂單 {order.name}，包含 {len(cart)} 項商品，總金額：NT$ {total_amount}，取件：{pickup_str}，歸還：{return_str}')
            
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
