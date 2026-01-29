import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from github import Github

# === ⚙️ 基础配置 ===
st.set_page_config(
    page_title="全域鹰眼 (家庭财富版)",
    page_icon="🦅",
    layout="centered"
)

# === 📊 核心数据定义 ===
MARKET_INDICES = {
    'sh000001': '上证指数',
    'sz399006': '创业板指',
    'hkHSTECH': '恒生科技'
}

# ⚠️ 确保是真实的 6 位代码
FUND_CODES_MAP = {
    '摩根均衡C (梁鹏/周期)': '009968',
    '泰康新锐C (韩庆/成长)': '009340',
    '财通优选C (金梓才/AI)': '009354'
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
        st.error(f"GitHub 连接失败: {e}")
        return None

def load_json(filename):
    """读取 JSON 文件"""
    repo = get_repo()
    if not repo: return {}, None
    try:
        content = repo.get_contents(filename)
        return json.loads(content.decoded_content.decode('utf-8')), content.sha
    except:
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

def save_factor_history(date_str, new_factors_dict):
    """📈 记录仪：保存当天的系数快照"""
    history, sha = load_json('factor_history.json')
    if not isinstance(history, dict):
        history = {}
    
    existing_record = history.get(date_str, {})
    existing_record.update(new_factors_dict)
    history[date_str] = existing_record
    
    save_json('factor_history.json', history, sha, f"Factor Log {date_str}")

# === 🕷️ 数据获取 (爬虫模块) ===

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
    """
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=1"
    headers = {
        "Referer": "http://fund.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            res = r.json()
            if "Data" in res and "LSJZList" in res["Data"]:
                data_list = res["Data"]["LSJZList"]
                if len(data_list) > 0:
                    latest_data = data_list[0]
                    net_date = latest_data["FSRQ"]
                    growth_rate = latest_data["JZZZL"]
                    if growth_rate == "": return None, None
                    return float(growth_rate), net_date
    except:
        pass
    return None, None

# === 🚀 主程序 ===
def main():
    st.title("🦅 家庭财富鹰眼 (V4.0)")

    funds_config, config_sha = load_json('funds.json')
    if not funds_config:
        st.stop()

    # ==========================================
    # 👇 侧边栏控制台
    # ==========================================
    with st.sidebar:
        st.header("🎮 控制台")
        # 🔥 新增了 "💰 持仓管理" 选项
        mode = st.radio("选择模式", ["📡 实时监控", "💰 持仓管理", "💾 收盘存证", "⚖️ 晚间审计"])
        st.divider()

        # --- 💰 模式 New: 持仓管理 (手机端改金额) ---
        if mode == "💰 持仓管理":
            st.info("📝 在这里修改持仓金额，点击保存后即刻生效。")
            
            with st.form("holding_form"):
                new_holdings = {}
                for name, info in funds_config.items():
                    # 显示输入框，默认值是当前的持仓
                    current_val = info.get('holding_value', 0)
                    new_val = st.number_input(
                        label=name.split('(')[0], # 只显示简名
                        value=float(current_val),
                        step=100.0,
                        format="%.2f"
                    )
                    new_holdings[name] = new_val
                
                # 提交按钮
                if st.form_submit_button("💾 保存新持仓到云端"):
                    try:
                        # 更新本地配置对象
                        for name, val in new_holdings.items():
                            funds_config[name]['holding_value'] = val
                        
                        # 写入 GitHub
                        save_json('funds.json', funds_config, config_sha, "Update Holdings via App")
                        st.success("🎉 修改成功！金额已更新。")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存失败: {e}")

        # --- 💾 模式 B: 收盘存证 ---
        elif mode == "💾 收盘存证":
            st.info("ℹ️ 最佳操作时间：收盘后 (15:00 - 23:59)。")
            if st.button("📸 立即存证"):
                with st.spinner("正在计算(经典单因子)..."):
                    snapshot_data = {}
                    all_codes = []
                    for f in funds_config.values():
                        for s in f['holdings']: all_codes.append(s['code'])
                    
                    prices = get_realtime_price(list(set(all_codes)))
                    
                    if prices:
                        today_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
                        
                        for name, info in funds_config.items():
                            val = 0
                            w = 0
                            for s in info['holdings']:
                                if s['code'] in prices:
                                    val += prices[s['code']]['change'] * s['weight']
                                    w += s['weight']
                            
                            raw_est = val / w if w > 0 else 0
                            snapshot_data[name] = raw_est
                        
                        history, hist_sha = load_json('history.json')
                        history[today_str] = snapshot_data
                        save_json('history.json', history, hist_sha, f"Snapshot {today_str}")
                        
                        st.success(f"✅ {today_str} 快照已保存！")
                        st.json(snapshot_data)
                    else:
                        st.error("行情获取失败")

        # --- ⚖️ 模式 C: 晚间审计 ---
        elif mode == "⚖️ 晚间审计":
            st.info("ℹ️ 对比'昨日快照'与'官方净值'，自动修正系数。")
            history, hist_sha = load_json('history.json')
            factor_history, _ = load_json('factor_history.json')
            
            if history:
                last_date = sorted(history.keys())[-1]
                st.markdown(f"📅 审计目标：**{last_date}**")
                
                audited_records = factor_history.get(last_date, {}) if factor_history else {}
                
                if st.button("🚀 开始审计"):
                    updates_log = []
                    need_save = False
                    current_batch_success = {}
                    progress_bar = st.progress(0)
                    
                    for idx, (name, info) in enumerate(funds_config.items()):
                        if name in audited_records:
                            updates_log.append(f"⏭️ {name}: 今日已完成")
                            progress_bar.progress((idx + 1) / len(funds_config))
                            continue
                        
                        raw_est = history[last_date].get(name)
                        code = FUND_CODES_MAP.get(name)
                        
                        if raw_est is not None and code:
                            off_pct, off_date = get_official_nav(code)
                            if off_date and off_date >= last_date:
                                if raw_est != 0:
                                    perfect_factor = off_pct / raw_est
                                    old_factor = info['factor']
                                    new_factor = (old_factor * 0.80) + (perfect_factor * 0.20)
                                    
                                    funds_config[name]['factor'] = round(new_factor, 4)
                                    current_batch_success[name] = round(new_factor, 4)
                                    
                                    updates_log.append(f"✅ {name}: {old_factor} -> {new_factor:.4f}")
                                    need_save = True
                            else:
                                updates_log.append(f"⏳ {name}: 官方未更新")
                        else:
                            updates_log.append(f"❌ {name}: 缺少数据")
                            
                        progress_bar.progress((idx + 1) / len(funds_config))
                    
                    if need_save:
                        save_json('funds.json', funds_config, config_sha, f"Audit Update {last_date}")
                        save_factor_history(last_date, current_batch_success)
                        st.balloons()
                        st.success("系数已修正并归档！重启中...")
                        time.sleep(3)
                        st.rerun()
                    else:
                        if not updates_log: st.info("今日已完成审计。")
                        else: st.text("\n".join(updates_log))
            else:
                st.error("无历史快照")

        # --- 📊 侧边栏：趋势分析 ---
        st.divider()
        with st.expander("📈 模型稳定性分析", expanded=False):
            factor_hist, _ = load_json('factor_history.json')
            if factor_hist:
                try:
                    df = pd.DataFrame.from_dict(factor_hist, orient='index')
                    df = df.sort_index()
                    if not df.empty:
                        st.caption("系数走势")
                        st.line_chart(df)
                        st.markdown("**稳定性评分 (标准差):**")
                        std_devs = df.std()
                        for name, val in std_devs.items():
                            color = "green" if val < 0.05 else "red"
                            short_name = name.split('(')[0]
                            st.markdown(f"- {short_name}: :{color}[{val:.4f}]")
                except:
                    st.caption("数据不足")
            else:
                st.caption("暂无数据")

    # ==========================================
    # 👇 主界面：实时监控 (家庭财富版)
    # ==========================================
    if mode == "📡 实时监控":
        placeholder = st.empty()
        
        all_codes = list(MARKET_INDICES.keys())
        for f in funds_config.values():
            for s in f['holdings']: all_codes.append(s['code'])
        all_codes = list(set(all_codes))
        
        while True:
            with placeholder.container():
                market_data = get_realtime_price(all_codes)
                if not market_data:
                    st.warning("📡 连接卫星中...")
                    time.sleep(2)
                    continue
                
                bj_time = datetime.utcnow() + timedelta(hours=8)
                st.caption(f"最后刷新: {bj_time.strftime('%H:%M:%S')}")
                
                # --- 家庭账户总看板 ---
                total_daily_profit = 0
                total_principal = 0
                fund_results = []
                
                for fund_name, fund_info in funds_config.items():
                    holdings = fund_info['holdings']
                    factor = fund_info.get('factor', 1.0)
                    principal = fund_info.get('holding_value', 0)
                    
                    total_val = 0
                    total_w = 0
                    top_stocks = []
                    
                    for s in holdings:
                        info = market_data.get(s['code'])
                        if info:
                            total_val += info['change'] * s['weight']
                            total_w += s['weight']
                            if len(top_stocks) < 5:
                                top_stocks.append({"股票": info['name'], "涨跌": f"{info['change']:+.2f}%"})
                    
                    raw_est = total_val / total_w if total_w > 0 else 0
                    final_est = raw_est * factor
                    
                    profit = principal * (final_est / 100)
                    total_daily_profit += profit
                    total_principal += principal
                    
                    fund_results.append({
                        "name": fund_name,
                        "est": final_est,
                        "profit": profit,
                        "factor": factor,
                        "top_stocks": top_stocks,
                        "principal": principal
                    })

                # 渲染看板
                st.header("💰 家庭今日盈亏")
                col_main1, col_main2 = st.columns(2)
                
                col_main1.metric(
                    label="今日预估盈亏 (元)",
                    value=f"{total_daily_profit:+.2f}",
                    delta=f"{total_daily_profit:+.2f} 元"
                )
                
                total_yield = (total_daily_profit / total_principal * 100) if total_principal > 0 else 0
                col_main2.metric(
                    label="整体收益率",
                    value=f"{total_yield:+.2f}%"
                )
                st.divider()

                # --- 市场风向 ---
                st.subheader("📈 市场风向")
                c1, c2, c3 = st.columns(3)
                cols = [c1, c2, c3]
                for i, code in enumerate(MARKET_INDICES):
                    info = market_data.get(code)
                    if info: cols[i].metric(MARKET_INDICES[code], f"{info['change']:.2f}%")
                st.divider()

                # --- 基金卡片 ---
                for res in fund_results:
                    emoji = "🔥" if res['est'] > 0 else "❄️"
                    color = "red" if res['est'] > 0 else "green"
                    
                    title_str = f"{emoji} {res['name'].split('(')[0]} | {res['est']:+.2f}% | ￥{res['profit']:+.1f}"
                    
                    with st.expander(title_str):
                        st.markdown(f"**实时估值**: :{color}[{res['est']:+.2f}%] (盈亏: `￥{res['profit']:+.2f}`)")
                        st.caption(f"持仓: ￥{res['principal']} | 系数: `{res['factor']}`")
                        st.table(res['top_stocks'])
            
            time.sleep(30)

if __name__ == "__main__":
    main()
