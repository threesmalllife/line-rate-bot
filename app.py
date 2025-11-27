import os
import datetime
import twder
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# =================設定區=================
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')

# Google Sheets 設定
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# 這裡預設讀取專案資料夾裡的 credentials.json
JSON_KEY_FILE = 'credentials.json' 
SHEET_NAME = '記帳機器人' # 你的試算表名稱

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 連線到 Google Sheets 的函式
def get_worksheet():
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1  # 開啟第一張工作表
    return sheet

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip() # 移除前後空白
    
    try:
        # === 功能 A: 刪除上一筆 ===
        if msg == "刪除":
            sheet = get_worksheet()
            all_records = sheet.get_all_values()
            
            if len(all_records) > 1: # 確保不刪除標題列
                last_row_index = len(all_records)
                deleted_row = all_records[-1] # 取得被刪除的那一行資料
                sheet.delete_rows(last_row_index)
                reply_text = f"🗑️ 已刪除最後一筆記錄：\n{deleted_row[0]} - {deleted_row[1]} JPY"
            else:
                reply_text = "目前沒有可以刪除的記錄喔！"

        # === 功能 B: 查詢目前總計 ===
        elif msg == "查詢" or msg == "結算":
            sheet = get_worksheet()
            # 讀取第二欄 (B欄) 所有金額，略過第一列標題
            col_values = sheet.col_values(2)[1:] 
            total_jpy = sum([float(x) for x in col_values if x.isdigit() or x.replace('.','',1).isdigit()])
            
            # 抓即時匯率換算總額
            currencies = twder.now('JPY')
            rate = float(currencies[2])
            total_ntd = total_jpy * rate
            
            reply_text = (
                f"📊 目前帳本統計：\n"
                f"🇯🇵 累積日幣：{total_jpy:,.0f} 円\n"
                f"🇹🇼 換算台幣：{total_ntd:,.0f} 元\n"
                f"(匯率 {rate})"
            )

        # === 功能 C: 記帳 (輸入數字) ===
        else:
            # 嘗試把輸入當作數字處理
            amount_jpy = float(msg)
            
            # 1. 抓匯率
            currencies = twder.now('JPY')
            rate = float(currencies[2])
            amount_ntd = amount_jpy * rate
            
            # 2. 寫入 Google Sheet
            sheet = get_worksheet()
            dt_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 新增一行 [時間, 日幣, 匯率, 台幣]
            sheet.append_row([dt_string, amount_jpy, rate, amount_ntd])
            
            # 3. 計算累計
            col_values = sheet.col_values(2)[1:]
            total_jpy = sum([float(x) for x in col_values])
            total_ntd = total_jpy * rate

            reply_text = (
                f"✅ 已記錄！\n"
                f"本次：{amount_jpy:,.0f} JPY (約 {amount_ntd:,.0f} TWD)\n"
                f"──────────\n"
                f"💰 目前累積日幣：{total_jpy:,.0f} 円\n"
                f"🇹🇼 累積換算台幣：{total_ntd:,.0f} 元"
            )

    except ValueError:
        reply_text = "請輸入「數字」記帳，或是輸入「刪除」、「查詢」。"
    except Exception as e:
        reply_text = f"發生錯誤：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(port=5000)