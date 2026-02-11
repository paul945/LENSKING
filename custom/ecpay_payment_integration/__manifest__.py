# -*- coding: utf-8 -*-
{
    'name': '綠界付款整合 (ECPay Payment Integration)',
    'version': '16.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': '綠界金流自動對帳，支援信用卡、ATM、超商付款',
    'description': """
綠界付款整合模組
================

功能特色：
---------
* 自動接收綠界付款通知
* 自動更新租賃訂單付款狀態
* 支援信用卡、ATM、超商代碼等多種付款方式
* 自動建立會計付款記錄
* LINE 通知整合（付款成功自動通知）
* 完整的付款日誌記錄

適用於：時光幻鏡攝影器材租借系統
    """,
    'author': '時光幻鏡',
    'website': 'https://www.lensking.com.tw',
    'license': 'LGPL-3',
    
    # 依賴模組
    'depends': [
        'base',
        'sale_renting',  # Odoo 租賃模組
        'account',       # 會計模組
    ],
    
    # 資料檔案
    'data': [
        'security/ir.model.access.csv',
        'data/system_parameters.xml',
        'data/automated_actions.xml',
        'views/rental_order_views.xml',
    ],
    
    # 安裝設定
    'installable': True,
    'application': False,
    'auto_install': False,
    
    # 版本資訊
    'sequence': 1,
}
