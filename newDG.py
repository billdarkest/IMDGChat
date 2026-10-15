import os
import sys
import io
import requests
import urllib.parse
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
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

# === CSV 全域快取 (啟動時只讀取一次) ===
CSV_URL = os.getenv("CSV_URL", None)
DG_DF = None
UN_COL = None

def load_csv_to_memory():
    global DG_DF, UN_COL
    if CSV_URL is None:
        print("❌ 未設定 CSV_URL，請在 Render Environment 新增")
        return
        
    try:
        print("📥 正在從 Google 試算表載入危險品資料...")
        response = requests.get(CSV_URL)
        response.encoding = 'utf-8'
        df = pd.read_csv(io.StringIO(response.text), sep=',', quotechar='"', engine='python', skip_blank_lines=True)
        df.columns = [c.strip().lower() for c in df.columns]

        if 'un_no' in df.columns:
            UN_COL = 'un_no'
        elif 'num' in df.columns:
            UN_COL = 'num'
        else:
            raise KeyError("未找到 'un_no' 或 'num' 欄位")

        df[UN_COL] = df[UN_COL].astype(str).str.replace("num", "", case=False).str.strip()
        DG_DF = df
        print(f"✅ CSV 載入成功！共 {len(DG_DF)} 筆資料，之後查詢將瞬間回覆。")
    except Exception as e:
        print(f"⚠️ CSV 載入失敗: {e}")

# 在程式啟動時立刻執行載入
load_csv_to_memory()

# === 處理訊息的自訂函式 ===
def handle_message(event):
    text = event.message.text.strip()

    # 🔄 隱藏指令：手動更新 CSV (不用重開機)
    if text.upper() == "!RELOAD":
        load_csv_to_memory()
        reply_text = f"✅ 危險品資料庫已重新下載並更新至記憶體！\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # 🧩 處理 4 碼 UN 編號查詢 (直接讀取記憶體，速度極快)
    if len(text) == 4 and text.isdigit():
        if DG_DF is not None and UN_COL is not None:
            match_row = DG_DF[DG_DF[UN_COL] == text]
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
        else:
            reply_text = "⚠️ 危險品資料尚未準備好，請稍後再試。"

        reply_text += f"\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🆕 處理 CINS 最新公告爬蟲
    elif text.upper() == "CINS":
        try:
            url = "https://www.cinsnet.com/newsy/"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            res = requests.get(url, headers=headers, timeout=5)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            news_links = []
            
            # 移除導覽列與頁尾，避免抓到無關按鈕
            for element in soup.find_all(['nav', 'header', 'footer']):
                element.decompose()
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.text.strip()
                if title and len(title) > 10 and "cinsnet.com" in href:
                    if (title, href) not in news_links:
                        news_links.append((title, href))
                if len(news_links) >= 5:
                    break
            
            if news_links:
                reply_text = "📰 【CINS 最新公告與動態】\n\n"
                for i, (title, link) in enumerate(news_links, 1):
                    reply_text += f"🔹 {title}\n{link}\n\n"
            else:
                reply_text = f"前往 CINS 查看：\n{url}"
        except Exception as e:
            reply_text = f"⚠️ 無法取得資訊: {e}\n請前往: {url}"
            
        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🔥 處理火災新聞搜尋
    elif text == "火災":
        try:
            # 透過 Google News RSS 搜尋中英文的貨櫃船火災新聞
            query = urllib.parse.quote("貨櫃船 火災 OR container ship fire")
            url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            
            res = requests.get(url, timeout=5)
            # 解析 XML 格式的 RSS
            root = ET.fromstring(res.text)
            news_items = root.findall('.//item')
            
            if news_items:
                reply_text = "🔥 【貨櫃船火災 相關新聞】\n\n"
                # 取最新的前 5 則新聞
                for i, item in enumerate(news_items[:5], 1):
                    title = item.find('title').text
                    link = item.find('link').text
                    reply_text += f"🔹 {title}\n{link}\n\n"
            else:
                reply_text = "目前未搜尋到相關的火災新聞。"
                
        except Exception as e:
            reply_text = f"⚠️ 無法取得新聞資訊: {e}"
            
        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🧭 處理長榮船期表查詢
    elif len(text) == 5 and text[0] == '*':
        targeturl = f"https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode={text[1:]}&vslName="
        reply_text = f"{targeturl}\n\n(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        
    # 🧭 處理長榮航次查詢
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
            print("✅ 訊息處理成功")

    return 'OK'

# === keepalive 給 UptimeRobot ===
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    return 'OK'

# === 主程式入口 ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
