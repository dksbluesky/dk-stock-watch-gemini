import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    # 抓取最近 10 天資料以確保有足夠樣本計算增減
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id: params["data_id"] = data_id
    
    resp = requests.get(url, params=params).json()
    return pd.DataFrame(resp.get("data", []))

def generate_report():
    try:
        # 1. 外資大台期貨 (TXF)
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalId", "TXF")
        df_fut = df_fut[df_fut['institutional_id'] == 'Foreign'].tail(2)
        fut_now = df_fut.iloc[-1]['open_interest_net']
        fut_diff = fut_now - df_fut.iloc[-2]['open_interest_net']
        
        # 2. 大盤融資餘額
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale").tail(2)
        m_total_now = df_m_total.iloc[-1]['MarginPurchaseTodayBalance'] / 100000000 # 億
        m_total_diff = m_total_now - (df_m_total.iloc[-2]['MarginPurchaseTodayBalance'] / 100000000)

        # 3. 006208 融資與借券 (張數)
        df_m_006208 = get_finmind_data("TaiwanStockMarginPurchaseShortSale", "006208").tail(2)
        m_006208_now = df_m_006208.iloc[-1]['MarginPurchaseTodayBalance']
        m_006208_diff = m_006208_now - df_m_006208.iloc[-2]['MarginPurchaseTodayBalance']
        
        df_sbl = get_finmind_data("TaiwanStockSbl", "006208").tail(2)
        sbl_now = df_sbl.iloc[-1]['ShortSaleTodayBalance']
        sbl_diff = sbl_now - df_sbl.iloc[-2]['ShortSaleTodayBalance']

        date_str = df_fut.iloc[-1]['date']
        
        # 依照您的要求結合「數據表」與「專業解析」
        report = f"📊 {date_str} 盤後籌碼結算報告\n"
        report += "--------------------------------\n"
        report += f"1. 外資大台指期貨淨部位：{int(fut_now):,} 口 ({'空單增加' if fut_diff < 0 else '空單減少'} {int(abs(fut_diff)):,} 口)\n"
        report += f"2. 大盤融資餘額：{m_total_now:,.2f} 億元 ({'增加' if m_total_diff > 0 else '減少'} {abs(m_total_diff):,.2f} 億元)\n"
        report += f"3. 006208 融資餘額：{int(m_006208_now):,} 張 ({'增加' if m_006208_diff > 0 else '減少'} {int(abs(m_006208_diff)):,} 張)\n"
        report += f"4. 006208 借券賣出餘額：{int(sbl_now):,} 張 ({'增加' if sbl_diff > 0 else '減少'} {int(abs(sbl_diff)):,} 張)\n\n"
        
        report += "🔍 籌碼面專業解析\n"
        report += f"• 外資空單水位 {'偏高' if fut_now < -40000 else '尚在安全範圍'}，宜密切關注避險動向。\n"
        report += f"• 大盤融資 {'減少' if m_total_diff < 0 else '增加'}，籌碼結構 {'有利於洗盤後再攻' if m_total_diff < 0 else '略顯凌亂'}。\n"
        report += f"• 006208 借券 {'減少' if sbl_diff < 0 else '增加'}，反映法人對於台股權值股的短線看 {'空力道趨緩' if sbl_diff < 0 else '壓抑情緒升溫'}。"
        
        return report
    except Exception as e:
        return f"❌ 數據擷取異常：{str(e)}"

def send_tg(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    send_tg(generate_report())