import os
import sys
import requests
import urllib.parse
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 建立 Flask 網頁伺服器應用程式
app = Flask(__name__)
# 會自動抓取你的檔名 (例如：DG42-24.py)
current_filename = os.path.basename(__file__)

# === LINE 環境變數設定 ===
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)

if channel_secret is None or channel_access_token is None:
    print('❌ 未設定 LINE_CHANNEL_SECRET 或 LINE_CHANNEL_ACCESS_TOKEN')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
parser = WebhookParser(channel_secret)

# === CSV 全域快取 (讀取本機檔案) ===
DG_DF = None

def load_csv_to_memory():
    global DG_DF
    # 對應我們剛剛產生的最終版 CSV
    file_path = "IMDG_42_24_Final.csv"
    
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案：{file_path}，請確認是否與程式碼放在同一層目錄")
        return
        
    try:
        print("📥 正在從本機載入 IMDG 42-24 危險品資料...")
        # 強制將所有欄位讀取為字串
        df = pd.read_csv(file_path, dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
        
        # 終極防呆：確保 un_no 乾淨，並自動在前面補 0 直到滿 4 碼
        if 'un_no' in df.columns:
            df['un_no'] = df['un_no'].astype(str).str.replace(".0", "", regex=False).str.strip().str.zfill(4)
        
        DG_DF = df
        print(f"✅ CSV 載入成功！共 {len(DG_DF)} 筆最新 42-24 資料，準備就緒。")
    except Exception as e:
        print(f"⚠️ CSV 載入失敗: {e}")

# 在程式啟動時立刻執行載入
load_csv_to_memory()

# === 處理訊息的自訂函式 ===
def handle_message(event):
    text = event.message.text.strip()

    # 🧩 處理 4 碼 UN 編號查詢 (支援同 UN 多筆資料顯示)
    if len(text) == 4 and text.isdigit():
        if DG_DF is not None and 'un_no' in DG_DF.columns:
            match_row = DG_DF[DG_DF['un_no'] == text]
            if not match_row.empty:
                reply_text = f"📦 查詢 UN 編號：{text}\n"
                reply_text += f"🔎 共找到 {len(match_row)} 筆不同規範：\n"
                reply_text += "=" * 20 + "\n"

                # 迴圈把所有符合的資料印出來
                for index, row in match_row.iterrows():
                    psn = str(row.get('proper_shipping_name', '')).strip()
                    cls = str(row.get('class_or_division', '')).strip()
                    
                    # 處理包裝等級 (PG)
                    pg = str(row.get('packing_group', '')).strip()
                    if pg.lower() == 'nan' or not pg:
                        pg = "無"
                        
                    ems = str(row.get('ems', '')).strip()
                    stow = str(row.get('stowage_and_segregation', '')).strip()

                    reply_text += (
                        f"📄 品名：{psn}\n"
                        f"📦 級別(PG)：{pg} | ⚠️ 類別：{cls}\n"
                        f"🚢 EMS：{ems}\n"
                        f"📋 隔離：{stow}\n"
                        f"-" * 20 + "\n"
                    )
            else:
                reply_text = f"❓ 查無此 UN 編號：{text}"
        else:
            reply_text = "⚠️ 危險品資料尚未準備好，請確認 CSV 檔案是否正確放置。"

        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🆕 處理 CINS 最新公告爬蟲
    elif text.upper() == "CINS":
        try:
            url = "https://www.cinsnet.com/newsy/"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            news_links = []
            
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
                for title, link in news_links:
                    reply_text += f"🔹 {title}\n{link}\n\n"
            else:
                reply_text = f"前往 CINS 查看：\n{url}"
        except Exception as e:
            reply_text = f"⚠️ 無法取得資訊: {e}\n請前往: {url}"
            
        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🆕 處理 SMDG 最新動態爬蟲
    elif text.upper() == "SMDG":
        try:
            url = "https://smdg.org/"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            news_links = []
            
            for element in soup.find_all(['nav', 'header', 'footer']):
                element.decompose()
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.text.strip()
                if title and len(title) > 10 and href.startswith("https://smdg.org/"):
                    if (title, href) not in news_links:
                        news_links.append((title, href))
                if len(news_links) >= 5:
                    break
            
            if news_links:
                reply_text = "⚓ 【SMDG 最新動態】\n\n"
                for title, link in news_links:
                    reply_text += f"🔹 {title}\n{link}\n\n"
            else:
                reply_text = f"前往 SMDG 查看：\n{url}"
        except Exception as e:
            reply_text = f"⚠️ 無法取得資訊: {e}\n請前往: {url}"
            
        reply_text += f"(回覆來自：{current_filename})"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    # 🔥 處理火災新聞搜尋
    elif text == "火災":
        try:
            query = urllib.parse.quote("貨櫃船 火災 OR container ship fire")
            url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            res = requests.get(url, timeout=5)
            root = ET.fromstring(res.text)
            news_items = root.findall('.//item')
            
            if news_items:
                reply_text = "🔥 【貨櫃船火災 相關新聞】\n\n"
                for item in news_items[:5]:
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

    return 'OK'

# === keepalive 給 UptimeRobot ===
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    return 'OK'

# === 主程式入口 ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
