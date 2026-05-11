import os
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    if not token:
        raise ValueError("FINMIND_TOKEN 環境變數未設定，請在 GitHub Secrets 中新增此金鑰。")
    tw_now = datetime.utcnow() + timedelta(hours=8)
    start_date = (tw_now - timedelta(days=40)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id:
        params["data_id"] = data_id
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != 200:
        raise ValueError(f"FinMind API 錯誤 [{dataset}]: status={data.get('status')}, msg={data.get('msg', '未知錯誤')}")
    df = pd.DataFrame(data.get("data", []))
    return df

def generate_report():
    try:
        # 1. 外資大台期貨：正確資料集為 TaiwanFuturesInstitutionalInvestors
        df_fut = get_finmind_data("TaiwanFuturesInstitutionalInvestors", "TX")
        if not df_fut.empty:
            # 過濾外資；欄位可能為 institutional_investors 或 name
            for col in ('institutional_investors', 'name'):
                if col in df_fut.columns:
                    # 外資值可能為 '外資及陸資(不含自營商)' 或含 '外資'
                    mask = df_fut[col].str.contains('外資', na=False)
                    if mask.any():
                        df_fut = df_fut[mask]
                    break
        if df_fut.empty:
            raise ValueError(f"外資大台期貨資料為空，請確認 TaiwanFuturesInstitutionalInvestors data_id=TX 是否有效")
        
        # 2. 大盤融資餘額
        df_m_total = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale")
        
        # 3. 006208 數據 (融資、融券、股價)
        df_m_006208 = get_finmind_data("TaiwanStockMarginPurchaseShortSale", "006208")
        df_price = get_finmind_data("TaiwanStockPrice", "006208")
        # 借券數據
        df_sbl = get_finmind_data("TaiwanStockSecuritiesLending", "006208")

        if len(df_fut) < 2 or len(df_m_total) < 2 or len(df_price) < 2:
            tw_now = datetime.utcnow() + timedelta(hours=8)
            raise ValueError(
                f"資料筆數不足 (外資期貨:{len(df_fut)}, 大盤融資:{len(df_m_total)}, 股價:{len(df_price)}) "
                f"[台灣時間 {tw_now.strftime('%Y-%m-%d %H:%M')}，星期{tw_now.weekday()+1}]"
            )

        # --- 原有數據計算 ---
        # TaiwanFuturesInstitutionalInvestors 無淨口數欄位，自行計算
        df_fut = df_fut.copy()
        df_fut['open_interest_net'] = (
            df_fut['long_open_interest_balance_volume'] - df_fut['short_open_interest_balance_volume']
        )
        fut_now = df_fut.iloc[-1]['open_interest_net']
        fut_diff = fut_now - df_fut.iloc[-2]['open_interest_net']
        
        def col_or_err(df, col, label):
            if col not in df.columns:
                raise ValueError(f"{label} 找不到欄位 '{col}'，可用欄位: {list(df.columns)}")
            return col

        # name 欄位區分融資/融券，過濾出融資列
        df_m_total_margin = df_m_total[df_m_total['name'] == 'MarginPurchase']
        if df_m_total_margin.empty:
            raise ValueError(f"TaiwanStockTotalMarginPurchaseShortSale 找不到 MarginPurchase，name值: {df_m_total['name'].unique().tolist()}")
        m_total_now = df_m_total_margin.iloc[-1]['TodayBalance'] / 100000000
        m_total_diff = (df_m_total_margin.iloc[-1]['TodayBalance'] - df_m_total_margin.iloc[-1]['YesBalance']) / 100000000

        col_or_err(df_m_006208, 'MarginPurchaseTodayBalance', 'TaiwanStockMarginPurchaseShortSale')
        m_006208_now = df_m_006208.iloc[-1]['MarginPurchaseTodayBalance']
        m_006208_diff = m_006208_now - df_m_006208.iloc[-2]['MarginPurchaseTodayBalance']
        
        # TaiwanStockSecuritiesLending 欄位名稱可能為 SBL_Balance 或其他
        _sbl_col = next((c for c in ('SBL_Balance', 'balance', 'ShortSaleTodayBalance') if not df_sbl.empty and c in df_sbl.columns), None)
        sbl_now = int(df_sbl.iloc[-1][_sbl_col]) if _sbl_col else 0
        sbl_diff = (sbl_now - int(df_sbl.iloc[-2][_sbl_col])) if (_sbl_col and len(df_sbl) > 1) else 0

        # --- 新增：券資比與量能判定邏輯 ---
        # 計算券資比
        short_bal_now = df_m_006208.iloc[-1]['ShortSaleTodayBalance']
        short_ratio = (short_bal_now / m_006208_now) * 100
        
        # 計算量能 20MA
        df_price['vol_20ma'] = df_price['Trading_Volume'].rolling(20).mean()
        curr_vol = df_price.iloc[-1]['Trading_Volume']
        ma20_vol = df_price.iloc[-1]['vol_20ma']
        vol_ratio = curr_vol / ma20_vol # 當前量是 20MA 的幾倍
        
        # 判定結論 (依照您的對照表)
        price_change = df_price.iloc[-1]['close'] - df_price.iloc[-2]['close']
        if price_change > 0 and vol_ratio >= 1.5:
            analysis_text = f"🚀 異常放量上漲 ({vol_ratio:.1f}倍量)，若券資比同步升高則具備軋空潛力。"
        elif price_change < 0 and vol_ratio >= 1.5:
            analysis_text = f"⚠️ 異常放量下跌 ({vol_ratio:.1f}倍量)，需注意籌碼鬆動風險。"
        else:
            analysis_text = "🛡️ 量能平穩，盤勢處於區間震盪。"

        # --- 格式化報告內容 ---
        date_str = df_fut.iloc[-1]['date']
        report = f"📊 {date_str} 盤後籌碼結算報告\n"
        report += "--------------------------------\n"
        report += f"1. 外資大台期貨：{int(fut_now):,} 口 ({'空增' if fut_diff < 0 else '空減'} {int(abs(fut_diff)):,} 口)\n"
        report += f"2. 大盤融資餘額：{m_total_now:,.2f} 億 ({'增' if m_total_diff > 0 else '減'} {abs(m_total_diff):,.2f} 億)\n"
        report += f"3. 006208 融資：{int(m_006208_now):,} 張 ({'增' if m_006208_diff > 0 else '減'} {int(abs(m_006208_diff)):,} 張)\n"
        report += f"4. 006208 借券：{int(sbl_now):,} 張 ({'增' if sbl_diff > 0 else '減'} {int(abs(sbl_diff)):,} 張)\n"
        report += "--------------------------------\n"
        report += f"🔹 006208 券資比：{short_ratio:.2f}%\n"
        report += f"🔹 20MA量能倍數：{vol_ratio:.2f} 倍 ({'⚠️異常' if vol_ratio >= 1.5 else '平穩'})\n\n"
        report += "🔍 籌碼面專業解析\n"
        report += f"• {analysis_text}\n"
        report += f"• 融資餘額變動為 {m_total_diff:,.2f} 億，散戶目前{'轉向積極' if m_total_diff > 0 else '趨於保守'}。"
        
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
