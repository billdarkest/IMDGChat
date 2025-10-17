def handle_message(event):
    # 🔹 讀取 Google Sheet CSV 成為 DataFrame
    try:
        df = pd.read_csv(CSV_URL)
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="❌ 無法讀取 Google Sheet，請稍後再試。\n錯誤訊息：" + str(e))
        )
        return

    # 🔹 檢查文字長度 4 的情況
    if len(event.message.text) == 4:
        match_row = df[df['num'].astype(str) == event.message.text]

        if not match_row.empty:
            row = match_row.iloc[0]

            # 🔹 清理 PSN 欄位（移除前綴 "PSN"）
            psn_clean = str(row['PSN']).replace("PSN", "").strip()

            # 🔹 清理 EN 欄位（移除前綴 "EN!" 與後綴 "!BB"）
            en_clean = str(row['EN']).replace("EN!", "").replace("!BB", "").strip()

            # 🔹 組出回覆文字
            targeturl = f"這是 {psn_clean}, EMS 為 {en_clean}\n{row['AAA']}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查無資料，請確認代碼是否正確。"))

    # 🔹 查詢航班代碼部分保持原樣
    elif len(event.message.text) == 5 and event.message.text[0] == '*':
        targeturl = "https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode=" + event.message.text[1:] + "&vslNasme="
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
    elif len(event.message.text) == 5 and event.message.text[0] == '+':
        targeturl = "https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code=" + event.message.text[1:]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            handle_message(event)
            print("小幫手回覆成功")

    return 'OK'


@app.route('/keepalive', methods=['GET'])
def keep_alive():
    print("喚醒")
    return 'OK'


if __name__ == "__main__":
    # 🔹 Render 會提供 PORT 環境變數
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
