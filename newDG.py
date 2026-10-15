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

# 建立 Flask 網頁伺服器應用程式
app = Flask(__name__)

# 自動取得目前執行的 Python 檔案名稱 (例如：newDG.py)
current_filename = os.path.basename(__file__)

# === LINE 環境變數設定 ===
# 從 Render 的 Environment Variables 讀取 LINE Bot 的金鑰
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)

# 如果沒有抓到金鑰，程式會直接停止 (確保不會因為少設定而發生無法預期的錯誤)
if channel_secret is None:
    print('❌ 未設定 LINE_CHANNEL_SECRET')
    sys.exit(1)
if channel_access_token is None:
    print('❌ 未設定 LINE_CHANNEL_ACCESS_TOKEN')
    sys.exit(1)

# 初始化 LINE Bot API 與 Webhook 解析器
line_bot_api = LineBotApi(channel_access_token)
parser = WebhookParser(channel_secret)

# === CSV 環境變數 ===
# 從 Render 讀取你存放危險品資料的 CSV 網址 (例如 Google Sheet 的發布網址)
CSV_URL = os.getenv("CSV_URL", None)
if CSV_URL is None:
    print("❌ 未設定 CSV_URL，請在 Render Environment 新增")
else:
    print(f"📄 Loaded CSV_URL: {CSV_URL}")

# === 處理訊息的自訂函式 ===
# 當收到文字訊息時，LINE 的 callback 會把事件丟給這個函式處理
def handle_message(event):
    # 將使用者傳來的文字去除前後多餘的空白
    text = event.message.text.strip()

    # 🧩 處理 4 碼 UN 編號查詢
    # 判斷條件：字數剛好是 4 個字，且全部都是數字
    if len(text) == 4 and text.isdigit():
        try:
            # 即時發送網路請求，下載最新的 CSV 內容
            response = requests.get(CSV_URL)
            response.encoding = 'utf-8'
            
            # 使用 pandas 把下載下來的文字轉換成表格 (DataFrame)
            df = pd.read_csv(io.StringIO(response.text), sep=',', quotechar='"', engine='python', skip_blank_lines=True)

            # 正規化欄位名稱（把欄位名稱的空白去掉，並轉成小寫，避免因為打錯字抓不到）
            df.columns = [c.strip().lower() for c in df.columns]

            # 嘗試偵測 UN 編號欄位叫什麼名字（可能叫 num 或 un_no）
            if 'un_no' in df.columns:
                un_col = 'un_no'
            elif 'num' in df.columns:
                un_col = 'num'
            else:
                # 如果都找不到，丟出錯誤
                raise KeyError("CSV 未找到 'un_no' 或 'num' 欄位")

            # 清理 UN 欄位：轉成字串、去掉 "num" 字眼、去除空白
            df[un_col] = df[un_col].astype(str).str.replace("num", "").str.strip()
            
            # 在表格中尋找 UN 欄位等於使用者輸入 (text) 的那筆資料
            match_row = df[df[un_col] == text]

            # 如果有找到資料
            if not match_row.empty:
                # 取出符合的第一筆資料
                row = match_row.iloc[0]

                # 清理並取得需要的欄位資料 (去除掉不要的文字如 PSN, EN!, !BB, AAA 等)
                psn = str(row.get('proper_shipping_name', '')).replace("PSN", "").strip()
                ems = str(row.get('ems', '')).replace("EN!", "").replace("!BB", "").strip()
                stow = str(row.get('stowage_and_segregation', '')).replace("AAA", "").strip()

                # 組裝要回覆給使用者的文字格式
                reply_text = (
                    f"📦 UN編號：{text}\n"
                    f"📄 品名：{psn}\n"
                    f"🚢 EMS：{ems}\n"
                    f"📋 儲存與隔離：{stow}"
                )
            else:
                # 表格裡找不到這個編號
                reply_text = f"❓ 查無此 UN 編號：{text}"

        except Exception as e:
            # 過程中有任何當機或錯誤，把錯誤訊息印給使用者看
            reply_text = f"⚠️ 發生錯誤：{e}"

        # 於回覆文字最下方加上目前的檔案名稱
        reply_text += f"\n\n(回覆來自：{current_filename})"

        # 呼叫 LINE API 將組合好的文字回傳給使用者
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🧭 處理 5 碼，且開頭為 '*' 的查詢 (長榮船期表查詢)
    elif len(text) == 5 and text[0] == '*':
        # text[1:] 代表取第2個字元到最後 (例如輸入 *0362，就會取 0362 放進網址)
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode={text[1:]}&vslName="
        reply_text = f"{targeturl}\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        
    # 🧭 處理 5 碼，且開頭為 '+' 的查詢 (長榮航次查詢)
    elif len(text) == 5 and text[0] == '+':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code={text[1:]}"
        reply_text = f"{targeturl}\n\n(檔案版本：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


# === LINE Webhook 接收端點 ===
# 這是 LINE 伺服器丟訊息過來時，你的程式接收的唯一入口 (網址結尾是 /callback)
@app.route("/callback", methods=['POST'])
def callback():
    # 取得 LINE 傳來的加密簽名
    signature = request.headers['X-Line-Signature']
    # 取得 LINE 傳來的完整訊息內容 (JSON 字串)
    body = request.get_data(as_text=True)

    try:
        # 解析這則訊息，並驗證是不是真的從 LINE 官方傳來的
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        # 如果驗證失敗 (可能是駭客偽造的請求)，回傳 HTTP 400 錯誤
        abort(400)

    # 逐一處理收到的事件 (有時候會一次收到多筆訊息)
    for event in events:
        # 我們只處理「訊息事件 (MessageEvent)」且必須是「文字訊息 (TextMessage)」
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            # 呼叫上面寫好的處理邏輯
            handle_message(event)
            print("✅ 小幫手回覆成功") # 在 Render 後台 Logs 會印出這行

    # 必須回傳 OK 讓 LINE 知道我們有收到，不然 LINE 會一直重發
    return 'OK'


# === keepalive 給 uptime robot ping 用 ===
# 防止 Render 免費伺服器因閒置超過 15 分鐘而休眠
# UptimeRobot 會定時打這個網址來叫醒機器
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    print("🩵 Keepalive ping received")
    return 'OK'


# === 主程式入口 ===
# 當這個 Python 檔案被執行時，啟動 Flask 伺服器
if __name__ == "__main__":
    # Render 會自動給予一個 PORT，如果沒有給，預設用 8000
    port = int(os.environ.get("PORT", 8000))
    # host="0.0.0.0" 代表允許外部網路連線進來
    app.run(host="0.0.0.0", port=port)
