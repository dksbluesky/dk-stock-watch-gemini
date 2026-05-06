import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 頁面配置 ---
st.set_page_config(page_title="富果籌碼分析儀", layout="wide")

# --- UI 標題 ---
st.title("📊 富果主力籌碼追蹤")
st.markdown("連線至 **Fugle Market Data API v1.0 (Historical)**")

# --- 金鑰讀取 ---
try:
    # 讀取 Secrets 中的 FUGLE_API_KEY，並清洗空白
    raw_key = st.secrets["FUGLE_API_KEY"]
    API_KEY = raw_key.strip().replace('"', '').replace("'", "")
except Exception:
    st.error("❌ 找不到 FUGLE_API_KEY，請在 Streamlit Secrets 中設定。")
    st.stop()

# --- 核心邏輯：富果 v1.0 資料抓取 ---
def get_fugle_broker_data(symbol):
    # 修正後的正確 v1.0 歷史分點路徑
    # 格式：/v1.0/stock/historical/brokers/reports/{symbol}
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/historical/brokers/reports/{symbol}"
    headers = {"X-API-KEY": API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        
        # 捕捉常見錯誤碼
        if response.status_code == 404:
            return None, f"找不到路徑 (404)。這通常是 API 路徑錯誤，或該股票無分點資料。"
        if response.status_code == 401:
            return None, "金鑰無效 (401)。請檢查 FUGLE_API_KEY 是否正確。"
        if response.status_code == 403:
            return None, "權限不足 (403)。您的 API Key 等級可能不包含歷史分點資料。"
        if response.status_code != 200:
            return None, f"連線錯誤 (狀態碼: {response.status_code})。內容：{response.text}"
            
        json_data = response.json()
        
        # 富果 v1.0 的資料通常放在 data 欄位下
        if "data" not in json_data:
            return None, f"API 回傳格式異常：{json_data.get('message', '未知錯誤')}"

        reports = json_data["data"]
        if not reports:
            return None, "查無分點資料。"

        processed_data = []
        for entry in reports:
            date = entry.get("date")
            brokers = entry.get("brokers", [])
            total_vol = entry.get("volume", 0) # 該股當日總成交量
            
            if not brokers: continue
            
            df_b = pd.DataFrame(brokers)
            # 計算淨買賣 (buy - sell)
            df_b['net'] = df_b['buy'] - df_b['sell']
            
            # 家數差計算
            buy_side = len(df_b[df_b['net'] > 0])
            sell_side = len(df_b[df_b['net'] < 0])
            agent_diff = buy_side - sell_side
            
            # 集中度計算 (前 15 名買超 - 前 15 名賣超)
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
        final_df = final_df.sort_values('日期') # 排序以計算 rolling
        
        # 計算 5日與 20日集中度
        # 公式：(主力淨額總和 / 成交量總和) * 100
        final_df['5日集中'] = (final_df['主力淨額'].rolling(5).sum() / final_df['當日成交量'].rolling(5).sum() * 100).round(2)
        final_df['20日集中'] = (final_df['主力淨額'].rolling(20).sum() / final_df['當日成交量'].rolling(20).sum() * 100).round(2)
        
        # 恢復倒序顯示最新日期
        return final_df.sort_values('日期', ascending=False).head(12), None

    except Exception as e:
        return None, f"執行發生異常：{str(e)}"

# --- 使用者操作區 ---
col1, col2 = st.columns([1, 4])
with col1:
    symbol = st.text_input("股票代碼", value="2330")
    btn = st.button("更新籌碼數據")

# --- 結果呈現 ---
if btn:
    with st.spinner(f'DK，正在為您連線富果分析 {symbol} 主力動向...'):
        df, err = get_fugle_broker_data(symbol)
        
        if err:
            st.error(f"⚠️ {err}")
        elif df is not None:
            # 配色邏輯：紅代表多頭訊號(家數差為負、集中度為正)
            def color_chip(val, col_name):
                if col_name == '買賣超':
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                elif col_name == '家數差':
                    color = '#ff4b4b' if val < 0 else '#00ba34' # 負數為紅(大戶接走)
                else:
                    color = '#ff4b4b' if val > 0 else '#00ba34'
                return f'color: {color}; font-weight: bold;'

            st.subheader(f"📊 {symbol} 主力分點數據分析")
            
            # 清理顯示表格 (排除計算中產生的 NaN)
            display_df = df[['日期', '買賣超', '家數差', '5日集中', '20日集中']].fillna(0)
            
            st.table(display_table := display_df.style.map(lambda x: color_chip(x, '買賣超'), subset=['買賣超'])
                                                .map(lambda x: color_chip(x, '家數差'), subset=['家數差'])
                                                .map(lambda x: color_chip(x, '集中'), subset=['5日集中', '20日集中']))
            
            st.success("數據抓取完成！提醒您：家數差為負時，通常代表籌碼正向大戶集中。")
