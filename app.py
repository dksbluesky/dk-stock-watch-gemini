import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="富果籌碼分析儀", layout="wide")

# --- UI 標題 ---
st.title("📊 富果主力籌碼追蹤")
st.markdown("連線至 **Fugle Market Data API v1.0**")

# --- 金鑰讀取 (確保 Secrets 名稱為 FUGLE_API_KEY) ---
try:
    raw_key = st.secrets["FUGLE_API_KEY"]
    API_KEY = raw_key.strip().replace('"', '').replace("'", "")
except Exception:
    st.error("❌ 找不到 FUGLE_API_KEY，請在 Streamlit Secrets 中設定。")
    st.stop()

# --- 核心邏輯：富果資料抓取與運算 ---
def get_fugle_data(symbol):
    # 修正後的正確 Endpoint 路徑
    # 根據官方文件，分點資料應透過參數 symbol 傳遞
    url = "https://api.fugle.tw/marketdata/v1.0/stock/brokers/reports"
    params = {"symbol": symbol}
    headers = {"X-API-KEY": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        # 如果發生 404，代表 Endpoint 有誤；403 代表權限不足
        if response.status_code != 200:
            return None, f"連線失敗 (狀態碼: {response.status_code})。訊息：{response.text}"
            
        json_data = response.json()
        
        if "data" not in json_data:
            return None, "API 回傳格式異常，請確認 API 權限是否包含分點資料。"

        # 解析富果資料結構
        reports = json_data["data"]
        processed_data = []
        
        for entry in reports:
            date = entry.get("date")
            brokers = entry.get("brokers", [])
            total_vol = entry.get("volume", 0) # 當日成交量
            
            if not brokers: continue
            
            df_b = pd.DataFrame(brokers)
            # 計算淨買賣 (buy - sell)
            df_b['net'] = df_b['buy'] - df_b['sell']
            
            # 家數差
            buy_side = len(df_b[df_b['net'] > 0])
            sell_side = len(df_b[df_b['net'] < 0])
            agent_diff = buy_side - sell_side
            
            # 主力集中度 (前 15 名買超 - 前 15 名賣超)
            top15_buy = df_b.nlargest(15, 'net')['net'].sum()
            top15_sell = df_b.nsmallest(15, 'net')['net'].sum()
            main_net = top15_buy + top15_sell
            
            processed_data.append({
                '日期': date,
                '買賣超': int(df_b['net'].sum()),
                '家數差': agent_diff,
                '主力淨額': main_net,
                '當日成交量': total_vol
            })
            
        if not processed_data:
            return None, "該股票近期無分點資料。"

        final_df = pd.DataFrame(processed_data)
        final_df = final_df.sort_values('日期')
        
        # 計算 5日與 20日集中度
        final_df['5日集中'] = (final_df['主力淨額'].rolling(5).sum() / final_df['當日成交量'].rolling(5).sum() * 100).round(2)
        final_df['20日集中'] = (final_df['主力淨額'].rolling(20).sum() / final_df['當當日成交量'].rolling(20).sum() * 100).round(2)
        
        return final_df.sort_values('日期', ascending=False).head(12), None

    except Exception as e:
        return None, f"執行錯誤：{str(e)}"

# --- 使用者輸入介面 ---
col1, col2 = st.columns([1, 3])
with col1:
    target_stock = st.text_input("輸入股票代碼", value="2330")
    run_btn = st.button("更新數據")

# --- 顯示結果 ---
if run_btn:
    with st.spinner('正在分析富果主力動向...'):
        df, err = get_fugle_data(target_stock)
        
        if err:
            st.error(f"⚠️ {err}")
            st.info("提示：富果分點資料 API 通常需要特定的訂閱權限，請確認您的 API Key 權限等級。")
        elif df is not None:
            # 視覺化美化
            def color_logic(val, col_name):
                if col_name == '買賣超':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col_name == '家數差':
                    color = '#ff4b4b' if val < 0 else '#00ba34' # 負數代表籌碼集中(紅)
                else: # 集中度
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold;'

            st.subheader(f"📊 {target_stock} 籌碼分析明細")
            
            # 過濾掉計算 rolling 時產生的空值
            table_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
            
            st.table(table_df.style.map(lambda x: color_logic(x, '買賣超'), subset=['買賣超'])
                                  .map(lambda x: color_logic(x, '家數差'), subset=['家數差'])
                                  .map(lambda x: color_logic(x, '集中'), subset=['5日集中', '20日集中']))
