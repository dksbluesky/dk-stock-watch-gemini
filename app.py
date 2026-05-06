import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="台股籌碼分析儀", layout="wide")

# --- 讀取 API Key (建議設定在 Streamlit Cloud 的 Secrets 中) ---
# 若本地測試，請在專案目錄下建立 .streamlit/secrets.toml
try:
    API_KEY = st.secrets["FINMIND_API_KEY"]
except:
    API_KEY = "請輸入您的API_KEY" # 這裡放入您截圖中的 Key 作為預備

def get_data(stock_id):
    dl = DataLoader()
    dl.login(api_token=API_KEY)
    
    # 抓取 40 天資料以計算 20 日集中度
    start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
    
    # 取得成交量與分點資料
    price_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
    broker_df = dl.taiwan_stock_broker_reports(stock_id=stock_id, start_date=start_date)
    
    if broker_df.empty or price_df.empty:
        return None

    dates = sorted(broker_df['date'].unique(), reverse=True)
    results = []

    for date in dates:
        daily_data = broker_df[broker_df['date'] == date].copy()
        daily_price = price_df[price_df['date'] == date]
        if daily_price.empty: continue
        
        total_vol = daily_price['trading_volume'].values[0] / 1000 # 轉為張數
        daily_data['net'] = daily_data['buy'] - daily_data['sell']
        
        buy_b = daily_data[daily_data['net'] > 0]
        sell_b = daily_data[daily_data['net'] < 0]
        
        # 集中度計算 (前15名買超 - 前15名賣超)
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
    # 計算 N 日集中度
    df['5日集中'] = (df['淨差'].rolling(window=5).sum() / df['成交量'].rolling(window=5).sum() * 100).round(2)
    df['20日集中'] = (df['淨差'].rolling(window=20).sum() / df['成交量'].rolling(window=20).sum() * 100).round(2)
    
    return df.head(10)

# --- UI 介面 ---
st.title("📊 主力籌碼分析")
stock_id = st.text_input("輸入股票代碼", value="2330")

if st.button("開始分析"):
    with st.spinner('正在分析大戶動向...'):
        df = get_data(stock_id)
        
        if df is not None:
            # 顏色邏輯函數
            def color_format(val, col_type):
                if col_type == 'buy_sell':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col_type == 'house_diff':
                    # 家數差負數為紅 (籌碼集中)
                    color = '#ff4b4b' if val < 0 else '#00ba34'
                else: # 集中度
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold'

            # 格式化顯示
            display_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].copy()
            
            # 套用樣式
            styled_df = display_df.style.applymap(lambda x: color_format(x, 'buy_sell'), subset=['買賣超'])\
                                      .applymap(lambda x: color_format(x, 'house_diff'), subset=['家數差'])\
                                      .applymap(lambda x: color_format(x, 'focus'), subset=['5日集中', '20日集中'])

            st.table(styled_df)
        else:
            st.error("暫無資料，請確認 API Key 或日期是否正確。")