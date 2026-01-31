import streamlit as st
import requests
import time
import json
import pandas as pd
import re
from datetime import datetime, timedelta
from github import Github

# === 🎨 1. 页面配置与 CSS 魔法 (Apple Glassmorphism V5.2) ===
st.set_page_config(
    page_title="Family Wealth V5.2",
    page_icon="💎",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 注入 CSS
st.markdown("""
    <style>
    /* 全局极光背景 */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgba(255, 230, 240, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    radial-gradient(circle at 90% 80%, rgba(230, 240, 255, 0.4) 0%, rgba(255, 255, 255, 0) 40%),
                    #fdfdfd;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    [data-testid="stSidebar"] {display: none;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 详情卡片美化 */
    .detail-box { background: rgba(255,255,255,0.6); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.4); }
    
    /* 信号提示 */
    .signal-buy { background-color: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 10px; }
    .signal-sell { background-color: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 10px; }
    
    /* 列表样式 */
    .ios-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .ios-pill { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; color: white; min-width: 60px; text-align: center;}
    </style>
""", unsafe_allow_html=True)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技',
    'usNDX': '纳斯达克'
}

# 基金名称到代码的映射（用于抓取东财估值）
# 请确保这里面的名称和你 funds.json 里的名称一致（前缀匹配即可）
FUND_CODES_MAP = {
    '摩根均衡': '009968',
    '泰康新锐': '009340',
    '财通优选': '009354',
    '红利低波': '512890' 
}

# === 🛠️ GitHub 与 数据获取 ===

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

# 1. 腾讯实时行情 (自算基础)
def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=3)
        price_data = {}
        parts = r.text.split(';')
        for part in parts:
            if '="' in part:
                try:
                    code = part.split('=')[0].split('_')[-1]
                    data = part.split('="')[1].split('~')
                    name = data[1].replace(" ", "")
                    close = float(data[4])
                    if close > 0:
                        pct = ((float(data[3]) - close) / close) * 100
                        price_data[code] = {'name': name, 'change': pct}
                except: continue
        return price_data
    except: return None

# 2. 东财实时估值 (参考系)
def get_eastmoney_valuation(fund_code):
    if not fund_code: return None
    timestamp = int(time.time() * 1000)
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js?rt={timestamp}"
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            match = re.search(r'jsonpgz\((.*?)\);', r.text)
            if match:
                data = json.loads(match.group(1))
                return float(data['gszzl'])
    except: return None
    return None

def get_benchmark_code(fund_name):
    if "纳斯达克" in fund_name or "QDII" in fund_name: return 'usNDX', '纳指'
    if "红利" in fund_name: return 'sh000001', '上证'
    if "周期" in fund_name or "均衡" in fund_name: return 'sh000001', '上证'
    return 'sz399006', '创指'

# === 🚀 主程序 ===
def main():
    funds_config, config_sha = load_json('funds.json')
    if not funds_config: st.warning("请先配置 funds.json"); st.stop()

    # 顶部状态栏
    bj_time = datetime.utcnow() + timedelta(hours=8)
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.caption(f"Last Updated: {bj_time.strftime('%H:%M:%S')}")
        st.markdown("<h3 style='margin:0'>Family Wealth V5.2</h3>", unsafe_allow_html=True)

    # 设置菜单
    zen_mode = False
    with col_t2:
        with st.popover("⚙️", use_container_width=True):
            st.caption("Mode")
            zen_mode = st.toggle("🧘 禅模式", value=False)
            st.caption("Actions")
            if st.button("更新持仓配置"):
                st.toast("请直接修改 GitHub 文件")

    # 获取行情
    all_codes = list(MARKET_INDICES.keys())
    for f in funds_config.values():
        for s in f['holdings']: all_codes.append(s['code'])
    
    market_data = get_realtime_price(list(set(all_codes)))
    if not market_data: st.error("行情接口连接失败"); st.stop()

    # 计算与展示
    total_profit = 0
    total_principal = 0
    
    # 遍历计算
    cards = []
    for name, info in funds_config.items():
        # 自算估值
        val = 0; w = 0; stocks = []
        for s in info['holdings']:
            d = market_data.get(s['code'])
            if d:
                val += d['change'] * s['weight']; w += s['weight']
                if len(stocks) < 3: stocks.append(d)
        
        my_est = (val / w * info.get('factor', 1.0)) if w > 0 else 0
        
        # 基础数据
        principal = info.get('holding_value', 0)
        profit = principal * my_est / 100
        total_profit += profit; total_principal += principal
        
        # 信号逻辑
        bench_code, bench_name = get_benchmark_code(name)
        bench_val = market_data.get(bench_code, {}).get('change', 0)
        
        signal = None
        if my_est < -2.5 and my_est < bench_val:
            signal = {"type": "BUY", "msg": f"跑输{bench_name} {abs(my_est-bench_val):.1f}%"}
        elif my_est > 3.0 and my_est > (bench_val + 1.5):
            signal = {"type": "SELL", "msg": f"跑赢{bench_name} {abs(my_est-bench_val):.1f}%"}
            
        cards.append({
            "name": name, "est": my_est, "profit": profit, 
            "principal": principal, "stocks": stocks, "signal": signal
        })

    # 1. 顶部总览
    m1, m2 = st.columns([1.5, 1])
    if zen_mode:
        m1.metric("今日预估盈亏", "****")
    else:
        m1.metric("今日预估盈亏", f"{total_profit:+.2f}", f"{total_profit:+.2f} 元")
    
    rate = (total_profit/total_principal*100) if total_principal>0 else 0
    m2.metric("整体收益率", f"{rate:+.2f}%")

    st.divider()

    # 2. 持仓卡片
    for c in cards:
        # 标题处理
        icon = "🔥" if c['signal'] and c['signal']['type']=="SELL" else ("🎯" if c['signal'] and c['signal']['type']=="BUY" else "💰")
        title = f"{icon} {c['name'].split('(')[0]} {c['est']:+.2f}%"
        
        with st.expander(title):
            # 信号提示
            if c['signal']:
                cls = "signal-buy" if c['signal']['type']=="BUY" else "signal-sell"
                st.markdown(f"<div class='{cls}'>{c['signal']['type']} | {c['signal']['msg']}</div>", unsafe_allow_html=True)
            
            # 🔥 双重估值校验
            # 尝试匹配东财代码
            ref_est = None
            for key, code in FUND_CODES_MAP.items():
                if key in c['name']:
                    ref_est = get_eastmoney_valuation(code)
                    break
            
            c1, c2 = st.columns([1.2, 2])
            
            # 左侧：数据区
            p_str = "****" if zen_mode else f"¥{c['profit']:+.1f}"
            
            est_html = f"""
            <div class='detail-box'>
                <div style='color:#888; font-size:12px'>今日盈亏</div>
                <div style='font-size:20px; font-weight:bold; color:{'#ff3b30' if c['profit']>0 else '#34c759'}'>{p_str}</div>
                <div style='margin: 8px 0; border-bottom:1px dashed #ddd'></div>
                <div style='display:flex; justify-content:space-between'>
                    <div><span style='color:#999; font-size:11px'>我的模型</span><br><b>{c['est']:+.2f}%</b></div>
                    <div style='text-align:right'><span style='color:#999; font-size:11px'>东财估值</span><br><span style='color:#666'>{f'{ref_est:+.2f}%' if ref_est is not None else '--'}</span></div>
                </div>
            </div>
            """
            c1.markdown(est_html, unsafe_allow_html=True)
            
            # 右侧：持仓前三
            rows = ""
            for s in c['stocks']:
                bg = "#ff3b30" if s['change']>0 else "#34c759"
                rows += f"<div class='ios-row'><span>{s['name']}</span><span class='ios-pill' style='background:{bg}'>{s['change']:+.2f}%</span></div>"
            c2.markdown(f"<div>{rows}</div>", unsafe_allow_html=True)

    # 3. 底部大盘
    st.markdown("<br><div style='color:#ccc; font-size:12px; text-align:center'>MARKET OVERVIEW</div>", unsafe_allow_html=True)
    cols = st.columns(len(MARKET_INDICES))
    for i, (code, name) in enumerate(MARKET_INDICES.items()):
        d = market_data.get(code)
        if d: cols[i].metric(name, f"{d['change']:+.2f}%")

    time.sleep(30)
    st.rerun()

if __name__ == "__main__":
    main()
