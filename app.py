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

# === 新增：喚醒專用路徑 ===
@app.route("/", methods=['GET'])
def home():
    return "Hello! I am awake!", 200


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # ==========================================
    # 設定時區：日本時間 (UTC+9)
    # ==========================================
    tz = datetime.timezone(datetime.timedelta(hours=9)) 
    now_jp = datetime.datetime.now(tz) # 取得現在的日本時間
    # ==========================================

    try:
        # === 功能 A: 刪除上一筆 ===
        if msg == "刪除":
            sheet = get_worksheet()
            all_records = sheet.get_all_values()
            
            if len(all_records) > 1:
                last_row_index = len(all_records)
                deleted_row = all_records[-1]
                sheet.delete_rows(last_row_index)
                reply_text = f"🗑️ 已刪除最後一筆記錄：\n{deleted_row[0]} - {deleted_row[1]} JPY"
            else:
                reply_text = "目前沒有可以刪除的記錄喔！"

        # === 功能 B: 查詢總帳本 ===
        elif msg == "查詢" or msg == "總計":
            sheet = get_worksheet()
            col_values = sheet.col_values(2)[1:] 
            total_jpy = sum([float(x) for x in col_values if x.replace('.','',1).isdigit()])
            
            currencies = twder.now('JPY')
            rate = float(currencies[2])
            total_ntd = total_jpy * rate
            
            reply_text = (
                f"📊 目前帳本總計：\n"
                f"🇯🇵 累積日幣：{total_jpy:,.0f} 円\n"
                f"🇹🇼 換算台幣：{total_ntd:,.0f} 元\n"
                f"(匯率 {rate})"
            )

        # === 功能 C: 查詢特定日期 (使用日本時間判斷) ===
        elif msg in ["今天", "昨天"] or (len(msg) == 10 and msg.count('-') == 2):
            
            target_date = ""
            if msg == "今天":
                # 使用 now_jp
                target_date = now_jp.strftime("%Y-%m-%d")
            elif msg == "昨天":
                # 使用 now_jp 減一天
                target_date = (now_jp - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                try:
                    datetime.datetime.strptime(msg, "%Y-%m-%d")
                    target_date = msg
                except ValueError:
                    reply_text = "日期格式錯誤，請輸入 YYYY-MM-DD"
                    target_date = None

            if target_date:
                sheet = get_worksheet()
                all_records = sheet.get_all_values()
                
                day_total_jpy = 0
                day_total_ntd = 0
                count = 0

                for row in all_records[1:]:
                    if row[0].startswith(target_date):
                        day_total_jpy += float(row[1])
                        day_total_ntd += float(row[3])
                        count += 1
                
                if count > 0:
                    reply_text = (
                        f"📅 {target_date} 消費統計：\n"
                        f"──────────\n"
                        f"🔢 筆數：{count} 筆\n"
                        f"🇯🇵 日幣：{day_total_jpy:,.0f} 円\n"
                        f"🇹🇼 台幣：{day_total_ntd:,.0f} 元"
                    )
                else:
                    reply_text = f"📅 {target_date}\n\n這一天沒有任何記帳紀錄喔！"

        # === 功能 D: 記帳 (使用日本時間紀錄) ===
        else:
            amount_jpy = float(msg)
            
            currencies = twder.now('JPY')
            rate = float(currencies[2])
            amount_ntd = amount_jpy * rate
            
            sheet = get_worksheet()
            
            # 使用日本時間字串寫入 Google Sheet
            dt_string = now_jp.strftime("%Y-%m-%d %H:%M:%S")
            
            sheet.append_row([dt_string, amount_jpy, rate, amount_ntd])
            
            reply_text = (
                f"✅ 已記錄這筆消費：\n"
                f"🇯🇵 {amount_jpy:,.0f} JPY\n"
                f"🇹🇼 約 {amount_ntd:,.0f} TWD\n"
                f"(匯率 {rate})"
            )

    except ValueError:
        reply_text = "看不懂這個指令喔 🥺"
    except Exception as e:
        reply_text = f"發生錯誤：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )
if __name__ == "__main__":
    app.run(port=5000)