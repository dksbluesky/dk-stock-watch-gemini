import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    # 將回溯天數增加到 20 天，確保跨長假也能抓到資料
    start_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
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
            df_fut = df_fut[df_fut['institutional_id'] == 'Foreign']
        
        # 2. 大盤融資餘額
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale")
        
        # 3. 006208 數據
        df_m_006208 = get_finmind_data("TaiwanStockMarginPurchaseShortSale", "006208")
        df_sbl = get_finmind_data("TaiwanStockSbl", "006208")

        # 核心檢查：確保至少有兩筆資料可以計算增減
        if len(df_fut) < 2 or len(df_m_total) < 2:
            return "📊 目前為市場非交易時段，伺服器數據整理中。請於下一個交易日 17:30 再次查看最準確的報告。"

        # 取最後兩筆資料計算
        fut_now = df_fut.iloc[-1]['open_interest_net']
        fut_diff = fut_now - df_fut.iloc[-2]['open_interest_net']
        
        m_total_now = df_m_total.iloc[-1]['MarginPurchaseTodayBalance'] / 100000000
        m_total_diff = m_total_now - (df_m_total.iloc[-2]['MarginPurchaseTodayBalance'] / 100000000)
        
        m_006208_now = df_m_006208.iloc[-1]['MarginPurchaseTodayBalance']
        m_006208_diff = m_006208_now - df_m_006208.iloc[-2]['MarginPurchaseTodayBalance']
        
        sbl_now = df_sbl.iloc[-1]['ShortSaleTodayBalance'] if not df_sbl.empty else 0
        sbl_diff = (sbl_now - df_sbl.iloc[-2]['ShortSaleTodayBalance']) if len(df_sbl) > 1 else 0

        date_str = df_fut.iloc[-1]['date']
        
        report = f"📊 {date_str} 盤後籌碼結算報告\n"
        report += "--------------------------------\n"
        report += f"1. 外資大台期貨：{int(fut_now):,} 口 ({'空增' if fut_diff < 0 else '空減'} {int(abs(fut_diff)):,} 口)\n"
        report += f"2. 大盤融資餘額：{m_total_now:,.2f} 億 ({'增' if m_total_diff > 0 else '減'} {abs(m_total_diff):,.2f} 億)\n"
        report += f"3. 006208 融資：{int(m_006208_now):,} 張 ({'增' if m_006208_diff > 0 else '減'} {int(abs(m_006208_diff)):,} 張)\n"
        report += f"4. 006208 借券：{int(sbl_now):,} 張 ({'增' if sbl_diff > 0 else '減'} {int(abs(sbl_diff)):,} 張)\n\n"
        report += "🔍 籌碼面專業解析\n"
        report += f"• 外資目前淨部位約 {int(fut_now):,} 口，壓力位階較高。\n"
        report += f"• 融資餘額變動為 {m_total_diff:,.2f} 億，顯示散戶籌碼{'趨於保守' if m_total_diff < 0 else '轉向積極'}。"
        
        return report
    except Exception as e:
        return f"❌ 系統邏輯異常：{str(e)}"

def send_tg(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    send_tg(generate_report())
