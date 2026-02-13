# -*- coding: utf-8 -*-
from odoo import models, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class LineClientService(models.AbstractModel):
    """
    LINE Messaging API 客戶端服務
    
    負責所有與 LINE Platform 的 API 溝通
    """
    _name = 'line.client.service'
    _description = 'LINE API 客戶端'
    
    LINE_API_URL = 'https://api.line.me/v2/bot'
    
    def _get_channel_access_token(self):
        """取得 Channel Access Token"""
        token = self.env['ir.config_parameter'].sudo().get_param('line.channel_access_token')
        if not token:
            raise ValueError('LINE Channel Access Token 未設定')
        return token
    
    def _get_headers(self):
        """取得 API 請求標頭"""
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self._get_channel_access_token()}'
        }
    
    # ==================== 發送訊息 ====================
    
    def send_text_message(self, line_user_id, text):
        """
        發送文字訊息
        
        Args:
            line_user_id: LINE User ID
            text: 文字內容
        """
        message = {
            'type': 'text',
            'text': text
        }
        return self._send_message(line_user_id, [message])
    
    def send_flex_message(self, line_user_id, alt_text, flex_contents):
        """
        發送 Flex Message
        
        Args:
            line_user_id: LINE User ID
            alt_text: 替代文字（無法顯示 Flex 時顯示）
            flex_contents: Flex Message 內容（dict）
        """
        message = {
            'type': 'flex',
            'altText': alt_text,
            'contents': flex_contents
        }
        return self._send_message(line_user_id, [message])
    
    def send_quick_reply(self, line_user_id, text, quick_reply_items):
        """
        發送帶有 Quick Reply 的文字訊息
        
        Args:
            line_user_id: LINE User ID
            text: 文字內容
            quick_reply_items: Quick Reply 項目列表
        """
        message = {
            'type': 'text',
            'text': text,
            'quickReply': {
                'items': quick_reply_items
            }
        }
        return self._send_message(line_user_id, [message])
    
    def _send_message(self, line_user_id, messages):
        """
        發送訊息到 LINE Platform
        
        Args:
            line_user_id: LINE User ID
            messages: 訊息列表
        """
        try:
            url = f'{self.LINE_API_URL}/message/push'
            payload = {
                'to': line_user_id,
                'messages': messages
            }
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                _logger.info(f'成功發送訊息給 {line_user_id}')
                return True
            else:
                _logger.error(f'發送訊息失敗：{response.status_code} - {response.text}')
                return False
                
        except Exception as e:
            _logger.error(f'發送訊息時發生錯誤：{str(e)}')
            return False
    
    # ==================== 取得用戶資訊 ====================
    
    def get_profile(self, line_user_id):
        """
        取得用戶個人資料
        
        Args:
            line_user_id: LINE User ID
            
        Returns:
            dict: 用戶資料 {'displayName', 'pictureUrl', 'statusMessage'}
        """
        try:
            url = f'{self.LINE_API_URL}/profile/{line_user_id}'
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                _logger.error(f'取得用戶資料失敗：{response.status_code}')
                return None
                
        except Exception as e:
            _logger.error(f'取得用戶資料時發生錯誤：{str(e)}')
            return None
    
    # ==================== 回覆訊息 ====================
    
    def reply_message(self, reply_token, messages):
        """
        回覆訊息（使用 Reply Token，只能用一次）
        
        Args:
            reply_token: Reply Token
            messages: 訊息列表
        """
        try:
            url = f'{self.LINE_API_URL}/message/reply'
            payload = {
                'replyToken': reply_token,
                'messages': messages
            }
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                _logger.info(f'成功回覆訊息')
                return True
            else:
                _logger.error(f'回覆訊息失敗：{response.status_code} - {response.text}')
                return False
                
        except Exception as e:
            _logger.error(f'回覆訊息時發生錯誤：{str(e)}')
            return False
