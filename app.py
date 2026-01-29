import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from github import Github

# === 🎨 1. 页面与UI设计 (高定版核心) ===
st.set_page_config(
    page_title="Family Wealth",
    page_icon="🌸", # 图标换成樱花
    layout="centered"
)

# 注入 CSS 样式：圆角、阴影、柔和配色
st.markdown("""
    <style>
    /* 全局字体优化 */
    .stApp {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* 标题样式 */
    h1 {
        font-weight: 300 !important;
        color: #333333;
        font-size: 2.2rem !important;
    }
    
    /* 盈亏大数字卡片 */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #f0f0f0;
        padding: 15px;
        border-radius: 15px; /* 圆角 */
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); /* 柔光阴影 */
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px); /* 悬浮微动 */
        box-shadow: 0 6px 16px rgba(0,0,0,0.08);
    }
    
    /* 基金卡片 (Expander) */
    .streamlit-expanderHeader {
        background-color: #fafafa;
        border-radius: 10px;
        font-weight: 500;
        font-size: 16px;
        border: none;
    }
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        border-radius: 12px;
        background-color: white;
        margin-bottom: 12px;
    }
    
    /* 隐藏杂项 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
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

    # === 侧边栏 (保持不变，功能区) ===
    with st.sidebar:
        st.header("⚙️ 设置") # 标题简化
        mode = st.radio("功能切换", ["📡 实时看板", "💰 持仓管理", "💾 收盘存证", "⚖️ 晚间审计"])
        st.divider()

        if mode == "💰 持仓管理":
            st.info("在这里调整持仓金额")
            with st.form("holding_form"):
                new_holdings = {}
                for name, info in funds_config.items():
                    current_val = info.get('holding_value', 0)
                    new_val = st.number_input(name.split('(')[0], value=float(current_val), step=100.0)
                    new_holdings[name] = new_val
                if st.form_submit_button("保存更改"):
                    for name, val in new_holdings.items(): funds_config[name]['holding_value'] = val
                    save_json('funds.json', funds_config, config_sha, "Update Holdings")
                    st.success("已更新！")
                    time.sleep(1); st.rerun()

        elif mode == "💾 收盘存证":
            if st.button("📸 立即存证"):
                with st.spinner("存证中..."):
                    snapshot_data = {}
                    all_codes = []
                    for f in funds_config.values():
                        for s in f['holdings']: all_codes.append(s['code'])
                    prices = get_realtime_price(list(set(all_codes)))
                    if prices:
                        today_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
                        for name, info in funds_config.items():
                            val = 0; w = 0
                            for s in info['holdings']:
                                if s['code'] in prices:
                                    val += prices[s['code']]['change'] * s['weight']; w += s['weight']
                            snapshot_data[name] = val / w if w > 0 else 0
                        history, hist_sha = load_json('history.json')
                        history[today_str] = snapshot_data
                        save_json('history.json', history, hist_sha, f"Snapshot {today_str}")
                        st.success("✅ 存证成功")

        elif mode == "⚖️ 晚间审计":
            st.info("系数修正模式")
            history, hist_sha = load_json('history.json')
            factor_history, _ = load_json('factor_history.json')
            if history:
                last_date = sorted(history.keys())[-1]
                st.write(f"审计日期: {last_date}")
                audited = factor_history.get(last_date, {}) if factor_history else {}
                if st.button("开始计算"):
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
                                updates.append(f"{name}: 系数更新")
                                need_save = True
                        progress.progress((idx+1)/len(funds_config))
                    if need_save:
                        save_json('funds.json', funds_config, config_sha, "Audit")
                        save_factor_history(last_date, current_success)
                        st.success("系数已修正"); st.rerun()
                    else: st.info("无需更新")
            else: st.error("无数据")
        
        # 底部图表
        st.divider()
        with st.expander("📊 算法稳定性", expanded=False):
            fh, _ = load_json('factor_history.json')
            if fh: st.line_chart(pd.DataFrame.from_dict(fh, orient='index').sort_index())

    # ==========================================
    # 👇 主界面：高端女性化 UI (Focus on Profit)
    # ==========================================
    if mode == "📡 实时看板":
        placeholder = st.empty()
        
        # 准备代码列表
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        all_codes = list(set(all_codes))
        
        while True:
            with placeholder.container():
                # 0. 贴心问候
                now_hour = (datetime.utcnow() + timedelta(hours=8)).hour
                greeting = "Good Morning ☀️" if 5 <= now_hour < 12 else "Good Afternoon ☕" if 12 <= now_hour < 18 else "Good Evening 🌙"
                st.caption(f"{greeting} | 数据实时刷新中...")
                st.markdown(f"<h1>Family Wealth <span style='font-size:20px; color:#888'>· 你的专属基金管家</span></h1>", unsafe_allow_html=True)
                
                market_data = get_realtime_price(all_codes)
                if not market_data:
                    st.warning("正在连接交易所..."); time.sleep(2); continue
                
                # 1. 核心计算 (为了算总账)
                total_profit = 0
                total_principal = 0
                cards_data = []
                
                for name, info in funds_config.items():
                    factor = info.get('factor', 1.0)
                    principal = info.get('holding_value', 0)
                    
                    # 算涨幅
                    val = 0; w = 0; stocks = []
                    for s in info['holdings']:
                        d = market_data.get(s['code'])
                        if d:
                            val += d['change'] * s['weight']; w += s['weight']
                            if len(stocks) < 3: # 缩减显示，只显示前3个，更简洁
                                stocks.append({"重仓": d['name'], "涨跌": f"{d['change']:+.2f}%"})
                    
                    est = (val / w * factor) if w > 0 else 0
                    profit = principal * est / 100
                    
                    total_profit += profit
                    total_principal += principal
                    
                    cards_data.append({
                        "name": name.split('(')[0], # 只要前面的名字
                        "est": est,
                        "profit": profit,
                        "principal": principal,
                        "stocks": stocks
                    })
                
                # 2. 💸 总盈亏看板 (C位展示)
                st.markdown("### ✨ 今日收益")
                c1, c2 = st.columns(2)
                
                # 颜色逻辑：女生通常喜欢红色代表涨（喜庆），绿色代表跌。或者为了高端，用柔和色。
                # 这里保持红涨绿跌，但颜色代码调得更“软”一点在 CSS 里不好做，直接用系统逻辑。
                
                c1.metric("预估盈利 (元)", f"{total_profit:+.2f}", delta=f"{total_profit:+.2f}")
                
                yield_rate = (total_profit/total_principal*100) if total_principal > 0 else 0
                c2.metric("总收益率", f"{yield_rate:+.2f}%")
                
                st.markdown("<br>", unsafe_allow_html=True) # 留点白

                # 3. 🌸 基金详情卡片 (中间层)
                st.markdown("### 🌸 持仓详情")
                for card in cards_data:
                    # 图标逻辑
                    icon = "📈" if card['est'] > 0 else "📉"
                    # 标题设计
                    title = f"{icon} {card['name']}　{card['est']:+.2f}%　(￥{card['profit']:+.1f})"
                    
                    with st.expander(title):
                        # 内部布局
                        kc1, kc2 = st.columns([1, 2])
                        kc1.markdown(f"""
                        **本金**: ￥{card['principal']:,}<br>
                        **盈亏**: <span style='color:{"#d63384" if card['profit']>0 else "#2e7d32"}; font-weight:bold'>￥{card['profit']:+.2f}</span>
                        """, unsafe_allow_html=True)
                        
                        kc2.table(card['stocks'])

                st.markdown("<br>", unsafe_allow_html=True)

                # 4. 📉 市场风向 (沉底)
                st.divider() # 加一条淡淡的分界线
                st.caption("🌍 市场大盘参考")
                mc1, mc2, mc3 = st.columns(3)
                m_cols = [mc1, mc2, mc3]
                for i, code in enumerate(MARKET_INDICES):
                    d = market_data.get(code)
                    if d: 
                        # 指数这里就不强调颜色了，用灰色调或者默认
                        m_cols[i].metric(MARKET_INDICES[code], f"{d['change']:.2f}%")
            
            time.sleep(30)

if __name__ == "__main__":
    main()
