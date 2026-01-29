import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from github import Github

# === 🎨 1. 页面配置与 CSS 魔法 (Apple Glassmorphism) ===
st.set_page_config(
    page_title="Family Wealth",
    page_icon="💎",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 注入 CSS：苹果风 + 毛玻璃 + 极光背景
st.markdown("""
    <style>
    /* 1. 全局极光背景 (让毛玻璃显形的背景) */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(255, 230, 240, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    radial-gradient(circle at 90% 80%, rgba(230, 240, 255, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    #fdfdfd; /* 兜底白色 */
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
    
    /* 2. 隐藏无关元素 */
    [data-testid="stSidebar"] {display: none;}
    [data-testid="stSidebarCollapsedControl"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 3. Settings 按钮 (胶囊风) */
    div[data-testid="stPopover"] > button {
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.6);
        background-color: rgba(255, 255, 255, 0.5);
        backdrop-filter: blur(10px); /* 毛玻璃 */
        color: #888;
        font-size: 13px;
        padding: 4px 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        transition: all 0.3s;
    }
    div[data-testid="stPopover"] > button:hover {
        background-color: rgba(255, 255, 255, 0.9);
        color: #333;
        transform: scale(1.02);
    }

    /* 4. 收益率大卡片 (毛玻璃化) */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.65); /* 半透明白 */
        backdrop-filter: blur(16px);            /* 强模糊 */
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.6); /* 玻璃边框 */
        padding: 15px 20px;
        border-radius: 20px; /* 更大的圆角 */
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.05); /* 柔光投影 */
        min-height: 115px !important; 
        max-height: 115px !important;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    div[data-testid="stMetricLabel"] {
        color: #666;
        font-size: 13px;
        font-weight: 500;
        letter-spacing: 0.5px;
    }
    
    /* 5. 基金卡片容器 (Expander) */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.7) !important;
        border-radius: 16px;
        font-weight: 600;
        color: #333;
        border: 1px solid rgba(255, 255, 255, 0.5);
        font-size: 15px;
    }
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 8px 24px rgba(0,0,0,0.04);
        border-radius: 16px;
        background-color: rgba(255, 255, 255, 0.5); /* 容器本身也半透明 */
        backdrop-filter: blur(10px);
        margin-bottom: 15px;
        overflow: hidden; /* 防止内容溢出圆角 */
    }
    div[data-testid="stExpanderDetails"] {
        background-color: rgba(255, 255, 255, 0.4); /* 展开后的背景 */
    }

    /* 6. 🔥 iOS 风格持仓列表 (取代旧表格) */
    .ios-list-container {
        padding: 0 5px;
    }
    .ios-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid rgba(0,0,0,0.05); /* 极细的分隔线 */
    }
    .ios-row:last-child {
        border-bottom: none;
    }
    
    /* 序号 */
    .ios-index {
        font-size: 12px;
        color: #bbb;
        width: 25px;
        font-weight: 600;
    }
    
    /* 股票名 */
    .ios-name {
        font-size: 15px;
        color: #333;
        font-weight: 500;
        flex-grow: 1; /* 撑开中间空间 */
    }
    
    /* 涨跌胶囊 */
    .ios-pill {
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        min-width: 70px;
        text-align: right;
        /* 默认样式，会被内联样式覆盖 */
    }
    
    /* 左侧详情区美化 */
    .detail-box {
        background: rgba(255,255,255,0.6);
        padding: 15px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.4);
    }
    </style>
""", unsafe_allow_html=True)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

FUND_CODES_MAP = {
    '摩根均衡C (梁鹏/周期)': '009968',
    '泰康新锐C (韩庆/成长)': '009340',
    '财通优选C (金梓才/AI)': '009354'
}

# === 🛠️ GitHub 数据库操作 ===

def get_repo():
    try:
        token = st.secrets["github_token"]
        username = st.secrets["github_username"]
        repo_name = st.secrets["repo_name"]
        g = Github(token)
        return g.get_user(username).get_repo(repo_name)
    except Exception as e:
        st.error(f"GitHub 连接失败: {e}")
        return None

def load_json(filename):
    repo = get_repo()
    if not repo: return {}, None
    try:
        content = repo.get_contents(filename)
        return json.loads(content.decoded_content.decode('utf-8')), content.sha
    except:
        return {}, None

def save_json(filename, data, sha, message):
    repo = get_repo()
    if repo:
        new_content = json.dumps(data, indent=4, ensure_ascii=False)
        if sha:
            repo.update_file(filename, message, new_content, sha)
        else:
            repo.create_file(filename, message, new_content)

def save_factor_history(date_str, new_factors_dict):
    history, sha = load_json('factor_history.json')
    if not isinstance(history, dict): history = {}
    existing_record = history.get(date_str, {})
    existing_record.update(new_factors_dict)
    history[date_str] = existing_record
    save_json('factor_history.json', history, sha, f"Factor Log {date_str}")

# === 🕷️ 数据获取 ===

def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    codes_str = ",".join(stock_codes)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    try:
        r = requests.get(url, timeout=3)
        text = r.text
        price_data = {}
        parts = text.split(';')
        for part in parts:
            if '="' in part:
                try:
                    key_raw = part.split('=')[0].strip()
                    code = key_raw.split('_')[-1] 
                    data = part.split('="')[1].strip('"').split('~')
                    if len(data) > 30:
                        name = data[1].replace(" ", "")
                        current = float(data[3])
                        close = float(data[4])
                        pct = 0.0
                        if close > 0: pct = ((current - close) / close) * 100
                        price_data[code] = {'name': name, 'change': pct}
                except: continue
        return price_data
    except: return None

def get_official_nav(fund_code):
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=1"
    headers = {
        "Referer": "http://fund.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            res = r.json()
            if "Data" in res and "LSJZList" in res["Data"]:
                data_list = res["Data"]["LSJZList"]
                if len(data_list) > 0:
                    latest_data = data_list[0]
                    return float(latest_data["JZZZL"]), latest_data["FSRQ"]
    except: pass
    return None, None

# === 🚀 主程序 ===
def main():
    funds_config, config_sha = load_json('funds.json')
    if not funds_config: st.stop()

    # ==========================================
    # 🌟 顶部导航栏
    # ==========================================
    
    bj_time = datetime.utcnow() + timedelta(hours=8)
    now_hour = bj_time.hour
    greeting = "Good Morning ☀️" if 5 <= now_hour < 12 else "Good Afternoon ☕" if 12 <= now_hour < 18 else "Good Evening 🌙"

    top_col1, top_col2 = st.columns([3, 1])
    
    with top_col1:
        st.caption(f"{greeting} | {bj_time.strftime('%m-%d %H:%M')}")
        st.markdown(f"<h2 style='margin-top:-10px; color:#333; letter-spacing:0.5px; font-weight:300'>Family Wealth</h2>", unsafe_allow_html=True)

    with top_col2:
        with st.popover("⚙️ Settings", use_container_width=True):
            st.markdown("### 🛠️ Menu")
            mode = st.radio("Mode", ["📡 实时看板", "💰 持仓管理", "💾 收盘存证", "⚖️ 晚间审计"], label_visibility="collapsed")
            st.divider()
            
            # --- 内部逻辑 (保持不变) ---
            if mode == "💰 持仓管理":
                st.info("Modify Holdings")
                with st.form("holding_form_pop"):
                    new_holdings = {}
                    for name, info in funds_config.items():
                        current_val = info.get('holding_value', 0)
                        short_name = name.split('(')[0]
                        new_val = st.number_input(short_name, value=float(current_val), step=100.0)
                        new_holdings[name] = new_val
                    
                    if st.form_submit_button("Save"):
                        for name, val in new_holdings.items(): funds_config[name]['holding_value'] = val
                        save_json('funds.json', funds_config, config_sha, "Update Holdings")
                        st.toast("Updated!")
                        time.sleep(1); st.rerun()

            elif mode == "💾 收盘存证":
                if st.button("📸 Snapshot", type="primary", use_container_width=True):
                    with st.spinner("Saving..."):
                        snapshot_data = {}
                        all_codes = []
                        for f in funds_config.values():
                            for s in f['holdings']: all_codes.append(s['code'])
                        prices = get_realtime_price(list(set(all_codes)))
                        if prices:
                            today_str = bj_time.strftime("%Y-%m-%d")
                            for name, info in funds_config.items():
                                val = 0; w = 0
                                for s in info['holdings']:
                                    if s['code'] in prices:
                                        val += prices[s['code']]['change'] * s['weight']; w += s['weight']
                                snapshot_data[name] = val / w if w > 0 else 0
                            history, hist_sha = load_json('history.json')
                            history[today_str] = snapshot_data
                            save_json('history.json', history, hist_sha, f"Snapshot {today_str}")
                            st.success(f"Saved: {today_str}")

            elif mode == "⚖️ 晚间审计":
                if st.button("🚀 Audit & Fix", type="primary", use_container_width=True):
                    history, _ = load_json('history.json')
                    factor_hist, _ = load_json('factor_history.json')
                    if history:
                        last_date = sorted(history.keys())[-1]
                        audited = factor_hist.get(last_date, {}) if factor_hist else {}
                        updates = []; need_save = False; current_success = {}
                        progress = st.progress(0)
                        for idx, (name, info) in enumerate(funds_config.items()):
                            if name in audited: progress.progress((idx+1)/len(funds_config)); continue
                            raw = history[last_date].get(name)
                            code = FUND_CODES_MAP.get(name)
                            if raw is not None and code:
                                off_pct, off_date = get_official_nav(code)
                                if off_date and off_date >= last_date and raw != 0:
                                    new_f = (info['factor'] * 0.8) + ((off_pct / raw) * 0.2)
                                    funds_config[name]['factor'] = round(new_f, 4)
                                    current_success[name] = round(new_f, 4)
                                    need_save = True
                            progress.progress((idx+1)/len(funds_config))
                        if need_save:
                            save_json('funds.json', funds_config, config_sha, "Audit")
                            save_factor_history(last_date, current_success)
                            st.success("Fixed!"); time.sleep(1); st.rerun()
                        else: st.info("No updates needed")

            st.divider()
            with st.expander("📊 Stability"):
                fh, _ = load_json('factor_history.json')
                if fh: st.line_chart(pd.DataFrame.from_dict(fh, orient='index').sort_index())

    # ==========================================
    # 👇 主展示区 (Apple Glass Mode)
    # ==========================================
    if mode == "📡 实时看板":
        placeholder = st.empty()
        
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        all_codes = list(set(all_codes))
        
        while True:
            with placeholder.container():
                market_data = get_realtime_price(all_codes)
                if not market_data:
                    st.warning("Connecting..."); time.sleep(2); continue
                
                total_profit = 0
                total_principal = 0
                cards_data = []
                
                for name, info in funds_config.items():
                    factor = info.get('factor', 1.0)
                    principal = info.get('holding_value', 0)
                    val = 0; w = 0; stocks = []
                    for s in info['holdings']:
                        d = market_data.get(s['code'])
                        if d:
                            val += d['change'] * s['weight']; w += s['weight']
                            if len(stocks) < 3: # 前3大重仓
                                stocks.append({
                                    "name": d['name'], 
                                    "pct": d['change']
                                })
                    
                    est = (val / w * factor) if w > 0 else 0
                    profit = principal * est / 100
                    total_profit += profit
                    total_principal += principal
                    
                    cards_data.append({
                        "name": name.split('(')[0],
                        "est": est,
                        "profit": profit,
                        "principal": principal,
                        "stocks": stocks
                    })
                
                # 1. 💰 总盈亏 (高度强制对齐)
                st.markdown("<br>", unsafe_allow_html=True)
                main_col1, main_col2 = st.columns([1.8, 1])
                
                main_col1.metric("今日家庭收益 (元)", f"{total_profit:+.2f}", delta=f"{total_profit:+.2f}")
                
                yield_rate = (total_profit/total_principal*100) if total_principal > 0 else 0
                main_col2.metric("收益率", f"{yield_rate:+.2f}%", delta_color="normal")
                
                # 2. 💎 持仓列表
                st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
                st.markdown("<span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>PORTFOLIO</span>", unsafe_allow_html=True)
                
                for card in cards_data:
                    # 图标逻辑
                    icon = "👑" if card['est'] > 0 else "📿"
                    title = f"{icon} {card['name']}　{card['est']:+.2f}%"
                    
                    with st.expander(title):
                        kc1, kc2 = st.columns([1.1, 2])
                        
                        # 左侧：玻璃质感小卡片
                        color_code = "#ff3b30" if card['profit']>0 else "#34c759" # iOS 红/绿
                        kc1.markdown(f"""
                        <div class='detail-box'>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>今日盈亏</div>
                            <div style='font-size:20px; font-weight:600; color:{color_code}; font-family:-apple-system'>￥{card['profit']:+.1f}</div>
                            <div style='height:15px'></div>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>本金</div>
                            <div style='font-size:16px; color:#333; font-weight:500'>￥{card['principal']:,}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 右侧：🔥 iOS 列表风格 (取代 Excel 表格)
                        # 这里我们用 div + flexbox 模拟苹果的列表
                        list_html = "<div class='ios-list-container'>"
                        for i, s in enumerate(card['stocks']):
                            # 涨跌胶囊颜色
                            if s['pct'] > 0:
                                bg_color = "#ff3b30"; txt_color = "white"
                            elif s['pct'] < 0:
                                bg_color = "#34c759"; txt_color = "white"
                            else:
                                bg_color = "#8e8e93"; txt_color = "white"
                            
                            list_html += f"""
                            <div class='ios-row'>
                                <div class='ios-index'>{i+1}</div>
                                <div class='ios-name'>{s['name']}</div>
                                <div class='ios-pill' style='background-color:{bg_color}; color:{txt_color}'>{s['pct']:+.2f}%</div>
                            </div>
                            """
                        list_html += "</div>"
                        
                        kc2.markdown(list_html, unsafe_allow_html=True)

                # 3. 🌍 底部大盘
                st.divider()
                st.markdown("<span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>MARKET INDICES</span>", unsafe_allow_html=True)
                
                mc1, mc2, mc3 = st.columns(3)
                m_cols = [mc1, mc2, mc3]
                for i, code in enumerate(MARKET_INDICES):
                    d = market_data.get(code)
                    if d: m_cols[i].metric(MARKET_INDICES[code], f"{d['change']:.2f}%")

            time.sleep(30)

if __name__ == "__main__":
    main()
