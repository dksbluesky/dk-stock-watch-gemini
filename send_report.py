import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    # 設定回溯日期長一點，確保假日也能抓到週五資料
    start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id: params["data_id"] = data_id
    
    resp = requests.get(url, params=params)
    data = resp.json()
    return pd.DataFrame(data.get("data", []))

def generate_report():
    try:
        # 抓取資料並取最後一筆 (確保是最新交易日)
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalId", "TXF")
        df_fut = df_fut[df_fut['institutional_id'] == 'Foreign']
        
        if df_fut.empty:
            return "⚠️ 目前 FinMind 資料庫維護中或 Token 異常，請稍後再試。"

        date_str = df_fut.iloc[-1]['date']
        report = f"✅ 連線測試成功！\n\n最新交易日：{date_str}\n籌碼報告已準備就緒。\n(目前為假日模式，數據將於明日 17:30 更新)"
        return report
    except Exception as e:
        return f"❌ 系統邏輯異常：{str(e)}"

def send_tg(text):
    # 這裡的環境變數必須與 GitHub Secrets 名稱完全一致
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # 增加安全性檢查
    if not bot_token or not chat_id:
        print("DEBUG: 找不到環境變數，請檢查 Secrets 設定名稱。")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text})
    print(f"DEBUG: Telegram 回應狀態: {resp.status_code}")
    print(f"DEBUG: Telegram 回應內容: {resp.text}")

if __name__ == "__main__":
    send_tg(generate_report())
