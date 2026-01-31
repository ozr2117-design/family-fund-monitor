import streamlit as st
import json
import requests
import pandas as pd
from datetime import datetime
import pytz

# ==========================================
# 1. 核心配置与人工审计日志 (Manual Audit Log)
# ==========================================
# 这里就是你要求的“上周偏离提示”，直接写在这里方便随时改
AUDIT_MEMO = {
    "摩根均衡": {
        "tag": "⚠️ 偏离较高", 
        "text": "上周偏离 -0.7%，需注意误差", 
        "color": "#FFF3CD", # 浅橙色背景
        "text_color": "#856404" # 深褐色文字
    },
    "泰康新锐": {
        "tag": "✅ 准确率高", 
        "text": "基本跟净值一致，可信度高", 
        "color": "#D4EDDA", # 浅绿色背景
        "text_color": "#155724" # 深绿色文字
    },
    "财通优选": {
        "tag": "👌 偏差可控", 
        "text": "偏离值可接受，参考性强", 
        "color": "#D1ECF1", # 浅蓝色背景
        "text_color": "#0C5460" # 深蓝色文字
    }
}

# 页面基础设置
st.set_page_config(page_title="Family Wealth V5.1", page_icon="📈", layout="centered")

# ==========================================
# 2. 极光样式 CSS (强制日间模式)
# ==========================================
st.markdown("""
<style>
    /* 强制背景为极光色，防止夜间模式黑底 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* 卡片样式 */
    .fund-card {
        background-color: rgba(255, 255, 255, 0.85);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-bottom: 15px;
        border: 1px solid rgba(255,255,255,0.6);
    }
    
    /* 审计胶囊样式 (新增) */
    .audit-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 500;
        margin-top: 8px;
        margin-bottom: 5px;
    }

    /* 文字颜色强制深色 */
    h1, h2, h3, p, span, div {
        color: #333333 !important;
    }
    
    /* 涨跌颜色 */
    .trend-up { color: #d9534f !important; font-weight: bold; }
    .trend-down { color: #28a745 !important; font-weight: bold; }
    .trend-flat { color: #6c757d !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 数据获取函数 (腾讯源)
# ==========================================
def get_realtime_price(stock_codes):
    """
    批量获取腾讯实时行情
    """
    if not stock_codes:
        return {}
    
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            return {}
        
        data_map = {}
        lines = r.text.split(';')
        for line in lines:
            if '="' in line:
                code = line.split('=')[0].split('_')[-1]
                params = line.split('="')[1].split('~')
                if len(params) > 30:
                    current_price = float(params[3])
                    last_close = float(params[4])
                    pct_change = float(params[32])
                    data_map[code] = {
                        'price': current_price,
                        'last_close': last_close,
                        'pct_change': pct_change
                    }
        return data_map
    except Exception as e:
        st.error(f"数据源连接失败: {e}")
        return {}

def calculate_fund_estimate(fund_info, market_data):
    """
    计算基金估算涨跌幅
    """
    total_weighted_change = 0.0
    total_weight = 0.0
    
    holdings = fund_info.get('holdings', [])
    factor = fund_info.get('factor', 1.0) # 获取系数，默认为1.0
    
    for stock in holdings:
        code = stock['code']
        weight = stock['weight']
        
        if code in market_data:
            change = market_data[code]['pct_change']
            total_weighted_change += change * weight
            total_weight += weight
            
    if total_weight > 0:
        # 归一化处理：假设前十大持仓代表整体
        estimated_change = (total_weighted_change / total_weight) * factor
        return estimated_change
    return 0.0

# ==========================================
# 4. 主程序逻辑
# ==========================================
def main():
    # 标题与时间
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    st.markdown(f"# 📈 Family Wealth V5.1")
    st.caption(f"最后更新: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    try:
        with open('funds.json', 'r', encoding='utf-8') as f:
            funds_config = json.load(f)
    except FileNotFoundError:
        st.error("找不到 funds.json 配置文件")
        return

    # 提取所有股票代码进行批量查询
    all_stocks = set()
    for fund in funds_config.values():
        for stock in fund.get('holdings', []):
            all_stocks.add(stock['code'])
            
    # 获取行情
    market_data = get_realtime_price(list(all_stocks))
    
    if not market_data:
        st.warning("等待开盘或数据源响应中...")
        return

    # ----------------------------------
    # 核心卡片渲染循环
    # ----------------------------------
    for fund_name, fund_info in funds_config.items():
        # 计算估值
        est_change = calculate_fund_estimate(fund_info, market_data)
        
        # 确定颜色
        if est_change > 0:
            color_class = "trend-up"
            sign = "+"
        elif est_change < 0:
            color_class = "trend-down"
            sign = ""
        else:
            color_class = "trend-flat"
            sign = ""
            
        # ----------------------------------
        # 🔥 新增功能：查找并显示人工审计提示
        # ----------------------------------
        audit_html = ""
        # 模糊匹配：只要配置里的名字包含在基金名里，就显示提示
        for key, memo in AUDIT_MEMO.items():
            if key in fund_name:
                audit_html = f"""
                <div class="audit-pill" style="background-color: {memo['color']}; color: {memo['text_color']};">
                    <strong>{memo['tag']}</strong> | {memo['text']}
                </div>
                """
                break
        
        # 渲染卡片 HTML
        st.markdown(f"""
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
        """, unsafe_allow_html=True)
        
    # 底部刷新按钮
    if st.button('🔄 刷新数据'):
        st.rerun()

if __name__ == "__main__":
    main()
