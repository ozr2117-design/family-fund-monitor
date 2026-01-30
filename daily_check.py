import requests
import json
import os
from datetime import datetime, timedelta

# === ⚙️ 配置区 ===
# 换成你的 Bark 链接 (如果是 PushPlus，逻辑类似)
# 格式: https://api.day.app/你的Key/推送标题/推送内容
BARK_URL = "https://api.day.app/8BTBArkBatQQdF39JpsBDg/重要警告?level=critical&volume=5" 

# 基金配置 (为了简单，这里直接读取本地 funds.json，或者你把 json 内容硬编码在这里)
# 在 GitHub Actions 里，它能读取到仓库里的 funds.json
def load_funds():
    with open('funds.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# === 🕷️ 核心逻辑 (复用你 V5.0 的代码) ===
def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    codes_str = ",".join(stock_codes)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    try:
        r = requests.get(url, timeout=3)
        price_data = {}
        parts = r.text.split(';')
        for part in parts:
            if '="' in part:
                try:
                    code = part.split('=')[0].split('_')[-1]
                    data = part.split('="')[1].split('~')
                    # 腾讯接口: index 3 是当前价, 4 是昨收
                    # 涨跌幅 = (当前 - 昨收) / 昨收 * 100
                    current = float(data[3])
                    close = float(data[4])
                    pct = ((current - close) / close) * 100 if close > 0 else 0
                    price_data[code] = pct
                except: continue
        return price_data
    except: return {}

def get_benchmark_pct(fund_name, market_data):
    # 简化的基准匹配
    code = 'sz399006' if "成长" in fund_name or "AI" in fund_name else 'sh000001'
    return market_data.get(code, 0)

# === 🚀 执行检查 ===
def main():
    print("开始执行巡检...")
    funds = load_funds()
    
    # 1. 提取所有股票代码
    all_codes = ['sh000001', 'sz399006'] # 大盘
    for f in funds.values():
        for s in f['holdings']: all_codes.append(s['code'])
    
    # 2. 获取行情
    market_data = get_realtime_price(list(set(all_codes)))
    if not market_data:
        print("行情获取失败")
        return

    # 3. 计算并判断信号
    messages = []
    
    for name, info in funds.items():
        factor = info.get('factor', 1.0)
        val = 0; w = 0
        for s in info['holdings']:
            if s['code'] in market_data:
                val += market_data[s['code']] * s['weight']
                w += s['weight']
        
        est = (val / w * factor) if w > 0 else 0
        
        # 获取基准
        bench_val = get_benchmark_pct(name, market_data)
        short_name = name.split('(')[0]

        # --- 信号判断逻辑 (和 V5.0 保持一致) ---
        # 🎯 买入信号
        if est < -2.5 and est < bench_val:
            base_unit = info.get('base_unit', 1000)
            multiplier = 2 if est < -4.0 else 1
            buy_amt = base_unit * multiplier
            messages.append(f"🟢【机会】{short_name} 跌幅 {est:.2f}%\n建议加仓 ¥{buy_amt}")
            
        # 🔥 止盈信号
        elif est > 3.0 and est > (bench_val + 1.5):
            messages.append(f"🔴【止盈】{short_name} 涨幅 {est:.2f}%\n建议卖出 1/4")

    # 4. 发送推送 (如果有消息)
    if messages:
        final_msg = "\n".join(messages)
        # URL 编码处理 (简单拼接)
        title = "基金信号提醒"
        requests.get(f"{BARK_URL}{title}/{final_msg}?group=fund")
        print("推送成功:", final_msg)
    else:
        print("今日无信号，不打扰。")

if __name__ == "__main__":
    main()
