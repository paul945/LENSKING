# Odoo 產品整合說明

## 🎯 目標

將 LINE Bot 從硬編碼的範例器材資料改為從 Odoo 讀取真實產品。

## 📦 已建立的檔案

### 1. odoo_product_service.py

**位置：** `services/odoo_product_service.py`

**功能：**
- 智慧產品分類（根據產品名稱自動分類）
- 從 Odoo 讀取產品列表
- 取得租賃價格（24 hour pricing）
- 取得產品圖片 URL
- 取得庫存數量

**主要方法：**
```python
# 取得分類下的產品
products = self.env['odoo.product.service'].get_products_by_category('Canon 相機', limit=10)

# 取得單一產品
product = self.env['odoo.product.service'].get_product_by_id(product_id)
```

## 🔧 需要修改的地方

### Step 1: 修改分類選單

**檔案：** `services/conversation_handler.py`
**方法：** `_send_category_menu()`

**目前：** 硬編碼 3 個分類（相機機身、鏡頭、閃光燈）
**修改為：** 6 個智慧分類

```python
categories = [
    {'name': 'Canon 相機', 'emoji': '📷', ...},
    {'name': 'Canon 鏡頭', 'emoji': '🔭', ...},
    {'name': 'Sony 相機', 'emoji': '📸', ...},
    {'name': 'Sony 鏡頭', 'emoji': '🎯', ...},
    {'name': '燈光配件', 'emoji': '💡', ...},
    {'name': '其他配件', 'emoji': '🎒', ...},
]
```

### Step 2: 修改器材列表展示

**檔案：** `services/conversation_handler.py`
**方法：** `_show_equipment_list()`

**目前的問題：**
```python
# 硬編碼的器材資料
equipment_data = {
    '相機機身': [
        {'name': 'Canon R6 Mark II', 'price': 1200, 'id': 'camera_001'},
        ...
    ]
}
```

**修改為：**
```python
# 從 Odoo 讀取產品
product_service = self.env['odoo.product.service']
equipment_list = product_service.get_products_by_category(category, limit=10)

# equipment_list 格式：
# [
#     {
#         'id': 123,
#         'name': 'Canon EOS R10 租借',
#         'price': 500.0,
#         'image_url': 'https://www.lensking.com.tw/web/image/product.template/123/image_128',
#         'qty': 3
#     },
#     ...
# ]
```

**Flex Message 修改（加入圖片）：**
```python
bubble = {
    'type': 'bubble',
    'hero': {
        'type': 'image',
        'url': eq.get('image_url') or 'https://via.placeholder.com/300',
        'size': 'full',
        'aspectRatio': '20:13',
        'aspectMode': 'cover'
    },
    'body': {
        'type': 'box',
        'layout': 'vertical',
        'contents': [
            {'type': 'text', 'text': eq['name'], 'weight': 'bold', 'size': 'lg', 'wrap': True},
            {
                'type': 'box',
                'layout': 'baseline',
                'margin': 'md',
                'contents': [
                    {'type': 'text', 'text': f"NT$ {eq['price']}", 'size': 'xl', 'color': '#FF6B6B', 'weight': 'bold'},
                    {'type': 'text', 'text': '/天', 'size': 'sm', 'color': '#999999'}
                ]
            },
            {'type': 'text', 'text': f"庫存：{eq['qty']} 台", 'size': 'sm', 'color': '#999999', 'margin': 'md'}
        ]
    },
    'footer': {
        'type': 'box',
        'layout': 'vertical',
        'contents': [{
            'type': 'button',
            'action': {
                'type': 'message',
                'label': '🛒 加入購物車',
                'text': f"加入購物車:{eq['id']}"  # 使用真實產品 ID
            },
            'style': 'primary',
            'color': '#667eea'
        }]
    }
}
```

### Step 3: 修改加入購物車邏輯

**檔案：** `services/conversation_handler.py`
**方法：** `_add_to_cart()`

**目前的問題：**
```python
# 硬編碼的器材資料
equipment_data = {
    'camera_001': {'name': 'Canon R6 Mark II', 'price': 1200},
    ...
}
equipment = equipment_data.get(equipment_id)
```

**修改為：**
```python
# 從 Odoo 讀取產品
product_service = self.env['odoo.product.service']
equipment = product_service.get_product_by_id(int(equipment_id))

if not equipment:
    text = '抱歉，找不到此器材。'
    ...
    return

# equipment 格式：
# {
#     'id': 123,
#     'name': 'Canon EOS R10 租借',
#     'price': 500.0,
#     'image_url': '...',
#     'qty': 3,
#     'category': 'Canon 相機'
# }
```

### Step 4: 修改訂單建立邏輯

**檔案：** `services/conversation_handler.py`
**方法：** `_create_order_from_cart()`

**修改產品搜尋：**
```python
# 目前：根據產品名稱搜尋
product = self.env['product.product'].sudo().search([
    ('name', '=', item['name'])
], limit=1)

# 改為：直接使用產品 ID（如果購物車儲存了 ID）
# 或改為使用 product.template ID 轉換
product_template = self.env['product.template'].sudo().browse(item['id'])
product = product_template.product_variant_id
```

## 📝 完整修改範例

### conversation_handler.py 關鍵修改

```python
def _show_equipment_list(self, line_user, category, reply_token):
    """顯示器材列表（從 Odoo 讀取）"""
    line_user.conversation_state = 'browsing_equipment'
    
    # 儲存選擇的分類
    temp_data = line_user.get_temp_data()
    temp_data['category'] = category
    line_user.set_temp_data(temp_data)
    
    line_client = self.env['line.client.service']
    
    # ⭐ 從 Odoo 讀取產品
    product_service = self.env['odoo.product.service']
    equipment_list = product_service.get_products_by_category(category, limit=10)
    
    if not equipment_list:
        text = f'抱歉，目前 {category} 暫無可租借器材。'
        messages = [{'type': 'text', 'text': text}]
        line_client.reply_message(reply_token, messages)
        return
    
    # 建立器材卡片（含圖片）
    bubbles = []
    for eq in equipment_list:
        bubble = {
            'type': 'bubble',
            'hero': {
                'type': 'image',
                'url': eq.get('image_url') or 'https://via.placeholder.com/300x200?text=No+Image',
                'size': 'full',
                'aspectRatio': '20:13',
                'aspectMode': 'cover'
            },
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': eq['name'],
                        'weight': 'bold',
                        'size': 'lg',
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
                        'text': f"庫存：{int(eq['qty'])} 台",
                        'size': 'sm',
                        'color': '#999999' if eq['qty'] > 0 else '#FF6B6B',
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
                            'label': '🛒 加入購物車',
                            'text': f"加入購物車:{eq['id']}"
                        },
                        'style': 'primary',
                        'color': '#667eea' if eq['qty'] > 0 else '#CCCCCC',
                        'disabled': eq['qty'] <= 0
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    flex_contents = {
        'type': 'carousel',
        'contents': bubbles
    }
    
    # ... 其餘程式碼相同
```

## 🚀 實作步驟

1. ✅ 建立 `odoo_product_service.py`（已完成）
2. ✅ 更新 `services/__init__.py`（已完成）
3. ⏳ 修改 `conversation_handler.py` 的 `_send_category_menu()`
4. ⏳ 修改 `conversation_handler.py` 的 `_show_equipment_list()`
5. ⏳ 修改 `conversation_handler.py` 的 `_add_to_cart()`
6. ⏳ 測試功能

## 📊 預期效果

### Before（v2.1.2）
- 3 個硬編碼分類
- 6 個範例產品
- 固定價格
- 無圖片
- 無庫存資訊

### After（v3.0.0）
- 6 個智慧分類
- 158 個真實產品
- 動態價格（從 Odoo）
- 產品圖片
- 即時庫存

## ⚠️ 注意事項

1. **產品名稱分類邏輯**
   - 目前根據關鍵字分類
   - 未來您分類完成後可改用 `categ_id`

2. **圖片處理**
   - 如果產品沒有圖片，顯示預設圖
   - URL 格式：`https://www.lensking.com.tw/web/image/product.template/{id}/image_128`

3. **價格取得**
   - 優先使用 24 hour pricing
   - 如果沒有，使用第一個可用的定價
   - 如果都沒有，使用預設值 500

4. **效能考量**
   - 目前每次都即時查詢 Odoo
   - 未來可考慮加入快取機制

## 🎯 需要協助嗎？

由於 `conversation_handler.py` 檔案較大（1000+ 行），手動修改需要小心。

您可以選擇：
1. 我提供完整的新版 `conversation_handler.py`
2. 或您先測試 `odoo_product_service.py` 是否正常運作
3. 再逐步修改各個方法

告訴我您的選擇！
