import requests
import os
import sys
from argparse import ArgumentParser
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import pandas as pd  # 🔹 用於 CSV 讀取

# -----------------------------
# Flask 初始化
# -----------------------------
app = Flask(__name__)

# -----------------------------
# LINE Channel 環境變數設定
# -----------------------------
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('❌ 請設定環境變數 LINE_CHANNEL_SECRET')
    sys.exit(1)
if channel_access_token is None:
    print('❌ 請設定環境變數 LINE_CHANNEL_ACCESS_TOKEN')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
parser = WebhookParser(channel_secret)

# -----------------------------
# Google Sheet CSV 連結
# -----------------------------
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTfHqhAoeOGajlma3K7Ym1CngD2VI3ua99fwPc767QpExzAMyV81S6L1IZ6TwzSPLO2irkZt96QA-3h/pub?output=csv"


# -----------------------------
# 處理訊息主邏輯
# -----------------------------
def handle_message(event):
    try:
        df = pd.read_csv(CSV_URL)
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"❌ 無法讀取 Google Sheet，請稍後再試。\n錯誤訊息：{e}")
        )
        return

    # 如果輸入長度為4 → 查詢表格
    if len(event.message.text) == 4:
        match_row = df[df['num'].astype(str) == event.message.text]

        if not match_row.empty:
            row = match_row.iloc[0]

            # 清理 PSN 欄位（去掉前綴 PSN）
            psn_clean = str(row['PSN']).replace("PSN", "").strip()

            # 清理 EN 欄位（去掉 EN! 與 !BB）
            en_clean = str(row['EN']).replace("EN!", "").replace("!BB", "").strip()

            targeturl = f"這是 {psn_clean}, EMS 為 {en_clean}\n{row['AAA']}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查無資料，請確認代碼是否正確。"))

    # 如果輸入以 * 開頭 → 查航班網址
    elif len(event.message.text) == 5 and event.message.text[0] == '*':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode={event.message.text[1:]}&vslNasme="
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))

    # 如果輸入以 + 開頭 → 查航次網址
    elif len(event.message.text) == 5 and event.message.text[0] == '+':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code={event.message.text[1:]}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))


# -----------------------------
# LINE Webhook 回呼
# -----------------------------
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
            print("✅ LINE Bot 已成功回覆訊息")

    return 'OK'


# -----------------------------
# Keepalive 路徑（Render ping 用）
# -----------------------------
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    print("⚡ Render 喚醒中")
    return 'OK'


# -----------------------------
# 啟動主程式
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
