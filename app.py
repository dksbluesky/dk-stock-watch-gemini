import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="2330 籌碼分析工具", layout="wide")

st.title("📊 專業籌碼監控儀")
st.markdown("連線至 **FinMind** 數據中心")

# --- 金鑰處理 ---
# 優先讀取 Secrets，若無則顯示輸入框
try:
    # 清洗 Token，移除可能的空白、引號或換行
    raw_token = st.secrets.get("FINMIND_API_KEY", "")
    API_TOKEN = raw_token.strip().replace('"', '').replace("'", "")
except Exception:
    API_TOKEN = ""

if not API_TOKEN:
    st.info("💡 請在 Streamlit Secrets 中設定 FINMIND_API_KEY。")
    API_TOKEN = st.text_input("或在此輸入您的 FinMind Token", type="password")

# --- 核心數據抓取邏輯 ---
@st.cache_data(ttl=3600)
def fetch_and_calculate_data(stock_id, token):
    if not token:
        return None, "尚未輸入有效的 Token。"
    
    try:
        dl = DataLoader()
        # 嘗試登入
        dl.login_by_token(api_token=token)
        
        # 抓取 60 天以利滾動計算
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        
        # 1. 抓取成交量與分點報表 (確保名稱為複數 reports)
        price_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        broker_df = dl.taiwan_stock_broker_reports(stock_id=stock_id, start_date=start_date)
        
        if broker_df.empty or price_df.empty:
            return None, "查無資料，請確認代碼是否正確或當前非交易時段。"

        # 2. 進行每日統計
        dates = sorted(broker_df['date'].unique())
        summary_list = []
        
        for d in dates:
            day_b = broker_df[broker_df['date'] == d].copy()
            day_p = price_df[price_df['date'] == d]
            if day_p.empty: continue
            
            total_vol = day_p['trading_volume'].values[0] / 1000 # 換算為張
            day_b['net'] = (day_b['buy'] - day_b['sell']) / 1000 # 換算為張數淨額
            
            # 家數差
            buys = day_b[day_b['net'] > 0]
            sells = day_b[day_b['net'] < 0]
            agent_diff = len(buys) - len(sells)
            
            # 前 15 名大戶淨差
            top15_buy_sum = buys.nlargest(15, 'net')['net'].sum()
            top15_sell_sum = sells.nsmallest(15, 'net')['net'].sum()
            force_net = top15_buy_sum + top15_sell_sum
            
            summary_list.append({
                '日期': d,
                '買賣超': int(day_b['net'].sum()),
                '家數差': agent_diff,
                '主力淨額': force_net,
                '成交量': total_vol
            })
            
        final_df = pd.DataFrame(summary_list)
        
        # 3. 計算集中度指標 (百分比)
        final_df['5日集中'] = (final_df['主力淨額'].rolling(5).sum() / final_df['成交量'].rolling(5).sum() * 100).round(2)
        final_df['20日集中'] = (final_df['主力淨額'].rolling(20).sum() / final_df['成交量'].rolling(20).sum() * 100).round(2)
        
        # 回傳最新 12 筆並降序排列
        return final_df.sort_values('日期', ascending=False).head(12), None
        
    except Exception as e:
        return None, f"執行錯誤：{str(e)}"

# --- 介面操作 ---
target = st.text_input("請輸入股票代碼", value="2330")
if st.button("啟動籌碼分析"):
    with st.spinner('正在為您調度數據...'):
        df, error = fetch_and_calculate_data(target, API_TOKEN)
        
        if error:
            st.error(f"分析失敗：{error}")
        elif df is not None:
            # 配色邏輯 (負數家數差顯紅)
            def chip_style(val, col_name):
                if col_name == '買賣超':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col_name == '家數差':
                    color = '#ff4b4b' if val < 0 else '#00ba34'
                else: # 集中度
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold;'

            st.subheader(f"📈 {target} 籌碼集中度明細表")
            
            # 過濾顯示欄位
            display = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
            
            st.table(display.style.map(lambda x: chip_style(x, '買賣超'), subset=['買賣超'])
                                 .map(lambda x: chip_style(x, '家數差'), subset=['家數差'])
                                 .map(lambda x: chip_style(x, '集中'), subset=['5日集中', '20日集中']))
            
            st.success("數據更新完畢。")
