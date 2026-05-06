import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="富果籌碼分析儀", layout="wide")

# --- UI 標題 ---
st.title("📊 富果主力籌碼追蹤")
st.markdown("連線至 **Fugle Market Data API** 進行即時分析")

# --- 金鑰讀取 ---
try:
    # 請在 Streamlit Secrets 中設定 FUGLE_API_KEY
    API_KEY = st.secrets["FUGLE_API_KEY"].strip()
except Exception:
    st.error("❌ 找不到 FUGLE_API_KEY，請在 Secrets 中設定。")
    st.stop()

# --- 核心邏輯：富果資料抓取 ---
def get_fugle_chip_data(symbol):
    base_url = f"https://api.fugle.tw/marketdata/v1/broker/reports/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    
    try:
        # 1. 抓取分點資料
        response = requests.get(base_url, headers=headers)
        data = response.json()
        
        if "data" not in data:
            return None, f"API 錯誤：{data.get('message', '未知錯誤')}"
        
        # 2. 解析資料 (富果的分點資料通常包含日期、買賣分點細節)
        # 註：這裡假設您需要的是近期的日報表彙整
        raw_reports = data["data"]
        results = []
        
        for report in raw_reports:
            date = report["date"]
            brokers = report["brokers"] # 分點清單
            total_volume = report["volume"] # 該股當日總成交量
            
            df_brokers = pd.DataFrame(brokers)
            # 計算淨買賣 (買進 - 賣出)
            df_brokers['net'] = df_brokers['buy'] - df_brokers['sell']
            
            # 家數差計算
            buy_count = len(df_brokers[df_brokers['net'] > 0])
            sell_count = len(df_brokers[df_brokers['net'] < 0])
            agent_diff = buy_count - sell_count
            
            # 集中度計算 (前15名大戶)
            top15_buy = df_brokers.nlargest(15, 'net')['net'].sum()
            top15_sell = df_brokers.nsmallest(15, 'net')['net'].sum()
            
            # 公式：Concentration = (Top 15 Buy + Top 15 Sell) / Total Volume
            concentration = ((top15_buy + top15_sell) / total_volume) * 100
            
            results.append({
                '日期': date,
                '買賣超': int(df_brokers['net'].sum()),
                '家數差': agent_diff,
                '淨額': top15_buy + top15_sell,
                '成交量': total_volume,
                '集中度': round(concentration, 2)
            })
            
        df = pd.DataFrame(results)
        # 計算 5日與 20日集中度 (透過 rolling 處理)
        df = df.sort_values('日期')
        df['5日集中'] = (df['淨額'].rolling(5).sum() / df['成交量'].rolling(5).sum() * 100).round(2)
        df['20日集中'] = (df['淨額'].rolling(20).sum() / df['成交量'].rolling(20).sum() * 100).round(2)
        
        return df.sort_values('日期', ascending=False).head(12), None

    except Exception as e:
        return None, str(e)

# --- 使用者操作區 ---
with st.sidebar:
    st.header("參數設定")
    symbol = st.text_input("股票代碼", value="2330")
    if st.button("獲取最新籌碼"):
        st.session_state.run = True

# --- 顯示成果 ---
if 'run' in st.session_state:
    with st.spinner(f"正在串接富果 API 分析 {symbol}..."):
        df, err = get_fugle_chip_data(symbol)
        
        if err:
            st.error(f"連線失敗：{err}")
        elif df is not None:
            # 配色邏輯 (負家數差 = 紅色 = 籌碼集中)
            def chip_style(val, col):
                if col == '買賣超':
                    c = '#ff4b4b' if val > 0 else '#00ba34'
                elif col == '家數差':
                    c = '#ff4b4b' if val < 0 else '#00ba34'
                else:
                    c = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {c}; font-weight: bold;'

            # 顯示表格
            st.subheader(f"📊 {symbol} 主力分點日報")
            show_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']]
            
            st.table(show_df.style.map(lambda x: chip_style(x, '買賣超'), subset=['買賣超'])
                                 .map(lambda x: chip_style(x, '家數差'), subset=['家數差'])
                                 .map(lambda x: chip_style(x, '集中'), subset=['5日集中', '20日集中']))
