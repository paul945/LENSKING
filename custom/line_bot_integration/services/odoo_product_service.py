# -*- coding: utf-8 -*-

import logging
from odoo import models

_logger = logging.getLogger(__name__)


class OdooProductService(models.AbstractModel):
    """
    Odoo 產品服務
    
    處理從 Odoo 讀取產品資料，供 LINE Bot 使用
    """
    _name = 'odoo.product.service'
    _description = 'Odoo Product Service for LINE Bot'
    
    def get_main_categories(self):
        """
        取得主要產品分類（租借商品下的第一層子分類）
        
        Returns:
            list: 分類列表，包含 id, name, display_name
        """
        try:
            # 先找到「租借商品」分類
            rental_category = self.env['product.category'].sudo().search([
                ('name', '=', '租借商品')
            ], limit=1)
            
            if not rental_category:
                _logger.warning('找不到「租借商品」分類')
                return []
            
            # 取得「租借商品」下的子分類
            categories = self.env['product.category'].sudo().search_read(
                [('parent_id', '=', rental_category.id)],
                ['id', 'name', 'display_name', 'product_count'],
                order='name'
            )
            
            _logger.info(f'找到 {len(categories)} 個主要分類')
            return categories
            
        except Exception as e:
            _logger.error(f'取得分類失敗：{str(e)}', exc_info=True)
            return []
    
    def get_products_by_category(self, category_id, limit=20):
        """
        根據分類 ID 取得產品列表（包含該分類及其子分類的所有產品）
        
        Args:
            category_id: 分類 ID
            limit: 返回產品數量限制
            
        Returns:
            list: 產品列表，包含 id, name, price, image_url, qty
        """
        try:
            # 取得該分類及其所有子分類
            category = self.env['product.category'].sudo().browse(category_id)
            
            if not category.exists():
                _logger.warning(f'分類 ID {category_id} 不存在')
                return []
            
            # 取得分類路徑（包含所有子分類）
            category_ids = [category_id]
            
            # 遞迴取得所有子分類
            def get_child_categories(parent_id):
                children = self.env['product.category'].sudo().search([
                    ('parent_id', '=', parent_id)
                ])
                child_ids = children.ids
                for child in children:
                    child_ids.extend(get_child_categories(child.id))
                return child_ids
            
            category_ids.extend(get_child_categories(category_id))
            
            _logger.info(f'分類 {category.name} 及子分類 IDs: {category_ids}')
            
            # 搜尋產品
            products = self.env['product.template'].sudo().search_read(
                [
                    ('categ_id', 'in', category_ids),
                    ('rent_ok', '=', True),
                    ('active', '=', True),
                ],
                [
                    'id',
                    'name',
                    'image_128',
                    'qty_available',
                ],
                limit=limit,
                order='name'
            )
            
            _logger.info(f'分類 {category.name} 找到 {len(products)} 個產品')
            
            # 處理產品資料
            result = []
            for product in products:
                # 取得租賃價格
                rental_price = self._get_rental_price(product['id'])
                
                # 取得圖片 URL
                image_url = None
                if product.get('image_128'):
                    image_url = f"https://www.lensking.com.tw/web/image/product.template/{product['id']}/image_128"
                
                result.append({
                    'id': product['id'],
                    'name': product['name'],
                    'price': rental_price or 500,  # 預設 500
                    'image_url': image_url,
                    'qty': product.get('qty_available', 0),
                })
            
            return result
            
        except Exception as e:
            _logger.error(f'取得產品列表失敗：{str(e)}', exc_info=True)
            return []
    
    def _get_rental_price(self, product_template_id):
        """
        取得產品的 24 小時租賃價格
        
        Args:
            product_template_id: 產品範本 ID
            
        Returns:
            float: 租賃價格（24小時）
        """
        try:
            # 搜尋 24 小時租賃定價
            pricing = self.env['product.pricing'].sudo().search_read(
                [
                    ('product_template_id', '=', product_template_id),
                    ('duration', '=', 24),
                    ('unit', '=', 'hour'),
                ],
                ['price'],
                limit=1
            )
            
            if pricing:
                return pricing[0]['price']
            
            # 如果沒有 24 小時定價，嘗試找其他定價
            alt_pricing = self.env['product.pricing'].sudo().search_read(
                [('product_template_id', '=', product_template_id)],
                ['price', 'duration', 'unit'],
                limit=1,
                order='duration'
            )
            
            if alt_pricing:
                return alt_pricing[0]['price']
            
            return None
            
        except Exception as e:
            _logger.error(f'取得租賃價格失敗（產品 {product_template_id}）：{str(e)}')
            return None
    
    def get_product_by_id(self, product_id):
        """
        根據 ID 取得單一產品詳細資訊
        
        Args:
            product_id: 產品範本 ID
            
        Returns:
            dict: 產品資訊
        """
        try:
            product = self.env['product.template'].sudo().browse(product_id)
            
            if not product.exists():
                return None
            
            rental_price = self._get_rental_price(product_id)
            
            image_url = None
            if product.image_128:
                image_url = f"https://www.lensking.com.tw/web/image/product.template/{product_id}/image_128"
            
            return {
                'id': product.id,
                'name': product.name,
                'price': rental_price or 500,
                'image_url': image_url,
                'qty': product.qty_available,
            }
            
        except Exception as e:
            _logger.error(f'取得產品詳情失敗（ID {product_id}）：{str(e)}', exc_info=True)
            return None
