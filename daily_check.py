import requests
import json
import os
from datetime import datetime

# ================= 配置区 =================
# 请务必替换为你自己的 Bark Key
BARK_URLS = [
    "https://api.day.app/8BTBArkBatQQdF39JpsBDg/推送标题/基金开搞！/", 
    "https://api.day.app/你的Key2/"
]
LOG_FILE = "signals.md"

# ================= 工具函数 =================
def load_funds():
    try:
        with open('funds.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

def get_realtime_price(stock_codes):
    if not stock_codes: return {}
    url = f"http://qt.gtimg.cn/q={','.join(stock_codes)}"
    try:
        r = requests.get(url, timeout=5)
        data_map = {}
        for line in r.text.split(';'):
            if '="' in line:
                code = line.split('=')[0].split('_')[-1]
                vals = line.split('="')[1].split('~')
                close = float(vals[4])
                if close > 0:
                    pct = ((float(vals[3]) - close) / close) * 100
                    data_map[code] = pct
        return data_map
    except: return {}

def get_benchmark(name, market_data):
    if "红利" in name: return market_data.get('sh000001', 0) # 红利对比上证
    if "纳斯达克" in name: return market_data.get('usNDX', 0)
    if any(k in name for k in ["成长", "AI", "优选"]): return market_data.get('sz399006', 0)
    return market_data.get('sh000001', 0)

def append_log(entries):
    if not entries: return
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 准备新行
    new_lines = []
    for e in entries:
        new_lines.append(f"| {today} | {e['name']} | {e['type']} | {e['detail']} | {e['action']} |\n")
    
    # 读取并插入
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("# 🤖 交易信号日记\n\n| 日期 | 基金 | 信号 | 详情 | 建议操作 |\n|---|---|---|---|---|\n")
            
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # 在表格线后插入（第4行）
    insert_idx = 4 if len(lines) >= 4 else len(lines)
    for line in reversed(new_lines):
        lines.insert(insert_idx, line)
        
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.writelines(lines)

# ================= 主逻辑 =================
def main():
    print(">>> 开始巡检")
    funds = load_funds()
    if not funds: return

    # 收集代码
    codes = ['sh000001', 'sz399006', 'usNDX']
    for f in funds.values():
        for s in f['holdings']: codes.append(s['code'])
    
    market = get_realtime_price(list(set(codes)))
    if not market: return

    msgs = []
    logs = []

    for name, info in funds.items():
        # 计算估值
        val = 0; w = 0
        for s in info['holdings']:
            if s['code'] in market:
                val += market[s['code']] * s['weight']; w += s['weight']
        
        est = (val / w * info.get('factor', 1.0)) if w > 0 else 0
        bench = get_benchmark(name, market)
        short_name = name.split('(')[0]
        base_unit = info.get('base_unit', 1000)

        # === 信号阈值判断 ===
        
        # 特殊逻辑：红利低波 (只做大跌狙击)
        if "红利" in name:
            if est < -3.5: # 只有跌超 3.5% 才提示
                msg = f"🟢【黄金坑】{short_name} 暴跌 {est:.2f}%\n🛡️ 防守反击机会\n👉 建议重仓 ¥{base_unit*2}"
                msgs.append(msg)
                logs.append({"name":short_name, "type":"🟢 黄金坑", "detail":f"{est:.2f}%", "action":f"买入 ¥{base_unit*2}"})
            continue # 红利不做止盈，跳过后续逻辑

        # 普通逻辑：波段交易
        if est < -2.5 and est < bench:
            buy_amt = base_unit * (2 if est < -4.0 else 1)
            msg = f"🟢【机会】{short_name} {est:.2f}%\n📉 跑输基准 {abs(est-bench):.1f}%\n👉 建议加仓 ¥{buy_amt}"
            msgs.append(msg)
            logs.append({"name":short_name, "type":"🟢 买入", "detail":f"{est:.2f}% (跑输{abs(est-bench):.1f}%)", "action":f"买入 ¥{buy_amt}"})
            
        elif est > 3.0 and est > (bench + 1.5):
            msg = f"🔴【止盈】{short_name} +{est:.2f}%\n🔥 情绪过热\n👉 建议卖出 1/4"
            msgs.append(msg)
            logs.append({"name":short_name, "type":"🔴 止盈", "detail":f"+{est:.2f}% (跑赢{abs(est-bench):.1f}%)", "action":"卖出 1/4"})

    # 发送与记录
    if msgs:
        body = "\n\n".join(msgs)
        for url in BARK_URLS:
            try: requests.get(f"{url.strip('/')}/基金信号提醒/{body}?group=fund", timeout=5)
            except: pass
        
        append_log(logs)
        print("✅ 信号已发送并记录")
    else:
        print("今日无信号")

if __name__ == "__main__":
    main()
