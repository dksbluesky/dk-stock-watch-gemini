import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    # 抓取最近 15 天確保有資料，尤其是過完週末後
    start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id: params["data_id"] = data_id
    
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        df = pd.DataFrame(data.get("data", []))
        return df
    except:
        return pd.DataFrame()

def generate_report():
    try:
        # 1. 外資大台期貨
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalId", "TXF")
        if not df_fut.empty and 'institutional_id' in df_fut.columns:
            df_fut = df_fut[df_fut['institutional_id'] == 'Foreign'].tail(2)
        
        # 2. 大盤融資餘額
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale").tail(2)
        
        # 3. 006208 融資與借券
        df_m_006208 = get_finmind_data("TaiwanStockMarginPurchaseShortSale", "006208").tail(2)
        df_sbl = get_finmind_data("TaiwanStockSbl", "006208").tail(2)

        # 安全檢查：確保所有資料都抓到了
        if df_fut.empty or df_m_total.empty or df_m_006208.empty:
            return "⚠️ 目前部分數據更新中，請稍後再試。"

        # 數據處理與增減計算
        fut_now = df_fut.iloc[-1]['open_interest_net']
        fut_diff = fut_now - df_fut.iloc[-2]['open_interest_net']
        
        m_total_now = df_m_total.iloc[-1]['MarginPurchaseTodayBalance'] / 100000000
        m_total_diff = m_total_now - (df_m_total.iloc[-2]['MarginPurchaseTodayBalance'] / 100000000)
        
        m_006208_now = df_m_006208.iloc[-1]['MarginPurchaseTodayBalance']
        m_006208_diff = m_006208_now - df_m_006208.iloc[-2]['MarginPurchaseTodayBalance']
        
        sbl_now = df_sbl.iloc[-1]['ShortSaleTodayBalance'] if not df_sbl.empty else 0
        sbl_diff = (sbl_now - df_sbl.iloc[-2]['ShortSaleTodayBalance']) if len(df_sbl) > 1 else 0

        date_str = df_fut.iloc[-1]['date']
        
        # 格式化輸出內容
        report = f"📊 {date_str} 盤後籌碼結算報告\n"
        report += "--------------------------------\n"
        report += f"1. 外資大台期貨：{int(fut_now):,} 口 ({'空增' if fut_diff < 0 else '空減'} {int(abs(fut_diff)):,} 口)\n"
        report += f"2. 大盤融資餘額：{m_total_now:,.2f} 億 ({'增' if m_total_diff > 0 else '減'} {abs(m_total_diff):,.2f} 億)\n"
        report += f"3. 006208 融資：{int(m_006208_now):,} 張 ({'增' if m_006208_diff > 0 else '減'} {int(abs(m_006208_diff)):,} 張)\n"
        report += f"4. 006208 借券：{int(sbl_now):,} 張 ({'增' if sbl_diff > 0 else '減'} {int(abs(sbl_diff)):,} 張)\n\n"
        
        report += "🔍 籌碼面專業解析\n"
        report += f"• 外資空單水位 {'偏高' if fut_now < -40000 else '適中'}。\n"
        report += f"• 大盤融資目前傾向於 {'籌碼清洗' if m_total_diff < 0 else '信心持穩'}。\n"
        report += "• 下週開盤建議優先關注台積電月線支撐。"
        
        return report
    except Exception as e:
        return f"❌ 數據彙整異常，請聯繫開發者檢查邏輯。({str(e)})"

def send_tg(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    send_tg(generate_report())
