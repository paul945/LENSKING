# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import hashlib
import hmac
import base64
import logging

_logger = logging.getLogger(__name__)


class LineWebhookController(http.Controller):
    """
    LINE Webhook Controller
    
    接收來自 LINE Platform 的 Webhook 事件
    """
    
    @http.route('/line/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def line_webhook(self, **kwargs):
        """
        LINE Webhook 端點
        
        接收 LINE Platform 發送的事件通知
        """
        try:
            # 取得請求內容
            body = request.httprequest.get_data(as_text=True)
            signature = request.httprequest.headers.get('X-Line-Signature', '')
            
            _logger.info(f'收到 LINE Webhook 請求')
            
            # 驗證簽章
            if not self._verify_signature(body, signature):
                _logger.error('LINE Webhook 簽章驗證失敗')
                return {'status': 'error', 'message': 'Invalid signature'}
            
            # 解析事件
            events = json.loads(body).get('events', [])
            
            for event in events:
                self._handle_event(event)
            
            return {'status': 'ok'}
            
        except Exception as e:
            _logger.error(f'處理 LINE Webhook 時發生錯誤：{str(e)}', exc_info=True)
            return {'status': 'error', 'message': str(e)}
    
    def _verify_signature(self, body, signature):
        """
        驗證 LINE 簽章
        
        Args:
            body: 請求內容
            signature: X-Line-Signature 標頭
            
        Returns:
            bool: 驗證是否通過
        """
        try:
            channel_secret = request.env['ir.config_parameter'].sudo().get_param('line.channel_secret')
            if not channel_secret:
                _logger.error('LINE Channel Secret 未設定')
                return False
            
            hash_value = hmac.new(
                channel_secret.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            calculated_signature = base64.b64encode(hash_value).decode('utf-8')
            
            return calculated_signature == signature
            
        except Exception as e:
            _logger.error(f'驗證簽章時發生錯誤：{str(e)}')
            return False
    
    def _handle_event(self, event):
        """
        處理 LINE 事件
        
        Args:
            event: LINE 事件物件
        """
        event_type = event.get('type')
        
        _logger.info(f'處理 LINE 事件：{event_type}')
        
        if event_type == 'message':
            self._handle_message_event(event)
        elif event_type == 'follow':
            self._handle_follow_event(event)
        elif event_type == 'unfollow':
            self._handle_unfollow_event(event)
        elif event_type == 'postback':
            self._handle_postback_event(event)
        else:
            _logger.info(f'未處理的事件類型：{event_type}')
    
    def _handle_message_event(self, event):
        """
        處理訊息事件
        
        Args:
            event: 訊息事件物件
        """
        try:
            source = event.get('source', {})
            line_user_id = source.get('userId')
            message = event.get('message', {})
            message_type = message.get('type')
            reply_token = event.get('replyToken')
            
            if not line_user_id:
                _logger.warning('收到沒有 userId 的訊息事件')
                return
            
            # 取得或建立 LINE 用戶
            line_user = self._get_or_create_line_user(line_user_id)
            
            # 處理不同類型的訊息
            if message_type == 'text':
                message_text = message.get('text', '')
                self._handle_text_message(line_user, message_text, reply_token)
            elif message_type == 'sticker':
                self._handle_sticker_message(line_user, reply_token)
            else:
                _logger.info(f'收到不支援的訊息類型：{message_type}')
                self._send_unsupported_message(line_user, reply_token)
            
        except Exception as e:
            _logger.error(f'處理訊息事件時發生錯誤：{str(e)}', exc_info=True)
    
    def _handle_text_message(self, line_user, message_text, reply_token):
        """
        處理文字訊息
        
        Args:
            line_user: LINE 用戶物件
            message_text: 訊息內容
            reply_token: 回覆 Token
        """
        # 使用 Conversation Handler 處理對話邏輯
        conversation_handler = request.env['conversation.handler'].sudo()
        conversation_handler.handle_message(
            line_user,
            'text',
            message_text,
            reply_token
        )
    
    def _handle_sticker_message(self, line_user, reply_token):
        """處理貼圖訊息"""
        line_client = request.env['line.client.service'].sudo()
        
        messages = [{
            'type': 'text',
            'text': '😊 收到您的貼圖了！\n\n請問需要什麼服務呢？'
        }]
        
        line_client.reply_message(reply_token, messages)
    
    def _send_unsupported_message(self, line_user, reply_token):
        """發送不支援的訊息類型回應"""
        line_client = request.env['line.client.service'].sudo()
        
        messages = [{
            'type': 'text',
            'text': '抱歉，目前不支援此類型的訊息。\n\n請使用文字訊息與我溝通。'
        }]
        
        line_client.reply_message(reply_token, messages)
    
    def _handle_follow_event(self, event):
        """
        處理加入好友事件
        
        Args:
            event: 加入好友事件物件
        """
        try:
            source = event.get('source', {})
            line_user_id = source.get('userId')
            reply_token = event.get('replyToken')
            
            if not line_user_id:
                return
            
            # 建立 LINE 用戶
            line_user = self._get_or_create_line_user(line_user_id)
            
            _logger.info(f'用戶 {line_user.display_name} ({line_user_id}) 加入好友')
            
            # 發送歡迎訊息
            line_client = request.env['line.client.service'].sudo()
            
            welcome_text = f"""🎉 歡迎加入時光幻鏡！

很高興認識您，{line_user.display_name or '您好'}！

我們提供專業的攝影器材租借服務：
📷 相機機身
🔭 各式鏡頭
⚡ 閃光燈
🎬 錄影設備

💡 隨時可以透過以下方式開始租借：
輸入「租借器材」或點選下方選單

如有任何問題，歡迎隨時聯絡我們！"""
            
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
                        'label': '💬 聯絡客服',
                        'text': '聯絡客服'
                    }
                },
            ]
            
            messages = [{
                'type': 'text',
                'text': welcome_text,
                'quickReply': {
                    'items': quick_reply_items
                }
            }]
            
            line_client.reply_message(reply_token, messages)
            
            # 記錄對話
            request.env['line.conversation'].sudo().log_outgoing_message(
                line_user,
                'quick_reply',
                welcome_text
            )
            
        except Exception as e:
            _logger.error(f'處理加入好友事件時發生錯誤：{str(e)}', exc_info=True)
    
    def _handle_unfollow_event(self, event):
        """
        處理取消好友事件
        
        Args:
            event: 取消好友事件物件
        """
        try:
            source = event.get('source', {})
            line_user_id = source.get('userId')
            
            if not line_user_id:
                return
            
            line_user = request.env['line.user'].sudo().search([
                ('line_user_id', '=', line_user_id)
            ], limit=1)
            
            if line_user:
                _logger.info(f'用戶 {line_user.display_name} ({line_user_id}) 取消好友')
                # 可以在這裡做一些清理工作，但不刪除記錄以保留歷史
                line_user.reset_state()
            
        except Exception as e:
            _logger.error(f'處理取消好友事件時發生錯誤：{str(e)}', exc_info=True)
    
    def _handle_postback_event(self, event):
        """
        處理 Postback 事件（按鈕點擊等）
        
        Args:
            event: Postback 事件物件
        """
        try:
            source = event.get('source', {})
            line_user_id = source.get('userId')
            postback_data = event.get('postback', {}).get('data', '')
            reply_token = event.get('replyToken')
            
            if not line_user_id:
                return
            
            line_user = self._get_or_create_line_user(line_user_id)
            
            _logger.info(f'收到 Postback：{postback_data}')
            
            # 處理 Postback 資料
            # 未來可以擴充更多功能
            
        except Exception as e:
            _logger.error(f'處理 Postback 事件時發生錯誤：{str(e)}', exc_info=True)
    
    def _get_or_create_line_user(self, line_user_id):
        """
        取得或建立 LINE 用戶
        
        Args:
            line_user_id: LINE User ID
            
        Returns:
            line.user: LINE 用戶物件
        """
        line_user = request.env['line.user'].sudo().search([
            ('line_user_id', '=', line_user_id)
        ], limit=1)
        
        if not line_user:
            # 從 LINE Platform 取得用戶資料
            line_client = request.env['line.client.service'].sudo()
            profile = line_client.get_profile(line_user_id)
            
            if profile:
                line_user = request.env['line.user'].sudo().create({
                    'line_user_id': line_user_id,
                    'display_name': profile.get('displayName', ''),
                    'picture_url': profile.get('pictureUrl', ''),
                    'status_message': profile.get('statusMessage', ''),
                })
                _logger.info(f'建立新 LINE 用戶：{line_user.display_name} ({line_user_id})')
            else:
                # 無法取得資料時建立基本記錄
                line_user = request.env['line.user'].sudo().create({
                    'line_user_id': line_user_id,
                    'display_name': f'用戶_{line_user_id[:8]}',
                })
                _logger.warning(f'無法取得 LINE 用戶資料，建立基本記錄：{line_user_id}')
        
        return line_user
