import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from github import Github

# === 🎨 1. 页面配置与 CSS 魔法 ===
st.set_page_config(
    page_title="Family Wealth",
    page_icon="🌸",
    layout="centered",
    initial_sidebar_state="collapsed" # 默认收起
)

# 注入 CSS：彻底隐藏侧边栏，美化按钮和字体
st.markdown("""
    <style>
    /* 1. 字体与全局背景 */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #fdfdfd; /* 极淡的暖白背景 */
    }
    
    /* 2. 隐藏原生侧边栏和顶部的汉堡菜单 */
    [data-testid="stSidebar"] {display: none;}
    [data-testid="stSidebarCollapsedControl"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 3. 美化"控制台"按钮 (Popover Button) */
    div[data-testid="stPopover"] > button {
        border-radius: 20px;
        border: 1px solid #eee;
        background-color: white;
        color: #666;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        font-size: 14px;
        padding: 5px 15px;
        transition: all 0.3s;
    }
    div[data-testid="stPopover"] > button:hover {
        border-color: #ffb7b2; /* 悬浮变粉色 */
        color: #ff80ab;
    }

    /* 4. 盈亏大数字卡片优化 */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #fcfcfc;
        padding: 15px 20px;
        border-radius: 16px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.03); /* 更柔和的高级阴影 */
    }
    
    /* 5. 基金详情卡片 */
    .streamlit-expanderHeader {
        background-color: #fff;
        border-radius: 12px;
        font-weight: 500;
        color: #444;
        border: 1px solid #f0f0f0;
    }
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 4px 12px rgba(0,0,0,0.02);
        border-radius: 12px;
        background-color: white;
        margin-bottom: 15px;
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
    # 🌟 顶部导航栏 (替代 Sidebar)
    # ==========================================
    
    # 1. 问候语逻辑
    bj_time = datetime.utcnow() + timedelta(hours=8)
    now_hour = bj_time.hour
    greeting = "Good Morning ☀️" if 5 <= now_hour < 12 else "Good Afternoon ☕" if 12 <= now_hour < 18 else "Good Evening 🌙"

    # 2. 顶部两列布局：左边问候，右边控制台按钮
    top_col1, top_col2 = st.columns([3, 1])
    
    with top_col1:
        st.caption(f"{greeting} | {bj_time.strftime('%m-%d %H:%M')}")
        st.markdown(f"<h2 style='margin-top:-10px; color:#444'>Family Wealth</h2>", unsafe_allow_html=True)

    with top_col2:
        # 🔥 核心改动：用 st.popover 代替 Sidebar
        # 这就是一个右上角的浮窗按钮，点击才会展开设置
        with st.popover("⚙️ 控制台", use_container_width=True):
            st.markdown("### 🛠️ 功能菜单")
            mode = st.radio("选择模式", ["📡 实时看板", "💰 持仓管理", "💾 收盘存证", "⚖️ 晚间审计"], label_visibility="collapsed")
            st.divider()
            
            # --- 把原来的侧边栏逻辑全部塞进这个小弹窗里 ---
            
            # 💰 持仓管理逻辑
            if mode == "💰 持仓管理":
                st.info("修改后点击保存")
                with st.form("holding_form_pop"):
                    new_holdings = {}
                    for name, info in funds_config.items():
                        current_val = info.get('holding_value', 0)
                        # 简写名字，省空间
                        short_name = name.split('(')[0]
                        new_val = st.number_input(short_name, value=float(current_val), step=100.0)
                        new_holdings[name] = new_val
                    
                    if st.form_submit_button("💾 保存生效"):
                        for name, val in new_holdings.items(): funds_config[name]['holding_value'] = val
                        save_json('funds.json', funds_config, config_sha, "Update Holdings")
                        st.toast("✅ 持仓已更新！")
                        time.sleep(1); st.rerun()

            # 💾 存证逻辑
            elif mode == "💾 收盘存证":
                if st.button("📸 立即存证", type="primary", use_container_width=True):
                    with st.spinner("⏳"):
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
                            st.success(f"✅ {today_str} 已存证")
            
            # ⚖️ 审计逻辑
            elif mode == "⚖️ 晚间审计":
                if st.button("🚀 开始修正", type="primary", use_container_width=True):
                    history, _ = load_json('history.json')
                    factor_hist, _ = load_json('factor_history.json')
                    if history:
                        last_date = sorted(history.keys())[-1]
                        audited = factor_hist.get(last_date, {}) if factor_hist else {}
                        updates = []; need_save = False; current_success = {}
                        
                        st.caption(f"审计日期: {last_date}")
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
                                    updates.append(f"{name.split('(')[0]}: 更新")
                                    need_save = True
                            progress.progress((idx+1)/len(funds_config))
                        
                        if need_save:
                            save_json('funds.json', funds_config, config_sha, "Audit")
                            save_factor_history(last_date, current_success)
                            st.success("✅ 系数已修正"); time.sleep(1); st.rerun()
                        else:
                            st.info("暂无更新")

            # 底部显示图表入口
            st.divider()
            with st.expander("📊 系数走势图"):
                fh, _ = load_json('factor_history.json')
                if fh: st.line_chart(pd.DataFrame.from_dict(fh, orient='index').sort_index())
                else: st.caption("暂无数据")

    # ==========================================
    # 👇 主展示区 (Focus Mode)
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
                    st.warning("📡 连接卫星中..."); time.sleep(2); continue
                
                # 计算总盈亏
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
                            if len(stocks) < 3:
                                stocks.append({"重仓": d['name'], "涨跌": f"{d['change']:+.2f}%"})
                    
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
                
                # 1. 💰 总盈亏卡片 (高端C位)
                st.markdown("<br>", unsafe_allow_html=True) # 增加一点呼吸感
                
                # 使用两列布局，左侧大数字，右侧小指标
                main_col1, main_col2 = st.columns([1.8, 1])
                
                main_col1.metric(
                    "今日家庭收益 (元)", 
                    f"{total_profit:+.2f}", 
                    delta=f"{total_profit:+.2f}"
                )
                
                yield_rate = (total_profit/total_principal*100) if total_principal > 0 else 0
                main_col2.metric(
                    "收益率", 
                    f"{yield_rate:+.2f}%",
                    delta_color="normal" # 收益率保持默认颜色，不抢眼
                )
                
                st.markdown("<br>", unsafe_allow_html=True)

                # 2. 🌸 持仓列表
                st.markdown("<span style='color:#888; font-size:14px; margin-left:5px'>我的持仓</span>", unsafe_allow_html=True)
                
                for card in cards_data:
                    # 动态Icon
                    icon = "🔥" if card['est'] > 0 else "🍃" # 换成更有意境的图标
                    
                    # 标题设计：尽量用空格对齐，模拟表格感
                    title = f"{icon} {card['name']}　{card['est']:+.2f}%"
                    
                    with st.expander(title):
                        # 内部布局
                        kc1, kc2 = st.columns([1, 2])
                        color_code = "#ff4d4f" if card['profit']>0 else "#52c41a" # 柔和红绿
                        
                        kc1.markdown(f"""
                        <div style='background-color:#f9f9f9; padding:10px; border-radius:8px;'>
                            <small style='color:#999'>今日盈亏</small><br>
                            <span style='color:{color_code}; font-size:18px; font-weight:bold'>￥{card['profit']:+.1f}</span>
                            <br><br>
                            <small style='color:#999'>本金</small><br>
                            <span style='color:#555'>￥{card['principal']:,}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        kc2.table(card['stocks'])

                # 3. 🌍 底部大盘 (极简注脚模式)
                st.markdown("<br><br>", unsafe_allow_html=True)
                st.divider()
                st.caption("🌍 Global Market Indices")
                mc1, mc2, mc3 = st.columns(3)
                cols = [mc1, mc2, mc3]
                for i, code in enumerate(MARKET_INDICES):
                    d = market_data.get(code)
                    if d: cols[i].metric(MARKET_INDICES[code], f"{d['change']:.2f}%", label_visibility="collapsed") # 隐藏标题，只显示名字在值里? 不，label_collapsed会隐藏标题。
                    # 修正：保持简约
                    # cols[i].markdown(f"**{MARKET_INDICES[code]}**: {d['change']:.2f}%") 

            time.sleep(30)

if __name__ == "__main__":
    main()
