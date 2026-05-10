import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id: params["data_id"] = data_id
    
    resp = requests.get(url, params=params)
    print(f"DEBUG: FinMind {dataset} 回應狀態: {resp.status_code}")
    
    data = resp.json()
    if data.get("msg") != "success":
        print(f"DEBUG: FinMind 錯誤訊息: {data.get('msg')}")
        
    return pd.DataFrame(data.get("data", []))

def generate_report():
    try:
        # 抓取資料
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalId", "TXF")
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale")
        
        if df_fut.empty or df_m_total.empty:
            return "❌ 錯誤：FinMind 資料抓取為空，請檢查 Token 是否有效。"

        # 這裡簡化邏輯，先確保能發送成功
        date_str = df_fut.iloc[-1]['date']
        report = f"測試連線成功！\n日期：{date_str}\n您的機器人已準備好為您服務。"
        return report
    except Exception as e:
        return f"❌ 程式執行異常：{str(e)}"

def send_tg(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    print(f"DEBUG: 準備發送到 Chat ID: {chat_id}")
    resp = requests.post(url, data={"chat_id": chat_id, "text": text})
    
    print(f"DEBUG: Telegram 回應狀態: {resp.status_code}")
    print(f"DEBUG: Telegram 回應內容: {resp.text}")

if __name__ == "__main__":
    content = generate_report()
    send_tg(content)
