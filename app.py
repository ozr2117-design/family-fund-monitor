import streamlit as st
import requests
import time
from datetime import datetime, timedelta # 👈 新增 timedelta

# === ⚙️ 配置区域 ===
st.set_page_config(
    page_title="全域鹰眼监控",
    page_icon="🦅",
    layout="centered"
)

# === 🔥 核心配置 ===
MY_FUNDS_CONFIG = {
    '摩根均衡C (梁鹏/周期)': {
        'factor': 0.83, 
        'holdings': [
            {'code': 'sz000683', 'name': '博源化工', 'weight': 8.81},
            {'code': 'sz002714', 'name': '牧原股份', 'weight': 8.72},
            {'code': 'sh601233', 'name': '桐昆股份', 'weight': 3.89},
            {'code': 'sz002497', 'name': '雅化集团', 'weight': 3.69},
            {'code': 'sh600711', 'name': '盛屯矿业', 'weight': 3.57},
            {'code': 'sz002384', 'name': '东山精密', 'weight': 3.39},
            {'code': 'sz300750', 'name': '宁德时代', 'weight': 3.37},
            {'code': 'sh603225', 'name': '新 凤 鸣', 'weight': 3.36},
            {'code': 'sh600141', 'name': '兴发集团', 'weight': 3.28},
            {'code': 'sz300014', 'name': '亿纬锂能', 'weight': 3.09},
        ]
    },
    '泰康新锐C (韩庆/成长)': {
        'factor': 0.77,
        'holdings': [
            {'code': 'sz002371', 'name': '北方华创', 'weight': 5.55},
            {'code': 'hk00700',  'name': '腾讯控股', 'weight': 5.02},
            {'code': 'sh601899', 'name': '紫金矿业', 'weight': 4.15},
            {'code': 'hk09988',  'name': '阿里巴巴', 'weight': 3.93},
            {'code': 'sz300274', 'name': '阳光电源', 'weight': 3.76},
            {'code': 'sz300750', 'name': '宁德时代', 'weight': 3.35},
            {'code': 'hk00981',  'name': '中芯国际', 'weight': 3.31},
            {'code': 'sh600487', 'name': '亨通光电', 'weight': 3.28},
            {'code': 'sh601138', 'name': '工业富联', 'weight': 3.24},
            {'code': 'sh689009', 'name': '九号公司', 'weight': 3.20},
        ]
    },
    '财通优选C (金梓才/AI)': {
        'factor': 0.89,
        'holdings': [
            {'code': 'sz300502', 'name': '新 易 盛', 'weight': 9.69},
            {'code': 'sz301377', 'name': '鼎泰高科', 'weight': 9.64},
            {'code': 'sz300308', 'name': '中际旭创', 'weight': 9.58},
            {'code': 'sh688498', 'name': '源杰科技', 'weight': 9.50},
            {'code': 'sh600183', 'name': '生益科技', 'weight': 9.41},
            {'code': 'sz002463', 'name': '沪电股份', 'weight': 9.14},
            {'code': 'sh688195', 'name': '腾景科技', 'weight': 9.03},
            {'code': 'sz300476', 'name': '胜宏科技', 'weight': 8.77},
            {'code': 'sh688183', 'name': '生益电子', 'weight': 8.61},
            {'code': 'sh601138', 'name': '工业富联', 'weight': 6.72},
        ]
    }
}

MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

# === 函数区域 ===
def get_realtime_price(stock_codes):
    """腾讯接口获取行情"""
    codes_str = ",".join(stock_codes)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    try:
        r = requests.get(url, timeout=3)
        text = r.text
    except:
        return None

    price_data = {}
    parts = text.split(';')
    for part in parts:
        if '="' in part:
            try:
                key_raw = part.split('=')[0].strip()
                code = key_raw.split('_')[-1] 
                data = part.split('="')[1].strip('"').split('~')
                if len(data) > 30:
                    name = data[1]
                    name = name.replace(" ", "")
                    current = float(data[3])
                    close = float(data[4])
                    pct = 0.0
                    if close > 0:
                        pct = ((current - close) / close) * 100
                    price_data[code] = {'name': name, 'change': pct}
            except:
                continue
    return price_data

# === 主程序 ===
def main():
    st.title("🦅 全域鹰眼监控 Pro+")
    
    # 👇👇👇 【在这里粘贴】 👇👇👇
    # 把它放在 main() 的一开始，placeholder 之前，while True 之前！
    
    with st.sidebar:
        st.header("🛠️ 晚间校准")
        
        # 1. 选择要校准的基金
        fund_list = list(MY_FUNDS_CONFIG.keys())
        selected_fund = st.selectbox("选择基金", fund_list)
        
        # 2. 输入数据
        st.caption("请对照支付宝/天天基金今晚的净值")
        official_pct = st.number_input(f"【B】官方实际涨跌 (%)", value=0.0, step=0.01, format="%.2f")
        est_pct = st.number_input(f"【A】算法刚才算的估值 (%)", value=0.0, step=0.01, format="%.2f")
        
        # 3. 计算逻辑
        if st.button("计算新系数"):
            if est_pct == 0:
                st.error("算法估值不能为0")
            else:
                current_factor = MY_FUNDS_CONFIG[selected_fund]['factor']
                # 还原原始估值
                raw_est = est_pct / current_factor 
                
                # 计算完美系数
                perfect_factor = official_pct / raw_est
                
                # EMA 平滑处理 (90%旧 + 10%新)
                new_factor = (current_factor * 0.9) + (perfect_factor * 0.1)
                
                st.divider()
                st.markdown(f"**当前系数:** `{current_factor:.2f}`")
                st.markdown(f"**建议系数:** `{new_factor:.2f}`")
                
                diff = official_pct - est_pct
                if abs(diff) < 0.2:
                    st.success("✅ 误差极小，无需修改！")
                else:
                    st.error(f"⚠️ 建议去代码里把 factor 改为 {new_factor:.2f}")

    # 👆👆👆 【粘贴结束】 👆👆👆
    
    placeholder = st.empty()
    
    all_codes = list(MARKET_INDICES.keys())
    for fund_data in MY_FUNDS_CONFIG.values():
        for stock in fund_data['holdings']:
            all_codes.append(stock['code'])
    all_codes = list(set(all_codes))

    while True:
        with placeholder.container():
            market_data = get_realtime_price(all_codes)
            
            if not market_data:
                st.warning("正在连接数据源...")
                time.sleep(2)
                continue
            
            # 🔥【修正点】UTC时间 + 8小时 = 北京时间
            bj_time = datetime.utcnow() + timedelta(hours=8)
            current_time = bj_time.strftime('%H:%M:%S')
            
            st.caption(f"最后刷新: {current_time} (北京时间 | 30秒自动刷新)")
            
            # 1. 大盘看板
            st.subheader("📈 市场风向")
            col1, col2, col3 = st.columns(3)
            
            indices_keys = list(MARKET_INDICES.keys())
            cols = [col1, col2, col3]
            
            for i, code in enumerate(indices_keys):
                name = MARKET_INDICES[code]
                info = market_data.get(code)
                if info:
                    cols[i].metric(label=name, value=f"{info['change']:.2f}%")
            
            st.divider()

            # 2. 基金卡片
            for fund_name, fund_info in MY_FUNDS_CONFIG.items():
                holdings = fund_info['holdings']
                factor = fund_info['factor']
                
                total_weighted_change = 0
                total_weight = 0
                
                for stock in holdings:
                    info = market_data.get(stock['code'])
                    if info:
                        total_weighted_change += info['change'] * stock['weight']
                        total_weight += stock['weight']

                if total_weight > 0:
                    raw_est = total_weighted_change / total_weight
                    corrected_est = raw_est * factor
                    
                    color = "red" if corrected_est > 0 else "green"
                    emoji = "🔥" if corrected_est > 0 else "❄️"
                    
                    # 🔥【智能展开逻辑】波动 > 1.5% 自动展开
                    is_expanded = abs(corrected_est) > 1.5
                    
                    with st.expander(f"{emoji} {fund_name.split('(')[0]}  |  {corrected_est:+.2f}%", expanded=is_expanded):
                        st.markdown(f"**实时估值**: :{color}[{corrected_est:+.2f}%] (系数 {factor})")
                        
                        if corrected_est > 2.0:
                            st.warning("💡 提示：热度过高，考虑止盈")
                        elif corrected_est < -2.0:
                            st.success("💡 提示：黄金坑，考虑补仓")
                            
                        # 显示持仓前五
                        top_stocks = []
                        for s in holdings[:5]:
                            s_info = market_data.get(s['code'])
                            if s_info:
                                top_stocks.append({
                                    "股票": s_info['name'],
                                    "涨跌": f"{s_info['change']:+.2f}%"
                                })
                        st.table(top_stocks)

        time.sleep(30)

if __name__ == "__main__":
    main()


