
import re
import requests
import os
import sys
from argparse import ArgumentParser

from flask import Flask, request, abort
from linebot import (
    LineBotApi, WebhookParser
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)

app = Flask(__name__)

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

line_bot_api = LineBotApi(channel_access_token)
parser = WebhookParser(channel_secret)



def handle_message(event):
    if len(event.message.text) == 4 :
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Mobile Safari/537.36"}
        res = requests.get("https://docs.google.com/spreadsheets/d/e/2PACX-1vTfHqhAoeOGajlma3K7Ym1CngD2VI3ua99fwPc767QpExzAMyV81S6L1IZ6TwzSPLO2irkZt96QA-3h/pubhtml", headers=headers)
        DG = re.findall('width:47px;left:-1px">num(.*?)</div></td', res.content.decode('utf-8'), re.S)
        SH = re.findall('left:-1px">PSN(.*?)</div></td><td', res.content.decode('utf-8'), re.S)
        EMS = re.findall('left:-1px">EN!(.*?)!BB</div></', res.content.decode('utf-8'), re.S)
        SS = re.findall('px;left:-1px">AAA(.*?)</div></td></tr><tr style="height:', res.content.decode('utf-8'), re.S)

        for D in range(0, 2856):
            if event.message.text == DG[D]:
                targeturl ="這是" + SH[D] + ", Ems為 " + EMS[D] + '\n' + SS[D]
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
            
    if len(event.message.text) == 5 and event.message.text[0] == '*':
        targeturl = "https://ss.shipmentlink.com/tvs2/jsp/TVS2_VesselSchedule.jsp?vslCode=" + event.message.text[1:] + "&vslNasme="
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=targeturl))
    elif len(event.message.text) == 5 and event.message.text[0] == '+':
        targeturl = "https://ss.shipmentlink.com/tvs2/jsp/TVS2_ShowVesselVoyage.jsp?vessel_name=&vessel_code=" + event.message.text[1:] + ""
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
    if 'HTTP_X_LINE_SIGNATURE' not in request.environ:
        print("喚醒")
        # 如果沒有 X-Line-Signature，就返回 200 OK
        return 'OK'

    # 如果有 X-Line-Signature，就返回 400 Bad Request
    abort(400)

if __name__ == "__main__":
    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    )
    arg_parser.add_argument('-p', '--port', type=int, default=8000, help='port')
    arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    options = arg_parser.parse_args()

    app.run(debug=options.debug, port=options.port)
