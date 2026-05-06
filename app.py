import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="2330 籌碼分析工具", layout="wide")

st.title("📊 籌碼動向分析儀")

# --- 金鑰處理 ---
# 優先讀取 Secrets，若無則顯示輸入框
try:
    token = st.secrets["FINMIND_API_KEY"].strip().replace('"', '').replace("'", "")
except Exception:
    token = st.text_input("請輸入 FinMind Token", type="password")

# --- 資料抓取與運算邏輯 ---
@st.cache_data(ttl=3600)
def get_data(stock_id, api_token):
    try:
        dl = DataLoader()
        # 嘗試登入
        dl.login_by_token(api_token=api_token)
        
        # 設定日期範圍 (需包含足夠計算 20 日滾動數據的長度)
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        
        # 1. 取得每日股價 (計算成交量張數)
        price_df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date)
        
        # 2. 修正後的方法名稱：taiwan_stock_broker_report (單數)
        broker_df = dl.taiwan_stock_broker_report(stock_id=stock_id, start_date=start_date)
        
        if broker_df.empty or price_df.empty:
            return None, "查無資料，請確認代碼是否正確或 Token 權限。"

        # 3. 處理每日數據彙整
        dates = sorted(broker_df['date'].unique())
        daily_records = []
        
        for d in dates:
            day_broker = broker_df[broker_df['date'] == d].copy()
            day_price = price_df[price_df['date'] == d]
            if day_price.empty: continue
            
            # 成交量轉為「張」
            total_vol = day_price['trading_volume'].values[0] / 1000
            
            # 計算淨買賣
            day_broker['net'] = (day_broker['buy'] - day_broker['sell']) / 1000
            buy_side = day_broker[day_broker['net'] > 0]
            sell_side = day_broker[day_broker['net'] < 0]
            
            # 家數差 (買進分點數 - 賣出分點數)
            agent_diff = len(buy_side) - len(sell_side)
            
            # 主力集中度 (買超前 15 名 + 賣超前 15 名)
            top15_buy = buy_side.nlargest(15, 'net')['net'].sum()
            top15_sell = sell_side.nsmallest(15, 'net')['net'].sum()
            main_net = top15_buy + top15_sell
            
            daily_records.append({
                '日期': d,
                '買賣超': int(day_broker['net'].sum()),
                '家數差': agent_diff,
                '主力淨額': main_net,
                '成交量': total_vol
            })
            
        df = pd.DataFrame(daily_records)
        
        # 滾動計算 5 日與 20 日集中度
        df['5日集中'] = (df['主力淨額'].rolling(5).sum() / df['成交量'].rolling(5).sum() * 100).round(2)
        df['20日集中'] = (df['主力淨額'].rolling(20).sum() / df['成交量'].rolling(20).sum() * 100).round(2)
        
        # 降序顯示最新日期
        return df.sort_values('日期', ascending=False).head(12), None
        
    except Exception as e:
        return None, str(e)

# --- 介面操作 ---
target = st.text_input("股票代碼", value="2330")
if st.button("執行分析"):
    if not token:
        st.error("請先設定或輸入有效 Token")
    else:
        with st.spinner('正在分析數據，請稍候...'):
            res, err = get_data(target, token)
            
            if err:
                st.error(f"分析失敗：{err}")
                if "Token" in err:
                    st.info("💡 建議檢查 Token 是否包含不可見字元，或嘗試重新在 FinMind 官網生成。")
            elif res is not None:
                # 定義紅綠配色
                def style_format(val, col_name):
                    if col_name == '買賣超':
                        color = '#ff4b4b' if val > 0 else '#00ba34'
                    elif col_name == '家數差':
                        color = '#ff4b4b' if val < 0 else '#00ba34' # 負數代表籌碼集中(紅)
                    else:
                        color = '#ff4b4b' if val > 0 else '#00ba34'
                    return f'color: {color}; font-weight: bold;'

                st.subheader(f"📊 {target} 籌碼集中度明細")
                display_table = res[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
                
                st.table(display_table.style.map(lambda x: style_format(x, '買賣超'), subset=['買賣超'])
                                            .map(lambda x: style_format(x, '家數差'), subset=['家數差'])
                                            .map(lambda x: style_format(x, '集中'), subset=['5日集中', '20日集中']))
