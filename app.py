
import base64
import hashlib
import hmac
import json
import os
from queue import Queue
import threading

import requests
from dotenv import load_dotenv
from flask import Flask, request

import commands


# ==========================================
# 1. 載入環境變數
# ==========================================

# 固定從 app.py 所在資料夾尋找 .env，避免工作目錄不同而讀取失敗。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(dotenv_path=ENV_PATH, override=True)

LINE_CHANNEL_SECRET = (
    os.getenv("LINE_CHANNEL_SECRET") or ""
).strip()

LINE_CHANNEL_ACCESS_TOKEN = (
    os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
).strip()

LINE_REPLY_API_URL = "https://api.line.me/v2/bot/message/reply"


# ==========================================
# 2. Flask 初始化
# ==========================================

app = Flask(__name__)
MESSAGE_QUEUE = Queue()


# 啟動時檢查環境變數，但不印出金鑰。
print("========== LINE Bot 設定檢查 ==========")
print("目前 .env 路徑：", ENV_PATH)
print(".env 檔案存在：", os.path.isfile(ENV_PATH))
print("Channel Secret 已載入：", bool(LINE_CHANNEL_SECRET))
print("Channel Access Token 已載入：", bool(LINE_CHANNEL_ACCESS_TOKEN))
print("=======================================")


# ==========================================
# 3. LINE 簽章驗證
# ==========================================

def verify_signature(body, signature):
    """
    使用 Channel Secret 對原始 request body
    計算 HMAC-SHA256，並與 LINE 傳來的簽章比較。
    """

    if not LINE_CHANNEL_SECRET or not signature:
        return False

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    expected_signature = base64.b64encode(digest).decode("utf-8")

    return hmac.compare_digest(expected_signature, signature)


# ==========================================
# 4. 回覆 LINE 訊息
# ==========================================

def reply_message(reply_token, message):

    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("錯誤：沒有載入 LINE_CHANNEL_ACCESS_TOKEN")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": str(message),
            }
        ],
    }

    try:
        response = requests.post(
            LINE_REPLY_API_URL,
            headers=headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()
        print("LINE 訊息回覆成功。")

    except requests.RequestException as error:
        print(f"LINE API 回覆失敗：{error}")

        if error.response is not None:
            print("LINE API 回應：", error.response.text)


def process_text_message(user_id, reply_token, message_text):
    """在背景處理文字指令並呼叫 LINE 回覆 API。"""
    try:
        reply_text = commands.handle_text(user_id, message_text)
        reply_message(reply_token, reply_text)
    except Exception as error:
        print(f"處理 LINE 訊息時發生錯誤：{error}")
        reply_message(reply_token, "處理訊息時發生錯誤，請稍後再試。")


def message_worker():
    """依序處理收到的訊息，避免確認指令和前一筆操作互相競爭。"""
    while True:
        user_id, reply_token, message_text = MESSAGE_QUEUE.get()
        try:
            process_text_message(user_id, reply_token, message_text)
        finally:
            MESSAGE_QUEUE.task_done()


threading.Thread(target=message_worker, daemon=True).start()


# ==========================================
# 5. LINE Webhook
# ==========================================

@app.route("/callback", methods=["POST"])
def callback():

    # 取得原始請求內容，不要先解析或修改 JSON。
    body = request.get_data()

    # 取得 LINE 傳送的簽章。
    signature = request.headers.get("X-Line-Signature", "")

    # 診斷資訊：不印出實際簽章或 Secret。
    print("收到 LINE Webhook POST")
    print("Request Body 長度：", len(body))
    print("收到 LINE Signature：", bool(signature))
    print("Channel Secret 已載入：", bool(LINE_CHANNEL_SECRET))

    # 驗證簽章。
    if not verify_signature(body, signature):
        print("簽章驗證失敗，拒絕請求。")
        return "無效的 LINE 簽章", 401

    print("簽章驗證成功。")

    # 解析 JSON。
    try:
        webhook_data = json.loads(body.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError):
        return "請求內容不是有效的 JSON", 400

    events = webhook_data.get("events", [])

    # 逐筆處理 LINE 事件。
    for event in events:

        message_data = event.get("message", {})

        # 只處理文字訊息。
        if message_data.get("type") != "text":
            continue

        source = event.get("source", {})
        user_id = source.get("userId")
        reply_token = event.get("replyToken")
        message_text = message_data.get("text", "")

        if not user_id:
            print("略過事件：找不到 user_id")
            continue

        if not reply_token:
            print("略過事件：找不到 replyToken")
            continue

        # 先讓 LINE 收到 Webhook 成功回應，再依序於背景處理訊息。
        # LINE 的 Webhook 回應期限較短，避免等待回覆 API 的網路延遲。
        MESSAGE_QUEUE.put((user_id, reply_token, message_text))

    return "OK", 200


# ==========================================
# 6. 啟動 Flask
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
