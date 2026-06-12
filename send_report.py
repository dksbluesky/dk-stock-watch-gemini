import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta


def get_finmind_data(dataset, data_id=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    token = os.getenv("FINMIND_TOKEN")
    if not token:
        raise ValueError("FINMIND_TOKEN 未設定")
    tw_now = datetime.utcnow() + timedelta(hours=8)
    start_date = (tw_now - timedelta(days=40)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date, "token": token}
    if data_id:
        params["data_id"] = data_id
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != 200:
        raise ValueError(f"FinMind [{dataset}] status={data.get('status')} msg={data.get('msg','')}")
    return pd.DataFrame(data.get("data", []))


def fetch_market(tw_now):
    """外資大台期貨 + 大盤融資餘額 (market-wide)."""
    # Futures
    df_fut = get_finmind_data("TaiwanFuturesInstitutionalInvestors", "TX")
    for col in ('institutional_investors', 'name'):
        if col in df_fut.columns:
            mask = df_fut[col].str.contains('外資', na=False)
            if mask.any():
                df_fut = df_fut[mask]
            break
    if len(df_fut) < 2:
        raise ValueError("外資大台期貨資料不足")
    df_fut = df_fut.copy()
    df_fut['net'] = df_fut['long_open_interest_balance_volume'] - df_fut['short_open_interest_balance_volume']
    fut_now  = int(df_fut.iloc[-1]['net'])
    fut_diff = int(df_fut.iloc[-1]['net'] - df_fut.iloc[-2]['net'])
    date_str = str(df_fut.iloc[-1]['date'])

    # Total margin
    df_mt = get_finmind_data("TaiwanStockTotalMarginPurchaseShortSale")
    df_mt_m = df_mt[df_mt['name'] == 'MarginPurchaseMoney']
    if df_mt_m.empty:
        raise ValueError("找不到 MarginPurchaseMoney")
    m_now  = round(df_mt_m.iloc[-1]['TodayBalance'] / 1e8, 2)
    m_diff = round((df_mt_m.iloc[-1]['TodayBalance'] - df_mt_m.iloc[-1]['YesBalance']) / 1e8, 2)

    return {
        "date": date_str,
        "futures_net": fut_now,
        "futures_diff": fut_diff,
        "margin_total_yi": m_now,
        "margin_total_diff_yi": m_diff,
        "margin_total_sentiment": "轉向積極" if m_diff > 0 else "趨於保守",
    }


def fetch_stock(code, name):
    """Per-stock: margin, short sale, price, chip ratio, volume."""
    try:
        df_m = get_finmind_data("TaiwanStockMarginPurchaseShortSale", code)
        df_p = get_finmind_data("TaiwanStockPrice", code)

        if len(df_m) < 2 or len(df_p) < 2:
            raise ValueError(f"資料筆數不足 (margin:{len(df_m)}, price:{len(df_p)})")

        # Margin
        margin_now  = int(df_m.iloc[-1]['MarginPurchaseTodayBalance'])
        margin_diff = int(margin_now - df_m.iloc[-2]['MarginPurchaseTodayBalance'])
        margin_date = str(df_m.iloc[-1]['date'])

        # Short sale
        sbl_now  = int(df_m.iloc[-1]['ShortSaleTodayBalance'])
        sbl_diff = int(sbl_now - df_m.iloc[-2]['ShortSaleTodayBalance'])

        # Chip ratio
        ratio_now  = (sbl_now / margin_now * 100) if margin_now else 0
        sbl_prev   = float(df_m.iloc[-2]['ShortSaleTodayBalance'])
        margin_prev = float(df_m.iloc[-2]['MarginPurchaseTodayBalance'])
        ratio_prev = (sbl_prev / margin_prev * 100) if margin_prev else 0
        ratio_diff = round(ratio_now - ratio_prev, 2)

        # Latest price (for display)
        price_close  = float(df_p.iloc[-1]['close'])
        price_change = round(price_close - float(df_p.iloc[-2]['close']), 2)

        # 籌碼情境判定 must compare 券資比 and 股價 movement on the SAME date.
        # 券資比 data (margin_date) often lags the latest price by 1 day,
        # so find price movement on margin_date itself rather than today's.
        df_p_sorted = df_p.sort_values('date').reset_index(drop=True)
        match_idx = df_p_sorted.index[df_p_sorted['date'] == margin_date]
        if len(match_idx) and match_idx[0] > 0:
            i = match_idx[0]
            situation_price_change = round(float(df_p_sorted.iloc[i]['close'] - df_p_sorted.iloc[i-1]['close']), 2)
        else:
            situation_price_change = price_change

        ratio_up = ratio_diff > 0
        price_up = situation_price_change > 0
        if ratio_up and price_up:
            situation = "🔥 軋空啟動：空方被迫買回，助長多頭氣勢。"
        elif not ratio_up and not price_up:
            situation = "⚠️ 殺多盤：多方認賠殺出，融資斷頭壓力大。"
        elif ratio_up and not price_up:
            situation = "🐻 空頭壓制：看空者眾且判斷正確，股價積弱不振。"
        else:
            situation = "🏳️ 軋空結束：空方已投降補回，後續推升力道減弱。"

        # Volume
        df_p = df_p.copy()
        df_p['vol_20ma'] = df_p['Trading_Volume'].rolling(20).mean()
        vol_ratio = float(df_p.iloc[-1]['Trading_Volume'] / df_p.iloc[-1]['vol_20ma'])
        vol_abnormal = vol_ratio >= 1.5
        if price_change > 0 and vol_abnormal:
            vol_analysis = f"🚀 異常放量上漲 ({vol_ratio:.1f}倍量)，若券資比同步升高則具備軋空潛力。"
        elif price_change < 0 and vol_abnormal:
            vol_analysis = f"⚠️ 異常放量下跌 ({vol_ratio:.1f}倍量)，需注意籌碼鬆動風險。"
        else:
            vol_analysis = "🛡️ 量能平穩，盤勢處於區間震盪。"

        return {
            "code": code,
            "name": name,
            "ok": True,
            "margin": margin_now,
            "margin_diff": margin_diff,
            "short_sale": sbl_now,
            "short_sale_diff": sbl_diff,
            "chip_ratio_pct": round(ratio_now, 2),
            "chip_ratio_diff_pct": ratio_diff,
            "chip_situation": situation,
            "chip_situation_date": margin_date,
            "vol_ratio": round(vol_ratio, 2),
            "vol_abnormal": vol_abnormal,
            "vol_analysis": vol_analysis,
            "price_close": price_close,
            "price_change": price_change,
        }
    except Exception as e:
        return {"code": code, "name": name, "ok": False, "error": str(e)}


def build_tg(market, stocks):
    lines = []
    lines.append(f"📊 {market['date']} 盤後籌碼結算報告")
    lines.append("")
    lines.append("🌐 大盤指標")
    fut = market['futures_net']
    fd  = market['futures_diff']
    lines.append(f"• 外資大台期貨：{fut:,} 口 ({'空增' if fd < 0 else '空減'} {abs(fd):,} 口)")
    m = market['margin_total_yi']
    md = market['margin_total_diff_yi']
    lines.append(f"• 大盤融資餘額：{m:,.2f} 億 ({'↑' if md > 0 else '↓'}{abs(md):.2f} 億) — 散戶{market['margin_total_sentiment']}")

    for s in stocks:
        lines.append("")
        lines.append(f"────────────")
        if not s.get('ok'):
            lines.append(f"📌 {s['code']} {s['name']}")
            lines.append(f"⚠️ 資料取得失敗：{s.get('error','未知錯誤')}")
            continue
        lines.append(f"📌 {s['code']} {s['name']}")
        lines.append(f"• 收盤：{s['price_close']:.2f} ({'▲' if s['price_change']>0 else '▼'}{abs(s['price_change']):.2f})")
        lines.append(f"• 融資：{s['margin']:,} 張 ({'↑' if s['margin_diff']>0 else '↓'}{abs(s['margin_diff']):,})｜借券：{s['short_sale']:,} 張 ({'↑' if s['short_sale_diff']>0 else '↓'}{abs(s['short_sale_diff']):,})")
        lines.append(f"• 券資比：{s['chip_ratio_pct']:.2f}% ({'↑' if s['chip_ratio_diff_pct']>0 else '↓'}{abs(s['chip_ratio_diff_pct']):.2f}%)")
        lines.append(f"• 情境（{s['chip_situation_date']}）：{s['chip_situation']}")
        lines.append(f"• 量能：{s['vol_ratio']:.2f} 倍 ({'⚠️異常' if s['vol_abnormal'] else '平穩'})")

    return "\n".join(lines)


def send_tg(text):
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token:  raise ValueError("TELEGRAM_TOKEN 未設定")
    if not chat_id: raise ValueError("TELEGRAM_CHAT_ID 未設定")
    # Split if > 4000 chars
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": chunk},
            timeout=30
        )
        print(f"[TG] status={resp.status_code}, body={resp.text[:200]}")
        resp.raise_for_status()


if __name__ == "__main__":
    import sys

    tw_now = datetime.utcnow() + timedelta(hours=8)

    # Load watchlist
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            watchlist = json.load(f)
    except FileNotFoundError:
        watchlist = [{"code": "006208", "name": "富邦台50"}]

    print(f"[INFO] 監控股票：{[s['code'] for s in watchlist]}")

    # Fetch data
    try:
        market = fetch_market(tw_now)
    except Exception as e:
        print(f"❌ 大盤資料錯誤：{e}")
        sys.exit(1)

    stocks = [fetch_stock(s["code"], s["name"]) for s in watchlist]

    for s in stocks:
        if s.get("ok"):
            print(f"[OK] {s['code']} {s['name']}")
        else:
            print(f"[FAIL] {s['code']} {s['name']}: {s.get('error')}")

    # Write JSON
    data = {
        "generated": tw_now.strftime('%Y-%m-%d %H:%M'),
        "market": market,
        "stocks": stocks,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/report.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[INFO] data/report.json 已寫入")

    # Send TG
    report = build_tg(market, stocks)
    print("=== REPORT ===")
    print(report)
    print("==============")
    try:
        send_tg(report)
        print("[TG] 訊息傳送成功")
    except Exception as e:
        print(f"[TG] 傳送失敗：{e}")
        sys.exit(1)
