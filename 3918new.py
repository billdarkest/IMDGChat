from flask import Flask, request, abort
from linebot import LineBotApi, WebhookParser
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
import pandas as pd
import os

app = Flask(__name__)

# 讀取環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CSV_URL = os.getenv("CSV_URL")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("❌ 請設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)


# === 處理 LINE webhook ===
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            handle_message(event)
            print("✅ 小幫手回覆成功")

    return 'OK'


# === 處理使用者訊息 ===
def handle_message(event):
    user_input = event.message.text.strip()

    if len(user_input) != 4 or not user_input.isdigit():
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入 4 位 UN number（例如：0004）")
        )
        return

    try:
        # 讀取 CSV
        df = pd.read_csv(CSV_URL)
        df.columns = df.columns.str.strip()

        # 處理 un_no 欄位去掉 "num"
        df['un_no_clean'] = df['un_no'].astype(str).str.replace('num', '').str.strip()

        match = df[df['un_no_clean'] == user_input]
        if match.empty:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ 查無此 UN 編號：{user_input}")
            )
            return

        row = match.iloc[0]
        ems_clean = str(row.get('ems', '')).replace("EN!", "").replace("!BB", "").strip()

        reply = (
            f"📦 UN編號：{row['un_no']}\n"
            f"📄 品名：{row['proper_shipping_name']}\n"
            f"🚢 EMS：{ems_clean}\n"
            f"📋 儲存與隔離：{row['stowage_and_segregation']}"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"⚠️ 發生錯誤：{e}")
        )


# === 保留給 UptimeRobot ping 的 keepalive ===
@app.route("/keepalive", methods=['GET'])
def keep_alive():
    print("⚡ UptimeRobot ping 收到，Render 保持清醒")
    return "OK"


# === 首頁測試用 ===
@app.route("/", methods=['GET'])
def home():
    return "LINE Bot 正在運行中 🚀"


# === 主程式 ===
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
