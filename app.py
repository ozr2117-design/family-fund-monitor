import streamlit as st
import requests
import time
import json
import pandas as pd
import re
import os
from datetime import datetime, timedelta
from github import Github

# ==========================================
# 0. 🎯 核心配置
# ==========================================
AUDIT_MEMO = {
    "摩根均衡": {
        "tag": "⚠️ 偏离注意", "text": "近期调仓频繁，估值仅供参考", 
        "color": "#fffbe6", "text_color": "#d48806"
    },
    "泰康新锐": {
        "tag": "✅ 估值精准", "text": "持仓稳定，净值参考性高", 
        "color": "#f6ffed", "text_color": "#389e0d"
    },
    "财通优选": {
        "tag": "👌 波动正常", "text": "弹性较大，适合做波段", 
        "color": "#e6f7ff", "text_color": "#096dd9"
    }
}

# 🛠️ 基金代码映射表 (纯享版 - 仅保留C类场外基金)
FUND_CODES_MAP = {
    '摩根均衡': '021274',
    '泰康新锐': '017366',
    '财通优选': '021528'
}

# === 🎨 1. 页面配置与 CSS ===
st.set_page_config(
    page_title="Family Wealth V7.7",
    page_icon="💎",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* 全局背景 */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(255, 230, 240, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    radial-gradient(circle at 90% 80%, rgba(230, 240, 255, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    #fdfdfd;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    
    [data-testid="stSidebar"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    div[data-testid="stPopover"] > button {
        border-radius: 20px; background: rgba(255,255,255,0.8); border: 1px solid #eee; color: #555;
    }
    
    /* 强制等高卡片 */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.65); backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.6); border-radius: 20px; padding: 15px 20px;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.05);
        /* 固定高度 */
        min-height: 120px !important; 
        max-height: 120px !important;
        display: flex; flex-direction: column; justify-content: center;
    }
    
    div[data-testid="stExpander"] {
        border: none; box-shadow: 0 8px 24px rgba(0,0,0,0.03);
        border-radius: 16px; background-color: rgba(255, 255, 255, 0.5);
        margin-bottom: 15px; overflow: hidden;
    }
    
    .ios-list-container { display: flex; flex-direction: column; width: 100%; }
    .ios-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid rgba(0,0,0,0.06); width: 100%; }
    .ios-row:last-child { border-bottom: none; }
    .ios-index { font-size: 12px; color: #aaa; width: 24px; font-weight: 600; margin-right: 8px; }
    .ios-name { font-size: 14px; color: #333; font-weight: 500; flex: 1; margin-right: 10px; }
    .ios-pill { padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; min-width: 65px; text-align: right; color: white; font-family: -apple-system; }
    .detail-box { background: rgba(255,255,255,0.6); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.4); }
    
    .signal-buy { background-color: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 15px; display: flex; align-items: center; }
    .signal-sell { background-color: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 15px; display: flex; align-items: center; }
    .audit-pill { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; margin-bottom: 12px; font-family: -apple-system; }

    .tag-base { font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; font-weight: 500; }
    .tag-yesterday { color: #888; background: #f0f0f5; }
    .tag-trend-up { color: #cf1322; background: #fff1f0; border: 1px solid #ffa39e; }
    .tag-trend-down { color: #389e0d; background: #f6ffed; border: 1px solid #b7eb8f; }
    .tag-trend-wait { color: #999; background: #f5f5f5; border: 1px dashed #ccc; }
    </style>
""", unsafe_allow_html=True)

MARKET_INDICES = {'sh000001': '上证指数', 'sz399006': '创业板指', 'hkHSTECH': '恒生科技'}

# === 🛠️ 辅助函数 ===
def get_benchmark_code(fund_name):
    if "周期" in fund_name or "均衡" in fund_name: return 'sh000001', '上证'
    elif "成长" in fund_name or "AI" in fund_name or "优选" in fund_name: return 'sz399006', '创指'
    else: return 'sh000001', '上证'

# === 🛠️ GitHub & 数据存储 ===
def get_repo():
    try:
        token = st.secrets["github_token"]
        username = st.secrets["github_username"]
        repo_name = st.secrets["repo_name"]
        return Github(token).get_user(username).get_repo(repo_name)
    except: return None

def load_json(filename):
    repo = get_repo()
    if not repo: return {}, None
    try:
        content = repo.get_contents(filename)
        return json.loads(content.decoded_content.decode('utf-8')), content.sha
    except: return {}, None

def save_json(filename, data, sha, message):
    repo = get_repo()
    if repo:
        new_content = json.dumps(data, indent=4, ensure_ascii=False)
        if sha: repo.update_file(filename, message, new_content, sha)
        else: repo.create_file(filename, message, new_content)

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
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=3)
        price_data = {}
        for part in r.text.split(';'):
            if '="' in part:
                try:
                    code = part.split('=')[0].split('_')[-1]
                    data = part.split('="')[1].strip('"').split('~')
                    if len(data) > 30:
                        name = data[1].replace(" ", "")
                        pct = float(data[32]) if len(data) > 32 and data[32] != '' else 0.0
                        if pct == 0.0: 
                            current = float(data[3]); close = float(data[4])
                            if close > 0: pct = ((current - close) / close) * 100
                        if abs(pct) > 60: pct = 0.0
                        price_data[code] = {'name': name, 'pct': pct}
                except: continue
        return price_data
    except: return None

def get_latest_official(fund_code):
    if not fund_code: return None, None
    url = f"http://qt.gtimg.cn/q=jj{fund_code}"
    try:
        r = requests.get(url, timeout=2)
        if '="' in r.text:
            content = r.text.split('="')[1].strip('";')
            data = content.split('~')
            if len(data) > 8:
                pct = float(data[7])
                date_str = data[8][:10]
                return pct, date_str
    except: pass
    return None, None

# === 🏴‍☠️ 历史数据灌入 ===
def fetch_history_from_eastmoney(fund_code):
    """从静态文件获取全量历史"""
    url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://fund.eastmoney.com/"}
    try:
        r = requests.get(url + f"?v={int(time.time())}", headers=headers, timeout=5)
        if r.status_code == 200:
            pattern = r'Data_netWorthTrend\s*=\s*(\[.*?\]);'
            match = re.search(pattern, r.text)
            if match:
                data = json.loads(match.group(1))
                history_map = {}
                for item in data:
                    d_str = time.strftime('%Y-%m-%d', time.localtime(item['x']/1000))
                    pct = item.get('equityReturn', 0)
                    history_map[d_str] = pct
                return history_map
    except: pass
    return None

def init_history_data(funds_config):
    hist, sha = load_json('nav_history.json')
    if not isinstance(hist, dict): hist = {}
    
    updated = False
    for name in funds_config.keys():
        short_name = name.split('(')[0].strip()
        f_code = None
        for k, v in FUND_CODES_MAP.items():
            if k in short_name or short_name in k:
                f_code = v; break
        
        if not f_code: continue
        
        # 强制更新，覆盖旧数据
        with st.spinner(f"正在校准 {short_name} 数据..."):
            full_data = fetch_history_from_eastmoney(f_code)
            if full_data:
                hist[short_name] = full_data # 直接替换，不merge
                updated = True
    
    if updated:
        save_json('nav_history.json', hist, sha, "Auto Correct History V7.7")
        return hist
    return hist

# === 📈 趋势计算 ===
def calculate_local_trend(hist, fund_name):
    if not hist or fund_name not in hist: return None
    records = sorted(hist[fund_name].items(), key=lambda x: x[0], reverse=True)
    if not records: return None
    
    first_val = records[0][1]
    direction = 1 if first_val > 0 else (-1 if first_val < 0 else 0)
    if direction == 0: return 0
    
    consecutive = 0
    for _, val in records:
        if (direction == 1 and val > 0) or (direction == -1 and val < 0):
            consecutive += 1
        else: break
        
    return consecutive * direction

# === 🚀 主程序 ===
def main():
    funds_config, config_sha = load_json('funds.json')
    if not funds_config: st.stop()

    # 🔥 核心修正：更改 Session State 密钥，强制触发重新清洗
    init_key = 'history_calibrated_v77'
    
    if init_key not in st.session_state:
        nav_hist = init_history_data(funds_config)
        st.session_state['nav_hist'] = nav_hist
        st.session_state[init_key] = True
    else:
        if 'nav_hist' not in st.session_state:
            nav_hist, _ = load_json('nav_history.json')
            st.session_state['nav_hist'] = nav_hist if nav_hist else {}
        else:
            nav_hist = st.session_state['nav_hist']

    bj_time = datetime.utcnow() + timedelta(hours=8)
    now_hour = bj_time.hour
    greeting = "Good Morning ☀️" if 5 <= now_hour < 12 else "Good Afternoon ☕" if 12 <= now_hour < 18 else "Good Evening 🌙"

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.caption(f"{greeting} | {bj_time.strftime('%m-%d %H:%M')}")
        st.markdown(f"<h2 style='margin-top:-10px; color:#333; font-weight:300'>Family Wealth</h2>", unsafe_allow_html=True)

    zen_mode = False
    with top_col2:
        with st.popover("⚙️ Settings", use_container_width=True):
            st.caption("Mode")
            zen_mode = st.toggle("🧘 禅模式", value=False)
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            mode = st.radio("Nav", ["📡  实时看板", "💰  持仓管理"], label_visibility="collapsed", key="nav")
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            action_mode = st.radio("Tools", ["💾  收盘存证", "⚖️  晚间审计"], label_visibility="collapsed", index=None, key="act")
            
            st.divider()
            # 🔥 新增：强制重置按钮
            if st.button("🗑️ 强制删除历史缓存", use_container_width=True):
                # 尝试删除本地文件
                try:
                    if os.path.exists('nav_history.json'):
                        os.remove('nav_history.json')
                    # 清除 Session State
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.toast("已重置！正在重启...", icon="♻️")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"删除失败: {e}")

            current_selection = action_mode if action_mode else mode
            if current_selection == "💰  持仓管理":
                st.divider()
                st.info("Manage Holdings")
                with st.form("h_form"):
                    new_h, new_b = {}, {}
                    for n, i in funds_config.items():
                        new_h[n] = st.number_input(n.split('(')[0], value=float(i.get('holding_value', 0)))
                    if st.form_submit_button("Save"):
                        for n in funds_config: funds_config[n]['holding_value'] = new_h[n]
                        save_json('funds.json', funds_config, config_sha, "Update")
                        st.toast("Saved!"); time.sleep(1); st.rerun()
            
            elif current_selection == "💾  收盘存证":
                st.divider()
                if st.button("Run Snapshot", type="primary", use_container_width=True):
                    with st.spinner("Saving..."):
                        st.toast("Snapshot feature pending") 

    # === 主看板逻辑 ===
    if "持仓管理" not in str(mode) and "持仓管理" not in str(action_mode):
        placeholder = st.empty()
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        
        while True:
            with placeholder.container():
                market = get_realtime_price(list(set(all_codes)))
                if not market: st.warning("Connecting..."); time.sleep(2); continue
                
                total_p = 0; total_b = 0; cards = []; msg = None
                nav_hist_updated = False
                
                for name, info in funds_config.items():
                    val=0; w=0; stocks=[]
                    for s in info['holdings']:
                        d = market.get(s['code'])
                        if d:
                            val += d['pct']*s['weight']; w += s['weight']
                            if len(stocks)<3: stocks.append(d)
                    est = (val/w * info.get('factor', 1.0)) if w>0 else 0
                    profit = info.get('holding_value', 0) * est / 100
                    total_p += profit; total_b += info.get('holding_value', 0)

                    # 官方净值更新
                    short_name = name.split('(')[0].strip()
                    f_code = None
                    for k, v in FUND_CODES_MAP.items():
                        if k in short_name or short_name in k:
                            f_code = v; break
                    
                    last_pct, last_date = get_latest_official(f_code)
                    
                    if last_pct is not None and nav_hist:
                        if short_name not in nav_hist: nav_hist[short_name] = {}
                        if last_date not in nav_hist[short_name] or nav_hist[short_name][last_date] != last_pct:
                            nav_hist[short_name][last_date] = last_pct
                            nav_hist_updated = True
                    
                    local_trend = calculate_local_trend(nav_hist, short_name)

                    bench_c, bench_n = get_benchmark_code(name)
                    bench_v = market.get(bench_c, {}).get('pct', 0)
                    sig = None; txt = ""; act = ""
                    base_u = info.get('base_unit', 1000)
                    
                    if est < -2.5 and est < bench_v:
                        sig = "BUY"; txt = f"跑输{bench_n} {abs(est-bench_v):.1f}%"; act = f"加仓 ¥{base_u * (2 if est<-4 else 1):,}"
                        if not msg: msg = "🎯 加仓机会"
                    elif est > 3.0 and est > (bench_v + 1.5):
                        sig = "SELL"; txt = f"跑赢{bench_n} {abs(est-bench_v):.1f}%"; act = "卖出 1/4"
                        if not msg: msg = "🔥 止盈机会"

                    cards.append({
                        "name": short_name, "full": name, "est": est, "profit": profit, "base": info.get('holding_value', 0),
                        "stocks": stocks, "sig": sig, "txt": txt, "act": act,
                        "last_pct": last_pct, "local_trend": local_trend
                    })
                
                if nav_hist_updated:
                    h, s = load_json('nav_history.json')
                    save_json('nav_history.json', nav_hist, s, "Auto Update")

                if msg: st.toast(msg)

                st.markdown("<br>", unsafe_allow_html=True)
                c1, c2 = st.columns([1.8, 1])
                p_s = "****" if zen_mode else f"{total_p:+.2f}"
                c1.metric("今日家庭收益 (元)", p_s, delta=None) 
                rate = (total_p/total_b*100) if total_b>0 else 0
                c2.metric("收益率", f"{rate:+.2f}%")

                st.markdown("<div style='margin-bottom: 12px;'></div><span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>PORTFOLIO</span>", unsafe_allow_html=True)

                for card in cards:
                    icon = "👑" if card['est']>0 else "📿"
                    suffix = f" {card['est']:+.2f}%"
                    if card['sig']=="BUY": suffix += " 🎯 机会"
                    elif card['sig']=="SELL": suffix += " 🔥 止盈"
                    
                    with st.expander(f"{icon} {card['name']}{suffix}"):
                        for k, v in AUDIT_MEMO.items():
                            if k in card['full']:
                                st.markdown(f"<div class='audit-pill' style='background-color:{v['color']}; color:{v['text_color']};'><strong>{v['tag']}</strong> | {v['text']}</div>", unsafe_allow_html=True)
                                break
                        
                        if card['sig']:
                            cls = "signal-buy" if card['sig']=="BUY" else "signal-sell"
                            st.markdown(f"<div class='{cls}'><div><div>🎯 {card['txt']}</div><div style='font-size:15px; margin-top:4px'>👉 {card['act']}</div></div></div>", unsafe_allow_html=True)

                        kc1, kc2 = st.columns([1.1, 2])
                        col_c = "#ff3b30" if card['profit']>0 else "#34c759"
                        p_show = "<span style='color:#aaa'>****</span>" if zen_mode else f"￥{card['profit']:+.1f}"
                        b_show = "****" if zen_mode else f"￥{card['base']:,}"

                        last_html = ""
                        if card['last_pct'] is not None:
                            l_col = "#ff3b30" if card['last_pct']>0 else ("#34c759" if card['last_pct']<0 else "#888")
                            last_html = f"<span class='tag-base tag-yesterday' style='color:{l_col}'>昨 {card['last_pct']:+.2f}%</span>"
                        
                        trend_html = ""
                        tr = card['local_trend']
                        if tr is not None:
                            if tr > 0: trend_html = f"<span class='tag-base tag-trend-up'>🔥 {tr}连涨</span>"
                            elif tr < 0: trend_html = f"<span class='tag-base tag-trend-down'>❄️ {abs(tr)}连跌</span>"
                            else: trend_html = "<span class='tag-base tag-trend-wait'>〰️ 0连涨</span>"
                        
                        # 🔥 修复：完全单行化 HTML，去除所有可能的格式问题
                        hist_row_html = ""
                        if last_html or trend_html:
                            hist_row_html = f"<div style='margin-top:8px; display:flex; align-items:center'><span style='font-size:11px; color:#aaa'>历史</span>{last_html}{trend_html}</div>"

                        kc1.markdown(f"""
                        <div class='detail-box'>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>今日盈亏</div>
                            <div style='font-size:20px; font-weight:600; color:{col_c}; font-family:-apple-system'>{p_show}</div>
                            <div style='height:15px'></div>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>本金</div>
                            <div style='font-size:16px; color:#333; font-weight:500'>{b_show}</div>
                            {hist_row_html}
                        </div>
                        """, unsafe_allow_html=True)

                        rows = ""
                        for i, s in enumerate(card['stocks']):
                            bg = "#ff3b30" if s['pct']>0 else ("#34c759" if s['pct']<0 else "#8e8e93")
                            rows += f"<div class='ios-row'><div class='ios-index'>{i+1}</div><div class='ios-name'>{s['name']}</div><div class='ios-pill' style='background-color:{bg}'>{s['pct']:+.2f}%</div></div>"
                        kc2.markdown(f"<div class='ios-list-container'>{rows}</div>", unsafe_allow_html=True)

                st.divider()
                st.markdown("<span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>MARKET INDICES</span>", unsafe_allow_html=True)
                mc1, mc2, mc3 = st.columns(3)
                for i, (k, v) in enumerate(MARKET_INDICES.items()):
                    d = market.get(k)
                    if d: [mc1, mc2, mc3][i].metric(v, f"{d['pct']:.2f}%")

            time.sleep(30)

if __name__ == "__main__":
    main()
