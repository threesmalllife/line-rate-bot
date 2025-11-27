import os
import twder
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==========================================
# 改用 os.environ.get 來讀取環境變數
# 這樣上傳 GitHub 時才不會洩漏密碼
# ==========================================
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    
    try:
        # 1. 嘗試將使用者輸入轉為數字
        jpy_amount = float(user_msg)
        
        # 2. 呼叫 twder 抓取「台灣銀行」即時資料
        # 回傳格式範例: ('2024/05/20 16:00', '0.20', '0.21', '0.205', '0.215')
        # Index 2 是「現金賣出」(銀行賣給你日幣的價格)，通常大家換匯是看這個
        currencies = twder.now('JPY') 
        current_rate = float(currencies[2]) # 抓取現金賣出匯率
        update_time = currencies[0]         # 抓取更新時間
        
        # 3. 計算換算結果
        ntd_amount = jpy_amount * current_rate
        
        # 4. 組合回覆訊息
        reply_text = (
            f"💰 換算結果：\n"
            f"🇯🇵 {jpy_amount:,.0f} JPY = 🇹🇼 {ntd_amount:,.0f} TWD\n"
            f"──────────\n"
            f"📊 目前匯率：{current_rate}\n"
            f"🕒 牌告時間：{update_time}\n"
            f"(資料來源：台灣銀行 現金賣出)"
        )
        
    except ValueError:
        # 如果不是數字，或是 twder 抓取失敗
        reply_text = "請輸入金額數字喔！(例如：2000)"
    except Exception as e:
        # 預防網路問題或其他錯誤
        reply_text = f"發生錯誤，請稍後再試。\n錯誤原因：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(port=5000)