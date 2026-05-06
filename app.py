import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="富果籌碼分析儀", layout="wide")

st.title("📊 富果主力籌碼追蹤")
st.markdown("連線至 **Fugle Market Data API v1.0** (正式版分點資料)")

# --- 金鑰讀取 ---
try:
    # 請確保 Streamlit Secrets 中的名稱為 FUGLE_API_KEY
    raw_key = st.secrets["FUGLE_API_KEY"]
    API_KEY = raw_key.strip().replace('"', '').replace("'", "")
except Exception:
    st.error("❌ 找不到 FUGLE_API_KEY，請在 Secrets 中設定。")
    st.stop()

# --- 核心邏輯：富果 v1.0 正確路徑分析 ---
def get_fugle_broker_data(symbol):
    # 正確路徑：marketdata -> v1.0 -> stock -> historical -> brokers -> reports -> {symbol}
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/brokers/reports/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        
        # 偵錯用：若依然失敗，顯示完整錯誤碼
        if response.status_code != 200:
            return None, f"連線失敗 (狀態碼: {response.status_code})。請確認您的 API 金鑰是否有「歷史分點」權限。"
            
        json_data = response.json()
        
        # 解析富果 data 欄位
        if "data" not in json_data:
            return None, "API 回傳格式不符，可能是權限受限或無此股票資料。"

        reports = json_data["data"]
        if not reports:
            return None, "查無該股票的近期分點資料。"

        processed_data = []
        for entry in reports:
            date = entry.get("date")
            brokers = entry.get("brokers", [])
            total_vol = entry.get("volume", 0) # 當日總成交量
            
            if not brokers: continue
            
            df_b = pd.DataFrame(brokers)
            # 計算淨買賣 (buy - sell)
            df_b['net'] = df_b['buy'] - df_b['sell']
            
            # 家數差 (買進分點數 - 賣出分點數)
            buy_agents = len(df_b[df_b['net'] > 0])
            sell_agents = len(df_b[df_b['net'] < 0])
            agent_diff = buy_agents - sell_agents
            
            # 集中度計算 (前 15 名買超總和 + 前 15 名賣超總和)
            top15_buy = df_b.nlargest(15, 'net')['net'].sum()
            top15_sell = df_b.nsmallest(15, 'net')['net'].sum()
            main_net_sum = top15_buy + top15_sell
            
            processed_data.append({
                '日期': date,
                '買賣超': int(df_b['net'].sum()),
                '家數差': agent_diff,
                '主力淨額': main_net_sum,
                '當日成交量': total_vol
            })
            
        final_df = pd.DataFrame(processed_data)
        final_df = final_df.sort_values('日期')
        
        # 計算 5日與 20日集中度 (主力淨額佔成交量比例)
        final_df['5日集中'] = (final_df['主力淨額'].rolling(5).sum() / final_df['當日成交量'].rolling(5).sum() * 100).round(2)
        final_df['20日集中'] = (final_df['主力淨額'].rolling(20).sum() / final_df['當日成交量'].rolling(20).sum() * 100).round(2)
        
        # 恢復日期降序顯示
        return final_df.sort_values('日期', ascending=False).head(12), None

    except Exception as e:
        return None, f"執行異常：{str(e)}"

# --- 使用者介面 ---
symbol = st.text_input("股票代碼 (直接輸入數字，如 2330)", value="2330")
if st.button("開始分析籌碼"):
    with st.spinner(f'正在為您連線富果分析 {symbol}...'):
        df, err = get_fugle_broker_data(symbol)
        
        if err:
            st.error(f"⚠️ {err}")
        elif df is not None:
            # 顏色邏輯函數
            def color_chip(val, col):
                if col == '買賣超':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col == '家數差':
                    color = '#ff4b4b' if val < 0 else '#00ba34' # 負數為紅(籌碼集中)
                else: # 集中度
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold'

            st.subheader(f"📊 {symbol} 籌碼集中度分析表")
            
            # 過濾空值並格式化
            table_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
            
            # 使用 st.table 展示，模仿附圖質感
            st.table(table_df.style.map(lambda x: color_chip(x, '買賣超'), subset=['買賣超'])
                                  .map(lambda x: color_chip(x, '家數差'), subset=['家數差'])
                                  .map(lambda x: color_chip(x, '集中'), subset=['5日集中', '20日集中']))
            
            st.success("分析完成！")
