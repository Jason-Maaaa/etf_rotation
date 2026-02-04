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
# 作者：阿萨德szx

# 克隆自聚宽文章：https://www.joinquant.com/post/62057
# 标题：【ETF轮动更新】增加20%收益-手动构建ET池
# 作者：阿萨德szx

from jqdata import *
import datetime
import math
import numpy as np
from scipy.optimize import minimize
from scipy.linalg import inv
import uuid

# from jqtoqmt import *
# g.strategy = 'jq1'  # 策略名
# order = qmt_order(order)
# order_target = qmt_order_target(order_target)
# order_value = qmt_order_value(order_value)
# order_target_value = qmt_order_target_value(order_target_value)


# etf_pool_config.py
etf_pool = [
            #境外
            "513100.XSHG",  # 纳指ETF
            "159509.XSHE",  # 纳指科技ETF
            "513520.XSHG",  # 日经ETF
            "513030.XSHG",  # 德国ETF
            # 商品
            "518880.XSHG",  # 黄金ETF
            "159980.XSHE",  # 有色ETF
            "159985.XSHE",  # 豆粕ETF
            "159981.XSHE",  # 能源化工ETF
            #"159870.XSHE",   # 化工
            
            "501018.XSHG",  # 南方原油
            # 债券
             "511090.XSHG",  # 30年国债ETF
            # 国内
            "513130.XSHG",  # 恒生科技
            "513690.XSHG",  # 港股红利
            
            
            "510180.XSHG",   #上证180
            "159915.XSHE",   #创业板ETF
            
            
            "510410.XSHG",   #资源
            "515650.XSHG",   #消费50
            "512290.XSHG",   #生物医药
            "588120.XSHG",   #科创100
            "515070.XSHG",   #人工智能ETF
            
            "159851.XSHE",   #金融科技
            "159637.XSHE",   #新能源车
            "516160.XSHG",   #新能源
            
            "159550.XSHE",   #互联网ETF
            "512710.XSHG",   #军工ETF
            "159692.XSHE",   #证券
            "512480.XSHG",   #半导体
            "515250.XSHG",    #智能汽车
            "159378.XSHE",     #通用航空
            "516510.XSHG",    #云计算
            "515050.XSHG",     #5G通信
            "159995.XSHE",     #芯片 
            "515790.XSHG",     #光伏
            "515000.XSHG"   #科技
            
            
        ]


# etf_pool = small_etf_pool = [
#     "513100.XSHG",  # 纳指ETF
#     "159915.XSHE",  # 创业板ETF  
#     "518880.XSHG",  # 黄金ETF
#     "511090.XSHG",  # 国债ETF
# ]  # 只保



# etf_pool = [
# # 境外
# "513100.XSHG", # 纳指ETF（跟踪纳斯达克100指数）
# "513520.XSHG", # 日经ETF（跟踪日经225指数）
# "513030.XSHG", # 德国ETF（跟踪德国DAX30指数）
# # 商品
# "518880.XSHG", # 黄金ETF（跟踪黄金现货价格）
# "159985.XSHE", # 豆粕ETF（跟踪豆粕期货价格）
# "501018.XSHG", # 南方原油（投资原油相关资产）
# # 国内及港股
# "513130.XSHG", # 恒生科技ETF（跟踪恒生科技指数）
# "510180.XSHG", # 华安上证180ETF（跟踪上证180指数）

# "512290.XSHG", # 国泰中证生物医药ETF（跟踪生物医药指数）
# "588120.XSHG", # 华夏上证科创板50ETF（跟踪科创板50指数）
# "515070.XSHG", # 华泰柏瑞中证光伏产业ETF（跟踪光伏产业指数）

# # 新增补充（无高度重叠项）
# "159845.XSHE", # 华夏中证1000ETF（跟踪中证1000指数，小盘宽基）
# "512480.XSHG", # 半导体ETF（跟踪半导体指数，细分科技赛道）
# "159806.XSHE", # 国泰中证新能源汽车ETF（聚焦新能源汽车全产业链）
# "516160.XSHG", # 南方中证新能源ETF（覆盖光伏、风电、储能等新能源全产业链）
# # "159928.XSHE", # 汇添富中证主要消费ETF（跟踪主要消费指数，覆盖食品饮料、家电等）

# ]






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
    
    
    "enable_volume_check": True,  # 是否启用成交量检测
    "volume_lookback": 5,  # 历史成交量参考天数（默认20天）
    "volume_threshold": 2.0,  # 放量阈值（当日成交量/历史平均 > 该值视为放量）
    
    
    "ma_filter_days": 20,  # 均线过滤天数（可自定义）
    "enable_ma_filter": True,  # 是否启用均线过滤
}

############打开星球
def order_(context, security, vol):  # 只保留3个必要参数
    o = order(security, vol)
    return o
    
    
def initialize(context):
    set_option("avoid_future_data", True)  # 打开防未来函数
    set_option("use_real_price", True)  # 开启动态复权模式(真实价格)
    log.info("初始函数开始运行且全局只运行一次")
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')
    set_slippage(FixedSlippage(0.0001), type="fund")
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
        run_daily(etf_rotation_sell, "10:29")
        # 11:00执行买入操作
        run_daily(etf_rotation_buy, "10:30")
    # 每日剩余资金购买货币ETF（保持不变）
    run_daily(end_trade, "14:59")

def process_initialize(context):
    print("重启程序")
    global g_strategys
    g_strategys = {
        "核心资产轮动策略": {
            "index": 0,
            "name": "核心资产轮动策略"
        }
    }


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




def get_etf_premium_rate_real(context,etf_code):
    """
    在实盘中计算ETF基金的溢价率
    etf_code: ETF代码，如 '510050.XSHG'
    """
    # 获取当前数据对象
    etf_price = get_price(etf_code, start_date=context.previous_date, end_date=context.previous_date).iloc[-1]['close']
    iopv = get_extras('unit_net_value',etf_code, start_date=context.previous_date, end_date=context.previous_date).iloc[-1].values[0]
    
    #  计算溢价率
    if iopv is not None and iopv != 0:
        premium_rate = (etf_price - iopv) / iopv * 100
    else:
        premium_rate = 0

    return premium_rate, etf_price, iopv













def etf_rotation_filter(context):
    strategy = g_etf_rotation
    # 1. 先对原始ETF池进行均线过滤（在动量计算前）
    filtered_pool = strategy["etf_pool"]  # 原始ETF池
    if strategy["enable_ma_filter"]:
        # 调用均线过滤函数，筛选出当前价 >= N日均价的ETF
        filtered_pool = filter_below_ma(
            stocks=filtered_pool,
            days=strategy["ma_filter_days"]
        )
    
    # 2. 仅对过滤后的ETF池计算动量评分
    data = pd.DataFrame(index=filtered_pool, 
                       columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    
    for etf in strategy["etf_pool"]:
        # 移除成交量异常检查的所有代码
        
        # 获取历史数据并计算当前价格
        df = attribute_history(etf, strategy["m_days"], "1d", ["close", "high"])
        prices = np.append(df["close"].values, current_data[etf].last_price)

        # 设置参数
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        # 计算年化收益率
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        # 计算R²
        ss_res = np.sum(weights * (y - (slope * x + intercept)) **2)
        ss_tot = np.sum(weights * (y - np.mean(y))** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        # 计算得分
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        # 过滤近3日跌幅超过5%的ETF
        if len(prices) >= 4 and min(prices[-1]/prices[-2], prices[-2]/prices[-3], prices[-3]/prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0
        
        
        # # 风控
        # # 三天内有一天跌超5%
        # con1 = min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95
        # # 三天内每天都跌，总共跌超4%
        # con2 = (prices[-1]< prices[-2])&(prices[-2]< prices[-3])&(prices[-3]< prices[-4])&(prices[-1]/prices[-4]< 0.95)
        # # 三天内每天都跌，总共跌超4%
        # con3 = (prices[-2]< prices[-3])&(prices[-3]< prices[-4])&(prices[-4]< prices[-5])&(prices[-2]/prices[-5]< 0.95)
        # # 后面也可以增加其他情况，比如近4天，近5天等
        # 过滤近期跌幅过大的ETF
        # if con1|con2|con3:
        #     data.loc[etf, "score"] = 0 
        
        # # 过滤溢价率超过6%的
        # if get_etf_premium_rate_real(context,etf)[0]>=6:
        #     data.loc[etf, "score"] = data.loc[etf, "score"]-1
    
    # 过滤ETF，并按得分降序排列
    data = data.query("0 < score < 5").sort_values(by="score", ascending=False)

    log.info(f"{'代码':<8} {'名称':<8} {'价格':<8} {'MA20':<8} {'5日涨跌':<8} {'波动率':<8} {'状态':<6} {'得分':<8} {'r2':<8} {'年化收益率':<8}")
    for etf in data.head(5).index:
        name = current_data[etf].name
        price = current_data[etf].last_price
        
        hist = attribute_history(etf, 25, '1d', ['close'])
        ma20 = hist['close'][-20:].mean() if len(hist) >= 20 else 0
        
        if len(hist) >= 6:
            prev_close_5 = hist['close'].iloc[-5]
            pct_5d = (price / prev_close_5 - 1) * 100
        else:
            pct_5d = 0
            
        if len(hist) >= 20:
             returns = hist['close'][-20:].pct_change().dropna()
             volatility = returns.std() * np.sqrt(250) * 100
        else:
             volatility = 0
        
        status = "📈多头" if price > ma20 else "📉空头"
        
        score_val = data.loc[etf, 'score']
        r2_val = data.loc[etf, 'r2']
        ann_ret = data.loc[etf, 'annualized_returns']
        
        log.info(f"{etf[:6]:<8} {name:<8} {price:<8.3f} {ma20:<8.3f} {pct_5d:>7.2f}% {volatility:>7.2f}% {status:<6} {score_val:<8.4f} {r2_val:<8.4f} {ann_ret:<8.4f}")

    return data.index.tolist()



# 通用工具函数
def filter_untradeable_stock(stocks):
    current_data = get_current_data()
    return [
        stock
        for stock in stocks
        if current_data[stock].paused or current_data[stock].last_price in 
           (current_data[stock].high_limit, current_data[stock].low_limit)
    ]


def check_etf_rotation_holdings(context):
    strategy = g_etf_rotation
    hold = list(g_positions[strategy["index"]].keys())
    if not hold:
        return []
    current_data = get_current_data()
    filtered = filter_limitup_stock(hold, 3)
    return [s for s in hold if s not in filtered and current_data[s].last_price < current_data[s].high_limit]


    
    
    
# 新增：仅执行卖出操作（10:30触发）
# 仅执行卖出操作（10:30触发）- 精简日志
def etf_rotation_sell(context):
    strategy = g_etf_rotation
    targets = etf_rotation_filter(context)[: strategy["stock_sum"]]
    current_data = get_current_data()
    hold_list = list(g_positions[strategy["index"]].keys())
    
    # 1. 优先卖出放量的持仓ETF（若启用成交量检测）
    if strategy["enable_volume_check"]:
        for stock in hold_list:
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
        # log.info(f"持仓超标（当前{len(current_hold_in_targets)}只，上限{strategy['stock_sum']}只），卖出排名靠后标的")
        for stock in current_hold_in_targets[strategy["stock_sum"]:]:
            current_pos = g_positions[strategy["index"]].get(stock, 0)
            price = current_data[stock].last_price
            sell_amount = current_pos * price
            etf_rotation_order_target_value(context, stock, 0)
            # log.info(f"卖出排名靠后标的：{stock}（{current_data[stock].name}），数量: {current_pos}股，金额: {sell_amount:.2f}元")
    
   
   

# 仅执行买入操作（11:00触发）- 精简日志
def etf_rotation_buy(context):
    strategy = g_etf_rotation
    # 1. 获取初始候选ETF
    raw_targets = etf_rotation_filter(context)[: strategy["stock_sum"]]
    if not raw_targets:
        return
    
    # 2. 过滤放量的候选ETF（若启用成交量检测）
    targets = []
    if strategy["enable_volume_check"]:
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
        
       
        # log.info(f"最新价: {last_price:.3f}元，目标市值: {target:.2f}元，当前市值: {current_value:.2f}元")
        
        if current_hold_count == 0:
            # 未持仓，计算买入需求
            need_buy_value = target - current_value
            actual_buy_value = min(need_buy_value, available_cash)
            if actual_buy_value <= max(strategy["min_money"], last_price * 100):
                # log.info(f"买入金额不足（需{need_buy_value:.2f}元，可用{available_cash:.2f}元），跳过")
                continue
            
            # 执行买入
            order_price = last_price * 1.005
            actual_order_amount = etf_rotation_order_target_value(context, stock, target)
            # log.info(f"买入：计划金额{actual_buy_value:.2f}元，订单价{order_price:.3f}元，实际数量{actual_order_amount}股")
        
        else:
            # 已持仓，判断是否补仓
            if current_value < target * 0.9:
                rebalance_amount = target - current_value
                actual_rebalance = min(rebalance_amount, available_cash)
                if actual_rebalance > max(strategy["min_money"], last_price * 100):
                    order_price = last_price * 1.005
                    actual_rebalance_amount = etf_rotation_order_target_value(context, stock, target)
                    # log.info(f"补仓：需{rebalance_amount:.2f}元，订单价{order_price:.3f}元，实际数量{actual_rebalance_amount}股")
                
                
                
                
                
                
                
                
                
                
                
def get_volume_ratio(context, security, lookback_days, threshold):
    """
    计算标的成交量比值（当日成交量/历史平均成交量）
    返回：若放量（>threshold）则返回比值，否则返回None，异常时返回None
    """
    try:
        # 1. 获取历史成交量（N天平均）
        hist_data = attribute_history(security, lookback_days, '1d', ['volume'])
        if hist_data.empty or len(hist_data) < lookback_days:
            return None
        avg_volume = hist_data['volume'].mean()

        # 2. 获取当日实时成交量（分钟数据累加）
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

        # 3. 超过阈值视为放量
        return volume_ratio if volume_ratio > threshold else None
    except Exception as e:
        log.warning(f"成交量检测失败 {security}：{e}")
        return None
        
def filter_below_ma(stocks, days=20):
    """
    过滤掉当前价格小于N日均价的股票/ETF（N可自定义）
    参数:
        stocks: 待过滤的标的列表
        days: 均线天数（默认20日，可自定义为5/10/60等）
    返回:
        过滤后的标的列表（仅保留当前价 >= N日均价的标的）
    """
    if not stocks:
        return []
    
    current_data = get_current_data()
    filtered = []
    
    for stock in stocks:
        try:
            # 获取N日历史收盘价数据
            hist = attribute_history(stock, days, "1d", ["close"])
            if len(hist) < days:  # 确保有足够的历史数据（避免新股/刚上市ETF）
                log.debug(f"{stock} 历史数据不足{days}天，跳过过滤")
                continue
                
            # 计算N日均价
            ma_n = hist["close"].mean()
            # 获取当前价格
            current_price = current_data[stock].last_price
            
            # 保留当前价 >= N日均价的标的
            if current_price >= ma_n:
                filtered.append(stock)
            else:
                log.debug(f"{stock} 过滤（当前价 {current_price:.2f} < {days}日均价 {ma_n:.2f}）")
                
        except Exception as e:
            log.warning(f"计算{stock} {days}日均价失败: {e}")
            continue
            
    return filtered



def filter_below_ma(stocks, days=20):
    """
    过滤掉当前价格小于N日均价的股票/ETF（N可自定义）
    参数:
        stocks: 待过滤的标的列表
        days: 均线天数（默认20日，可自定义为5/10/60等）
    返回:
        过滤后的标的列表（仅保留当前价 >= N日均价的标的）
    """
    if not stocks:
        return []
    
    current_data = get_current_data()
    filtered = []
    
    for stock in stocks:
        try:
            # 获取N日历史收盘价数据
            hist = attribute_history(stock, days, "1d", ["close"])
            if len(hist) < days:  # 确保有足够的历史数据（避免新股/刚上市ETF）
                log.debug(f"{stock} 历史数据不足{days}天，跳过过滤")
                continue
                
            # 计算N日均价
            ma_n = hist["close"].mean()
            # 获取当前价格
            current_price = current_data[stock].last_price
            
            # 保留当前价 >= N日均价的标的
            if current_price >= ma_n:
                filtered.append(stock)
            else:
                log.debug(f"{stock} 过滤（当前价 {current_price:.2f} < {days}日均价 {ma_n:.2f}）")
                
        except Exception as e:
            log.warning(f"计算{stock} {days}日均价失败: {e}")
            continue
            
    return filtered