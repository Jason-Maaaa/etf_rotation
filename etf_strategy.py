# 克隆自聚宽文章：https://www.joinquant.com/post/15002
# 标题：价值选股与RSRS择时
# 作者：K线放荡不羁

# 克隆自聚宽文章：https://www.joinquant.com/post/63055
# 标题：最新不报错版本etf轮动
# 作者：招财进宝量化

# 克隆自聚宽文章：https://www.joinquant.com/post/62984
# 标题：etf轮动准备实盘 折腾这个策略 一下午了
# 作者：招财进宝量化

# 克隆自聚宽文章：https://www.joinquant.com/post/62562
# 标题：四大行 轮动做T，已实盘
# 作者：ddq1999

# 克隆自聚宽文章：https://www.joinquant.com/post/62057
# 标题：删
# 作者：阿萨德szxscore

# 克隆自聚宽文章：https://www.joinquant.com/post/62057
# 标题：【ETF轮动更新】增加20%收益-手动构建ET池
# 作者：阿萨德szx

from jqdata import *
import datetime
import math
import numpy as np
import pandas as pd  # 【修复1】补充了 pandas，否则 DataFrame 会报错
import re
from scipy.optimize import minimize
from scipy.linalg import inv
import uuid

# etf_pool = [
#     # 境外
#     "513100.XSHG", # 纳指ETF（跟踪纳斯达克100指数）
#     "513520.XSHG", # 日经ETF（跟踪日经225指数）
#     "513030.XSHG", # 德国ETF（跟踪德国DAX30指数）
#     # 商品
#     "518880.XSHG", # 黄金ETF（跟踪黄金现货价格）
#     "159985.XSHE", # 豆粕ETF（跟踪豆粕期货价格）
#     "501018.XSHG", # 南方原油（投资原油相关资产）
#     # 国内及港股
#     "513130.XSHG", # 恒生科技ETF（跟踪恒生科技指数）
#     "510180.XSHG", # 华安上证180ETF（跟踪上证180指数）
#     "512290.XSHG", # 国泰中证生物医药ETF（跟踪生物医药指数）
#     "588120.XSHG", # 华夏上证科创板50ETF（跟踪科创板50指数）
#     "515070.XSHG", # 华泰柏瑞中证光伏产业ETF（跟踪光伏产业指数）
#     # 新增补充（无高度重叠项）
#     "159845.XSHE", # 华夏中证1000ETF（跟踪中证1000指数，小盘宽基）
#     "512480.XSHG", # 半导体ETF（跟踪半导体指数，细分科技赛道）
#     "159806.XSHE", # 国泰中证新能源汽车ETF（聚焦新能源汽车全产业链）
#     "516160.XSHG", # 南方中证新能源ETF（覆盖光伏、风电、储能等新能源全产业链）
#     "159928.XSHE", # 汇添富中证主要消费ETF（跟踪主要消费指数，覆盖食品饮料、家电等）
# ]
etf_pool = [
    # ===== 境外资产 =====
    "513100.XSHG", # 纳指ETF (核心避险/长牛)
    "513520.XSHG", # 日经ETF (海外轮动)
    "513030.XSHG", # 德国ETF (欧洲代表)
    
    # ===== 大宗商品 =====
    "518880.XSHG", # 黄金ETF (避险/低相关性)
    "159985.XSHE", # 豆粕ETF (农产品/抗通胀)
    "501018.XSHG", # 南方原油 (能源周期)
    
    # ===== 国内宽基与成长赛道 =====
    "513130.XSHG", # 恒生科技ETF (高弹性港股)
    "510180.XSHG", # 上证180ETF (价值蓝筹)
    "159845.XSHE", # 中证1000ETF (小盘成长)
    "588120.XSHG", # 科创100 (硬科技)
    
    # ===== 行业/主题 (曾经的赢家) =====
    "512480.XSHG", # 半导体ETF (科技主线)
    "512290.XSHG", # 生物医药 (长坡厚雪)
    "515070.XSHG", # 光伏产业 (周期成长)
    "159806.XSHE", # 新能源车 (产业链代表)
    "516160.XSHG", # 新能源 (清洁能源)
    "159928.XSHE", # 主要消费 (白马股防御)
    "516510.XSHG", # 云计算ETF    (2026 AI 应用爆发的直接受益者)
    "159770.XSHE", # 机器人ETF    (2026 具身智能元年，高弹性 Beta)
    "510880.XSHG", # 红利ETF      (2026 终极防御，抗衡科技股共振风险)
    
    # ===== 压力测试 (用于排除后视镜偏差的“毒药”) =====
    # "512200.XSHG", # 房地产ETF (测试：单边阴跌能否全程空仓？)
    # "159992.XSHE", # 创新药ETF (测试：低位阴跌伴随假反弹，是否会反复割肉？)
    # "512660.XSHG", # 军工ETF   (测试：高波动/无序震荡下，R2和成交量过滤是否生效？)
    # "512000.XSHG", # 证券ETF   (测试：脉冲行情/爆量诱多，滑点磨损是否会吃掉本金？)
    # "512980.XSHG", # 传媒ETF   (测试：曾经的大牛股进入长期熊市，动量是否能及时掉头？)
]

# 全局变量
g_strategys = {}
g_portfolio_value_proportion = [1]  # 测试版
g_positions = {i: {} for i in range(len(g_portfolio_value_proportion))}  # 记录每个子策略的持仓股票
g_weights = {}  # 全天候权重
g.channel = 'etfld'  # 请保持和ThsAutoTrader里面的channel一

# 核心资产轮动策略相关参数
g_etf_rotation = {
    "index": 0,
    "name": "核心资产轮动策略",
    "stock_sum": 1,
    "hold_list": [],
    "min_money": 500,  # 最小交易额(限制手续费)
    "etf_pool": etf_pool,
    "m_days": 25,  # 动量参考天数
    
    "enable_volume_check": False,  # 是否启用成交量检测
    "volume_lookback": 5,  # 历史成交量参考天数（默认20天）
    "volume_threshold": 2.0,  # 放量阈值（当日成交量/历史平均 > 该值视为放量）
    
    "ma_filter_days": 20,  # 均线过滤天数（可自定义）
    "enable_ma_filter": False,  # 是否启用均线过滤
    
    # ---- 新增：跌幅限制开关 ----
    "enable_drop_limit": False, 
    
    # ---- 量价背离顶部识别参数 ----
    "enable_vol_divergence_filter": False,   # 是否启用量价背离过滤
    "vol_recent_days": 3,                   # 近期成交量观察窗口（天）
    "vol_baseline_days": 10,                # 历史基准成交量窗口（天，紧接近期之前）
    "vol_shrink_ratio": 0.7,                # 缩量阈值：近期均量 / 基准均量 < 该比值触发
    "price_high_percentile": 0.80,          # 价格高位判定：当前价在动量周期内超过该分位数时才检测
    "verbose_etf_filter_log": True,         # 是否打印每只ETF的筛选明细（代码/名称/得分/R2/过滤原因）
}

############打开星球
def order_(context, security, vol):  # 只保留3个必要参数
    o = order(security, vol)
    return o

def _normalize_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(v)

def _sync_backtest_extras(context):
    global g_etf_rotation
    keys = (
        "enable_drop_limit",
        "enable_vol_divergence_filter",
        "enable_volume_check",
        "enable_ma_filter",
    )
    loaded = {}
    source = []

    # 1) 先尝试从 g.xxx 读取（JoinQuant create_backtest 常见注入方式）
    for key in keys:
        if hasattr(g, key):
            loaded[key] = getattr(g, key)
            source.append(f"g.{key}")

    # 2) 再尝试从 context.run_params 读取（不同环境下可能在这里）
    run_params = getattr(context, "run_params", None)
    if run_params is not None:
        try:
            extras = run_params.get("extras", {}) if isinstance(run_params, dict) else getattr(run_params, "extras", {})
            if isinstance(extras, dict):
                for key in keys:
                    if key in extras:
                        loaded[key] = extras[key]
                        source.append(f"run_params.extras.{key}")
        except Exception as e:
            log.info(f"[参数同步] run_params 读取异常: {e}")

        # 3) 兜底：从回测名称中的编码标签解析
        # 标签格式：__CFG_D1_V0_Q1_M1
        token_text = ""
        try:
            if isinstance(run_params, dict):
                for field in ("name", "backtest_name", "note", "memo", "desc", "description"):
                    value = run_params.get(field)
                    if value:
                        token_text += f" {value}"
            else:
                for field in ("name", "backtest_name", "note", "memo", "desc", "description"):
                    value = getattr(run_params, field, None)
                    if value:
                        token_text += f" {value}"
            token_text += f" {run_params}"
        except Exception:
            pass

        m = re.search(r"__CFG_D([01])_V([01])_Q([01])_M([01])", token_text)
        if m:
            loaded["enable_drop_limit"] = bool(int(m.group(1)))
            loaded["enable_vol_divergence_filter"] = bool(int(m.group(2)))
            loaded["enable_volume_check"] = bool(int(m.group(3)))
            loaded["enable_ma_filter"] = bool(int(m.group(4)))
            source.append("name_cfg_tag")

    for key, value in loaded.items():
        g_etf_rotation[key] = _normalize_bool(value)

    return loaded, source

def initialize(context):
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    
    # 1. 声明全局变量
    global g_etf_rotation
    loaded_params, loaded_source = _sync_backtest_extras(context)

    # 打印日志（这是验证参数是否传成功的唯一标准，请务必查看回测日志）
    log.info("="*30)
    log.info(f"回测启动参数确认:")
    log.info(f"收到 extras 参数: {loaded_params if loaded_params else '无'}")
    log.info(f"参数来源: {loaded_source if loaded_source else '无'}")
    log.info(f"run_params快照: {getattr(context, 'run_params', '无')}")
    log.info(f"跌5%开关: {g_etf_rotation['enable_drop_limit']}")
    log.info(f"背离开关: {g_etf_rotation['enable_vol_divergence_filter']}")
    log.info(f"放量开关: {g_etf_rotation['enable_volume_check']}")
    log.info(f"均线过滤开关: {g_etf_rotation['enable_ma_filter']}")
    log.info("="*30)
    set_slippage(FixedSlippage(0.003), type="fund")
    set_slippage(FixedSlippage(0.003), type="stock")
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.001,
            open_commission=0.0003,
            close_commission=0.0003,
            close_today_commission=0,
            min_commission=5,
        ),
        type="stock",
    )
    # 设置货币ETF交易佣金0
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0,
            open_commission=0,
            close_commission=0,
            close_today_commission=0,
            min_commission=0,
        ),
        type="mmf",
    )
    
    if g_portfolio_value_proportion[0] > 0:
        # 10:30执行卖出操作
        run_daily(etf_rotation_sell, "10:23")
        # 11:00执行买入操作
        run_daily(etf_rotation_buy, "10:25")
    # 每日剩余资金购买货币ETF（保持不变）
    run_daily(end_trade, "14:59")

def process_initialize(context):
    print("重启程序")
    global g_strategys, g_positions
    g_strategys = {
        "核心资产轮动策略": {
            "index": 0,
            "name": "核心资产轮动策略"
        }
    }
    strategy = g_etf_rotation
    idx = strategy["index"]
    pool = set(strategy["etf_pool"])
    g_positions[idx] = {}
    for sec, pos in context.portfolio.positions.items():
        if pos.total_amount > 0 and sec in pool:
            g_positions[idx][sec] = pos.total_amount
    strategy["hold_list"] = list(g_positions[idx].keys())

# 尾盘处理
def end_trade(context):
    marked = {s for d in g_positions.values() for s in d}
    current_data = get_current_data()
    for stock in context.portfolio.positions:
        if stock not in marked:
            price = current_data[stock].last_price
            pos = context.portfolio.positions[stock].total_amount
            if my_order(context,stock, -pos, price, 0):
                log.info(f"卖出{stock}因送股未记录在持仓中", price, pos)

def my_order(context,security, vol, price, target_position):
    o = order_(context,security, vol)
    return o

# 核心资产轮动策略实现
def get_etf_rotation_total_value(context):
    index = g_etf_rotation["index"]
    if not g_positions[index]:
        return 0
    return sum(context.portfolio.positions[key].price * value 
              for key, value in g_positions[index].items())

def etf_rotation_order_target_value(context, security, value):
    strategy = g_etf_rotation
    current_data = get_current_data()

    # 检查标的是否停牌、涨停、跌停
    if current_data[security].paused:
        log.info(f"{security}: 今日停牌")
        return False
    if current_data[security].last_price == current_data[security].high_limit:
        log.info(f"{security}: 当前涨停")
        return False
    if current_data[security].last_price == current_data[security].low_limit:
        log.info(f"{security}: 当前跌停")
        return False

    # 获取当前标的的价格
    price = current_data[security].last_price
    # 获取当前策略的持仓数量
    current_position = g_positions[strategy["index"]].get(security, 0)
    # 所有策略中持仓数量
    current_position_all = context.portfolio.positions[security].total_amount if security in context.portfolio.positions else 0
    # 计算目标持仓数量
    target_position = (int(value / price) // 100) * 100 if price != 0 else 0
    # 计算需要调整的数量
    adjustment = target_position - current_position
    target_position_all = current_position_all + adjustment

    # 检查是否当天买入卖出
    closeable_amount = context.portfolio.positions[security].closeable_amount if security in context.portfolio.positions else 0
    if adjustment < 0 and closeable_amount == 0:
        log.info(f"{security}: 当天买入不可卖出")
        return False

    # 下单并更新持仓
    if adjustment != 0:
        o = my_order(context, security, adjustment, price, target_position_all)
        if o:
            # 更新持仓数量
            filled = o.filled if o.is_buy else -o.filled
            g_positions[strategy["index"]][security] = filled + current_position
            # 如果当前持仓为零，移除该证券
            if g_positions[strategy["index"]][security] == 0:
                g_positions[strategy["index"]].pop(security, None)
            # 更新持有列表
            strategy["hold_list"] = list(g_positions[strategy["index"]].keys())
            return True
    return False

def etf_rotation_filter(context):
    strategy = g_etf_rotation
    pool = list(strategy["etf_pool"])
    ma_days = strategy["ma_filter_days"]
    m_days = strategy["m_days"]
    # 1. 均线过滤：得到可交易子集 + 每只标的均线诊断（用于日志）
    if strategy["enable_ma_filter"]:
        filtered_pool, ma_details = filter_below_ma(stocks=pool, days=ma_days)
        log.info(
            f"[ETF筛选] 均线({ma_days}日)后剩余 {len(filtered_pool)}/{len(pool)} 只"
        )
    else:
        filtered_pool = pool
        ma_details = {
            s: {
                "pass_ma": True,
                "ma_n": None,
                "current_price": None,
                "reason": "均线过滤已关闭",
            }
            for s in pool
        }
    # 2. 全池计算动量/得分（指数用完整池，避免均线未过却仍入选）
    data = pd.DataFrame(
        index=pool,
        columns=["annualized_returns", "r2", "score"],
        dtype=float,
    )
    current_data = get_current_data()
    log_rows = []
    for etf in pool:
        name = current_data[etf].name
        md = ma_details.get(
            etf,
            {
                "pass_ma": False,
                "ma_n": None,
                "current_price": None,
                "reason": "无均线数据",
            },
        )
        fetch_days = m_days + strategy["vol_baseline_days"] + strategy["vol_recent_days"]
        df = attribute_history(etf, fetch_days, "1d", ["close", "high", "volume"])
        prices = np.append(df["close"].values, current_data[etf].last_price)
        momentum_prices = prices[-(m_days + 1) :]
        y = np.log(momentum_prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(slope * 250) - 1
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r2_val = 1 - ss_res / ss_tot if ss_tot else 0.0
        momentum_score = annualized_returns * r2_val
        score = float(momentum_score)
        min_3d_ratio = None
        drop_triggered = False
        
        if len(prices) >= 4:
            min_3d_ratio = float(
                min(
                    prices[-1] / prices[-2],
                    prices[-2] / prices[-3],
                    prices[-3] / prices[-4],
                )
            )
            # 【修复】：加入 enable_drop_limit 开关控制
            if strategy.get("enable_drop_limit", True) and min_3d_ratio < 0.95:
                score = 0.0
                drop_triggered = True
                
        vol_div_triggered = False
        price_percentile = None
        vol_recent = vol_baseline = None
        vol_ratio_vb = None
        if strategy.get("enable_vol_divergence_filter", True) and score > 0:
            try:
                recent_n = strategy["vol_recent_days"]
                baseline_n = strategy["vol_baseline_days"]
                shrink_thr = strategy["vol_shrink_ratio"]
                high_pct = strategy["price_high_percentile"]
                vols = df["volume"].values
                vol_recent = float(vols[-recent_n:].mean())
                vol_baseline = float(vols[-(recent_n + baseline_n) : -recent_n].mean())
                momentum_close = df["close"].values[-(m_days):]
                price_percentile = float(
                    np.mean(momentum_close <= current_data[etf].last_price)
                )
                at_price_high = price_percentile >= high_pct
                volume_shrinking = (vol_baseline > 0) and (
                    vol_recent / vol_baseline < shrink_thr
                )
                vol_ratio_vb = (
                    vol_recent / vol_baseline if vol_baseline > 0 else None
                )
                if at_price_high and volume_shrinking:
                    score = 0.0
                    vol_div_triggered = True
            except Exception as e:
                log.debug(f"[量价背离] {etf} 检测异常（跳过）: {e}")
                
        score_before_ma = float(score)
        if strategy["enable_ma_filter"] and not md["pass_ma"]:
            score = 0.0
        data.loc[etf, "annualized_returns"] = annualized_returns
        data.loc[etf, "r2"] = r2_val
        data.loc[etf, "score"] = score
        band_ok = 0 < score < 5
        reasons = []
        if strategy["enable_ma_filter"] and not md["pass_ma"]:
            reasons.append("均线未过")
        if drop_triggered:
            reasons.append("近3日有一日跌超5%")
        if vol_div_triggered:
            reasons.append("量价背离顶部")
        if score <= 0:
            if not reasons:
                reasons.append("得分为0")
        elif score >= 5:
            reasons.append("得分≥5超出区间")
        if band_ok:
            status_short = "候选"
        elif (
            strategy["enable_ma_filter"]
            and not md["pass_ma"]
            and 0 < score_before_ma < 5
        ):
            status_short = "均线挡"
        else:
            status_short = "落选"
        reason_str = "；".join(reasons) if reasons else "—"
        log_rows.append(
            {
                "代码": etf,
                "名称": name,
                "状态": status_short,
                "过滤原因": reason_str,
                "动量分": round(momentum_score, 6),
                "排序分": round(score, 6),
                "年化收益": round(annualized_returns, 4),
                "R2": round(r2_val, 4),
                "斜率": round(slope, 6),
                "均线过": "是" if md["pass_ma"] else "否",
                "现价": (
                    round(md["current_price"], 4)
                    if md["current_price"] is not None
                    else ""
                ),
                "N日均": (
                    round(md["ma_n"], 4) if md["ma_n"] is not None else ""
                ),
                "3日价比": (
                    round(min_3d_ratio, 4)
                    if min_3d_ratio is not None
                    else ""
                ),
                "价分位%": (
                    round(price_percentile * 100, 2)
                    if price_percentile is not None
                    else ""
                ),
                "近远量比": (
                    round(vol_ratio_vb, 4)
                    if vol_ratio_vb is not None
                    else ""
                ),
            }
        )
    if strategy.get("verbose_etf_filter_log", True) and log_rows:
        log_df = pd.DataFrame(log_rows)
        log_df = log_df.sort_values("排序分", ascending=False)
        with pd.option_context(
            "display.max_rows", None,
            "display.max_columns", None,
            "display.width", 320,
            "display.max_colwidth", 28,
            "display.unicode.east_asian_width", True,
        ):
            table_text = log_df.to_string(index=False)
        ma_hdr = (
            f"均线({ma_days}日)后 {len(filtered_pool)}/{len(pool)} 只"
            if strategy["enable_ma_filter"]
            else "均线过滤关闭"
        )
        log.info(
            f"[ETF筛选] {ma_hdr} | m_days={m_days} | "
            f"背离:价分位≥{strategy['price_high_percentile']:.0%}且"
            f"近{strategy['vol_recent_days']}d/基{strategy['vol_baseline_days']}d量比<{strategy['vol_shrink_ratio']}\n"
            f"{table_text}"
        )
    # 过滤ETF，并按得分降序排列
    data = data.query("0 < score < 5").sort_values(by="score", ascending=False)
    ranked = data.index.tolist()
    log.info(f"[ETF筛选] 区间(0<score<5) 入选共 {len(ranked)} 只，按得分降序: {ranked}")
    return ranked

# 仅执行卖出操作（10:30触发）- 精简日志
def etf_rotation_sell(context):
    strategy = g_etf_rotation
    targets = etf_rotation_filter(context)[: strategy["stock_sum"]]
    current_data = get_current_data()
    hold_list = list(g_positions[strategy["index"]].keys())
    
    # 1. 优先卖出放量的持仓ETF（若启用成交量检测）
    if strategy.get("enable_volume_check", True):
        for stock in list(hold_list): # 【修复3】使用 list() 包裹，防止循环移除时跳过元素
            vol_ratio = get_volume_ratio(
                context,
                stock,
                strategy["volume_lookback"],
                strategy["volume_threshold"]
            )
            if vol_ratio is not None:
                # 放量，强制卖出
                log.info(f"持仓 {stock} 放量（比值：{vol_ratio:.2f}），触发卖出")
                etf_rotation_order_target_value(context, stock, 0)
                # 从持仓列表中移除（避免重复处理）
                if stock in hold_list:
                    hold_list.remove(stock)

    # 清仓不在目标列表中的标的
    for stock in hold_list:
        if stock not in targets:
            current_pos = g_positions[strategy["index"]].get(stock, 0)
            price = current_data[stock].last_price
            sell_amount = current_pos * price
            etf_rotation_order_target_value(context, stock, 0)
            
    # 若持仓超标，卖出目标列表中排名靠后的
    current_hold_in_targets = [s for s in hold_list if s in targets]
    if len(current_hold_in_targets) > strategy["stock_sum"]:
        for stock in current_hold_in_targets[strategy["stock_sum"]:]:
            current_pos = g_positions[strategy["index"]].get(stock, 0)
            price = current_data[stock].last_price
            sell_amount = current_pos * price
            etf_rotation_order_target_value(context, stock, 0)

# 仅执行买入操作（11:00触发）- 精简日志
def etf_rotation_buy(context):
    strategy = g_etf_rotation
    # 1. 获取初始候选ETF
    raw_targets = etf_rotation_filter(context)[: strategy["stock_sum"]]
    if not raw_targets:
        return
    
    # 2. 过滤放量的候选ETF（若启用成交量检测）
    targets = []
    if strategy.get("enable_volume_check", True):
        for etf in raw_targets:
            vol_ratio = get_volume_ratio(
                context,
                etf,
                strategy["volume_lookback"],
                strategy["volume_threshold"]
            )
            if vol_ratio is None:
                # 未放量或检测失败，保留为候选
                targets.append(etf)
            else:
                log.info(f"排除买入 {etf}（放量，比值：{vol_ratio:.2f}）")
    else:
        targets = raw_targets  # 不启用检测，直接使用初始候选

    if not targets:
        log.info("无符合条件的买入标的（均放量）")
        return
    
    current_data = get_current_data()
    portfolio = context.portfolio
    hold_list = list(g_positions[strategy["index"]].keys())
    current_hold_in_targets = [s for s in hold_list if s in targets]
    current_hold_count = len(current_hold_in_targets)
    
    total_value = portfolio.total_value
    available_cash = portfolio.available_cash
    target_value = total_value * g_portfolio_value_proportion[strategy["index"]]
    
    for stock in targets:
        stock_name = current_data[stock].name
        weight = 1 / len(targets)
        target = target_value * weight
        last_price = current_data[stock].last_price
        current_position = g_positions[strategy["index"]].get(stock, 0)
        current_value = current_position * last_price
        
        if current_hold_count == 0:
            # 未持仓，计算买入需求
            need_buy_value = target - current_value
            actual_buy_value = min(need_buy_value, available_cash)
            if actual_buy_value <= max(strategy["min_money"], last_price * 100):
                continue
            # 执行买入
            order_price = last_price * 1.005
            actual_order_amount = etf_rotation_order_target_value(context, stock, target)
        else:
            # 已持仓，判断是否补仓
            if current_value < target * 0.9:
                rebalance_amount = target - current_value
                actual_rebalance = min(rebalance_amount, available_cash)
                if actual_rebalance > max(strategy["min_money"], last_price * 100):
                    order_price = last_price * 1.005
                    actual_rebalance_amount = etf_rotation_order_target_value(context, stock, target)

def get_volume_ratio(context, security, lookback_days, threshold):
    try:
        hist_data = attribute_history(security, lookback_days, '1d', ['volume'])
        if hist_data.empty or len(hist_data) < lookback_days:
            return None
        avg_volume = hist_data['volume'].mean()
        today = context.current_dt.date()
        df_vol = get_price(
            security,
            start_date=today,
            end_date=context.current_dt,
            frequency='1m',
            fields=['volume'],
            skip_paused=False,
            fq='pre',
            panel=True,
            fill_paused=False
        )
        if df_vol is None or df_vol.empty:
            return None
        current_volume = df_vol['volume'].sum()
        volume_ratio = current_volume / avg_volume
        return volume_ratio if volume_ratio > threshold else None
    except Exception as e:
        log.warning(f"成交量检测失败 {security}：{e}")
        return None
        
def filter_below_ma(stocks, days=20):
    if not stocks:
        return [], {}
    current_data = get_current_data()
    filtered = []
    details = {}
    for stock in stocks:
        try:
            hist = attribute_history(stock, days, "1d", ["close"])
            cur = current_data[stock].last_price
            if len(hist) < days:
                details[stock] = {
                    "pass_ma": False,
                    "ma_n": None,
                    "current_price": float(cur),
                    "reason": f"历史不足{days}日",
                }
                continue
            ma_n = float(hist["close"].mean())
            current_price = float(cur)
            if current_price >= ma_n:
                filtered.append(stock)
                details[stock] = {
                    "pass_ma": True,
                    "ma_n": ma_n,
                    "current_price": current_price,
                    "reason": "站上均线",
                }
            else:
                details[stock] = {
                    "pass_ma": False,
                    "ma_n": ma_n,
                    "current_price": current_price,
                    "reason": f"未站上均线(现{current_price:.4g}<{days}日均{ma_n:.4g})",
                }
        except Exception as e:
            log.warning(f"计算{stock} {days}日均价失败: {e}")
            try:
                cur = current_data[stock].last_price
            except Exception:
                cur = None
            details[stock] = {
                "pass_ma": False,
                "ma_n": None,
                "current_price": float(cur) if cur is not None else None,
                "reason": f"均线计算异常:{e}",
            }
    return filtered, details