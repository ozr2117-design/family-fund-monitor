import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from github import Github

# ==========================================
# 0. 🎯 核心配置：人工审计日志 (Audit Memo)
# ==========================================
# 既然删除了自动审计，我们保留这个静态配置，作为你的人工备注
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

# === 🎨 1. 页面配置与 CSS (回归极简 V5.5) ===
st.set_page_config(
    page_title="Family Wealth",
    page_icon="💎",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* 1. 全局极光背景 - 调淡了一点，更清爽 */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(255, 230, 240, 0.3) 0%, rgba(255, 255, 255, 0) 40%),
                    radial-gradient(circle at 90% 80%, rgba(230, 240, 255, 0.3) 0%, rgba(255, 255, 255, 0) 40%),
                    #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    
    /* 2. 隐藏无关元素 */
    [data-testid="stSidebar"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 3. 按钮样式优化 */
    div[data-testid="stPopover"] > button {
        border-radius: 20px;
        background: rgba(255,255,255,0.8);
        border: 1px solid #eee;
        box-shadow: 0 2px 8px rgba(0,0,0,0.02);
        color: #555;
    }
    
    /* 4. 大卡片 (Metric) */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.8);
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.03);
        padding: 15px;
    }
    
    /* 5. 基金折叠卡片 (Expander) */
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 4px 12px rgba(0,0,0,0.02);
        border-radius: 16px;
        background-color: rgba(255, 255, 255, 0.6);
        margin-bottom: 12px;
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 500 !important;
        color: #333 !important;
    }
    
    /* 6. 持仓列表 (iOS 风格) */
    .ios-list-container { display: flex; flex-direction: column; width: 100%; margin-top: 5px; }
    .ios-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(0,0,0,0.04); width: 100%; }
    .ios-row:last-child { border-bottom: none; }
    .ios-index { font-size: 11px; color: #ccc; width: 20px; font-weight: 600; margin-right: 4px; }
    .ios-name { font-size: 13px; color: #444; font-weight: 500; flex: 1; }
    .ios-pill { padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; min-width: 60px; text-align: center; color: white; font-family: "SF Mono", Menlo, monospace; }
    
    /* 7. 左侧详情框 */
    .detail-box { 
        background: rgba(255,255,255,0.5); 
        padding: 12px; 
        border-radius: 12px; 
        border: 1px solid rgba(0,0,0,0.03); 
    }
    
    /* 8. 信号提示条 */
    .signal-box {
        padding: 10px 14px;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 600;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
    }
    .sig-buy { background-color: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; }
    .sig-sell { background-color: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; }

    /* 9. 审计标签 (简化版) */
    .audit-tag {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 11px;
        margin-bottom: 10px;
        font-weight: 500;
    }
    </style>
""", unsafe_allow_html=True)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

# === 🛠️ 辅助逻辑 ===
def get_benchmark_code(fund_name):
    if "周期" in fund_name or "均衡" in fund_name or "红利" in fund_name: return 'sh000001', '上证'
    elif "成长" in fund_name or "AI" in fund_name or "优选" in fund_name: return 'sz399006', '创指'
    else: return 'sh000001', '上证'

# === 🛠️ GitHub 操作 ===
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

# === 🕷️ 极速数据获取 (只用腾讯) ===
def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    # 腾讯接口响应极快，且不需要复杂Header
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=2) # 2秒超时，不等待
        price_data = {}
        parts = r.text.split(';')
        for part in parts:
            if '="' in part:
                try:
                    code = part.split('=')[0].split('_')[-1]
                    data = part.split('="')[1].strip('"').split('~')
                    if len(data) > 30:
                        name = data[1].replace(" ", "")
                        
                        # 🛡️ 熔断机制：防止解析错误
                        try:
                            # 优先取腾讯预计算涨跌幅 (Index 32)
                            pct = float(data[32]) if len(data) > 32 and data[32] != '' else 0.0
                            if pct == 0.0: # 降级计算
                                current = float(data[3])
                                close = float(data[4])
                                if close > 0: pct = ((current - close) / close) * 100
                        except: pct = 0.0
                        
                        # 🛡️ 异常值过滤：涨跌超过 40% 视为数据错误
                        if abs(pct) > 40: pct = 0.0
                            
                        price_data[code] = {'name': name, 'change': pct}
                except: continue
        return price_data
    except: return None

# === 🚀 主程序 ===
def main():
    funds_config, config_sha = load_json('funds.json')
    if not funds_config: st.stop()

    # 顶部状态
    bj_time = datetime.utcnow() + timedelta(hours=8)
    greeting = "Market Closed 🌙" if bj_time.hour >= 15 or bj_time.hour < 9 else "Trading Now ⚡"
    
    c1, c2 = st.columns([3, 1])
    with c1:
        st.caption(f"{greeting} | {bj_time.strftime('%H:%M:%S')}")
        st.markdown("<h2 style='margin-top:-10px; color:#333; font-weight:300'>Family Wealth</h2>", unsafe_allow_html=True)

    zen_mode = False
    with c2:
        with st.popover("⚙️ 设置", use_container_width=True):
            zen_mode = st.toggle("🧘 禅模式", value=False)
            
            st.divider()
            # 简化的持仓修改入口
            with st.expander("💰 修改持仓金额"):
                with st.form("h_form"):
                    new_h = {}
                    for n, i in funds_config.items():
                        new_h[n] = st.number_input(n.split('(')[0], value=float(i.get('holding_value', 0)))
                    if st.form_submit_button("保存"):
                        for n in funds_config: funds_config[n]['holding_value'] = new_h[n]
                        save_json('funds.json', funds_config, config_sha, "Update Holdings")
                        st.toast("保存成功"); time.sleep(1); st.rerun()

    # 主循环
    placeholder = st.empty()
    all_codes = list(MARKET_INDICES.keys())
    for f in funds_config.values():
        for s in f['holdings']: all_codes.append(s['code'])
    all_codes = list(set(all_codes))
    
    while True:
        with placeholder.container():
            market = get_realtime_price(all_codes)
            if not market:
                st.info("⌛ 连接数据源中...")
                time.sleep(1)
                continue
            
            total_p = 0; total_base = 0; cards = []; msg = None
            
            for name, info in funds_config.items():
                val=0; w=0; stocks=[]
                for s in info['holdings']:
                    d = market.get(s['code'])
                    if d:
                        val += d['change']*s['weight']; w+=s['weight']
                        if len(stocks)<3: stocks.append(d)
                
                est = (val/w * info.get('factor', 1.0)) if w>0 else 0
                profit = info.get('holding_value', 0) * est / 100
                total_p += profit; total_base += info.get('holding_value', 0)
                
                # 信号判断
                bench_c, bench_n = get_benchmark_code(name)
                bench_v = market.get(bench_c, {}).get('change', 0)
                
                sig_type = None; sig_txt = ""; sig_act = ""
                base_u = info.get('base_unit', 1000)
                
                if est < -2.5 and est < bench_v:
                    sig_type = "BUY"; sig_txt = f"跑输{bench_n} {abs(est-bench_v):.1f}%"
                    sig_act = f"建议加仓 ¥{base_u * (2 if est<-4 else 1):,}"
                    if not msg: msg = "🎯 出现加仓机会"
                elif est > 3.0 and est > (bench_v + 1.5):
                    sig_type = "SELL"; sig_txt = f"跑赢{bench_n} {abs(est-bench_v):.1f}%"
                    sig_act = "建议卖出 1/4"
                    if not msg: msg = "🔥 出现止盈机会"
                
                cards.append({
                    "name": name.split('(')[0], "full": name, "est": est,
                    "profit": profit, "base": info.get('holding_value', 0),
                    "stocks": stocks, "sig": sig_type, "txt": sig_txt, "act": sig_act
                })
            
            if msg: st.toast(msg)
            
            # 1. 顶部总览
            st.markdown("<br>", unsafe_allow_html=True)
            c1, c2 = st.columns([2, 1])
            p_show = "****" if zen_mode else f"{total_p:+.2f}"
            c1.metric("今日预估收益", p_show, delta=None if zen_mode else f"{total_p:+.2f}")
            
            rate = (total_p/total_base*100) if total_base>0 else 0
            c2.metric("收益率", f"{rate:+.2f}%")
            
            # 2. 列表区
            st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
            
            for c in cards:
                icon = "🔥" if c['sig']=="SELL" else ("🎯" if c['sig']=="BUY" else "💰")
                title = f"{icon} {c['name']} {c['est']:+.2f}%"
                
                with st.expander(title):
                    # 静态审计标签 (不影响布局)
                    for k, v in AUDIT_MEMO.items():
                        if k in c['full']:
                            st.markdown(f"<span class='audit-tag' style='background:{v['color']}; color:{v['text_color']}'>{v['tag']} | {v['text']}</span>", unsafe_allow_html=True)
                            break
                    
                    # 信号条
                    if c['sig']:
                        cls = "sig-buy" if c['sig']=="BUY" else "sig-sell"
                        icon_s = "🎯" if c['sig']=="BUY" else "🔥"
                        st.markdown(f"<div class='signal-box {cls}'><div>{icon_s} {c['txt']}<br><span style='opacity:0.8; font-weight:400'>👉 {c['act']}</span></div></div>", unsafe_allow_html=True)
                    
                    # 数据详情
                    kc1, kc2 = st.columns([1.2, 2])
                    
                    # 左侧：金额
                    col_p = "#ff4d4f" if c['profit']>0 else "#27c24c"
                    p_s = "<span style='color:#ccc'>****</span>" if zen_mode else f"¥{c['profit']:+.1f}"
                    b_s = "****" if zen_mode else f"¥{c['base']:,}"
                    
                    kc1.markdown(f"""
                    <div class='detail-box'>
                        <div style='font-size:12px; color:#999'>今日盈亏</div>
                        <div style='font-size:22px; font-weight:600; color:{col_p}; font-family:-apple-system'>{p_s}</div>
                        <div style='height:10px'></div>
                        <div style='font-size:12px; color:#999'>本金</div>
                        <div style='font-size:15px; color:#333; font-weight:500'>{b_s}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 右侧：股票 (iOS 风格)
                    rows = ""
                    for i, s in enumerate(c['stocks']):
                        bg = "#ff4d4f" if s['change']>0 else "#27c24c"
                        rows += f"<div class='ios-row'><div class='ios-index'>{i+1}</div><div class='ios-name'>{s['name']}</div><div class='ios-pill' style='background:{bg}'>{s['change']:+.2f}%</div></div>"
                    kc2.markdown(f"<div class='ios-list-container'>{rows}</div>", unsafe_allow_html=True)

            # 3. 底部行情
            st.divider()
            cols = st.columns(3)
            for i, (k, v) in enumerate(MARKET_INDICES.items()):
                d = market.get(k)
                if d: cols[i].metric(v, f"{d['change']:+.2f}%")
            
            time.sleep(15) # 刷新间隔改为15秒，更从容

if __name__ == "__main__":
    main()
