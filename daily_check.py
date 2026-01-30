import requests
import json
import os
from datetime import datetime, timedelta

# ==========================================
# ⚙️ 配置区 (记得填回你的 Bark Key)
# ==========================================
BARK_URLS = [
    "https://api.day.app/8BTBArkBatQQdF39JpsBDg/推送标题/基金开搞！/",
    "https://api.day.app/你的Key2/"
]

LOG_FILE = "signals.md"  # 日记文件名

# ==========================================
# 🛠️ 核心逻辑区
# ==========================================

def load_funds():
    try:
        with open('funds.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

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
                    close = float(data[4])
                    if close > 0:
                        price_data[code] = ((float(data[3]) - close) / close) * 100
                except: continue
        return price_data
    except: return {}

def get_benchmark_pct(fund_name, market_data):
    code = 'sz399006' if any(k in fund_name for k in ["成长", "AI", "优选"]) else 'sh000001'
    return market_data.get(code, 0)

# 🔥 新增：写日记功能
def append_to_log(log_entries):
    if not log_entries: return
    
    today = datetime.now().strftime("%Y-%m-%d")
    new_lines = []
    
    for entry in log_entries:
        # 格式: | 日期 | 基金 | 信号 | 详情 | 操作 |
        line = f"| {today} | {entry['name']} | {entry['type']} | {entry['detail']} | {entry['action']} |"
        new_lines.append(line)
        
    try:
        # 读取现有内容
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # 在表头(第2行)下面插入新内容，这样最新的在最上面
        insert_idx = 2
        for i, line in enumerate(lines):
            if "|---" in line:
                insert_idx = i + 1
                break
                
        # 插入
        for line in reversed(new_lines):
            lines.insert(insert_idx, line + "\n")
            
        # 写入
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("✅ 日记写入成功")
    except Exception as e:
        print(f"❌ 写日记失败: {e}")

# ==========================================
# 🚀 主程序
# ==========================================
def main():
    print(">>> 开始执行巡检...")
    funds = load_funds()
    if not funds: return
    
    all_codes = ['sh000001', 'sz399006']
    for f in funds.values():
        for s in f['holdings']: all_codes.append(s['code'])
    
    market_data = get_realtime_price(list(set(all_codes)))
    if not market_data: return

    messages = []
    log_entries = [] # 专门用于写日记的数据结构
    
    for name, info in funds.items():
        factor = info.get('factor', 1.0)
        base_unit = info.get('base_unit', 1000)
        val = 0; w = 0
        for s in info['holdings']:
            if s['code'] in market_data:
                val += market_data[s['code']] * s['weight']; w += s['weight']
        
        est = (val / w * factor) if w > 0 else 0
        bench_val = get_benchmark_pct(name, market_data)
        short_name = name.split('(')[0]

        # 信号判断
        signal_type = None
        detail = ""
        action = ""
        
        # 1. 买入
        if est < -2.5 and est < bench_val:
            multiplier = 2 if est < -4.0 else 1
            buy_amt = base_unit * multiplier
            msg = f"🟢【机会】{short_name} {est:.2f}%\n📉 跑输基准 {abs(est-bench_val):.1f}%\n👉 建议加仓 ¥{buy_amt:,}"
            messages.append(msg)
            
            # 记录日志数据
            log_entries.append({
                "name": short_name,
                "type": "🟢 买入机会",
                "detail": f"估值 {est:.2f}% (跑输 {abs(est-bench_val):.1f}%)",
                "action": f"买入 ¥{buy_amt:,}"
            })

        # 2. 卖出
        elif est > 3.0 and est > (bench_val + 1.5):
            msg = f"🔴【止盈】{short_name} +{est:.2f}%\n🔥 跑赢基准 {abs(est-bench_val):.1f}%\n👉 建议卖出 1/4"
            messages.append(msg)
            
            log_entries.append({
                "name": short_name,
                "type": "🔴 止盈提醒",
                "detail": f"估值 +{est:.2f}% (跑赢 {abs(est-bench_val):.1f}%)",
                "action": "卖出 1/4"
            })

    # 执行操作
    if messages:
        # 1. 推送 Bark
        final_body = "\n\n".join(messages)
        title = "基金信号提醒"
        for url in BARK_URLS:
            if "你的Key" in url: continue
            try:
                clean_url = url.rstrip('/')
                requests.get(f"{clean_url}/{title}/{final_body}?group=fund")
            except: pass
        print("✅ 推送完成")
        
        # 2. 写日记 (仅当有信号时)
        append_to_log(log_entries)
        
    else:
        print("今日无信号")

if __name__ == "__main__":
    main()
