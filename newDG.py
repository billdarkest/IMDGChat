import os
import sys
import io
import requests
import pandas as pd
from bs4 import BeautifulSoup  # 🆕 爬蟲套件
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

# 如果沒有抓到金鑰，程式會直接停止
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
# 從 Render 讀取你存放危險品資料的 CSV 網址
CSV_URL = os.getenv("CSV_URL", None)
if CSV_URL is None:
    print("❌ 未設定 CSV_URL，請在 Render Environment 新增")
else:
    print(f"📄 Loaded CSV_URL: {CSV_URL}")

# === 處理訊息的自訂函式 ===
def handle_message(event):
    # 將使用者傳來的文字去除前後多餘的空白
    text = event.message.text.strip()

    # 🧩 處理 4 碼 UN 編號查詢
    if len(text) == 4 and text.isdigit():
        try:
            # 即時發送網路請求，下載最新的 CSV 內容
            response = requests.get(CSV_URL)
            response.encoding = 'utf-8'
            
            # 使用 pandas 把下載下來的文字轉換成表格
            df = pd.read_csv(io.StringIO(response.text), sep=',', quotechar='"', engine='python', skip_blank_lines=True)
            df.columns = [c.strip().lower() for c in df.columns]

            # 嘗試偵測 UN 編號欄位
            if 'un_no' in df.columns:
                un_col = 'un_no'
            elif 'num' in df.columns:
                un_col = 'num'
            else:
                raise KeyError("CSV 未找到 'un_no' 或 'num' 欄位")

            # 清理 UN 欄位並比對
            df[un_col] = df[un_col].astype(str).str.replace("num", "").str.strip()
            match_row = df[df[un_col] == text]

            # 如果有找到資料
            if not match_row.empty:
                row = match_row.iloc[0]
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

        # 於回覆文字最下方加上目前的檔案名稱
        reply_text += f"\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🆕 處理 CINS 最新公告爬蟲 (輸入「CINS最新」觸發)
    elif text.upper() == "CINS":
        try:
            # 網址更新為最新的 newsy 頁面
            url = "https://www.cinsnet.com/newsy/"
            # 加上 User-Agent 偽裝成瀏覽器，避免被阻擋
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            res = requests.get(url, headers=headers, timeout=5)
            
            # 解析網頁 HTML
            soup = BeautifulSoup(res.text, 'html.parser')
            
            news_links = []
            # 在新聞頁面中，通常標題會包在 a 標籤中
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.text.strip()
                
                # 過濾掉沒有文字的連結，或是首頁、聯絡我們等無關導覽列
                if title and len(title) > 10 and "cinsnet.com" in href and "contact" not in href.lower():
                    if (title, href) not in news_links:
                        news_links.append((title, href))
                
                # 最多只取前 5 筆
                if len(news_links) >= 5:
                    break
            
            if news_links:
                reply_text = "📰 【CINS 最新公告與動態】\n\n"
                for i, (title, link) in enumerate(news_links, 1):
                    reply_text += f"🔹 {title}\n{link}\n\n"
            else:
                reply_text = f"前往 CINS 最新動態查看：\n{url}"
                
        except Exception as e:
            reply_text = f"⚠️ 無法即時取得 CINS 網站資訊: {e}\n請直接前往: {url}"
            
        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🧭 處理 5 碼，且開頭為 '*' 的查詢 (長榮船期表查詢)
    elif len(text) == 5 and text[0] == '*':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode={text[1:]}&vslName="
        reply_text = f"{targeturl}\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        
    # 🧭 處理 5 碼，且開頭為 '+' 的查詢 (長榮航次查詢)
    elif len(text) == 5 and text[0] == '+':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code={text[1:]}"
        reply_text = f"{targeturl}\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# === LINE Webhook 接收端點 ===
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
