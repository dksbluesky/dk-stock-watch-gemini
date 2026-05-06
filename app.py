import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import sys

st.set_page_config(page_title="2330 籌碼分析", layout="wide")

# 顯示環境資訊 (除錯用)
# st.write(f"Python Version: {sys.version}")

# 安全讀取 Secrets
try:
    API_KEY = st.secrets["FINMIND_API_KEY"]
except Exception:
    st.error("❌ 找不到 Secrets 中的 FINMIND_API_KEY，請檢查 Streamlit 設定。")
    st.stop()

def get_data(stock_id):
    try:
        dl = DataLoader()
        # 修正：使用官方建議的 login_by_token 方法
        dl.login_by_token(api_token=API_KEY) 
        
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        
        price_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        broker_df = dl.taiwan_stock_broker_reports(stock_id=stock_id, start_date=start_date)
        
        if broker_df.empty:
            return None, "找不到分點資料"

        dates = sorted(broker_df['date'].unique(), reverse=True)
        results = []
        for date in dates:
            daily_data = broker_df[broker_df['date'] == date].copy()
            daily_price = price_df[price_df['date'] == date]
            if daily_price.empty: continue
            
            total_vol = daily_price['trading_volume'].values[0] / 1000
            daily_data['net'] = daily_data['buy'] - daily_data['sell']
            buy_b = daily_data[daily_data['net'] > 0]
            sell_b = daily_data[daily_data['net'] < 0]
            
            top15_buy = buy_b.nlargest(15, 'net')['net'].sum()
            top15_sell = sell_b.nsmallest(15, 'net')['net'].sum()
            
            results.append({
                '日期': date,
                '買賣超': int(daily_data['net'].sum() / 1000),
                '家數差': len(buy_b) - len(sell_b),
                '淨差': (top15_buy + top15_sell) / 1000,
                '成交量': total_vol
            })

        df = pd.DataFrame(results)
        df['5日集中'] = (df['淨差'].rolling(window=5).sum() / df['成交量'].rolling(window=5).sum() * 100).round(2)
        df['20日集中'] = (df['淨差'].rolling(window=20).sum() / df['成交量'].rolling(window=20).sum() * 100).round(2)
        return df.head(10), None
    except Exception as e:
        return None, str(e)

st.title("📊 主力籌碼分析表")
stock_id = st.text_input("輸入代碼", value="2330")

if st.button("開始分析"):
    df, err = get_data(stock_id)
    if err:
        st.error(f"發生錯誤: {err}")
    elif df is not None:
        # 樣式定義
        def highlight_cols(val, col):
            if col == '買賣超':
                color = '#ff4b4b' if val > 0 else '#00ba34'
            elif col == '家數差':
                color = '#ff4b4b' if val < 0 else '#00ba34' # 負數為紅(集中)
            else:
                color = '#ff4b4b' if val > 0 else '#00ba34'
            return f'color: {color}; font-weight: bold'

        styled = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].style.map(
            lambda x: highlight_cols(x, '買賣超'), subset=['買賣超']
        ).map(
            lambda x: highlight_cols(x, '家數差'), subset=['家數差']
        ).map(
            lambda x: highlight_cols(x, '集中'), subset=['5日集中', '20日集中']
        )
        st.table(styled)
