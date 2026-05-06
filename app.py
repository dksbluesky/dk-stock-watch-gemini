import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="2330 籌碼分析", layout="wide")

st.title("📊 主力籌碼分析表")
st.markdown("連線至 **FinMind 數據庫** 進行深度分析")

# --- 金鑰讀取 ---
# 建議將您的 Token 放入 Streamlit Secrets 中的 FINMIND_API_KEY
try:
    token = st.secrets["FINMIND_API_KEY"].strip()
except Exception:
    # 若 Secrets 未設定，則提示輸入
    st.warning("請在 Streamlit Secrets 中設定 FINMIND_API_KEY 以利長期使用。")
    token = "請在此輸入您的Token" 

# --- 核心邏輯 ---
@st.cache_data(ttl=3600)
def get_finmind_data(stock_id, api_token):
    try:
        dl = DataLoader()
        dl.login_by_token(api_token=api_token)
        
        # 抓取 60 天資料以確保 20 日滾動計算準確
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        
        # 1. 取得成交量
        price_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        # 2. 取得分點報表
        broker_df = dl.taiwan_stock_broker_reports(stock_id=stock_id, start_date=start_date)
        
        if broker_df.empty or price_df.empty:
            return None, "查無資料，請確認代碼或 Token 有效性。"

        # 3. 每日計算
        dates = sorted(broker_df['date'].unique())
        daily_list = []
        
        for date in dates:
            day_data = broker_df[broker_df['date'] == date].copy()
            day_price = price_df[price_df['date'] == date]
            if day_price.empty: continue
            
            vol = day_price['trading_volume'].values[0] / 1000 # 換算為張
            day_data['net'] = (day_data['buy'] - day_data['sell']) / 1000
            
            # 買賣家數差
            buy_side = day_data[day_data['net'] > 0]
            sell_side = day_data[day_data['net'] < 0]
            agent_diff = len(buy_side) - len(sell_side)
            
            # 主力集中度 (前15買 - 前15賣) / 總量
            top15_buy = buy_side.nlargest(15, 'net')['net'].sum()
            top15_sell = sell_side.nsmallest(15, 'net')['net'].sum()
            main_net = top15_buy + top15_sell
            
            daily_list.append({
                '日期': date,
                '買賣超': int(day_data['net'].sum()),
                '家數差': agent_diff,
                '主力淨額': main_net,
                '成交量': vol
            })
            
        df = pd.DataFrame(daily_list)
        # 計算 5日與 20日集中度
        df['5日集中'] = (df['主力淨額'].rolling(5).sum() / df['成交量'].rolling(5).sum() * 100).round(2)
        df['20日集中'] = (df['主力淨額'].rolling(20).sum() / df['成交量'].rolling(20).sum() * 100).round(2)
        
        return df.sort_values('日期', ascending=False).head(12), None
    except Exception as e:
        return None, str(e)

# --- 介面呈現 ---
stock_id = st.text_input("輸入股票代碼", value="2330")
if st.button("更新數據"):
    with st.spinner('親愛的，正在為您整理籌碼動向...'):
        df, err = get_finmind_data(stock_id, token)
        
        if err:
            st.error(f"分析失敗：{err}")
        elif df is not None:
            # 樣式渲染
            def color_format(val, col):
                if col == '買賣超':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col == '家數差':
                    color = '#ff4b4b' if val < 0 else '#00ba34' # 負數為紅(集中)
                else: # 集中度
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold;'

            st.subheader(f"📊 {stock_id} 主力分點數據")
            display_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
            
            st.table(display_df.style.map(lambda x: color_format(x, '買賣超'), subset=['買賣超'])
                                     .map(lambda x: color_format(x, '家數差'), subset=['家數差'])
                                     .map(lambda x: color_format(x, '集中'), subset=['5日集中', '20日集中']))
            
            st.success("數據已對齊最新分點報表。")
