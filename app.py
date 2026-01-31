import streamlit as st
import requests
import time
import json
import pandas as pd
import random
from datetime import datetime, timedelta
from github import Github

# ==========================================
# 0. 🎯 核心配置：人工审计日志 (Audit Memo)
# ==========================================
AUDIT_MEMO = {
    "摩根均衡": {
        "tag": "⚠️ 偏离较高", "text": "上周偏离 -0.7%，需注意误差", 
        "color": "#FFF3CD", "text_color": "#856404"
    },
    "泰康新锐": {
        "tag": "✅ 准确率高", "text": "基本跟净值一致，可信度高", 
        "color": "#D4EDDA", "text_color": "#155724"
    },
    "财通优选": {
        "tag": "👌 偏差可控", "text": "偏离值可接受，参考性强", 
        "color": "#D1ECF1", "text_color": "#0C5460"
    }
}

# === 🎨 1. 页面配置与 CSS 魔法 (V5.4 Stable) ===
st.set_page_config(
    page_title="Family Wealth",
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
    [data-testid="stSidebarCollapsedControl"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 按钮样式 */
    div[data-testid="stPopover"] > button {
        border-radius: 20px;
        background-color: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.6);
        box-shadow: 0 2px 10px rgba(0,0,0,0.03);
    }
    
    /* 大卡片 */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.65);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.6);
        border-radius: 20px;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.05);
    }
    
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 8px 24px rgba(0,0,0,0.03);
        border-radius: 16px;
        background-color: rgba(255, 255, 255, 0.5);
        backdrop-filter: blur(10px);
        margin-bottom: 15px;
        overflow: hidden;
    }
    
    .ios-list-container { display: flex; flex-direction: column; width: 100%; }
    .ios-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid rgba(0,0,0,0.06); width: 100%; }
    .ios-row:last-child { border-bottom: none; }
    .ios-index { font-size: 12px; color: #aaa; width: 24px; font-weight: 600; margin-right: 8px; }
    .ios-name { font-size: 14px; color: #333; font-weight: 500; flex: 1; margin-right: 10px; }
    .ios-pill { padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; min-width: 65px; text-align: right; color: white; font-family: -apple-system; }
    .detail-box { background: rgba(255,255,255,0.6); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.4); }
    
    .signal-buy { background-color: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 15px; display: flex; align-items: center; }
    .signal-sell { background-color: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 15px; display: flex; align-items: center; }

    .audit-pill { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; margin-bottom: 12px; font-family: -apple-system; }
    
    .trend-pill { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; margin-right: 6px; margin-top: 6px; font-family: -apple-system; }
    .trend-up { background-color: #fff1f0; color: #cf1322; border: 1px solid #ffa39e; }
    .trend-down { background-color: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
    .trend-stats { background-color: #f5f5f7; color: #666; border: 1px solid #e1e1e6; }
    .trend-wait { background-color: #f0f0f0; color: #999; border: 1px dashed #ccc; }
    </style>
""", unsafe_allow_html=True)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

# 用于历史数据抓取的映射表 (请确保这些名字能匹配 funds.json 中的名字)
FUND_CODES_MAP = {
    '摩根均衡': '009968',
    '泰康新锐': '009340',
    '财通优选': '009354',
    '红利低波': '512890'
}

# === 🛠️ 辅助逻辑 ===
def get_benchmark_code(fund_name):
    if "周期" in fund_name or "均衡" in fund_name or "红利" in fund_name: return 'sh000001', '上证'
    elif "成长" in fund_name or "AI" in fund_name or "优选" in fund_name: return 'sz399006', '创指'
    else: return 'sh000001', '上证'

# === 🛠️ GitHub 数据库操作 ===
def get_repo():
    try:
        token = st.secrets["github_token"]
        username = st.secrets["github_username"]
        repo_name = st.secrets["repo_name"]
        g = Github(token)
        return g.get_user(username).get_repo(repo_name)
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

# === 🕷️ 数据获取 (熔断增强版) ===

# 1. 实时行情 (腾讯)
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
                    data = part.split('="')[1].split('~')
                    if len(data) > 30:
                        name = data[1].replace(" ", "")
                        
                        # 🔥 熔断机制：安全解析
                        try:
                            # 尝试获取涨跌幅 (Index 30 是腾讯预计算好的涨跌幅，更准)
                            pct = float(data[32]) if len(data) > 32 and data[32] != '' else 0.0
                            # 如果 Index 32 没数据，退化到手动计算
                            if pct == 0.0:
                                current = float(data[3])
                                close = float(data[4])
                                if close > 0: pct = ((current - close) / close) * 100
                        except:
                            pct = 0.0

                        # 🔥 熔断检查：如果涨跌幅绝对值超过 50%，视为数据异常（防止读取到日期 20260130 导致页面炸裂）
                        if abs(pct) > 50:
                            pct = 0.0
                            
                        price_data[code] = {'name': name, 'change': pct}
                except: continue
        return price_data
    except: return None

# 2. 基金历史净值 (双引擎: 腾讯 -> 东财)
def get_fund_history(fund_code, limit=30):
    if not fund_code: return []
    
    # Plan A: 腾讯接口
    url_tencent = f"http://web.ifzq.gtimg.cn/appstock/app/fund/nav/get?code=jj{fund_code}"
    try:
        r = requests.get(url_tencent, timeout=2)
        if r.status_code == 200:
            res = r.json()
            key = f"jj{fund_code}"
            if "data" in res and key in res["data"]:
                data_list = res["data"][key]["data"]
                history = []
                for item in reversed(data_list):
                    if len(history) >= limit: break
                    history.append(float(item[2]))
                if history: return history
    except: pass

    # Plan B: 东财接口 (备份)
    url_east = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize={limit}"
    headers = {
        "Referer": "http://fund.eastmoney.com/", 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url_east, headers=headers, timeout=3)
        if r.status_code == 200:
            res = r.json()
            if "Data" in res and "LSJZList" in res["Data"]:
                history = []
                for item in res["Data"]["LSJZList"]:
                    val = item.get("JZZZL", "0")
                    if val: history.append(float(val))
                return history
    except: pass
    
    return []

# 3. 趋势计算
def calculate_trend(current_est, history_data):
    if not history_data: return 0, "等待数据..."
    full_timeline = [current_est] + history_data
    consecutive = 0
    direction = 1 if full_timeline[0] > 0 else (-1 if full_timeline[0] < 0 else 0)
    
    if direction != 0:
        for val in full_timeline:
            if (direction == 1 and val > 0) or (direction == -1 and val < 0):
                consecutive += 1
            else: break
            
    red_days = sum(1 for x in full_timeline[:30] if x > 0)
    green_days = sum(1 for x in full_timeline[:30] if x < 0)
    return (consecutive * direction), f"{red_days}红 / {green_days}绿"

# 4. 官方净值获取
def get_official_nav(fund_code):
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=1"
    headers = {"Referer": "http://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200 and "Data" in r.json():
            data = r.json()["Data"]["LSJZList"][0]
            return float(data["JZZZL"]), data["FSRQ"]
    except: pass
    return None, None

# === 🚀 主程序 ===
def main():
    funds_config, config_sha = load_json('funds.json')
    if not funds_config: st.stop()

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
            st.caption("Views")
            mode = st.radio("Nav", ["📡  实时看板", "💰  持仓管理"], label_visibility="collapsed", key="nav")
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            st.caption("Actions")
            action_mode = st.radio("Tools", ["💾  收盘存证", "⚖️  晚间审计"], label_visibility="collapsed", index=None, key="act")

            current_selection = action_mode if action_mode else mode
            if current_selection == "💰  持仓管理":
                st.divider()
                st.info("Manage Holdings")
                with st.form("holding_form"):
                    new_h, new_b = {}, {}
                    for name, info in funds_config.items():
                        st.markdown(f"**{name.split('(')[0]}**")
                        c1, c2 = st.columns(2)
                        new_h[name] = c1.number_input(f"持仓", value=float(info.get('holding_value', 0)), step=100.0, key=f"h_{name}")
                        new_b[name] = c2.number_input(f"加仓", value=float(info.get('base_unit', 1000)), step=100.0, key=f"b_{name}")
                    if st.form_submit_button("Save"):
                        for n in funds_config:
                            funds_config[n]['holding_value'] = new_h[n]
                            funds_config[n]['base_unit'] = new_b[n]
                        save_json('funds.json', funds_config, config_sha, "Update")
                        st.toast("Saved!"); time.sleep(1); st.rerun()

            elif current_selection == "💾  收盘存证":
                st.divider()
                if st.button("Run Snapshot", type="primary", use_container_width=True):
                    with st.spinner("Saving..."):
                        codes = []
                        for f in funds_config.values(): 
                            for s in f['holdings']: codes.append(s['code'])
                        prices = get_realtime_price(list(set(codes)))
                        if prices:
                            today = bj_time.strftime("%Y-%m-%d")
                            snap = {}
                            for n, i in funds_config.items():
                                val=0; w=0
                                for s in i['holdings']:
                                    if s['code'] in prices:
                                        val += prices[s['code']]['change']*s['weight']; w+=s['weight']
                                snap[n] = val/w if w>0 else 0
                            hist, hsha = load_json('history.json')
                            hist[today] = snap
                            save_json('history.json', hist, hsha, f"Snap {today}")
                            st.success(f"Saved: {today}")

            elif current_selection == "⚖️  晚间审计":
                st.divider()
                if st.button("Start Audit", type="primary", use_container_width=True):
                    hist, _ = load_json('history.json')
                    fhist, _ = load_json('factor_history.json')
                    if hist:
                        last = sorted(hist.keys())[-1]
                        audited = fhist.get(last, {}) if fhist else {}
                        need_save = False; cur_succ = {}
                        bar = st.progress(0)
                        for idx, (n, i) in enumerate(funds_config.items()):
                            if n in audited: bar.progress((idx+1)/len(funds_config)); continue
                            raw = hist[last].get(n)
                            code = FUND_CODES_MAP.get(n.split('(')[0]) # 简化匹配
                            if raw and code:
                                off, date = get_official_nav(code)
                                if date and date >= last and raw != 0:
                                    new_f = (i['factor']*0.8) + ((off/raw)*0.2)
                                    funds_config[n]['factor'] = round(new_f, 4)
                                    cur_succ[n] = round(new_f, 4)
                                    need_save = True
                            bar.progress((idx+1)/len(funds_config))
                        if need_save:
                            save_json('funds.json', funds_config, config_sha, "Audit")
                            save_factor_history(last, cur_succ)
                            st.success("Optimized!"); time.sleep(1); st.rerun()
                        else: st.info("No updates")

    if "持仓管理" not in str(mode) and "持仓管理" not in str(action_mode):
        placeholder = st.empty()
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        
        while True:
            with placeholder.container():
                market = get_realtime_price(list(set(all_codes)))
                if not market: st.warning("Connecting..."); time.sleep(2); continue
                
                total_p = 0; total_base = 0; cards = []; msg = None
                
                for name, info in funds_config.items():
                    val=0; w=0; stocks=[]
                    for s in info['holdings']:
                        d = market.get(s['code'])
                        if d:
                            val += d['change']*s['weight']; w += s['weight']
                            # 🔥 修复KeyError: 统一写入 pct
                            if len(stocks)<3: stocks.append({"name": d['name'], "pct": d['change']})
                    
                    est = (val/w * info.get('factor', 1.0)) if w>0 else 0
                    profit = info.get('holding_value', 0) * est / 100
                    total_p += profit; total_base += info.get('holding_value', 0)

                    # 趋势计算
                    short_name = name.split('(')[0]
                    f_code = None
                    for k_map, v_map in FUND_CODES_MAP.items():
                        if k_map in short_name or short_name in k_map:
                            f_code = v_map
                            break
                    hist_data = get_fund_history(f_code)
                    consecutive, trend_ratio = calculate_trend(est, hist_data)

                    # 信号逻辑
                    bench_code, bench_name = get_benchmark_code(name)
                    bench_val = market.get(bench_code, {}).get('change', 0)
                    sig_type = None; sig_desc = ""; act_adv = ""
                    base_u = info.get('base_unit', 1000)

                    if est < -2.5 and est < bench_val:
                        sig_type = "BUY"
                        mult = 2 if est < -4.0 else 1
                        sig_desc = f"超跌错杀：跑输{bench_name} {abs(est-bench_val):.1f}%"
                        act_adv = f"建议加仓: +¥{base_u*mult:,}"
                        if not msg: msg = "🎯 加仓机会"
                    elif est > 3.0 and est > (bench_val + 1.5):
                        sig_type = "SELL"
                        sig_desc = f"短期过热：跑赢{bench_name} {abs(est-bench_val):.1f}%"
                        act_adv = "建议卖出: 1/4 持仓"
                        if not msg: msg = "🔥 止盈机会"

                    cards.append({
                        "name": short_name, "full_name": name,
                        "est": est, "profit": profit, "principal": info.get('holding_value', 0),
                        "stocks": stocks, "sig_type": sig_type, "sig_desc": sig_desc, "act_adv": act_adv,
                        "consecutive": consecutive, "trend_ratio": trend_ratio
                    })
                
                if msg: st.toast(msg)

                st.markdown("<br>", unsafe_allow_html=True)
                c1, c2 = st.columns([1.8, 1])
                p_disp = "****" if zen_mode else f"{total_p:+.2f}"
                c1.metric("今日家庭收益 (元)", p_disp, delta=None if zen_mode else f"{total_p:+.2f}")
                rate = (total_p/total_base*100) if total_base>0 else 0
                c2.metric("收益率", f"{rate:+.2f}%")

                st.markdown("<div style='margin-bottom: 12px;'></div><span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>PORTFOLIO</span>", unsafe_allow_html=True)

                for card in cards:
                    icon = "👑" if card['est']>0 else "📿"
                    suffix = f" {card['est']:+.2f}%"
                    if card['sig_type']=="BUY": suffix += " 🎯 机会"
                    elif card['sig_type']=="SELL": suffix += " 🔥 止盈"
                    
                    with st.expander(f"{icon} {card['name']}{suffix}"):
                        for k, v in AUDIT_MEMO.items():
                            if k in card['full_name']:
                                st.markdown(f"<div class='audit-pill' style='background-color:{v['color']}; color:{v['text_color']};'><strong>{v['tag']}</strong> | {v['text']}</div>", unsafe_allow_html=True)
                                break
                        
                        if card['sig_type']:
                            cls = "signal-buy" if card['sig_type']=="BUY" else "signal-sell"
                            icon_s = "🎯" if card['sig_type']=="BUY" else "🔥"
                            st.markdown(f"<div class='{cls}'><div><div>{icon_s} {card['sig_desc']}</div><div style='font-size:15px; margin-top:4px'>👉 {card['act_adv']}</div></div></div>", unsafe_allow_html=True)

                        kc1, kc2 = st.columns([1.1, 2])
                        col_c = "#ff3b30" if card['profit']>0 else "#34c759"
                        prof_s = "<span style='color:#aaa'>****</span>" if zen_mode else f"￥{card['profit']:+.1f}"
                        prin_s = "****" if zen_mode else f"￥{card['principal']:,}"

                        cons = card['consecutive']
                        if "等待" in card['trend_ratio']: tr_html = "<span class='trend-pill trend-wait'>⏳ 暂无历史</span>"
                        elif cons > 0: tr_html = f"<span class='trend-pill trend-up'>🔥 {cons}连涨</span>"
                        elif cons < 0: tr_html = f"<span class='trend-pill trend-down'>❄️ {abs(cons)}连跌</span>"
                        else: tr_html = "<span class='trend-pill trend-wait'>〰️ 0连涨</span>"
                        st_html = f"<span class='trend-pill trend-stats'>近30天: {card['trend_ratio']}</span>"

                        kc1.markdown(f"""
                        <div class='detail-box'>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>今日盈亏</div>
                            <div style='font-size:20px; font-weight:600; color:{col_c}; font-family:-apple-system'>{prof_s}</div>
                            <div style='height:15px'></div>
                            <div style='font-size:12px; color:#888; margin-bottom:2px'>本金</div>
                            <div style='font-size:16px; color:#333; font-weight:500'>{prin_s}</div>
                            <div style='margin-top:8px'>{tr_html}{st_html}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        rows = ""
                        for i, s in enumerate(card['stocks']):
                            # 🔥 修复KeyError: 读取 pct
                            pct = s.get('pct', 0.0)
                            bg = "#ff3b30" if pct>0 else ("#34c759" if pct<0 else "#8e8e93")
                            rows += f"<div class='ios-row'><div class='ios-index'>{i+1}</div><div class='ios-name'>{s['name']}</div><div class='ios-pill' style='background-color:{bg}'>{pct:+.2f}%</div></div>"
                        kc2.markdown(f"<div class='ios-list-container'>{rows}</div>", unsafe_allow_html=True)

                st.divider()
                st.markdown("<span style='color:#999; font-size:12px; letter-spacing:1px; margin-left:2px; font-weight:500'>MARKET INDICES</span>", unsafe_allow_html=True)
                mc1, mc2, mc3 = st.columns(3)
                for i, (k, v) in enumerate(MARKET_INDICES.items()):
                    d = market.get(k)
                    if d: [mc1, mc2, mc3][i].metric(v, f"{d['change']:.2f}%")

            time.sleep(30)

if __name__ == "__main__":
    main()
