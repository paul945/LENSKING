# -*- coding: utf-8 -*-
{
    'name': 'LINE Bot 整合',
    'version': '1.0.0',
    'category': 'Sales',
    'summary': 'LINE Bot 自動化租借系統',
    'description': """
LINE Bot 整合模組
=================

功能：
-----
* LINE Messaging API 整合
* 自動接收客戶訊息
* 器材瀏覽與選擇
* 自動建立租借訂單
* 發送付款連結
* 訂單狀態通知

技術：
-----
* LINE Messaging API
* Flex Message
* Quick Reply
* LIFF (未來版本)

作者：Claude (Anthropic)
客戶：時光幻鏡攝影器材租借
    """,
    'author': 'Claude',
    'website': 'https://www.lensking.com.tw',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'sale_management',
        'ecpay_payment_integration',  # 依賴 Phase 1 的綠界模組
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/system_parameters.xml',
        'views/line_user_views.xml',
        'views/line_conversation_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
