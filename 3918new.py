from flask import Flask, request, abort

import requests

import re

from bs4 import BeautifulSoup

import pymysql

count = 0
for i in range(50):
    inputlist = input('請優雅的輸入UN:')
    if inputlist.isdigit():
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Mobile Safari/537.36"}
        res = requests.get(
            "https://docs.google.com/spreadsheets/d/e/2PACX-1vTfHqhAoeOGajlma3K7Ym1CngD2VI3ua99fwPc767QpExzAMyV81S6L1IZ6TwzSPLO2irkZt96QA-3h/pubhtml",
            headers=headers)
        DG = re.findall('</div></th><td class="s0" dir="ltr">(.*?)</td><td class=', res.content.decode('utf-8'), re.S)
        SH = re.findall(
            'td class="s0 softmerge" dir="ltr"><div class="softmerge-inner" style="width:27px;left:-1px">(.*?)</div></td><td class="s4" dir="ltr">',
            res.content.decode('utf-8'), re.S)
        EMS = re.findall('</div></td><td class="s4" dir="ltr">.*?</td><td class="s0" dir="ltr">(.*?)</td><td',
                         res.content.decode('utf-8'), re.S)
        SS = re.findall('QQQ(.*?)AAA', res.content.decode('utf-8'), re.S)
        DG.remove('un_no')
        SS.remove('stowage_and_segregation')
        print(len(DG), len(SH), len(EMS), len(SS))
        for D in range(0, 2853):
            if inputlist == DG[D]:
                print(DG[D])
                print("這是" + SH[D] + ",ems為" + EMS[D])
                print(SS[D])
                count += 1
        if count == 10:
            print("你查了10次，感覺有點累了")
        elif count == 50:
            print("猛！你查了50次，休息一下，至少重開程式去喝個水")
        else:
            continue

    else:
        print("你打錯了嗎")
