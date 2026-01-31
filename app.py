import streamlit as st
import json
import requests
from datetime import datetime
import pytz

# ==========================================
# 1. 核心配置区
# ==========================================
AUDIT_MEMO = {
    "摩根均衡": {"tag": "⚠️ 偏离较高", "text": "上周偏离 -0.7%，需注意误差", "color": "#FFF3CD", "text_color": "#856404"},
    "泰康新锐": {"tag": "✅ 准确率高", "text": "基本跟净值一致，可信度高", "color": "#D4EDDA", "text_color": "#155724"},
    "财通优选": {"tag": "👌 偏差可控", "text": "偏离值可接受，参考性强", "color": "#D1ECF1", "text_color": "#0C5460"}
}

st.set_page_config(page_title="Family Wealth V5.1", page_icon="📈", layout="centered")

# ==========================================
# 2. 样式设置 (单行压缩，防止乱码)
# ==========================================
st.markdown("""<style>.stApp{background:linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%)}.fund-card{background-color:rgba(255,255,255,0.85);padding:20px;border-radius:15px;box-shadow:0 4px 15px rgba(0,0,0,0.05);margin-bottom:15px;border:1px solid rgba(255,255,255,0.6)}.audit-pill{display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:500;margin-top:8px;margin-bottom:5px}h1,h2,h3,p,span,div,strong{color:#333333!important}.trend-up{color:#d9534f!important;font-weight:bold}.trend-down{color:#28a745!important;font-weight:bold}.trend-flat{color:#6c757d!important;font-weight:bold}.profit-val{font-size:1.1rem;margin-top:5px;opacity:0.9}</style>""", unsafe_allow_html=True)

# ==========================================
# 3. 工具函数
# ==========================================
def get_realtime_price(codes):
    if not codes: return {}
    try:
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        r = requests.get(url, timeout=3)
        data = {}
        if r.status_code == 200:
            for line in r.text.split(';'):
                if '="' in line:
                    c = line.split('=')[0].split('_')[-1]
                    p = line.split('="')[1].split('~')
                    if len(p)>30: data[c]={'price':float(p[3]),'pct_change':float(p[32])}
        return data
    except: return {}

def calc_est(fund, mkt):
    w_chg, w_tot = 0.0, 0.0
    fac = fund.get('factor', 1.0)
    for s in fund.get('holdings', []):
        if s['code'] in mkt:
            w_chg += mkt[s['code']]['pct_change'] * s['weight']
            w_tot += s['weight']
    
    # 返回两个值：涨跌幅(%) 和 预估收益(金额)
    est_pct = (w_chg/w_tot*fac) if w_tot>0 else 0.0
    base = fund.get('base_unit', 0)
    est_profit = base * (est_pct / 100)
    return est_pct, est_profit

# ==========================================
# 4. 核心渲染 (列表拼接法 - 包含盈亏显示)
# ==========================================
def make_html(name, est, profit, fac, base):
    # 颜色逻辑
    if est>0: cls,sg="trend-up","+"
    elif est<0: cls,sg="trend-down",""
    else: cls,sg="trend-flat",""
    
    # 审计提示
    memo = ""
    for k,v in AUDIT_MEMO.items():
        if k in name:
            memo = f"<div class='audit-pill' style='background-color:{v['color']};color:{v['text_color']};'><strong>{v['tag']}</strong> | {v['text']}</div>"
            break
            
    # 拼接 HTML (带盈亏金额)
    html = [
        "<div class='fund-card'>",
        "<div style='display:flex;justify-content:space-between;align-items:center;'>",
        f"<h3 style='margin:0;font-size:1.2rem;'>{name}</h3>",
        f"<div style='text-align:right;'>",
        f"<span class='{cls}' style='font-size:1.5rem;'>{sg}{est:.2f}%</span>",
        f"<div class='{cls} profit-val'>{sg}{profit:.2f}</div>",  # 这里加回了具体金额
        f"</div>",
        "</div>",
        memo,
        f"<div style='margin-top:10px;font-size:0.9rem;color:#666;'>系数: {fac:.2f} | 底仓: {base}</div>",
        "</div>"
    ]
    return "".join(html)

# ==========================================
# 5. 主程序
# ==========================================
def main():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    st.markdown(f"# 📈 Family Wealth V5.1")
    
    # 恢复设置面板 (Settings)
    with st.expander("⚙️ 系统设置 (Settings)"):
        st.caption(f"最后更新时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        if st.button("🔄 强制刷新数据"):
            st.rerun()
        st.info("如需修改持仓，请前往 GitHub 编辑 funds.json")

    try:
        with open('funds.json','r',encoding='utf-8') as f: funds=json.load(f)
    except: st.error("No funds.json"); return
    
    codes = {s['code'] for f in funds.values() for s in f.get('holdings',[])}
    mkt = get_realtime_price(list(codes))
    
    if not mkt: st.warning("等待开盘..."); return
    
    # 渲染卡片
    for n, f in funds.items():
        # 这里接收两个返回值：百分比 和 金额
        est_pct, est_profit = calc_est(f, mkt)
        
        # 调用生成器
        card_html = make_html(n, est_pct, est_profit, f.get('factor',1.0), f.get('base_unit',0))
        st.markdown(card_html, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
