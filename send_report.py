import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    # 修正：手動計算台灣時間，確保 start_date 正確
    # GitHub 伺服器是 UTC，我們加 8 小時變台灣時間
    tw_now = datetime.utcnow() + timedelta(hours=8)
    start_date = (tw_now - timedelta(days=45)).strftime('%Y-%m-%d')
    
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id: params["data_id"] = data_id
    
    try:
        resp = requests.get(url, params=params).json()
        df = pd.DataFrame(resp.get("data", []))
        return df
    except:
        return pd.DataFrame()

def generate_report():
    try:
        # 1. 外資大台期貨 (修正 ID 為 TX)
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalId", "TX")
        if not df_fut.empty and 'institutional_id' in df_fut.columns:
            df_fut = df_fut[df_fut['institutional_id'] == 'Foreign']
        
        # 2. 大盤融資
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale")
        
        # 3. 006208 相關
        df_m_006208 = get_finmind_data("TaiwanStockMarginPurchaseShortSale", "006208")
        df_price = get_finmind_data("TaiwanStockPrice", "006208")
        df_sbl = get_finmind_data("TaiwanStockSbl", "006208")

        # 核心檢查：如果完全沒資料才顯示整理中
        if df_fut.empty or df_m_total.empty or df_price.empty:
            return "📊 資料庫連線正常，但今日最新數據尚未完全入庫，請約 18:30 後再次嘗試手動更新。"

        # 取最後兩筆計算 (確保能抓到最近的一個交易日)
        fut_now = df_fut.iloc[-1]['open_interest_net']
        fut_diff = fut_now - df_fut.iloc[-2]['open_interest_net']
        
        m_total_now = df_m_total.iloc[-1]['MarginPurchaseTodayBalance'] / 100000000
        m_total_diff = m_total_now - (df_m_total.iloc[-2]['MarginPurchaseTodayBalance'] / 100000000)
        
        # 券資比與量能
        short_ratio = (df_m_006208.iloc[-1]['ShortSaleTodayBalance'] / df_m_006208.iloc[-1]['MarginPurchaseTodayBalance'] * 100)
        df_price['vol_20ma'] = df_price['Trading_Volume'].rolling(20).mean()
        vol_ratio = df_price.iloc[-1]['Trading_Volume'] / df_price.iloc[-1]['vol_20ma']
        
        latest_date = df_fut.iloc[-1]['date']
        
        report = f"📊 {latest_date} 盤後籌碼結算報告\n"
        report += "--------------------------------\n"
        report += f"1. 外資大台期貨：{int(fut_now):,} 口 ({'空增' if fut_diff < 0 else '空減'} {int(abs(fut_diff)):,})\n"
        report += f"2. 大盤融資餘額：{m_total_now:,.2f} 億 ({'增' if m_total_diff > 0 else '減'} {abs(m_total_diff):,.2f})\n"
        report += f"3. 006208 融資：{int(df_m_006208.iloc[-1]['MarginPurchaseTodayBalance']):,} 張\n"
        report += f"4. 006208 借券：{int(df_sbl.iloc[-1]['ShortSaleTodayBalance']):,} 張\n"
        report += "--------------------------------\n"
        report += f"🔹 006208 券資比：{short_ratio:.2f}%\n"
        report += f"🔹 20MA量能倍數：{vol_ratio:.2f} 倍\n\n"
        report += "🔍 實戰邏輯判定：\n"
        
        price_change = df_price.iloc[-1]['close'] - df_price.iloc[-2]['close']
        if price_change > 0 and vol_ratio >= 1.5:
            report += "🚀 異常放量上漲，具備軋空潛力，觀察空方回補力道。"
        elif price_change < 0 and vol_ratio >= 1.5:
            report += "⚠️ 異常放量下跌，需注意籌碼鬆動與融資多頭踩踏。"
        else:
            report += "🛡️ 目前量能平穩，盤勢處於區間震盪，建議觀望。"

        return report
    except Exception as e:
        return f"❌ 系統邏輯異常：{str(e)}"

def send_tg(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    send_tg(generate_report())
