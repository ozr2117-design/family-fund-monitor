import requests
import json
import os
from datetime import datetime, timedelta

# ==========================================
# ⚙️ 配置区 (请在这里填入你们两台手机的 Bark 链接)
# ==========================================
BARK_URLS = [
    "https://api.day.app/8BTBArkBatQQdF39JpsBDg/推送标题/基金到买点啦！/",   # 📱 你的手机 (保留最后的斜杠)
    "https://api.day.app/你的Key2/"    # 📱 妻子的手机
]

# ==========================================
# 🛠️ 核心逻辑区 (无需修改)
# ==========================================

# 1. 读取 GitHub 仓库里的基金配置
def load_funds():
    try:
        # 在 GitHub Actions 环境下，直接读取根目录的 funds.json
        with open('funds.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取配置失败: {e}")
        return {}

# 2. 获取实时行情 (腾讯接口)
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
                    # 腾讯数据格式: v_sh000001="指数~...~当前价~昨收~..."
                    code = part.split('=')[0].split('_')[-1]
                    data = part.split('="')[1].split('~')
                    
                    current = float(data[3])
                    close = float(data[4])
                    
                    # 计算涨跌幅
                    pct = 0.0
                    if close > 0:
                        pct = ((current - close) / close) * 100
                        
                    price_data[code] = pct
                except: continue
        return price_data
    except Exception as e:
        print(f"行情获取错误: {e}")
        return {}

# 3. 智能匹配基准指数
def get_benchmark_pct(fund_name, market_data):
    # 简单的关键词匹配：成长/AI/优选 -> 看创业板(sz399006)，其他 -> 看上证(sh000001)
    code = 'sz399006' if any(k in fund_name for k in ["成长", "AI", "优选"]) else 'sh000001'
    return market_data.get(code, 0)

# ==========================================
# 🚀 主程序执行
# ==========================================
def main():
    print(">>> 开始执行基金巡检...")
    funds = load_funds()
    if not funds: return
    
    # 1. 提取所有需要查询的代码 (包含大盘指数)
    all_codes = ['sh000001', 'sz399006'] 
    for f in funds.values():
        for s in f['holdings']: all_codes.append(s['code'])
    
    # 2. 批量获取行情
    market_data = get_realtime_price(list(set(all_codes)))
    if not market_data:
        print("行情接口无响应，任务终止。")
        return

    # 3. 计算估值并判断信号
    messages = []
    
    for name, info in funds.items():
        factor = info.get('factor', 1.0)
        base_unit = info.get('base_unit', 1000) # 获取基准买入额
        
        # 计算估值
        val = 0; w = 0
        for s in info['holdings']:
            if s['code'] in market_data:
                val += market_data[s['code']] * s['weight']
                w += s['weight']
        
        # 核心估值公式
        est = (val / w * factor) if w > 0 else 0
        
        # 获取基准涨跌幅
        bench_val = get_benchmark_pct(name, market_data)
        short_name = name.split('(')[0] # 简化名字，如"财通优选"

        # --- 🔥 V5.0 信号判断逻辑 ---
        
        # [信号 A] 🎯 买入机会: 跌幅深 (< -2.5%) 且 跑输基准
        # (测试时可将 -2.5 改为 100 来强制触发)
        if est < 100 and est < bench_val:
            # 金字塔加仓: 跌幅超过 -4% 买两份
            multiplier = 2 if est < -4.0 else 1
            buy_amt = base_unit * multiplier
            
            msg = f"🟢【机会】{short_name} {est:.2f}%\n📉 跑输基准 {abs(est-bench_val):.1f}%\n👉 建议加仓 ¥{buy_amt:,}"
            messages.append(msg)
            
        # [信号 B] 🔥 止盈提醒: 涨幅大 (> 3.0%) 且 跑赢基准 (> 1.5%)
        elif est > 3.0 and est > (bench_val + 1.5):
            msg = f"🔴【止盈】{short_name} +{est:.2f}%\n🔥 跑赢基准 {abs(est-bench_val):.1f}%\n👉 建议卖出 1/4"
            messages.append(msg)

    # 4. 执行群发推送
    if messages:
        print(f"检测到 {len(messages)} 条信号，准备推送...")
        
        # 拼接消息内容
        final_body = "\n\n".join(messages)
        title = "基金信号提醒"
        
        # 遍历 URL 列表，给每台手机发一遍
        for url in BARK_URLS:
            if "你的Key" in url: continue # 跳过没填Key的默认行
            
            try:
                # 清理 URL 格式 (防止多余的斜杠)
                clean_url = url.rstrip('/')
                # 构造 Bark 请求: URL/标题/内容?group=fund
                # 注意: Bark 默认支持 GET 请求，直接拼接即可
                push_url = f"{clean_url}/{title}/{final_body}?group=fund&icon=https://cdn-icons-png.flaticon.com/512/3310/3310624.png"
                
                requests.get(push_url)
                print(f"✅ 推送成功 -> ...{clean_url[-6:]}")
            except Exception as e:
                print(f"❌ 推送失败: {e}")
    else:
        print("今日无信号触发，保持静默。")

if __name__ == "__main__":
    main()
