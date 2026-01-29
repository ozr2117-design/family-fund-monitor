import streamlit as st
import requests
import time
import json
from datetime import datetime, timedelta
from github import Github

# === ⚙️ 基础配置 ===
st.set_page_config(
    page_title="全域鹰眼 (存证审计版)",
    page_icon="🦅",
    layout="centered"
)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

# ⚠️⚠️⚠️ 请务必确认这里的基金名称与 funds.json 里的完全一致
# 并且填入正确的 6 位基金代码 (用于抓取官方净值)
FUND_CODES_MAP = {
    '摩根均衡C (梁鹏/周期)': '021274',
    '泰康新锐C (韩庆/成长)': '017366',
    '财通优选C (金梓才/AI)': '021528' 
}

# === 🛠️ GitHub 数据库操作 ===

def get_repo():
    """连接 GitHub 仓库"""
    try:
        token = st.secrets["github_token"]
        username = st.secrets["github_username"]
        repo_name = st.secrets["repo_name"]
        g = Github(token)
        return g.get_user(username).get_repo(repo_name)
    except Exception as e:
        st.error(f"GitHub 连接失败，请检查 Secrets 配置: {e}")
        return None

def load_json(filename):
    """读取 JSON 文件"""
    repo = get_repo()
    if not repo: return {}, None
    try:
        content = repo.get_contents(filename)
        return json.loads(content.decoded_content.decode('utf-8')), content.sha
    except:
        st.warning(f"文件 {filename} 读取失败或不存在")
        return {}, None

def save_json(filename, data, sha, message):
    """写入 JSON 文件"""
    repo = get_repo()
    if repo:
        new_content = json.dumps(data, indent=4, ensure_ascii=False)
        if sha:
            repo.update_file(filename, message, new_content, sha)
        else:
            repo.create_file(filename, message, new_content)

# === 🕷️ 数据获取 ===

def get_realtime_price(stock_codes):
    """腾讯接口获取实时行情"""
    if not stock_codes: return {}
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
                    name = data[1].replace(" ", "")
                    # 计算涨跌幅
                    current = float(data[3])
                    close = float(data[4])
                    pct = 0.0
                    if close > 0:
                        pct = ((current - close) / close) * 100
                    price_data[code] = {'name': name, 'change': pct}
            except:
                continue
    return price_data

def get_official_nav(fund_code):
    """
    🚀 升级版爬虫：直连天天基金(东财)官方接口
    需要伪装 Headers，数据最快最全。
    """
    # 官方历史净值接口 (LSJZ = Lishi Jingzhi)
    # pageIndex=1&pageSize=1 表示只取最新的一条数据
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=1"
    
    # ⚠️ 关键：东财接口必须带 Referer，否则会报 403 Forbidden
    headers = {
        "Referer": "http://fund.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            res = r.json()
            # 解析官方数据结构: Data -> LSJZList -> 第一个元素
            if "Data" in res and "LSJZList" in res["Data"]:
                data_list = res["Data"]["LSJZList"]
                if len(data_list) > 0:
                    latest_data = data_list[0]
                    
                    # 字段说明：
                    # FSRQ: 净值日期 (例如 2026-01-29)
                    # JZZZL: 日增长率 (例如 1.25 表示 +1.25%)
                    
                    net_date = latest_data["FSRQ"]
                    growth_rate = latest_data["JZZZL"]
                    
                    # 容错处理：有时候刚更新净值但涨跌幅还是空字符串
                    if growth_rate == "":
                        return None, None
                        
                    return float(growth_rate), net_date
    except Exception as e:
        # 调试时可以打印错误 st.error(f"接口报错: {e}") 
        pass
    
    return None, None
# === 🚀 主程序 ===
def main():
    st.title("🦅 全域鹰眼 (V4.0)")

    # 1. 读取配置
    funds_config, config_sha = load_json('funds.json')
    if not funds_config:
        st.stop()

    # ==========================================
    # 👇 侧边栏：三大模式控制台
    # ==========================================
    with st.sidebar:
        st.header("🎮 控制台")
        mode = st.radio("选择模式", ["📡 实时监控", "💾 收盘存证", "⚖️ 晚间审计"])
        st.divider()

        # --- 💾 模式 B: 收盘存证 (下午 14:50 - 15:10 使用) ---
        if mode == "💾 收盘存证":
            st.info("ℹ️ 最佳操作时间：收盘后 (15:00 - 23:59)。数据已定型，存证最精准。")
            
            if st.button("📸 立即拍摄快照 (Save Snapshot)"):
                with st.spinner("正在计算全网实时数据..."):
                    snapshot_data = {}
                    all_stocks = []
                    # 收集所有股票代码
                    for f in funds_config.values():
                        for s in f['holdings']: all_stocks.append(s['code'])
                    
                    # 抓取行情
                    prices = get_realtime_price(list(set(all_stocks)))
                    
                    if prices:
                        today_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
                        
                        for name, info in funds_config.items():
                            val = 0
                            w = 0
                            for s in info['holdings']:
                                if s['code'] in prices:
                                    val += prices[s['code']]['change'] * s['weight']
                                    w += s['weight']
                            
                            # ⚠️ 关键点：这里存储的是【未乘系数】的原始估值
                            # 这样我们才能算出纯粹的持仓偏差
                            if w > 0:
                                raw_est = val / w
                                snapshot_data[name] = raw_est
                        
                        # 读取旧历史并追加
                        history, hist_sha = load_json('history.json')
                        history[today_str] = snapshot_data
                        
                        # 写入 GitHub
                        save_json('history.json', history, hist_sha, f"Snapshot {today_str}")
                        st.success(f"✅ {today_str} 快照已保存！")
                        st.json(snapshot_data)
                    else:
                        st.error("行情接口连接失败，无法存证")

        # --- ⚖️ 模式 C: 晚间审计 (晚上 21:30 后使用) ---
        elif mode == "⚖️ 晚间审计":
            st.info("ℹ️ 对比'昨日快照'与'官方净值'，自动修正误差系数。")
            
            history, hist_sha = load_json('history.json')
            if history:
                # 自动找最近的一个日期
                last_date = sorted(history.keys())[-1]
                st.markdown(f"📅 审计目标日期：**{last_date}**")
                
                if st.button("🚀 开始审计与修正"):
                    updates_log = []
                    need_save = False
                    progress_bar = st.progress(0)
                    
                    # 遍历每一个基金
                    for idx, (name, info) in enumerate(funds_config.items()):
                        # 1. 找算法数据
                        raw_est = history[last_date].get(name)
                        
                        # 2. 找官方数据
                        code = FUND_CODES_MAP.get(name)
                        
                        if raw_est is not None and code:
                            off_pct, off_date = get_official_nav(code)
                            
                            # 校验日期：官方数据必须 >= 快照日期
                            if off_date and off_date >= last_date:
                                # 3. 计算新系数
                                # 公式：官方涨跌 = 原始估值 * 完美系数
                                if raw_est != 0:
                                    perfect_factor = off_pct / raw_est
                                    old_factor = info['factor']
                                    
                                    # 🤖 减震逻辑：EMA (80%旧 + 20%新)
                                    new_factor = (old_factor * 0.8) + (perfect_factor * 0.2)
                                    
                                    # 更新配置字典
                                    funds_config[name]['factor'] = round(new_factor, 4)
                                    
                                    # 记录日志
                                    err = off_pct - (raw_est * old_factor)
                                    updates_log.append(f"✅ {name}\n   误差: {err:+.2f}% | 系数: {old_factor} -> {new_factor:.4f}")
                                    need_save = True
                                else:
                                    updates_log.append(f"⚠️ {name}: 原始估值为0，跳过")
                            else:
                                updates_log.append(f"⏳ {name}: 官方数据尚未更新 ({off_date})")
                        else:
                            updates_log.append(f"❌ {name}: 缺少代码配置或快照")
                        
                        progress_bar.progress((idx + 1) / len(funds_config))
                    
                    st.divider()
                    for log in updates_log:
                        st.text(log)
                    
                    # 4. 保存结果
                    if need_save:
                        with st.spinner("正在写入新系数..."):
                            save_json('funds.json', funds_config, config_sha, f"Audit Update {last_date}")
                        st.balloons()
                        st.success("🎉 系数已修正！系统将在 3 秒后自动重启...")
                        time.sleep(3)
                        st.rerun()
                    else:
                        st.warning("没有进行任何修改 (可能是数据未更新)")
            else:
                st.error("找不到历史快照，请先执行【收盘存证】。")

    # ==========================================
    # 👇 主界面：实时监控 (只在监控模式显示)
    # ==========================================
    if mode == "📡 实时监控":
        placeholder = st.empty()
        
        # 预先提取所有代码
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        all_codes = list(set(all_codes))
        
        while True:
            with placeholder.container():
                # 1. 获取行情
                market_data = get_realtime_price(all_codes)
                if not market_data:
                    st.warning("📡 正在连接行情卫星...")
                    time.sleep(2)
                    continue
                
                # 2. 显示时间
                bj_time = datetime.utcnow() + timedelta(hours=8)
                st.caption(f"最后刷新: {bj_time.strftime('%H:%M:%S')} (北京时间) | V4.0运行中")
                
                # 3. 大盘看板
                st.subheader("📈 市场风向")
                col1, col2, col3 = st.columns(3)
                cols = [col1, col2, col3]
                for i, code in enumerate(MARKET_INDICES):
                    info = market_data.get(code)
                    if info:
                        cols[i].metric(MARKET_INDICES[code], f"{info['change']:.2f}%")
                
                st.divider()

                # 4. 基金列表
                for fund_name, fund_info in funds_config.items():
                    holdings = fund_info['holdings']
                    factor = fund_info['factor']
                    
                    total_val = 0
                    total_w = 0
                    
                    # 算持仓
                    top_stocks = []
                    for s in holdings:
                        info = market_data.get(s['code'])
                        if info:
                            total_val += info['change'] * s['weight']
                            total_w += s['weight']
                            # 收集前5大持仓用于展示
                            if len(top_stocks) < 5:
                                top_stocks.append({
                                    "股票": info['name'],
                                    "涨跌": f"{info['change']:+.2f}%"
                                })
                    
                    if total_w > 0:
                        # 核心公式：原始 * 系数
                        raw_est = total_val / total_w
                        final_est = raw_est * factor
                        
                        # 样式逻辑
                        color = "red" if final_est > 0 else "green"
                        emoji = "🔥" if final_est > 0 else "❄️"
                        expanded = abs(final_est) > 1.5 # 大波动自动展开
                        
                        with st.expander(f"{emoji} {fund_name.split('(')[0]} | {final_est:+.2f}%", expanded=expanded):
                            st.markdown(f"**实时估值**: :{color}[{final_est:+.2f}%] (系数: `{factor}`)")
                            if final_est > 2.0: st.warning("💡 提示：热度过高")
                            elif final_est < -2.0: st.success("💡 提示：黄金坑机会")
                            
                            st.table(top_stocks)
            
            # 30秒刷新一次
            time.sleep(30)

if __name__ == "__main__":
    main()


