# LINE Bot 整合模組

## 簡介

這是一個為時光幻鏡攝影器材租借系統開發的 LINE Bot 整合模組，讓客戶可以透過 LINE 輕鬆租借攝影器材。

## 功能特色

### 🤖 LINE Bot 功能
- ✅ 自動接收客戶訊息
- ✅ 智慧對話處理
- ✅ 器材分類瀏覽
- ✅ 器材詳細資訊展示
- ✅ 訂單自動建立
- ✅ 付款連結自動發送
- ✅ 訂單狀態通知

### 📊 後台管理
- ✅ LINE 用戶管理
- ✅ 對話記錄查詢
- ✅ 訂單追蹤
- ✅ 統計分析

## 安裝步驟

### 1. 上傳模組
將 `line_bot_integration` 資料夾上傳到 Odoo.sh 的 `custom` 目錄

### 2. 更新應用程式列表
在 Odoo 後台：
1. 進入「應用程式」
2. 點選「更新應用程式列表」
3. 搜尋「LINE Bot」
4. 點選「安裝」

### 3. 設定 LINE Webhook

#### LINE Developers 設定
1. 登入 [LINE Developers Console](https://developers.line.biz/console/)
2. 選擇您的 Channel
3. 前往「Messaging API」設定頁面
4. 設定 Webhook URL：
   ```
   https://www.lensking.com.tw/line/webhook
   ```
5. 啟用「Use webhook」
6. 停用「Auto-reply messages」
7. 停用「Greeting messages」

#### 驗證 Webhook
點選「Verify」按鈕測試連線

### 4. 測試 LINE Bot

#### 掃描 QR Code
使用 LINE 掃描 Channel 的 QR Code 加入好友

#### 發送測試訊息
發送「租借器材」測試功能

## 系統需求

### Odoo 模組依賴
- `base`
- `sale`
- `sale_management`
- `ecpay_payment_integration` (Phase 1 綠界模組)

### Python 套件
- `requests`

## 架構說明

### 模組結構
```
line_bot_integration/
├── __init__.py
├── __manifest__.py
├── controllers/
│   └── line_webhook.py          # Webhook Controller
├── models/
│   ├── line_user.py              # LINE 用戶模型
│   ├── line_conversation.py      # 對話記錄模型
│   └── sale_order.py             # 訂單擴充
├── services/
│   ├── line_client.py            # LINE API 客戶端
│   └── conversation_handler.py   # 對話處理器
├── data/
│   └── system_parameters.xml     # 系統參數
├── views/
│   ├── line_user_views.xml       # 用戶視圖
│   ├── line_conversation_views.xml
│   └── menu_views.xml            # 選單
└── security/
    └── ir.model.access.csv       # 權限設定
```

### 對話流程
```
用戶發送訊息
    ↓
LINE Platform
    ↓
Webhook (/line/webhook)
    ↓
驗證簽章
    ↓
解析事件
    ↓
對話處理器 (Conversation Handler)
    ↓
根據狀態處理
    ↓
發送回應 (LINE Client)
    ↓
記錄對話
```

## 使用說明

### 客戶操作流程

#### 1. 加入好友
掃描 QR Code 或搜尋 LINE ID

#### 2. 開始租借
發送「租借器材」或點選選單

#### 3. 選擇分類
點選器材分類（相機、鏡頭、閃光燈等）

#### 4. 選擇器材
瀏覽器材並點選「選擇租借」

#### 5. 確認訂單
查看訂單資訊

#### 6. 完成付款
點選付款連結完成付款

### 後台操作

#### 查看 LINE 用戶
1. 進入「LINE Bot」→「LINE 用戶」
2. 查看用戶資料、對話狀態、訂單記錄

#### 查看對話記錄
1. 進入「LINE Bot」→「對話記錄」
2. 篩選日期、用戶、訊息類型

#### 管理系統參數
1. 進入「LINE Bot」→「設定」→「LINE API 設定」
2. 修改 Channel Access Token 等參數

## 常見問題

### Q1: Webhook 驗證失敗
**解決方案：**
1. 確認 Channel Secret 設定正確
2. 檢查 Webhook URL 格式
3. 確認模組已安裝啟用

### Q2: 收不到訊息
**解決方案：**
1. 檢查「Use webhook」是否已啟用
2. 確認「Auto-reply messages」已停用
3. 查看 Odoo 日誌確認是否有錯誤

### Q3: 無法發送訊息
**解決方案：**
1. 確認 Channel Access Token 正確
2. 檢查 Token 是否過期
3. 確認網路連線正常

## 技術支援

### 文件
- [LINE Messaging API 文件](https://developers.line.biz/en/docs/messaging-api/)
- [Odoo 開發文件](https://www.odoo.com/documentation/)

### 聯絡
- Email: lensfantasy@gmail.com
- 電話: 0905-527-577

## 版本歷史

### v1.0.0 (2026-02-13)
- ✅ 初始版本
- ✅ 基本對話功能
- ✅ 器材瀏覽
- ✅ 訂單建立
- ✅ 付款整合

## 授權

LGPL-3

## 作者

Claude (Anthropic)  
客戶：時光幻鏡攝影器材租借
