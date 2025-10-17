import os
import sys
import io
import requests
import pandas as pd
from argparse import ArgumentParser
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# === LINE 環境變數設定 ===
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('❌ 未設定 LINE_CHANNEL_SECRET')
    sys.exit(1)
if channel_access_token is None:
    print('❌ 未設定 LINE_CHANNEL_ACCESS_TOKEN')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
parser = WebhookParser(channel_secret)

# === CSV 環境變數 ===
CSV_URL = os.getenv("CSV_URL", None)
if CSV_URL is None:
    print("❌ 未設定 CSV_URL，請在 Render Environment 新增")
else:
    print(f"📄 Loaded CSV_URL: {CSV_URL}")

# === 處理訊息 ===
def handle_message(event):
    text = event.message.text.strip()

    # 🧩 處理 4 碼 UN 編號查詢
    if len(text) == 4 and text.isdigit():
        try:
            # 下載 CSV 並解析（支援含逗號欄位）
            response = requests.get(CSV_URL)
            response.encoding = 'utf-8'
            df = pd.read_csv(io.StringIO(response.text), sep=',', quotechar='"', engine='python', skip_blank_lines=True)

            # 正規化欄位名稱（去除空白）
            df.columns = [c.strip().lower() for c in df.columns]

            # 嘗試偵測 UN 編號欄位（可能叫 num 或 un_no）
            if 'un_no' in df.columns:
                un_col = 'un_no'
            elif 'num' in df.columns:
                un_col = 'num'
            else:
                raise KeyError("CSV 未找到 'un_no' 或 'num' 欄位")

            df[un_col] = df[un_col].astype(str).str.replace("num", "").str.strip()
            match_row = df[df[un_col] == text]

            if not match_row.empty:
                row = match_row.iloc[0]

                # 清理資料
                psn = str(row.get('proper_shipping_name', '')).replace("PSN", "").strip()
                ems = str(row.get('ems', '')).replace("EN!", "").replace("!BB", "").strip()
                stow = str(row.get('stowage_and_segregation', '')).replace("AAA", "").strip()

                reply_text = (
                    f"📦 UN編號：{text}\n"
                    f"📄 品名：{psn}\n"
                    f"🚢 EMS：{ems}\n"
                    f"📋 儲存與隔離：{stow}"
                )
            else:
                reply_text = f"❓ 查無此 UN 編號：{text}"

        except Exception as e:
            reply_text = f"⚠️ 發生錯誤：{e}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🧭 5 碼開頭 * 或 + 的查詢
    elif len(text) == 5 and text[0] == '*':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode={text[1:]}&vslName="
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
    elif len(text) == 5 and text[0] == '+':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code={text[1:]}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))


# === LINE Webhook ===
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            handle_message(event)
            print("✅ 小幫手回覆成功")

    return 'OK'


# === keepalive 給 uptime robot ping 用 ===
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    print("🩵 Keepalive ping received")
    return 'OK'


# === 主程式入口 ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
