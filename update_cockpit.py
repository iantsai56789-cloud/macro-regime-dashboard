import os
import datetime
import io
import pandas as pd
import requests

# ==========================================
# 核心配置：請在此處輸入你的個人資金參數
# ==========================================
MONTHLY_BUDGET = 50000  # 每月常態投資額度 (TWD)
BONUS_INPUT = 200000  # 當期獎金/非線性利潤 (TWD)
TOTAL_ASSETS = 12000000  # 你的系統總資產估值 (TWD)
TOTAL_DEBT = 3100000  # 你的系統總負債金額 (TWD)


def fetch_fred_data(series_id):
    """免 API Key 直接抓取美聯儲 FRED 最新數據"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            df = df[df[series_id] != "."]  # 清除無效數據
            df[series_id] = pd.to_numeric(df[series_id])
            return df.iloc[-1][series_id], df.iloc[-1]["DATE"]
    except Exception as e:
        print(f"無法獲取 FRED 指標 {series_id}: {e}")
    return None, None


def fetch_yahoo_daily(ticker):
    """免 API Key 抓取 Yahoo Finance 歷史數據並計算最新值與均線"""
    end_dt = int(datetime.datetime.now().timestamp())
    start_dt = end_dt - (360 * 24 * 60 * 60)  # 抓取大約一年的數據計算均線
    url = f"https://query1.finance.yahoo.com/v7/finance/download/{ticker}?period1={start_dt}&period2={end_dt}&interval=1d&events=history&includeAdjustedClose=true"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
            df = df.dropna(subset=["Close"])
            return df
    except Exception as e:
        print(f"無法獲取 Yahoo 標的 {ticker}: {e}")
    return None


def run_regime_pipeline():
    print(
        f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 啟動全球權威數據同步..."
    )

    # 1. 抓取 A. 流動性模組
    fci_val, fci_date = fetch_fred_data("NFCI")  # 全美金融條件指數 (負數代表寬鬆)
    fed_val, _ = fetch_fred_data("WALCL")  # 聯準會資產負債表規模

    # 2. 抓取 B. 總體成長模組
    sahm_val, sahm_date = fetch_fred_data("SAHMREALTIME")  # 薩姆規則失業率轉折指標

    # 3. 抓取 C. 信用與通膨模組
    bbb_spread, _ = fetch_fred_data(
        "BAMLC0A4CBBB"
    )  # 美國 BBB 投資級公司債利差
    pce_val, _ = fetch_fred_data("PCEPILFE")  # 核心 PCE 年增率

    # 4. 抓取 D. 情緒與即時價格模組 (用台股加權指數 ^TWII 或 S&P500 ^GSPC 作為權益代表)
    vix_df = fetch_yahoo_daily("^VIX")
    vix_ma20 = vix_df["Close"].tail(20).mean() if vix_df is not None else 15.0
    current_vix = vix_df["Close"].iloc[-1] if vix_df is not None else 15.0

    twii_df = fetch_yahoo_daily("^TWII")
    if twii_df is not None:
        current_twii = twii_df["Close"].iloc[-1]
        ma200_twii = twii_df["Close"].tail(200).mean()
        twii_deviation = (
            (current_twii - ma200_twii) / ma200_twii
        ) * 100  # 200MA 乖離率
    else:
        twii_deviation = 0.0

    # ==========================================
    # 演算法邏輯：將真實數據動態映射為歸一化 Z-Score (-2.5 到 +2.5)
    # ==========================================
    # A. 流動性
    s_fci = 1.5 if fci_val > 0 else -1.0
    s_fed = 0.5 if fed_val < 7000000 else -0.5
    m_liquidity = (s_fci * 0.6) + (s_fed * 0.4)

    # B. 成長 (薩姆規則高於 0.5% 代表失業率暴衝衰退)
    s_sahm = 2.5 if sahm_val >= 0.5 else -0.5
    s_growth_proxy = 1.5 if twii_deviation > 5 else -1.0  # 用市場動能代指實體科技景氣
    m_growth = (s_sahm * 0.6) + (s_growth_proxy * 0.4)

    # C. 信用與通膨
    s_spread = 2.0 if bbb_spread > 2.0 else -0.8
    s_pce = 1.0 if pce_val > 3.5 else 0.0
    m_credit_inflation = (s_spread * 0.5) + (s_pce * 0.5)

    # D. 情緒與估值 (目前處於高估值時代，給予預設權重)
    s_cape = 2.2  # 由於 CAPE 數據庫多為月更，此處定錨在 2026 高估值區
    s_vix_dev = 1.5 if (current_vix < 14 and twii_deviation > 8) else 0.0
    m_sentiment_valuation = (s_cape * 0.5) + (s_vix_dev * 0.5)

    # 最終權威總分公式
    i_regime = (
        (m_liquidity * 0.35)
        + (m_growth * 0.25)
        + (m_credit_inflation * 0.20)
        + (m_sentiment_valuation * 0.20)
    )

    # 計算資金分配
    act_fixed = MONTHLY_BUDGET * 0.8
    act_floating = MONTHLY_BUDGET * 0.2

    status_title = "常態歷史均值體制"
    status_class = (
        "bg-slate-800 text-slate-300 border-slate-700"  # 預設中性樣式
    )
    report_text = "數據解析中..."

    # 交叉裁決判定
    if fci_val > 0.1 or sahm_val >= 0.5 or m_liquidity >= 0.8:
        status_title = "危險：流動性斷裂 / 衰退體制"
        status_class = "bg-rose-950/40 text-rose-400 border-rose-800"
        act_floating = 0
        report_text = f"<strong>【最高級別防禦熔斷】</strong>系統偵測到金融條件指數升至 {fci_val}，或薩姆規則已達觸發臨界點（{sahm_val}%）。此時無論大盤估值高低，實體經濟與流動性已拉響警報！月度 20% 浮動加碼金<strong>強制歸零拦截</strong>，全面保留現金，綜合 LTV 必須嚴格壓低，準備應對左尾清算。"
    elif twii_deviation > 8.0 and fci_val < -0.4:
        status_title = "結構：高估值結構牛市 (1995/2026模式)"
        status_class = "bg-emerald-950/30 text-emerald-400 border-emerald-800"
        act_floating = MONTHLY_BUDGET * 0.1  # 截留一半
        report_text = f"<strong>【結構牛市持股觀測】</strong>當前台股 200MA 正乖離達 {twii_deviation:.1f}%，市場情緒高亢。但與此同時，全美金融條件指數為極度寬鬆的 {fci_val}，實體流動性未見斷裂。系統判定此為典型<strong>『高估值擴張牛市』</strong>（高估值不等於立即崩盤）。底倉雷打不動，浮動資金釋放 50% 順勢配置，其餘 50% 轉為現金儲備。"
    elif i_regime < -0.3:
        status_title = "機會：價值回檔配置體制"
        status_class = "bg-amber-950/40 text-amber-400 border-amber-800"
        report_text = f"<strong>【資產特價防線】</strong>綜合體制得分為負值 ({i_regime:.2f})。基本面信用利差無異常，但大盤出現技術性修正。20% 浮動加碼金解凍，<strong>全額市價進場</strong>吸納打折的核心股權籌碼。"
    else:
        report_text = f"<strong>【常態紀律執行】</strong>全球總經指標落在常態分位。全美金融條件 ({fci_val}) 與台股均線乖離 ({twii_deviation:.1f}%) 運作正常。剝離主觀情緒，80% 核心底倉持續扣款。"

    ltv_val = (TOTAL_DEBT / TOTAL_ASSETS) * 100
    ltv_class = "text-emerald-400" if ltv_val <= 30 else "text-amber-400"
    if ltv_val > 40:
        ltv_class = "text-rose-500 animate-pulse"

    # ==========================================
    # 第參部分：動態生成全量網頁原始碼
    # ==========================================
    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>永續資本控管中樞 (每日自動更新版)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #090d16; color: #f1f5f9; font-family: 'PingFang TC', sans-serif; }}
    </style>
</head>
<body class="p-4 lg:p-6">
    <div class="max-w-7xl mx-auto border-b border-slate-800 pb-4 mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
            <h1 class="text-xl font-black tracking-wider text-indigo-400 uppercase flex items-center gap-2">
                <span class="inline-block w-3 h-3 bg-indigo-500 rounded-sm"></span>
                Institutional Liquidity Regime Overlay System
            </h1>
            <p class="text-slate-400 text-[11px] font-mono mt-0.5">系統狀態：數據每日全自動同步更新 // AUTOMATIC ENGINE ACTIVE</p>
        </div>
        <div class="text-right text-xs text-slate-500 font-mono">
            最後資料更新時間：<span class="text-indigo-400 font-bold">{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
        </div>
    </div>

    <div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div class="lg:col-span-7 space-y-4">
            <div class="bg-slate-900 rounded-xl p-4 border border-slate-800">
                <h3 class="text-xs font-bold text-indigo-400 border-b border-slate-800 pb-2 mb-3">📡 今日自動採集權威指標矩陣</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div class="bg-slate-950 p-2.5 rounded border border-slate-800 flex justify-between">
                        <span class="text-slate-400">全美金融條件 (FRED: NFCI)</span>
                        <span class="font-mono text-sky-400 font-bold">{fci_val} (發布日:{fci_date})</span>
                    </div>
                    <div class="bg-slate-950 p-2.5 rounded border border-slate-800 flex justify-between">
                        <span class="text-slate-400">薩姆規則衰退指標 (Sahm Rule)</span>
                        <span class="font-mono text-emerald-400 font-bold">{sahm_val}% (發布日:{sahm_date})</span>
                    </div>
                    <div class="bg-slate-950 p-2.5 rounded border border-slate-800 flex justify-between">
                        <span class="text-slate-400">BBB級投資公司債利差</span>
                        <span class="font-mono text-amber-400 font-bold">{bbb_spread}%</span>
                    </div>
                    <div class="bg-slate-950 p-2.5 rounded border border-slate-800 flex justify-between">
                        <span class="text-slate-400">台股大盤 200MA 歷史乖離率</span>
                        <span class="font-mono text-rose-400 font-bold">{twii_deviation:.2f}%</span>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                <div class="bg-slate-900 p-3 rounded-xl border border-slate-800"><span class="text-[10px] text-slate-500 block">A. 流動性模組 (35%)</span><span class="text-sm font-bold font-mono text-sky-400">{(m_liquidity >= 0 ? "+" : "") + str(round(m_liquidity,2))}</span></div>
                <div class="bg-slate-900 p-3 rounded-xl border border-slate-800"><span class="text-[10px] text-slate-500 block">B. 實體成長 (25%)</span><span class="text-sm font-bold font-mono text-emerald-400">{(m_growth >= 0 ? "+" : "") + str(round(m_growth,2))}</span></div>
                <div class="bg-slate-900 p-3 rounded-xl border border-slate-800"><span class="text-[10px] text-slate-500 block">C. 信用通膨 (20%)</span><span class="text-sm font-bold font-mono text-amber-400">{(m_credit_inflation >= 0 ? "+" : "") + str(round(m_credit_inflation,2))}</span></div>
                <div class="bg-slate-900 p-3 rounded-xl border border-slate-800"><span class="text-[10px] text-slate-500 block">D. 情緒估值 (20%)</span><span class="text-sm font-bold font-mono text-rose-400">{(m_sentiment_valuation >= 0 ? "+" : "") + str(round(m_sentiment_valuation,2))}</span></div>
            </div>
        </div>

        <div class="lg:col-span-5 space-y-4">
            <div class="bg-slate-900 rounded-xl p-5 border border-slate-800 space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-slate-950 p-3 rounded border border-slate-800 text-center">
                        <span class="text-[10px] text-slate-500 block uppercase">綜合體制得分 ($I_{{regime}}$)</span>
                        <div class="text-3xl font-black font-mono tracking-tight my-1 text-indigo-400">{(i_regime >= 0 ? "+" : "") + f"{i_regime:.2f}"}</div>
                    </div>
                    <div class="bg-slate-950 p-3 rounded border border-slate-800 text-center">
                        <span class="text-[10px] text-slate-500 block uppercase">動態負債率 (LTV)</span>
                        <div class="text-2xl font-black font-mono tracking-tight my-1 {ltv_class}">{ltv_val:.2f}%</div>
                    </div>
                </div>

                <div class="p-3 rounded-lg text-xs font-bold text-center border {status_class}">
                    {status_title}
                </div>

                <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1.5 text-xs">
                    <span class="text-[11px] font-bold text-indigo-400 block mb-1">⚡ 今日自動分流硬執行預算：</span>
                    <div class="flex justify-between border-b border-slate-900 py-1">
                        <span class="text-slate-400">1. 月固定底倉 (0050/QQQ)</span>
                        <span class="font-bold text-emerald-400 font-mono">{int(act_fixed):,} TWD</span>
                    </div>
                    <div class="flex justify-between border-b border-slate-900 py-1">
                        <span class="text-slate-400">2. 月浮動加碼金</span>
                        <span class="font-bold text-amber-400 font-mono">{int(act_floating):,} TWD</span>
                    </div>
                    <div class="flex justify-between border-b border-slate-900 py-1">
                        <span class="text-slate-400">3. 獎金流：補底倉分流 (35%)</span>
                        <span class="font-bold text-emerald-500 font-mono">{int(BONUS_INPUT * 0.35):,} TWD</span>
                    </div>
                    <div class="flex justify-between py-1">
                        <span class="text-slate-400">4. 獎金流：防禦蓄水池 (35%)</span>
                        <span class="font-bold text-indigo-400 font-mono">{int(BONUS_INPUT * 0.35):,} TWD</span>
                    </div>
                </div>
            </div>

            <div class="bg-slate-900 rounded-xl p-4 border border-slate-800 text-xs leading-relaxed font-medium text-slate-300">
                {report_text}
            </div>
        </div>
    </div>
</body>
</html>
"""

    # 將生成的精美網頁寫入本地檔案
    output_filename = "macro_regime_cockpit.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(
        f"✅ 體制模型計算完畢！最新主控台網頁已生成至：{os.path.abspath(output_filename)}"
    )


if __name__ == "__main__":
    run_regime_pipeline()
