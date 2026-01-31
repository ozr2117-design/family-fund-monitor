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
# 2. 样式设置 (CSS)
# ==========================================
# 为了防止缩进问题，这里也采用紧凑写法
st.markdown("""<style>.stApp {background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);}.fund-card {background-color: rgba(255, 255, 255, 0.85);padding: 20px;border-radius: 15px;box-shadow: 0 4px 15px rgba(0,0,0,0.05);margin-bottom: 15px;border: 1px solid rgba(255,255,255,0.6);}.audit-pill {display: inline-block;padding: 4px 12px;border-radius: 20px;font-size: 13px;font-weight: 500;margin-top: 8px;margin-bottom: 5px;}h1, h2, h3, p, span, div, strong {color: #333333 !important;}.trend-up {color: #d9534f !important; font-weight: bold;}.trend-down {color: #28a745 !important; font-weight: bold;}.trend-flat {color: #6c757d !important; font-weight: bold;}</style>""", unsafe_allow_html=True)

# ==========================================
# 3. 工具函数
# ==========================================
def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    try:
        url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
        r = requests.get(url, timeout=3)
        if r.status_code != 200: return {}
        data_map = {}
        for line in r.text.split(';'):
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
    except: return {}

def calculate_estimate(fund_info, market_data):
    total_w_change, total_w = 0.0, 0.0
    factor = fund_info.get('factor', 1.0)
    for s in fund_info.get('holdings', []):
        code, w = s['code'], s['weight']
        if code in market_data:
            total_w_change += market_data[code]['pct_change'] * w
            total_w += w
    return (total_w_change / total_w * factor) if total_w > 0 else 0.0

# ==========================================
# 4. 生成卡片 HTML 的专用函数 (核心修复)
# ==========================================
def create_card_html(fund_name, est_change, factor, base_unit):
    # 1. 计算颜色和符号
    if est_change > 0: color_cls, sign = "trend-up", "+"
    elif est_change < 0: color_cls, sign = "trend-down", ""
    else: color_cls, sign = "trend-flat", ""
    
    # 2. 生成审计提示 HTML (单行模式)
    audit_html = ""
    for k, v in AUDIT_MEMO.items():
        if k in fund_name:
            audit_html = f"<div class='audit-pill' style='background-color:{v['color']};color:{v['text_color']};'><strong>{v['tag']}</strong> | {v['text']}</div>"
            break
            
    # 3. 拼接最终 HTML (关键：强制连接成一行，无换行符)
    # 我们用 join 把所有片段连起来，彻底杜绝编辑器自动加缩进的机会
    html_parts = [
        f"<div class='fund-card'>",
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>",
        f"<h3 style='margin:0;font-size:1.2rem;'>{fund_name}</h3>",
        f"<span class='{color_cls}' style='font-size:1.5rem;'>{sign}{est_change:.2f}%</span>",
        f"</div>",
        audit_html, # 插入胶囊
        f"<div style='margin-top:10px;font-size:0.9rem;color:#666;'>系数: {factor:.2f} | 底仓: {base_unit}</div>",
        f"</div>"
    ]
    return "".join(html_parts)

# ==========================================
# 5. 主程序
# ==========================================
def main():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    st.markdown(f"# 📈 Family Wealth V5.1")
    st.caption(f"最后更新: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        with open('funds.json', 'r', encoding='utf-8') as f: funds = json.load(f)
    except: 
        st.error("Missing funds.json"); return

    all_codes = {s['code'] for f in funds.values() for s in f.get('holdings', [])}
    market = get_realtime_price(list(all_codes))
    
    if not market:
        st.warning("等待开盘或接口响应...")
        return

    # 渲染循环
    for name, info in funds.items():
        est = calculate_estimate(info, market)
        # 调用我们的“防缩进”生成器
        card_html = create_card_html(name, est, info.get('factor', 1.0), info.get('base_unit', 0))
        st.markdown(card_html, unsafe_allow_html=True)

    if st.button('🔄 刷新数据'): st.rerun()

if __name__ == "__main__":
    main()
