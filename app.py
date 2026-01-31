import streamlit as st
import json
import requests
from datetime import datetime
import pytz

# ==========================================
# 1. 核心配置与人工审计日志
# ==========================================
AUDIT_MEMO = {
    "摩根均衡": {
        "tag": "⚠️ 偏离较高", 
        "text": "上周偏离 -0.7%，需注意误差", 
        "color": "#FFF3CD", 
        "text_color": "#856404"
    },
    "泰康新锐": {
        "tag": "✅ 准确率高", 
        "text": "基本跟净值一致，可信度高", 
        "color": "#D4EDDA", 
        "text_color": "#155724"
    },
    "财通优选": {
        "tag": "👌 偏差可控", 
        "text": "偏离值可接受，参考性强", 
        "color": "#D1ECF1", 
        "text_color": "#0C5460"
    }
}

st.set_page_config(page_title="Family Wealth V5.1", page_icon="📈", layout="centered")

# ==========================================
# 2. 极光样式 CSS (强制日间模式)
# ==========================================
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    .fund-card {
        background-color: rgba(255, 255, 255, 0.85);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-bottom: 15px;
        border: 1px solid rgba(255,255,255,0.6);
    }
    .audit-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 500;
        margin-top: 8px;
        margin-bottom: 5px;
    }
    h1, h2, h3, p, span, div, strong {
        color: #333333 !important;
    }
    .trend-up { color: #d9534f !important; font-weight: bold; }
    .trend-down { color: #28a745 !important; font-weight: bold; }
    .trend-flat { color: #6c757d !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 数据获取函数
# ==========================================
def get_realtime_price(stock_codes):
    if not stock_codes:
        return {}
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code != 200: return {}
        data_map = {}
        lines = r.text.split(';')
        for line in lines:
            if '="' in line:
                code = line.split('=')[0].split('_')[-1]
                params = line.split('="')[1].split('~')
                if len(params) > 30:
                    data_map[code] = {
                        'price': float(params[3]),
                        'last_close': float(params[4]),
                        'pct_change': float(params[32])
                    }
        return data_map
    except Exception as e:
        st.error(f"数据源错误: {e}")
        return {}

def calculate_fund_estimate(fund_info, market_data):
    total_weighted_change = 0.0
    total_weight = 0.0
    holdings = fund_info.get('holdings', [])
    factor = fund_info.get('factor', 1.0)
    
    for stock in holdings:
        code = stock['code']
        weight = stock['weight']
        if code in market_data:
            change = market_data[code]['pct_change']
            total_weighted_change += change * weight
            total_weight += weight
            
    if total_weight > 0:
        return (total_weighted_change / total_weight) * factor
    return 0.0

# ==========================================
# 4. 主程序逻辑
# ==========================================
def main():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    st.markdown(f"# 📈 Family Wealth V5.1")
    st.caption(f"最后更新: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        with open('funds.json', 'r', encoding='utf-8') as f:
            funds_config = json.load(f)
    except FileNotFoundError:
        st.error("找不到 funds.json")
        return

    all_stocks = set()
    for fund in funds_config.values():
        for stock in fund.get('holdings', []):
            all_stocks.add(stock['code'])
            
    market_data = get_realtime_price(list(all_stocks))
    if not market_data:
        st.warning("等待开盘...")
        return

    for fund_name, fund_info in funds_config.items():
        est_change = calculate_fund_estimate(fund_info, market_data)
        
        # 颜色判断
        if est_change > 0:
            color_class = "trend-up"
            sign = "+"
        elif est_change < 0:
            color_class = "trend-down"
            sign = ""
        else:
            color_class = "trend-flat"
            sign = ""
            
        # 生成审计提示 HTML (单行模式，防止缩进错误)
        audit_html = ""
        for key, memo in AUDIT_MEMO.items():
            if key in fund_name:
                audit_html = f'<div class="audit-pill" style="background-color: {memo["color"]}; color: {memo["text_color"]};"><strong>{memo["tag"]}</strong> | {memo["text"]}</div>'
                break
        
        # ⚠️ 核心修复：构建无缩进的 HTML 字符串
        # 我们先把变量准备好，然后用最简单的 f-string 拼接，避免 st.markdown 识别缩进
        card_html = f"""
<div class="fund-card">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h3 style="margin:0; font-size:1.2rem;">{fund_name}</h3>
        <span class="{color_class}" style="font-size:1.5rem;">{sign}{est_change:.2f}%</span>
    </div>
    {audit_html}
    <div style="margin-top:10px; font-size:0.9rem; color:#666;">
        系数: {fund_info.get('factor', 1.0):.2f} | 
        底仓: {fund_info.get('base_unit', 0)}
    </div>
</div>
"""
        st.markdown(card_html, unsafe_allow_html=True)
        
    if st.button('🔄 刷新数据'):
        st.rerun()

if __name__ == "__main__":
    main()
