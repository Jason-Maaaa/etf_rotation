# 克隆自聚宽文章：https://www.joinquant.com/post/66494
# 标题：三马v10.3-ETF持有数量修改版
# 作者：天外飞砖

# 克隆自聚宽文章：https://www.joinquant.com/post/65761
# 标题：三马v10.3-无未来函数 年化151% 回撤11%
# 作者：布宽量化

# 克隆自聚宽文章：https://www.joinquant.com/post/64881
# 标题：【变种小狮子】带涨停基因的股池轮动V2.2(BUGFIX)
# 作者：0xtao

# 克隆自聚宽文章：https://www.joinquant.com/post/64752
# 标题：三马V10框架回测速度大幅优化提升
# 作者：O泡果奶

# 克隆自聚宽文章：https://www.joinquant.com/post/63661
# 标题：三马v10.2 测试框架
# 作者：Cibo

"""
Cibo 三驾马车优化版
策略1：带涨停基因的股池轮动策略
策略2：ETF反弹策略 (只能测试 23.9月后, 2000etf上市时间为23.9)
策略3：ETF轮动策略
"""
# 导入标准库：日期时间处理
import datetime
# 导入标准库：数学计算函数（如exp、log等）
import math
# 导入标准库：表格美化显示
import prettytable
# 导入numpy：数值计算库，用于数组运算、线性回归等
import numpy as np
# 导入pandas：数据分析库，用于DataFrame操作
import pandas as pd
# 从datetime导入timedelta：用于日期差值计算
from datetime import timedelta
# 导入聚宽数据接口：提供股票数据、行情数据等API
from jqdata import *
# 导入聚宽因子库：提供基本面数据查询接口
from jqfactor import *
# 导入PrettyTable：用于打印格式化的表格
from prettytable import PrettyTable

#from jqmt import *

# 重写订单函数以支持实盘推送
#order = push_order(order)
#order_target = push_order_target(order_target)
#order_value = push_order_value(order_value)
#order_target_value = push_order_target_value(order_target_value)


""" ====================== 基础配置 ====================== """


def initialize(context):
    """初始化策略.

    系统入口函数，按顺序完成：
    1. 回测环境配置
    2. 基础参数设置
    3. 策略参数设置
    4. 日志级别调整
    
    Args:
        context: 策略上下文对象，包含账户信息、持仓、当前时间等
    """
    # 配置回测环境：基准、滑点、交易成本等
    set_backtest()
    # 设置基础参数：资金分配比例、全局状态变量等
    set_params(context)
    # 设置各策略的具体参数：选股数量、止损阈值等
    set_strategy_params(context)
    # 设置日志级别：将订单日志设为error级别，减少冗余输出
    log.set_level('order', 'error')  # 屏蔽订单详细日志


def set_params(context):
    """设置基础参数.

    注意:
    1. ETF反弹核心标的在23.9月才上市, 回测过去周期策略失效
    2. 本策略预设的研究周期设计为 长:18-25, 中20-25, 短24-25
    """

    # ========== [配置] 资金分配比例 ==========
    # 格式: [策略1比例, 策略2比例, 策略3比例]
    # 策略1: 涨停基因轮动, 策略2: ETF反弹, 策略3: ETF轮动
    # 调整此参数可改变各策略的资金占比, 三个数字之和应为1.0
    g.portfolio_value_proportion = [0.4, 0.2, 0.4]  # [配置] 标准配置 (实盘/短回测推荐)
    #g.portfolio_value_proportion = [0.5, 0, 0.5]   # [配置] 长回测配置 (18-25年推荐, 策略2在23.9前无效)
    #g.portfolio_value_proportion = [0, 0.3, 0.7]   # [配置] 保守配置 (纯ETF组合)

    # 单策略测试配置
    #g.portfolio_value_proportion = [1, 0, 0]  # [配置] 仅测试策略1
    #g.portfolio_value_proportion = [0, 1, 0]  # [配置] 仅测试策略2
    #g.portfolio_value_proportion = [0, 0, 1]  # [配置] 仅测试策略3

    # ========== [配置] 涨停基因轮动空仓期资金动态分配 ==========
    # 策略1在1月和4月会空仓, 开启此功能后空仓期资金将分配给其他策略
    g.enable_dynamic_proportion = True  # [配置] 是否启用动态分配 (默认: False, 建议: True)
    g.dynamic_proportion_base = [0.4, 0.2, 0.4]  # [配置] 分配基准比例 (决定空仓期资金如何分配给策略2和3)

    # ========== 全局内部状态变量初始化 ==========
    # 记录初始资金总额，用于计算收益率
    g.starting_cash = context.portfolio.total_value
    # 字典：记录每只股票属于哪个策略 {股票代码: 策略ID(1/2/3)}
    g.stock_strategy = {}
    # 字典：记录各策略当前持仓的股票列表 {策略ID: [股票代码列表]}
    g.strategy_holdings = {1: [], 2: [], 3: []}
    # 保存原始资金分配比例（用于策略1空仓期后恢复）
    g.portfolio_value_proportion_original = g.portfolio_value_proportion[:]
    # 标记策略1是否处于空仓期（1月/4月）
    g.strategy1_paused = False
    # 字典：记录各策略的初始资金分配 {策略ID: 初始资金}
    g.strategy_starting_cash = {
        1: g.starting_cash * g.portfolio_value_proportion[0],  # 策略1初始资金
        2: g.starting_cash * g.portfolio_value_proportion[1],  # 策略2初始资金
        3: g.starting_cash * g.portfolio_value_proportion[2],  # 策略3初始资金
    }
    # 字典：用于临时存储各策略的市值数据（每日计算用）
    g.strategy_value_data = {}
    # 字典：记录各策略的累计盈亏 {策略ID: 累计盈亏金额}
    g.strategy_value = {
        1: g.starting_cash * g.portfolio_value_proportion[0],  # 策略1初始值
        2: g.starting_cash * g.portfolio_value_proportion[1],  # 策略2初始值
        3: g.starting_cash * g.portfolio_value_proportion[2],  # 策略3初始值
    }

    # ========== 策略2资金平衡初始化 ==========
    # 注意：此处必须在初始化时执行一次资金平衡，因为策略2的核心标的在2023.9.28才上市
    # 该函数会根据日期自动调整资金分配：2023.9.28前将策略2资金并入策略3，之后拨正
    g.strategy_etf_2000_proportion = g.portfolio_value_proportion[1]  # 保存策略2原始比例
    g.strategy_etf_2000_proportion_reset = None  # 资金平衡重置标记
    strategy2_capital_balance(context)  # 执行初始资金平衡


def set_strategy_params(context):
    """设置策略参数.

    包含三个策略的所有可调参数
    修改这些参数可优化策略表现
    """

    # ========== [配置] 策略1: 涨停基因轮动 参数 ==========

    # -- 止损策略类型常量 (供止损配置使用) --
    g.STOPLOSS_BY_LIMIT = 1  # 个股止损线
    g.STOPLOSS_BY_MARKET = 2  # 市场趋势止损
    g.STOPLOSS_COMBINED = 3  # 综合止损（推荐）

    # -- 卖出原因标记常量 (内部状态使用) --
    g.SELL_REASON_LIMITUP = 'limitup'  # 涨停打开
    g.SELL_REASON_STOPLOSS = 'stoploss'  # 止损触发

    # -- 核心参数 --
    g.pass_april = True  # [配置] 是否在1月和4月空仓 (True=空仓, False=不空仓, 默认: True)

    # -- 选股参数 --
    g.stock_num = 6  # [配置] 持股数量 (默认: 6, 建议范围: 4-10)
    g.limit_days_window = 3 * 250  # [配置] 历史涨停参考窗口期 (默认: 750个交易日, 建议: 500-1000)
    g.init_stock_count = 600  # [配置] 初始股池数量 (默认: 1000个, 按市值排序后取前N个)

    # -- 止损参数 --
    g.run_stoploss = False  # [配置] 是否启用止损 (True=启用, False=禁用, 默认: True)
    g.stoploss_strategy = 3  # [配置] 止损策略 (1=个股止损线, 2=市场趋势止损, 3=综合止损(推荐), 默认: 3)
    g.stoploss_limit = 0.93  # [配置] 个股止损线 (默认: 0.91 表示-9%, 建议范围: 0.88-0.93)
    g.stoploss_market = 0.95  # [配置] 市场趋势止损阈值 (默认: 0.93 表示大盘平均跌-7%时清仓)

    # -- 高级参数 --
    g.filter_loss_black = True  # [配置] 是否启用止损黑名单 (True=启用, False=禁用, 默认: True)
    g.hv_control = False  # [配置] 是否启用天量检测 (True=启用, False=禁用, 默认: False, 建议关闭)
    g.hv_duration = 120  # [配置] 天量检测周期 (默认: 120天, 当hv_control=True时生效)
    g.hv_ratio = 0.9  # [配置] 天量阈值 (默认: 0.9, 表示当日成交量达到历史90%分位时卖出)
    g.no_trading_buy = []  # [配置] 空仓期买入股票 (默认: [], 空仓期可选择买入指定股票)

    # -- 内部状态变量 (无需修改) --
    # g.no_trading_today_signal = False  # 今日是否空仓期标记
    # g.yesterday_hl_list = []  # 昨日涨停股票列表
    # g.target_list = []  # 目标股票列表
    # g.not_buy_again = []  # 本周已买入股票（避免重复买入）
    # g.reason_to_sell = ''  # 卖出原因记录
    # g.loss_black = {}  # 止损黑名单 {股票代码: 止损时间}
    # g.no_trading_hold_signal = False  # 空仓期持仓清空标记
    
    if not hasattr(g, 'no_trading_today_signal'): g.no_trading_today_signal = False  # 今日是否空仓期标记
    if not hasattr(g, 'yesterday_hl_list'): g.yesterday_hl_list = []  # 昨日涨停股票列表
    if not hasattr(g, 'target_list'): g.target_list = []  # 目标股票列表
    if not hasattr(g, 'not_buy_again'): g.not_buy_again = []  # 本周已买入股票（避免重复买入）
    if not hasattr(g, 'reason_to_sell'): g.reason_to_sell = ''  # 卖出原因记录
    if not hasattr(g, 'loss_black'): g.loss_black = {}  # 止损黑名单 {股票代码: 止损时间}
    if not hasattr(g, 'no_trading_hold_signal'): g.no_trading_hold_signal = False  # 空仓期持仓清空标记

    # ========== [配置] 策略2: ETF反弹 参数 ==========

    g.limit_days = 2  # [配置] 最短持仓天数 (默认: 2天, 建议范围: 2-5)
    g.n_days = 5  # [配置] 最长持仓天数 (默认: 5天, 建议范围: 3-7)
    g.etf_rebound_hold_num = 1  # [配置] 新增：策略2持仓ETF数量 (默认: 3只, 建议范围: 2-5)

    # [配置] ETF反弹池：按小盘→大盘顺序排列，优先级递减
    # 反弹条件：开盘跌破前4日最高价2% 且 收盘上涨1%
    # 数组顺序即为优先级，小盘ETF弹性更大，排名靠前优先买入
    g.etf_pool_2 = [
        '563300.XSHG',  #'159536.XSHE',  # 中证2000ETF｜超小盘弹性标的（嘉实）← 最高优先级，2023.9上市
        '512100.XSHG',  #'159629.XSHE',  # 中证1000ETF｜小盘成长（鹏华）
        '159922.XSHE',  # 中证500ETF｜中盘代表（嘉实）备选基金'563360.XSHG'
        '159919.XSHE',  # 沪深300ETF｜大盘蓝筹（嘉实）
        '159783.XSHE'   # 中证A50ETF｜超大盘核心（嘉实）← 最低优先级
    ]

    # -- 策略2内部状态变量 --
    # g.buy_list = []  # 待买入ETF列表
    if not hasattr(g, 'buy_list'): g.buy_list = []  # 待买入ETF列表


    # ========== [配置] 策略3: ETF轮动 参数 ==========

    g.m_days = 25  # [配置] 动量计算参考天数 (默认: 25天)
    g.etf_rotation_hold_num = 1  # [配置] 持仓ETF数量
    
    # [配置] 策略3新增参数 (来自etf_rota_pro.py)
    g.enable_volume_check = True  # 是否启用成交量检测
    g.volume_lookback = 5  # 历史成交量参考天数
    g.volume_threshold = 2.0  # 放量阈值
    g.ma_filter_days = 20  # 均线过滤天数
    g.enable_ma_filter = True  # 是否启用均线过滤

    # [配置] ETF轮动池 (严格一致)
    g.etf_pool_3 = [
        # 境外
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
        "159201.XSHE",  #现金流ETF
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

    # -- 策略3内部状态变量 --
    # 无需RSRS缓存

    # ---- 量价背离顶部识别参数 ----
    g.enable_vol_divergence_filter = True   # 是否启用量价背离过滤
    g.vol_recent_days  = 3                  # 近期成交量观察窗口（天）
    g.vol_baseline_days = 10                # 历史基准成交量窗口（天，紧接近期之前）
    g.vol_shrink_ratio  = 0.7               # 缩量阈值：近期均量 / 基准均量 < 该比值触发
    g.price_high_percentile = 0.80          # 价格高位判定：当前价在动量周期内超过该分位数时才检测



def set_backtest():
    """设置回测参数.

    配置回测环境、基准、滑点和交易成本
    """
    # 避免未来数据
    set_option('avoid_future_data', True)

    # 设置基准：沪深300指数
    set_benchmark('000300.XSHG')

    # 使用真实价格（非复权价格）
    set_option('use_real_price', True)

    # 滑点设置
    set_slippage(FixedSlippage(0.002), type="stock")  # 股票滑点 0.2%
    set_slippage(FixedSlippage(0.001), type="fund")   # 基金滑点 0.1%

    # 交易成本配置 (类型, 印花税, 佣金率, 最低佣金)
    cost_configs = [
        ("stock", 0.0005, 0.85 / 10000, 5),  # 股票: 印花税0.05%, 佣金万0.85, 最低5元
        ("fund", 0, 0.5 / 10000, 5),         # 基金: 无印花税, 佣金万0.5, 最低5元
        ("mmf", 0, 0, 0)                      # 货币基金: 零成本
    ]
    for asset_type, close_tax, commission, min_comm in cost_configs:
        set_order_cost(OrderCost(
            open_tax=0, close_tax=close_tax,
            open_commission=commission, close_commission=commission,
            close_today_commission=0, min_commission=min_comm
        ), type=asset_type)


""" ====================== 策略1: 带涨停基因的股池轮动 ====================== """


def strategy1_adjust_proportion_pause():
    """策略1空仓期将资金按比例分配给其他策略.

    当策略1进入空仓期（1月/4月）时，将其资金按照g.dynamic_proportion_base
    的比例分配给策略2和策略3，提高资金使用效率。
    """
    if not g.enable_dynamic_proportion:
        return
    if g.strategy1_paused:
        return

    strategy1_proportion = g.portfolio_value_proportion_original[0]
    if strategy1_proportion == 0:
        return

    # 计算策略2和策略3的基准比例
    base_etf_rebound = g.dynamic_proportion_base[1]
    base_etf_rotation = g.dynamic_proportion_base[2]
    other_total = base_etf_rebound + base_etf_rotation

    if other_total == 0:
        print("⚠️ 策略1 空仓期间其他策略基准比例为0 无法分配资金")
        return

    # 重新分配比例
    g.portfolio_value_proportion = [0]
    additional_etf_rebound = strategy1_proportion * (base_etf_rebound / other_total)
    g.portfolio_value_proportion.append(g.portfolio_value_proportion_original[1] + additional_etf_rebound)
    additional_etf_rotation = strategy1_proportion * (base_etf_rotation / other_total)
    g.portfolio_value_proportion.append(g.portfolio_value_proportion_original[2] + additional_etf_rotation)

    g.strategy1_paused = True
    print(f"📊 策略1 进入空仓期 资金重新分配")
    print(f"   原始比例:{' '.join([f'{x:.2%}' for x in g.portfolio_value_proportion_original])}")
    print(f"   调整后比例:{' '.join([f'{x:.2%}' for x in g.portfolio_value_proportion])}")
    print(f"   分配依据基准:{' '.join([f'{x:.2%}' for x in g.dynamic_proportion_base])}")


def strategy1_restore_proportion_resume():
    """策略1恢复运行时还原原始资金比例.

    当策略1退出空仓期恢复运行时，将资金比例还原为初始配置。
    """
    if not g.enable_dynamic_proportion:
        return
    if not g.strategy1_paused:
        return

    g.portfolio_value_proportion = g.portfolio_value_proportion_original[:]
    g.strategy1_paused = False
    print(f"📊 策略1 恢复运行 资金比例还原")
    print(f"   当前比例:{' '.join([f'{x:.2%}' for x in g.portfolio_value_proportion])}")


def strategy1_prepare(context):
    """准备策略1运行环境，检查空仓期并获取昨日涨停列表.

    每日9:05执行，完成：
    1. 判断是否进入/退出空仓期，并调整资金分配
    2. 获取昨日涨停股票列表，用于盘中监控
    """
    # 检查是否进入或退出空仓期
    new_no_trading_signal = strategy1_is_no_trading_period(context)
    if hasattr(g, 'no_trading_today_signal'):
        if not g.no_trading_today_signal and new_no_trading_signal:
            # 进入空仓期
            strategy1_adjust_proportion_pause()
        elif g.no_trading_today_signal and not new_no_trading_signal:
            # 退出空仓期
            strategy1_restore_proportion_resume()
    else:
        if new_no_trading_signal:
            strategy1_adjust_proportion_pause()

    g.no_trading_today_signal = new_no_trading_signal

    # 获取昨日涨停股票列表
    if g.strategy_holdings[1]:
        df = get_price(g.strategy_holdings[1], end_date=context.previous_date, frequency='daily',
                      fields=['close','high_limit','low_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_hl_list = list(df.code)
    else:
        g.yesterday_hl_list = []


def strategy1_get_history_highlimit(context, stock_list, days=750, p=0.10):
    """筛选历史涨停频率高的股票.

    核心选股逻辑：筛选出过去N天内涨停次数最多的前10%股票。
    这些股票具有"涨停基因"，更容易再次涨停。

    Args:
        context: 策略上下文
        stock_list: 待筛选股票列表
        days: 历史回溯天数，默认750天（约3年交易日）
        p: 保留前p%的股票，默认0.10 (即前10%)

    Returns:
        list: 筛选后的股票代码列表
    """
    # 获取历史价格数据：获取过去days天的收盘价和涨停价
    df = get_price(
        stock_list,  # 股票列表
        end_date=context.previous_date,  # 截止日期（昨日）
        frequency="daily",  # 日线数据
        fields=["close", "high_limit"],  # 需要收盘价和涨停价两个字段
        count=days,  # 获取days天的数据
        panel=False,  # 返回DataFrame而非Panel
        fill_paused=False,  # 停牌日不填充数据
    )

    # 筛选出涨停日：收盘价等于涨停价的交易日（说明当日涨停）
    df = df[df["close"] == df["high_limit"]]

    # 统计每只股票的涨停次数并排序
    # groupby按股票代码分组，size()统计每组数量（即涨停次数）
    grouped_result = df.groupby('code').size().reset_index(name='count')
    # 按涨停次数降序排列（涨停次数多的在前）
    grouped_result = grouped_result.sort_values(by=["count"], ascending=False)

    # 取前p%：只保留涨停次数最多的前p%股票
    # int(len(grouped_result)*p) 计算需要保留的数量
    result_list = grouped_result["code"].tolist()[:int(len(grouped_result)*p)]
    log.info(f"ℹ️ 策略1 选股筛选 初始池:{len(grouped_result)}个 历史涨停筛选后:{len(result_list)}个")
    return result_list


def strategy1_get_start_point(context, stock_list, days=750):
    """计算股票历史启动点并按价格偏离度排序.

    核心思想：寻找最近一次涨停之前的第一个阴线作为"启动点"，
    选择当前价格距离启动点较近的股票，这些股票上涨空间更大。

    Args:
        context: 策略上下文
        stock_list: 待处理股票列表
        days: 历史回溯天数，默认750天

    Returns:
        list: 按价格偏离度排序的股票代码列表（偏离度从小到大）
    """
    # 获取历史OHLC数据
    df = get_price(
        stock_list,
        end_date=context.previous_date,
        frequency="daily",
        fields=["open", "low", "close", "high_limit"],
        count=days,
        panel=False,
    )

    stock_start_point = {}  # 存储每只股票的启动点价格
    stock_price_bias = {}   # 存储每只股票的价格偏离度
    current_data = get_current_data()

    for code, group in df.groupby('code'):
        group = group.sort_values('time')
        # 找到所有涨停日
        limit_hit_rows = group[group['close'] == group['high_limit']]

        if not limit_hit_rows.empty:
            # 获取最近一次涨停
            latest_limit_hit = limit_hit_rows.iloc[-1]
            latest_limit_index = latest_limit_hit.name

            # 从涨停日往前找第一个阴线
            previous_rows = group[group.index <= latest_limit_index].iloc[::-1]
            for idx, row in previous_rows.iterrows():
                if row['close'] < row['open']:  # 阴线
                    stock_start_point[code] = row['low']  # 启动点为阴线最低价
                    break

    # 计算价格偏离度：当前价 / 启动点价格
    for code, start_point in stock_start_point.items():
        last_price = current_data[code].last_price
        bias = last_price / start_point
        stock_price_bias[code] = bias

    # 按偏离度从小到大排序（偏离度小 = 离启动点近 = 上涨空间大）
    sorted_list = sorted(stock_price_bias.items(), key=lambda x: x[1], reverse=False)
    return [i[0] for i in sorted_list]


def strategy1_get_stock_list(context):
    """策略1选股主流程.

    多重过滤流程：
    1. 基础过滤：次新股、科创板、ST、停牌
    2. 市值筛选：选取小市值前1000只
    3. 状态过滤：涨停、跌停、止损黑名单
    4. 核心筛选：历史涨停频率、启动点偏离度
    5. 行业分散：最多选10个行业

    Returns:
        list: 最终选出的股票列表（数量为stock_num*2，实际买入stock_num只）
    """
    # 获取昨日日期（用于数据查询）
    yesterday = context.previous_date

    # 1. 获取全市场股票：获取指定日期的所有股票代码列表
    initial_list = get_all_securities("stock", yesterday).index.tolist()

    # 2. 基础过滤：逐步过滤掉不符合条件的股票
    initial_list = strategy1_filter_new(context, initial_list)      # 过滤次新股（上市不足375天）
    initial_list = strategy1_filter_kcbj(initial_list)              # 过滤科创板/北交所（涨跌幅限制不同）
    initial_list = strategy1_filter_st(initial_list)                # 过滤ST股（风险高）
    initial_list = strategy1_filter_paused(initial_list)            # 过滤停牌股（无法交易）

    # 3. 止损黑名单过滤：如果启用黑名单功能，过滤掉最近止损的股票（避免反复止损）
    if g.filter_loss_black:
        initial_list = strategy1_filter_loss_black(context, initial_list, days=20)

    # 4. 按市值排序，取前1000只小市值股票
    # 小市值股票弹性更大，更容易涨停
    q = query(
        valuation.code, indicator.eps  # 查询股票代码和每股收益
    ).filter(
        valuation.code.in_(initial_list)  # 只查询过滤后的股票
    ).order_by(
        valuation.market_cap.asc()  # 按市值从小到大排序
    )
    df = get_fundamentals(q)  # 获取基本面数据
    # 取前g.init_stock_count只（默认1000只）小市值股票
    initial_list = df['code'].tolist()[:g.init_stock_count]

    # 5. 状态过滤：过滤掉当前无法交易的股票
    initial_list = strategy1_filter_limitup(context, initial_list)    # 过滤涨停（保留已持仓的涨停股）
    initial_list = strategy1_filter_limitdown(context, initial_list)  # 过滤跌停（保留已持仓的跌停股）

    # 6. 核心筛选：历史涨停频率
    # 筛选出过去750天内涨停次数最多的前10%股票（具有"涨停基因"）
    initial_list = strategy1_get_history_highlimit(context, initial_list, g.limit_days_window)

    # 7. 核心筛选：启动点偏离度排序
    # 计算每只股票当前价格距离"启动点"的偏离度，选择偏离度小的（上涨空间大）
    initial_list = strategy1_get_start_point(context, initial_list, g.limit_days_window)

    # 8. 行业分散：从不同行业中各选一只股票，最多选10个行业
    # 避免行业过度集中导致的风险
    stock_list = strategy1_get_stock_industry(initial_list)

    # 9. 取前stock_num*2只作为候选池
    # 实际买入时只买入前stock_num只，多选一些作为备选
    final_list = stock_list[:g.stock_num*2]
    # 格式化显示股票列表（方便日志查看）
    formatted_list = ' '.join([format_stock_code(s) for s in final_list])
    log.info(f'ℹ️ 策略1 今日前10名:{formatted_list}')
    return final_list


def strategy1_sell(context):
    """策略1卖出逻辑.

    每周二10:15执行，完成：
    1. 打印日期分隔线
    2. 清空空仓期遗留持仓
    3. 卖出不在目标池的股票（保留涨停股）
    """
    print("━" * 30 + f" {str(context.current_dt.date())} " + "━" * 30)

    if not g.no_trading_today_signal:
        current_data = get_current_data()

        # 清空空仓期遗留持仓
        strategy1_close_no_trading_hold(context)

        # 获取目标股票池
        g.not_buy_again = []
        g.target_list = strategy1_get_stock_list(context)
        target_list = g.target_list[:g.stock_num*2]
        # 格式化显示目标股票池
        formatted_target = ' '.join([format_stock_code(s) for s in target_list])
        log.info(f"ℹ️ 策略1 目标股票池:{formatted_target}")

        # 遍历当前持仓，卖出不在目标池的股票
        for stock in g.strategy_holdings[1]:
            # 卖出条件：
            # 1. 不在目标池
            # 2. 昨日未涨停（昨日涨停的股票需要等待盘中检查）
            # 3. 当前未涨停（已涨停无法卖出）
            if (stock not in target_list) and (stock not in g.yesterday_hl_list) and (current_data[stock].last_price < current_data[stock].high_limit):
                log.info(f"ℹ️ 策略1 平仓 {format_stock_code(stock)} 原因:不在目标池")
                close_position(stock)
            else:
                log.info(f"🔒 策略1 保持 {format_stock_code(stock)}")


def strategy1_buy(context):
    """策略1买入逻辑.

    每周二10:30执行，完成：
    1. 获取目标股票池
    2. 买入新股票补仓至目标数量
    3. 记录已买入股票避免重复买入
    """
    if not g.no_trading_today_signal:
        current_data = get_current_data()

        # 获取目标股票池
        g.not_buy_again = []
        g.target_list = strategy1_get_stock_list(context)
        target_list = g.target_list[:g.stock_num*2]
        # 格式化显示目标股票池
        formatted_target = ' '.join([format_stock_code(s) for s in target_list])
        log.info(f"ℹ️ 策略1 目标股票池:{formatted_target}")

        # 买入新股票
        strategy1_buy_security(context, target_list)

        # 记录本周已买入股票
        for stock in g.strategy_holdings[1]:
            g.not_buy_again.append(stock)


def strategy1_check_limit_up(context):
    """检查昨日涨停股今日表现，涨停打开则卖出.

    策略逻辑：
    - 昨日涨停的股票如果今日继续封板则持有
    - 如果涨停打开则立即卖出（涨停打开通常预示反转）
    """
    now_time = context.current_dt

    if g.yesterday_hl_list:
        for stock in g.yesterday_hl_list:
            # 检查持仓和可平仓数量（-100表示无限制）
            if stock in context.portfolio.positions and context.portfolio.positions[stock].closeable_amount > -100:
                # 获取最新1分钟数据
                current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close','high_limit'],
                                        skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)

                # 判断是否涨停
                if current_data.iloc[0,0] < current_data.iloc[0,1]:
                    # 涨停打开，卖出
                    log.info(f"ℹ️ {format_stock_code(stock)} 涨停打开→平仓")
                    close_position(stock)
                    g.reason_to_sell = g.SELL_REASON_LIMITUP
                else:
                    # 继续涨停，持有
                    log.info(f"💎 {format_stock_code(stock)} 涨停封板→继续持有")


def strategy1_check_remain_amount(context):
    """检查余额并补仓.

    如果因涨停打开而卖出导致持仓不足，用余额补仓至目标数量。
    """
    if g.reason_to_sell == g.SELL_REASON_LIMITUP:
        if len(g.strategy_holdings[1]) < g.stock_num:
            # 获取目标股票池
            target_list = strategy1_get_stock_list(context)

            # 过滤本周已买入的股票
            target_list = strategy1_filter_not_buy_again(target_list)
            target_list = target_list[:min(g.stock_num, len(target_list))]

            # 格式化显示股票列表
            formatted_target_list = ' '.join([format_stock_code(s) for s in target_list])
            log.info(f'ℹ️ 策略1 余额补仓 可用资金:{round(context.portfolio.cash, 2)}元 目标池:{formatted_target_list}')
            strategy1_buy_security(context, target_list)

    g.reason_to_sell = ''


def strategy1_trade_afternoon(context):
    """策略1下午盘中检查.

    每日14:20和14:55执行，完成：
    1. 检查涨停股表现
    2. 检查天量（如启用）
    3. 检查换手率异常
    4. 余额补仓
    """
    if not g.no_trading_today_signal:
        # 检查涨停股
        strategy1_check_limit_up(context)

        # 检查天量（如启用）
        if g.hv_control:
            strategy1_check_high_volume(context)

        # 检查换手率异常
        strategy1_check_turnover(context)

        # 余额补仓
        strategy1_check_remain_amount(context)


def strategy1_sell_stocks(context):
    """策略1止盈止损.

    每日10:00执行，根据配置的止损策略执行：
    1. g.STOPLOSS_BY_LIMIT: 个股止损线（止盈100%或止损-9%）
    2. g.STOPLOSS_BY_MARKET: 市场趋势止损（大盘暴跌清仓）
    3. g.STOPLOSS_COMBINED: 综合止损（推荐，先检查大盘再检查个股）
    """
    if not g.run_stoploss:
        return

    if g.stoploss_strategy == g.STOPLOSS_BY_LIMIT:
        # 策略1：个股止损线
        for stock in context.portfolio.positions.keys():
            if stock in g.strategy_holdings[1]:
                # 止盈：收益达到100%
                if context.portfolio.positions[stock].price >= context.portfolio.positions[stock].avg_cost * 2:
                    close_position(stock)
                    log.debug(f"🎯 策略1 止盈 {format_stock_code(stock)} 收益:+100%")
                    g.loss_black[stock] = context.current_dt  # 加入黑名单

                # 止损：亏损达到阈值
                elif context.portfolio.positions[stock].price < context.portfolio.positions[stock].avg_cost * g.stoploss_limit:
                    profit_ratio = (context.portfolio.positions[stock].price / context.portfolio.positions[stock].avg_cost - 1) * 100
                    close_position(stock)
                    log.debug(f"🛑 策略1 止损 {format_stock_code(stock)} 亏损:{profit_ratio:.0f}%")
                    g.reason_to_sell = g.SELL_REASON_STOPLOSS
                    g.loss_black[stock] = context.current_dt  # 加入黑名单

    elif g.stoploss_strategy == g.STOPLOSS_BY_MARKET:
        # 策略2：市场趋势止损
        # 计算深证成指成分股的平均跌幅
        stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date,
                            frequency='daily', fields=['close', 'open'], count=1, panel=False)
        down_ratio = (stock_df['close'] / stock_df['open']).mean()

        # 如果大盘暴跌，清仓全部持仓
        if down_ratio <= g.stoploss_market:
            g.reason_to_sell = g.SELL_REASON_STOPLOSS
            log.debug(f"🛑 策略1 清仓全部持仓 原因:大盘暴跌 平均降幅:{(down_ratio - 1) * 100:.2f}%")
            for stock in g.strategy_holdings[1][:]:
                close_position(stock)

    elif g.stoploss_strategy == g.STOPLOSS_COMBINED:
        # 策略3：综合止损（推荐）
        # 先检查大盘
        stock_df = get_price(security=get_index_stocks('399101.XSHE'), end_date=context.previous_date,
                            frequency='daily', fields=['close', 'open'], count=1, panel=False)
        down_ratio = (stock_df['close'] / stock_df['open']).mean()

        if down_ratio <= g.stoploss_market:
            # 大盘暴跌，清仓全部
            g.reason_to_sell = g.SELL_REASON_STOPLOSS
            log.debug(f"🛑 策略1 清仓全部持仓 原因:大盘暴跌 平均降幅:{(down_ratio - 1) * 100:.2f}%")
            for stock in g.strategy_holdings[1][:]:
                close_position(stock)
        else:
            # 大盘正常，检查个股止损线
            for stock in context.portfolio.positions.keys():
                if stock in g.strategy_holdings[1]:
                    if context.portfolio.positions[stock].price < context.portfolio.positions[stock].avg_cost * g.stoploss_limit:
                        profit_ratio = (context.portfolio.positions[stock].price / context.portfolio.positions[stock].avg_cost - 1) * 100
                        close_position(stock)
                        log.debug(f"🛑 策略1 止损 {format_stock_code(stock)} 亏损:{profit_ratio:.0f}%")
                        g.reason_to_sell = g.SELL_REASON_STOPLOSS
                        g.loss_black[stock] = context.current_dt


def strategy1_check_high_volume(context):
    """检查并卖出天量股票.

    天量逻辑：如果当日成交量达到过去120天的90%分位数，判定为天量，
    天量通常预示主力出货，应立即卖出。

    注意：此功能默认关闭（g.hv_control=False），因为可能产生过多交易。
    """
    current_data = get_current_data()

    for stock in g.strategy_holdings[1][:]:
        # 跳过不满足卖出条件的股票
        if stock not in context.portfolio.positions:
            continue
        if current_data[stock].paused:  # 停牌
            continue
        if current_data[stock].last_price == current_data[stock].high_limit:  # 涨停
            continue
        if context.portfolio.positions[stock].closeable_amount == 0:  # 不可卖出
            continue

        # 获取历史成交量
        df_volume = get_bars(stock, count=g.hv_duration, unit='1d', fields=['volume'], include_now=True, df=True)

        # 判断是否天量
        if df_volume['volume'].values[-1] > g.hv_ratio*df_volume['volume'].values.max():
            r = close_position(stock)
            log.info(f"🔥 策略1 平仓 {format_stock_code(stock)} 原因:天量")
            g.reason_to_sell = g.SELL_REASON_LIMITUP


def strategy1_check_turnover(context):
    """检查换手率异常并卖出（缩量或放量）.

    换手率异常逻辑：
    1. 缩量：20日平均换手率 < 0.3%，判定为缩量，流动性枯竭，卖出
    2. 放量：当日换手率 > 10% 且是均值的2倍以上，判定为放量，可能见顶，卖出
    """
    # 换手率阈值（算法常量，一般不需调整）
    shrink_threshold, expand_threshold, expand_ratio = 0.003, 0.1, 2

    current_data = get_current_data()

    for stock in g.strategy_holdings[1][:]:
        # 跳过不满足卖出条件的股票
        if stock not in context.portfolio.positions:
            continue
        if current_data[stock].paused:  # 停牌
            continue
        if current_data[stock].last_price >= current_data[stock].high_limit * 0.97:  # 接近涨停（0.97即跌幅3%）
            continue
        if context.portfolio.positions[stock].closeable_amount == 0:  # 不可卖出
            continue

        # 计算当日换手率和20日平均换手率
        rt = strategy1_calculate_turnover(context, stock, False)  # 当日换手率
        avg = strategy1_calculate_turnover(context, stock, True)  # 20日平均换手率

        if avg == 0:
            continue

        r = rt / avg  # 倍数
        action, icon = '', ''

        # 判断缩量
        if avg < shrink_threshold:
            action, icon = '缩量', '❄️'
        # 判断放量
        elif rt > expand_threshold and r > expand_ratio:
            action, icon = '放量', '🔥'

        # 卖出
        if action:
            close_position(stock)
            log.info(f"{icon} 策略1 平仓 {format_stock_code(stock)} 原因:{action} 换手率:{rt:.2%} 均值:{avg:.2%} 倍率:{r:.1f}x")
            g.reason_to_sell = g.SELL_REASON_LIMITUP


def strategy1_calculate_turnover(context, stock, is_avg=False):
    """计算股票的换手率.

    换手率 = 成交量 / 流通市值
    根据is_avg参数决定计算实时换手率或平均换手率。

    Args:
        context: 策略上下文
        stock: 股票代码
        is_avg: True返回20日平均换手率，False返回当日实时换手率

    Returns:
        float: 换手率，流通市值为0时返回0.0
    """
    if is_avg:
        # 计算20日平均换手率
        df_volume = get_price(stock, end_date=context.previous_date, frequency='daily', fields=['volume'], count=20)
        df_cap = get_valuation(stock, end_date=context.previous_date, fields=['circulating_cap'], count=1)
        circulating_cap = df_cap['circulating_cap'].iloc[0] if not df_cap.empty else 0

        if circulating_cap == 0:
            return 0.0

        # 流通市值单位是亿，需要转换为股数（*10000万股）
        df_volume['turnover_ratio'] = df_volume['volume'] / (circulating_cap * 10000)
        return df_volume['turnover_ratio'].mean()
    else:
        # 计算当日实时换手率
        date_now = context.current_dt

        # 获取今日分钟级成交量
        df_vol = get_price(stock, start_date=date_now.date(), end_date=date_now, frequency='1m', fields=['volume'],
                          skip_paused=False, fq='pre', panel=True, fill_paused=False)
        volume = df_vol['volume'].sum()

        # 获取流通市值
        date_pre = context.previous_date
        df_circulating_cap = get_valuation(stock, end_date=date_pre, fields=['circulating_cap'], count=1)
        circulating_cap = df_circulating_cap['circulating_cap'].iloc[0] if not df_circulating_cap.empty else 0

        if circulating_cap == 0:
            return 0.0

        turnover_ratio = volume / (circulating_cap * 10000)
        return turnover_ratio


def strategy1_buy_security(context, target_list):
    """策略1买入股票.

    买入逻辑：
    1. 计算策略1可用资金
    2. 平均分配给每只待买入股票
    3. 买入至目标持仓数量

    Args:
        context: 策略上下文
        target_list: 目标股票列表（已按优先级排序）
    """
    # 计算策略1的目标市值：总资产 × 策略1资金占比
    strategy_value = context.portfolio.total_value * g.portfolio_value_proportion[0]

    # 计算当前策略1的持仓市值：遍历所有持仓，累加属于策略1的持仓市值
    current_value = sum([pos.value for pos in context.portfolio.positions.values() if pos.security in g.strategy_holdings[1]])

    # 可用资金 = 目标市值 - 当前持仓市值（确保不为负）
    available_cash = max(0, strategy_value - current_value)

    # 如果可用资金少于100元，无法买入，直接返回
    if available_cash < 100:
        return

    # 计算需要买入的数量
    position_count = len(g.strategy_holdings[1])  # 当前已持仓数量
    target_num = g.stock_num  # 目标持仓数量（默认6只）

    # 如果当前持仓数小于目标数，需要买入
    if target_num > position_count:
        # 平均分配资金：将可用资金平均分配给需要买入的股票
        # (target_num - position_count) 是需要买入的股票数量
        value = available_cash / (target_num - position_count)
        bought_num = 0  # 已买入数量计数器

        # 依次买入：按target_list的顺序买入（已按优先级排序）
        for stock in target_list:
            # 只买入尚未持仓的股票
            if stock not in g.strategy_holdings[1]:
                # 如果还没买够，继续买入
                if bought_num < (target_num - position_count):
                    # 调用开仓函数买入股票（策略ID=1）
                    open_position(context, stock, value, 1)
                    bought_num += 1  # 买入计数+1
                    # 如果已持仓数达到目标数，停止买入
                    if len(g.strategy_holdings[1]) == target_num:
                        break


def strategy1_is_no_trading_period(context):
    """判断当前日期是否为策略1空仓期（1月和4月）.

    空仓期逻辑：
    - 1月1日-1月30日：年报季，市场波动大，空仓规避
    - 4月1日-4月30日：一季报季，市场波动大，空仓规避

    Returns:
        bool: True表示空仓期，False表示正常交易期
    """
    today = context.current_dt.strftime('%m-%d')

    if g.pass_april:
        # 判断是否在1月或4月
        if (('04-01' <= today) and (today <= '04-30')) or (('01-01' <= today) and (today <= '01-30')):
            return True
        else:
            return False
    else:
        return False


def strategy1_close_no_trading_hold(context):
    """清仓策略1空仓期间持仓.

    如果从非空仓期进入空仓期，清空所有持仓。
    """
    if g.no_trading_hold_signal:
        for stock in g.strategy_holdings[1][:]:
            close_position(stock)
            log.info(f"ℹ️ 策略1 平仓 {format_stock_code(stock)} 原因:空仓期")
        g.no_trading_hold_signal = False


def strategy1_close_account(context):
    """空仓期清仓策略1并可选买入指定股票.

    每日14:50执行，如果处于空仓期：
    1. 清空所有持仓
    2. 可选择买入g.no_trading_buy中指定的股票（默认为空）
    """
    if g.no_trading_today_signal:
        if len(g.strategy_holdings[1]) != 0 and not g.no_trading_hold_signal:
            # 清仓
            for stock in g.strategy_holdings[1][:]:
                r = close_position(stock)
                log.info(f"ℹ️ 策略1 平仓 {format_stock_code(stock)} 原因:进入空仓期")

            # 可选买入指定股票
            if g.no_trading_buy:
                strategy1_buy_security(context, g.no_trading_buy)

            g.no_trading_hold_signal = True


def strategy1_filter_paused(stock_list):
    """过滤停牌股票.

    Args:
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]


def strategy1_filter_st(stock_list):
    """过滤ST及退市标签股票.

    ST股（Special Treatment）：财务状况异常的股票，风险高，不买入。

    Args:
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]


def strategy1_filter_kcbj(stock_list):
    """过滤科创板和北交所股票.

    科创板（68开头）和北交所（4/8开头）股票涨跌幅限制不同，
    风险较高，策略不适用。

    Args:
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    for stock in stock_list[:]:
        # 北交所：4/8开头，科创板：68开头
        if stock[0] == '4' or stock[0] == '8' or stock[:2] == '68':
            stock_list.remove(stock)
    return stock_list


def strategy1_filter_limitup(context, stock_list):
    """过滤涨停股票（保留已持仓）.

    涨停的股票无法买入，但如果已持仓则保留。

    Args:
        context: 策略上下文
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] < current_data[stock].high_limit]


def strategy1_filter_limitdown(context, stock_list):
    """过滤跌停股票（保留已持仓）.

    跌停的股票无法卖出，但如果已持仓则保留。

    Args:
        context: 策略上下文
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if (stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] > current_data[stock].low_limit)]


def strategy1_filter_new(context, stock_list):
    """过滤次新股（上市不足375天）.

    次新股价格波动大，且缺乏足够的历史数据，不适合本策略。

    Args:
        context: 策略上下文
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    yesterday = context.previous_date
    return [stock for stock in stock_list if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]


def strategy1_filter_not_buy_again(stock_list):
    """过滤本周已买入的股票.

    避免在同一周内重复买入同一只股票。

    Args:
        stock_list: 股票列表

    Returns:
        list: 过滤后的股票列表
    """
    return [stock for stock in stock_list if stock not in g.not_buy_again]


def strategy1_filter_loss_black(context, stock_list, days=20):
    """过滤止损黑名单中的股票.

    止损后的股票加入黑名单，在days天内不再买入，
    避免反复止损同一只股票。

    Args:
        context: 策略上下文
        stock_list: 股票列表
        days: 黑名单持续天数，默认20天

    Returns:
        list: 过滤后的股票列表
    """
    result_list = []
    for stock in stock_list:
        # 检查是否在黑名单中且未过期
        if (
            stock in g.loss_black.keys()
            and context.current_dt - g.loss_black[stock]
            < datetime.timedelta(days=days)
        ):
            log.info(f"⚠️ 策略1 过滤 {format_stock_code(stock)} 原因:止损黑名单 止损时间:{g.loss_black[stock].strftime('%Y-%m-%d')}")
            continue
        result_list.append(stock)
    return result_list


def strategy1_get_stock_industry(stock):
    """获取股票所属行业并进行行业分散（最多10个行业）.

    行业分散逻辑：从不同行业中各选一只股票，最多选10个行业，
    避免行业过度集中导致的风险。

    Args:
        stock: 股票代码或股票列表

    Returns:
        list: 行业分散后的股票列表
    """
    result = get_industry(security=stock)
    selected_stocks = []
    industry_list = []

    for stock_code, info in result.items():
        industry_name = info['sw_l2']['industry_name']  # 申万二级行业

        # 每个行业只选一只
        if industry_name not in industry_list:
            industry_list.append(industry_name)
            selected_stocks.append(stock_code)

            # 最多10个行业
            if len(industry_list) == 10:
                break

    return selected_stocks


""" ====================== 策略2: ETF反弹 ====================== """


def strategy2_sell(context):
    """策略2卖出逻辑.

    每日14:49执行，完成：
    1. 筛选符合反弹条件的ETF（开盘价跌破前4日最高价2%且收盘涨1%）
    2. 检查是否需要换仓（有更高优先级的ETF符合条件）
    3. 卖出满足条件的持仓：
       - 今日收盘价 < 昨日收盘价 且 持仓 >= 2天
       - 持仓 >= 5天
       - 需要换仓腾出资金

    注意：2023.10.01之前不运行（核心标的未上市）
    """
    # 获取当前日期字符串，用于判断是否在策略2可运行日期之后
    cur_date = str(context.current_dt.date())
    # 如果日期早于2023-10-01，策略2的核心标的（中证2000ETF）还未上市，直接返回
    if cur_date <= "2023-10-01":
        return

    # 初始化列表：待买入ETF列表、待卖出ETF列表、需要换仓腾出资金的ETF列表
    g.buy_list = []
    sell_list = []
    sell_for_money_list = []

    # 遍历ETF池，寻找符合反弹条件的ETF
    for etf in g.etf_pool_2:
        # 获取前4日数据：需要最高价和收盘价
        df = get_price(etf, end_date=context.previous_date, count=4, frequency='daily', fields=['high', 'close'])
        df = df.reset_index()  # 重置索引，使日期成为普通列

        # 如果数据不足4天，跳过该ETF
        if len(df) < 4:
            return

        pre_high_max = df['high'].max()  # 前4日最高价（用于判断是否跌破）
        yestoday_close = df['close'].iloc[-1]  # 昨日收盘价（用于判断今日是否下跌）

        # 获取当前实时数据
        current_data = get_current_data()
        today_open = current_data[etf].day_open  # 今日开盘价
        today_close = current_data[etf].last_price  # 今日收盘价（当前最新价）

        # 反弹条件判断：开盘跌破前高2% 且 收盘上涨1%
        # today_open / pre_high_max < 0.98 表示开盘价低于前4日最高价的98%（即跌破2%）
        # today_close / today_open > 1.01 表示收盘价相对开盘价上涨超过1%
        if today_open / pre_high_max < 0.98 and today_close / today_open > 1.01:
            # 符合反弹条件，加入买入列表
            g.buy_list.append(etf)

        # 卖出条件1：今日收盘 < 昨日收盘（今日下跌）
        if today_close < yestoday_close:
            # 今日下跌，加入卖出列表
            sell_list.append(etf)

    # 如果有符合条件的ETF
    if g.buy_list:
        # 按优先级排序（g.etf_pool_2的顺序即为优先级）
        g.buy_list.sort(key=lambda x: g.etf_pool_2.index(x))
        # 选择优先级最高的前N只，而不是只选第一只
        selected_etfs = g.buy_list[:min(g.etf_rebound_hold_num, len(g.buy_list))]
        g.buy_list = selected_etfs
        
        # 检查是否需要换仓：如果当前持有的ETF不在新的选中列表中，且优先级较低，则卖出
        current_holdings = g.strategy_holdings[2]
        for current_etf in current_holdings:
            # 如果当前持仓不在新选中的列表中，或者新列表中有更高优先级的ETF需要替换
            if current_etf not in selected_etfs:
                # 检查是否需要腾出资金：如果当前持仓优先级低于新选中ETF中优先级最低的
                if (selected_etfs and 
                    g.etf_pool_2.index(current_etf) > g.etf_pool_2.index(selected_etfs[-1])):
                    sell_for_money_list.append(current_etf)
    
    #if g.buy_list:
        # 按优先级排序（g.etf_pool_2的顺序即为优先级）
        #g.buy_list.sort(key=lambda x: g.etf_pool_2.index(x))
        #selected_etf = g.buy_list[0]  # 选择优先级最高的
        #g.buy_list = [selected_etf]

        # 检查是否需要换仓：如果当前持有更高优先级的ETF，卖出以便买入新的反弹标的
        #current_holdings = g.strategy_holdings[2]
        #if current_holdings and g.etf_pool_2.index(current_holdings[0]) < g.etf_pool_2.index(selected_etf):
            #sell_for_money_list.append(current_holdings[0])

    # 执行卖出
    for etf in g.strategy_holdings[2]:
        position = context.portfolio.positions[etf]
        security = position.security
        trade_date = position.init_time
        holding_days = len(get_trade_days(start_date=trade_date, end_date=context.current_dt)) - 1

        # 卖出条件：
        # 1. 在sell_list中 且 持仓 >= 2天
        # 2. 持仓 >= 5天
        # 3. 需要换仓
        if (security in sell_list and holding_days >= g.limit_days) or (holding_days >= g.n_days) or \
                (security in sell_for_money_list):
            close_position(security)
            log.info(f"ℹ️ 策略2 平仓 {format_stock_code(security)} 持仓天数:{holding_days}天")

    if not g.buy_list:
        print(f"ℹ️ 策略2 今日无反弹标的")


def strategy2_buy(context):
    """策略2买入逻辑.

    每日14:50执行，买入符合反弹条件的ETF。

    注意：2023.10.01之前不运行（核心标的未上市）
    """
    cur_date = str(context.current_dt.date())
    if cur_date <= "2023-10-01":
        return

    # 过滤掉已持仓的ETF
    g.buy_list = list(set(g.buy_list) - set(g.strategy_holdings[2]))

    if len(g.buy_list) > 0:
        # 计算策略2可用资金
        cash = context.portfolio.total_value * g.portfolio_value_proportion[1]
        
        if cash < 100:
            log.warn(f'⚠️ 策略2 资金不足 可用:{context.portfolio.available_cash:.2f}元')
        else:
            # 平均分配资金给每只要买入的ETF
            cash_per_etf = cash / len(g.buy_list)
            for etf in g.buy_list:
                print(f"ℹ️ 策略2 买入候选:{format_stock_code(etf)}")
                open_position(context, etf, cash_per_etf, 2)
    #if len(g.buy_list) > 0:
        # 计算策略2可用资金
        #cash = context.portfolio.total_value * g.portfolio_value_proportion[1]

        #if cash < 100:
            #log.warn(f'⚠️ 策略2 资金不足 可用:{context.portfolio.available_cash:.2f}元')
        #else:
            #cash = context.portfolio.total_value * g.portfolio_value_proportion[1]
            #for etf in g.buy_list:
                #print(f"ℹ️ 策略2 买入候选:{format_stock_code(etf)}")
                #open_position(context, etf, cash, 2)


def strategy2_capital_balance(context):
    """策略2资金再平衡.

    历史原因：中证2000ETF在2023.9.28才上市，之前策略2无法运行。

    资金调整逻辑：
    - 2023.9.28之前：将策略2资金并入策略3
    - 2023.9.28之后：拨正资金，将策略3的部分资金转回策略2
    """
    cur_date = str(context.current_dt.date())

    # 2023.9.28之前：并入策略3
    if cur_date < "2023-09-28" and g.strategy_etf_2000_proportion_reset is None:
        g.portfolio_value_proportion[2] += g.strategy_etf_2000_proportion
        g.portfolio_value_proportion[1] = 0
        g.strategy_etf_2000_proportion_reset = False

    # 2023.9.28之后：拨正资金
    elif cur_date >= "2023-09-28" and g.strategy_etf_2000_proportion_reset is False:
        strategy_total_value = context.portfolio.total_value * g.strategy_etf_2000_proportion

        # 如果策略3有持仓，卖出部分资金
        if g.strategy_holdings[3]:
            cur_etf = g.strategy_holdings[3][0]
            if context.portfolio.positions[cur_etf].closeable_amount > 0:
                o = order_value(cur_etf, -strategy_total_value)
                if o:
                    profit = (o.price - o.avg_cost) * o.amount
                    profit_pct = (o.price - o.avg_cost) / o.avg_cost * 100
                    profit_icon = "↑" if profit > 0 else "↓"
                    print(f"💸 策略2 资金转移 {format_stock_code(cur_etf)} 卖价:{o.price:.3f} 成本:{o.avg_cost:.3f} 卖量:{o.amount} 盈亏:{profit:+.2f} ({profit_pct:+.2f}%) {profit_icon}")

        # 调整比例
        g.portfolio_value_proportion[2] -= g.strategy_etf_2000_proportion
        g.portfolio_value_proportion[1] = g.strategy_etf_2000_proportion
        g.strategy_etf_2000_proportion_reset = True


""" ====================== 策略3: ETF轮动 ====================== """


def strategy3_filter_below_ma(stocks, days=20):
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
                # log.debug(f"{stock} 历史数据不足{days}天，跳过过滤")
                continue
                
            # 计算N日均价
            ma_n = hist["close"].mean()
            # 获取当前价格
            current_price = current_data[stock].last_price
            
            # 保留当前价 >= N日均价的标的
            if current_price >= ma_n:
                filtered.append(stock)
            else:
                # log.debug(f"{stock} 过滤（当前价 {current_price:.2f} < {days}日均价 {ma_n:.2f}）")
                pass
                
        except Exception as e:
            log.warn(f"计算{stock} {days}日均价失败: {e}")
            continue
            
    return filtered


def strategy3_get_volume_ratio(context, security, lookback_days, threshold):
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
        if avg_volume == 0:
             return None
        volume_ratio = current_volume / avg_volume

        # 3. 超过阈值视为放量
        return volume_ratio if volume_ratio > threshold else None
    except Exception as e:
        log.warn(f"成交量检测失败 {security}：{e}")
        return None


def strategy3_get_etf_rank(context, etf_pool):
    """ETF轮动筛选 (Strictly Consistent with etf_rota_pro.py)."""
    
    # 1. 先对原始ETF池进行均线过滤（在动量计算前）
    filtered_pool = etf_pool
    if g.enable_ma_filter:
        filtered_pool = strategy3_filter_below_ma(
            stocks=filtered_pool,
            days=g.ma_filter_days
        )
    
    # 2. 仅对过滤后的ETF池计算动量评分
    data = pd.DataFrame(index=filtered_pool, 
                       columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    
    for etf in filtered_pool:
        try:
            # 获取历史数据（含成交量），天数 = 动量天数 + 量价背离天数
            fetch_days = g.m_days + g.vol_baseline_days + g.vol_recent_days
            df = attribute_history(etf, fetch_days, "1d", ["close", "high", "volume"])
            prices = np.append(df["close"].values, current_data[etf].last_price)

            # 仅取 m_days+1 个价格点用于动量计算，与 etf_rota_pro 保持一致
            momentum_prices = prices[-(g.m_days + 1):]
            y = np.log(momentum_prices)
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

            # ============================================================
            # 量价背离顶部识别：价格处于阶段高位 + 近期成交量显著萎缩 → 剔除
            # 逻辑：动量得分虽高，但量能已经先行衰竭，说明多头动力不足，
            # 继续追入极易买在顶部，买入后主力出货导致急速下跌。
            # ============================================================
            if g.enable_vol_divergence_filter and data.loc[etf, "score"] > 0:
                try:
                    vols         = df["volume"].values
                    vol_recent   = vols[-g.vol_recent_days:].mean()
                    vol_baseline = vols[-(g.vol_recent_days + g.vol_baseline_days):-g.vol_recent_days].mean()

                    # 当前价格在动量周期内的分位数
                    momentum_close   = df["close"].values[-g.m_days:]
                    price_percentile = np.mean(momentum_close <= current_data[etf].last_price)

                    at_price_high    = price_percentile >= g.price_high_percentile
                    volume_shrinking = (vol_baseline > 0) and (vol_recent / vol_baseline < g.vol_shrink_ratio)

                    if at_price_high and volume_shrinking:
                        log.info(
                            f"📊 量价背离 {etf} 价格分位:{price_percentile:.0%}(>{g.price_high_percentile:.0%}) "
                            f"近{g.vol_recent_days}日均量:{vol_recent:.0f} 基准:{vol_baseline:.0f} "
                            f"比值:{vol_recent/vol_baseline:.2f}(<{g.vol_shrink_ratio}) → score置0"
                        )
                        data.loc[etf, "score"] = 0
                except Exception as ve:
                    log.debug(f"❗ 量价背离检测异常 {etf}（跳过）: {ve}")

        except Exception as e:
            data.loc[etf, "score"] = 0

    # 过滤ETF，并按得分降序排列
    data = data.query("0 < score < 5").sort_values(by="score", ascending=False)
    
    # 打印排名日志（含持仓标记）
    # 获取策略3当前持仓列表，用于在排名中高亮显示
    current_holdings_3 = g.strategy_holdings[3] if hasattr(g, 'strategy_holdings') else []
    log.info(f"{'代码':<8} {'名称':<8} {'价格':<8} {'MA20':<8} {'5日涨跌':<8} {'波动率':<8} {'状态':<6} {'得分':<8} {'r2':<8} {'年化收益率':<8} {'持仓':<6}")
    for etf in data.head(50).index:
        try:
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
            holding_tag = "💼持仓" if etf in current_holdings_3 else "      "
            
            score_val = data.loc[etf, 'score']
            r2_val = data.loc[etf, 'r2']
            ann_ret = data.loc[etf, 'annualized_returns']
            
            log.info(f"{etf[:6]:<8} {name:<8} {price:<8.3f} {ma20:<8.3f} {pct_5d:>7.2f}% {volatility:>7.2f}% {status:<6} {score_val:<8.4f} {r2_val:<8.4f} {ann_ret:<8.4f} {holding_tag}")
        except:
            pass

    return data.index.tolist()


def strategy3_sell(context):
    """策略3卖出逻辑 (Strictly Consistent with etf_rota_pro.py)."""
    
    # 1. 获取目标 (stock_sum)
    rank_list = strategy3_get_etf_rank(context, g.etf_pool_3)
    targets = rank_list[: g.etf_rotation_hold_num]
    
    hold_list = g.strategy_holdings[3]
    
    # 2. 优先卖出放量的持仓ETF（若启用成交量检测）
    if g.enable_volume_check:
        for stock in list(hold_list):
            vol_ratio = strategy3_get_volume_ratio(
                context,
                stock,
                g.volume_lookback,
                g.volume_threshold
            )
            if vol_ratio is not None:
                # 放量，强制卖出
                log.info(f"持仓 {stock} 放量（比值：{vol_ratio:.2f}），触发卖出")
                close_position(stock)
    
    # 3. 清仓不在目标列表中的标的
    hold_list = g.strategy_holdings[3]
    for stock in list(hold_list):
        if stock not in targets:
            log.info(f"卖出 {stock} 不在目标列表中")
            close_position(stock)


def strategy3_buy(context):
    """策略3买入逻辑 (Strictly Consistent with etf_rota_pro.py)."""
    # 1. 获取初始候选ETF
    rank_list = strategy3_get_etf_rank(context, g.etf_pool_3)
    raw_targets = rank_list[: g.etf_rotation_hold_num]
    
    if not raw_targets:
        return
    
    # 2. 过滤放量的候选ETF（若启用成交量检测）
    targets = []
    if g.enable_volume_check:
        for etf in raw_targets:
            vol_ratio = strategy3_get_volume_ratio(
                context,
                etf,
                g.volume_lookback,
                g.volume_threshold
            )
            if vol_ratio is None:
                # 未放量或检测失败，保留为候选
                targets.append(etf)
            else:
                log.info(f"排除买入 {etf}（放量，比值：{vol_ratio:.2f}）")
    else:
        targets = raw_targets

    if not targets:
        log.info("无符合条件的买入标的（均放量）")
        return
    
    current_data = get_current_data()
    hold_list = g.strategy_holdings[3]
    current_hold_in_targets = [s for s in hold_list if s in targets]
    current_hold_count = len(current_hold_in_targets)
    
    total_value = context.portfolio.total_value
    available_cash = context.portfolio.available_cash
    target_strategy_value = total_value * g.portfolio_value_proportion[2]
    
    for stock in targets:
        weight = 1.0 / len(targets)
        target_val = target_strategy_value * weight
        
        last_price = current_data[stock].last_price
        
        if stock in context.portfolio.positions:
            current_value = context.portfolio.positions[stock].value
        else:
            current_value = 0
            
        # 最小交易额检查
        min_money = 500
        
        if current_hold_count == 0:
            # 未持仓，计算买入需求
            need_buy_value = target_val - current_value
            actual_buy_value = min(need_buy_value, available_cash)
            
            if actual_buy_value <= max(min_money, last_price * 100):
                continue
            
            # 执行买入
            open_position(context, stock, target_val, 3)
            
        else:
            # 已持仓，判断是否补仓
            if current_value < target_val * 0.9:
                rebalance_amount = target_val - current_value
                actual_rebalance = min(rebalance_amount, available_cash)
                
                if actual_rebalance > max(min_money, last_price * 100):
                    open_position(context, stock, target_val, 3)



""" ====================== 辅助的定时执行函数 ====================== """


def make_record(context):
    """记录各策略每日收益并绘制曲线.

    每日15:01执行，完成：
    1. 计算各策略当前价值
    2. 计算各策略收益率
    3. 绘制策略收益曲线
    4. 预览次日ETF动量排名
    """
    positions = context.portfolio.positions
    if not positions:
        return

    current_data = get_current_data()

    # 初始化策略价值数据
    g.strategy_value_data = {1: 0, 2: 0, 3: 0}
    copy_strategy_value = {
        1: g.strategy_value[1],
        2: g.strategy_value[2],
        3: g.strategy_value[3],
    }

    # 计算各策略的盈亏
    for stock, pos in positions.items():
        strategy_id = g.stock_strategy[stock]
        current_value = pos.total_amount * current_data[stock].last_price
        cost_value = pos.total_amount * pos.avg_cost
        pnl_value = current_value - cost_value

        copy_strategy_value[strategy_id] += pnl_value
        g.strategy_value_data[strategy_id] += current_value

    # 计算各策略的基准资金（使用原始比例，不受动态调整影响）
    base_cash_1 = g.starting_cash * g.portfolio_value_proportion_original[0]
    base_cash_2 = g.starting_cash * g.strategy_etf_2000_proportion
    base_cash_3 = g.starting_cash * g.portfolio_value_proportion_original[2]

    # 记录策略1收益率
    if base_cash_1 > 0:
        record(涨停基因轮动=round(copy_strategy_value[1] / base_cash_1 * 100 - 100, 2))

    # 记录策略2收益率
    if base_cash_2 > 0:
        record(ETF反弹=round(copy_strategy_value[2] / base_cash_2 * 100 - 100, 2))

    # 记录策略3收益率
    if base_cash_3 > 0:
        record(ETF轮动=round(copy_strategy_value[3] / base_cash_3 * 100 - 100, 2))

    # 预览次日ETF动量排名（仅当策略3启用时）
    if g.portfolio_value_proportion[2]:
        print("ℹ️ 收盘后检测最新的ETF动量排名 方便明日参考")
        strategy3_get_etf_rank(context, g.etf_pool_3)


def print_summary(context):
    """打印当前投资组合的总资产和持仓详情.

    每日15:02执行，打印持仓表格，包含：
    - 每只股票的盈亏情况
    - 各策略的总市值和占比
    - 总资产
    """
    total_value = round(context.portfolio.total_value, 2)
    current_stocks = context.portfolio.positions

    # 空仓状态
    if not current_stocks:
        print(f"🚤 当前总资产:{total_value} 状态:休息中")
        return

    # 创建持仓表格
    table = PrettyTable([
        "所属策略",
        "股票代码",
        "股票名称",
        "持仓数量",
        "持仓价格",
        "当前价格",
        "盈亏数额",
        "盈亏比例",
        "股票市值",
        "仓位占比"])
    table.hrules = prettytable.ALL

    total_market_value = 0

    # 遍历持仓
    for stock in current_stocks:
        current_shares = current_stocks[stock].total_amount
        current_price = round(get_current_data()[stock].last_price, 3)
        avg_cost = round(current_stocks[stock].avg_cost, 3)

        # 计算盈亏
        profit_ratio = (current_price - avg_cost) / avg_cost if avg_cost != 0 else 0
        profit_ratio_percent = f"{profit_ratio * 100:.2f}%"
        profit_ratio_percent += f" {'↑' if profit_ratio > 0 else '↓'}"

        profit_amount = round((current_price - avg_cost) * current_shares, 2)
        market_value = round(current_shares * current_price, 2)
        total_market_value += market_value

        stock_code = stock.split(".")[0]

        # 获取股票名称（不含代码）
        try:
            stock_info = get_security_info(stock)
            stock_name = stock_info.display_name if stock_info else stock_code
        except Exception:
            stock_name = stock_code

        # 添加行
        strategy_names = {1: "策略1", 2: "策略2", 3: "策略3"}
        table.add_row([
            strategy_names[g.stock_strategy[stock]],
            stock_code,
            stock_name,
            current_shares,
            avg_cost,
            current_price,
            profit_amount,
            profit_ratio_percent,
            market_value,
            f"{market_value / context.portfolio.total_value * 100:.2f}%"
        ])

    # 添加策略汇总行
    total_value = context.portfolio.total_value
    if g.strategy_value_data[1]:
        table.add_row(["策略1", "", "", "", "", "", "", "", f"{g.strategy_value_data[1]:.2f}",
                       f"{g.strategy_value_data[1] / total_value * 100:.2f}%"])
    if g.strategy_value_data[2]:
        table.add_row(["策略2", "", "", "", "", "", "", "", f"{g.strategy_value_data[2]:.2f}",
                       f"{g.strategy_value_data[2] / total_value * 100:.2f}%"])
    if g.strategy_value_data[3]:
        table.add_row(["策略3", "", "", "", "", "", "", "", f"{g.strategy_value_data[3]:.2f}",
                       f"{g.strategy_value_data[3] / total_value * 100:.2f}%"])

    # 添加总计行
    table.add_row(["总市值", "", "", "", "", "", "", "", f"{total_market_value:.2f}", ""])
    table.add_row(["总资产", "", "", "", "", "", "", "", f"{total_value:.2f}", ""])

    print(f'当前总资产\n{table}')


""" ====================== 公共函数 ====================== """


def my_order_target_value(security, value):
    """封装下单函数并打印交易信息.

    Args:
        security: 证券代码
        value: 目标市值，0表示清仓

    Returns:
        Order: 订单对象
    """
    o = order_target_value(security, value)
    if o:
        if o.is_buy:
            # 买入
            if o.price * o.amount > 0:
                print(f"📦 建仓 {format_stock_code(security)} 买价:{o.price:.3f} 买量:{o.amount} 价值:{o.price * o.amount:.2f}")
                return o
        else:
            # 卖出
            if o.price * o.amount > 0:
                profit = (o.price - o.avg_cost) * o.amount
                profit_pct = (o.price - o.avg_cost) / o.avg_cost * 100
                profit_icon = "↑" if profit > 0 else "↓"
                print(f"📤 平仓 {format_stock_code(security)} 卖价:{o.price:.3f} 成本:{o.avg_cost:.3f} 卖量:{o.amount} 盈亏:{profit:+.2f} ({profit_pct:+.2f}%) {profit_icon}")
                return o


#def open_position(context, security, value, strategy_id):
    """开仓买入并记录策略持仓.

    Args:
        context: 策略上下文
        security: 证券代码
        value: 买入金额
        strategy_id: 策略ID（1/2/3）

    Returns:
        Order: 订单对象
    """
    # 最小买入金额检查
#    if value <= 5000:
#        return

    # 如果已持仓，检查是否需要调整
#    if security in context.portfolio.positions:
#        security_value = context.portfolio.positions[security].value
#        if abs(value - security_value) < 5000:
#            return

    # 下单
#    order = my_order_target_value(security, value)
#    if order:
        # 记录持仓
#        security not in g.strategy_holdings[strategy_id] and g.strategy_holdings[strategy_id].append(security)
#        g.stock_strategy[security] = strategy_id

#    return order

def open_position(context, security, value, strategy_id):
    """开仓买入并记录策略持仓.
    
    统一的买入函数，被三个策略调用，完成：
    1. 买入金额检查（最小5000元）
    2. 如果已持仓，判断是否需要调整仓位
    3. 执行买入订单
    4. 记录持仓到对应策略的持仓列表
    
    Args:
        context: 策略上下文
        security: 证券代码（股票或ETF）
        value: 目标持仓市值（元）
        strategy_id: 策略ID（1/2/3）
    
    Returns:
        Order: 订单对象，如果买入失败返回None
    """
    # 最小买入金额检查：如果目标市值小于等于5000元，不买入（避免小额交易）
    if value <= 5000:
        return
    
    # 如果已持仓，检查是否需要调整（改为根据目标持仓市值调整）
    if security in context.portfolio.positions:
        # 获取当前持仓市值
        security_value = context.portfolio.positions[security].value
        # 如果当前市值与目标市值差异超过20%，则调整仓位
        # 这样可以避免频繁小额调整，只在差异较大时调整
        if abs(value - security_value) / value > 0.2:
            # 调整到目标市值
            order = my_order_target_value(security, value)
            if order:
                # 记录持仓：如果该股票不在策略持仓列表中，则添加
                # 使用 and 的短路特性：如果已在列表中，不执行append；如果不在，执行append
                security not in g.strategy_holdings[strategy_id] and g.strategy_holdings[strategy_id].append(security)
                # 记录该股票属于哪个策略
                g.stock_strategy[security] = strategy_id
            return order
        else:
            # 差异小于20%，不需要调整，直接返回
            return
    else:
        # 新买入：如果该股票尚未持仓
        order = my_order_target_value(security, value)
        if order:
            # 记录持仓：添加到对应策略的持仓列表
            security not in g.strategy_holdings[strategy_id] and g.strategy_holdings[strategy_id].append(security)
            # 记录该股票属于哪个策略
            g.stock_strategy[security] = strategy_id
        return order

def close_position(security):
    """平仓卖出并清空策略持仓.

    统一的卖出函数，被三个策略调用，完成：
    1. 执行卖出订单（目标市值为0表示清仓）
    2. 从策略持仓列表中移除该股票
    3. 更新策略的累计盈亏

    Args:
        security: 证券代码（股票或ETF）

    Returns:
        Order: 订单对象，如果卖出失败返回None
    """
    # 下单：目标市值为0表示全部卖出（清仓）
    order = my_order_target_value(security, 0)
    if order:
        # 清除持仓记录：从对应策略的持仓列表中移除该股票
        strategy_id = g.stock_strategy[security]  # 获取该股票所属的策略ID
        # 使用 and 的短路特性：如果该股票在列表中，执行remove；如果不在，不执行
        security in g.strategy_holdings[strategy_id] and g.strategy_holdings[strategy_id].remove(security)

        # 更新策略价值：计算本次卖出的盈亏并累加到策略总盈亏中
        # pnl_value = (卖出价 - 成本价) × 卖出数量
        pnl_value = (order.price - order.avg_cost) * order.amount
        # 累加到对应策略的累计盈亏
        g.strategy_value[strategy_id] += pnl_value

    return order


def format_stock_code(stock_code):
    """格式化股票代码显示.

    将股票代码格式化为：代码(名称) 的形式，方便阅读。

    Args:
        stock_code: 股票代码

    Returns:
        str: 格式化后的代码（包含名称）
    """
    try:
        stock_info = get_security_info(stock_code)
        if stock_info is None:
            return f"{stock_code[:6]}"
        return f"{stock_code[:6]}({stock_info.display_name})"
    except Exception:
        return f"{stock_code[:6]}"


""" ====================== 执行入口, 定时任务下发 ====================== """


def after_code_changed(context):
    """策略代码变更后的入口函数，配置定时任务.

    根据启用的策略配置相应的定时任务。
    所有时间均为北京时间，对应A股交易时间：
    - 开盘：9:30
    - 收盘：15:00
    """
    # ========== 诊断信息 ==========
    print("=" * 80)
    print("🔍 after_code_changed 诊断信息")
    print(f"🔍 当前时间:{context.current_dt}")

    # 检查关键变量是否存在
    has_proportion = hasattr(g, 'portfolio_value_proportion')
    has_etf_2000 = hasattr(g, 'strategy_etf_2000_proportion')

    print(f"🔍 g.portfolio_value_proportion 存在:{has_proportion}")
    if has_proportion:
        print(f"🔍 g.portfolio_value_proportion 值:{g.portfolio_value_proportion}")
        if hasattr(g, 'portfolio_value_proportion_original'):
            print(f"🔍 g.portfolio_value_proportion_original 值:{g.portfolio_value_proportion_original}")
        if hasattr(g, 'strategy1_paused'):
            print(f"🔍 g.strategy1_paused:{g.strategy1_paused}")

    print(f"🔍 g.strategy_etf_2000_proportion 存在:{has_etf_2000}")
    if has_etf_2000:
        print(f"🔍 g.strategy_etf_2000_proportion 值:{g.strategy_etf_2000_proportion}")

    # 检查是否有持仓
    has_positions = len(context.portfolio.positions) > 0
    print(f"🔍 当前是否有持仓:{has_positions}")
    if has_positions:
        print(f"🔍 持仓列表:{list(context.portfolio.positions.keys())}")

    print("=" * 80)

    # 清空所有定时任务
    unschedule_all()

    # ========== 容错初始化：确保必要的全局变量已初始化 ==========
    # 修复bug: 如果变量不存在，重新初始化而不是直接返回
    if not has_proportion:
        print("⚠️ 检测到 g.portfolio_value_proportion 丢失！")
        if has_positions:
            print("⚠️ 警告：账户有持仓，重置资金比例可能影响策略行为")
        # 使用代码中的默认配置重新初始化
        g.portfolio_value_proportion = [0.4, 0.2, 0.4]
        g.portfolio_value_proportion_original = [0.4, 0.2, 0.4]
        g.strategy1_paused = False
        print("✅ 已重新初始化 g.portfolio_value_proportion = [0.4, 0.2, 0.4]")

    # 强制重新加载策略参数，防止模拟盘更新代码时新增变量未生效导致异常
    set_strategy_params(context)
    
    if not has_etf_2000:
        print("⚠️ 检测到 g.strategy_etf_2000_proportion 丢失！")
        g.strategy_etf_2000_proportion = g.portfolio_value_proportion[1]
        g.strategy_etf_2000_proportion_reset = None
        print(f"✅ 已重新初始化 g.strategy_etf_2000_proportion = {g.strategy_etf_2000_proportion}")

    # ========== 策略1定时任务 ==========
    # 只有当策略1的资金占比大于0时才配置定时任务
    if g.portfolio_value_proportion[0] > 0:
        # 每日9:05执行：准备策略1运行环境，检查是否进入/退出空仓期，获取昨日涨停列表
        run_daily(strategy1_prepare, '9:05')                  # 准备：检查空仓期
        # 每周二10:02执行：卖出不在目标池的股票（保留涨停股）
        run_weekly(strategy1_sell, 2, '10:02')                # 卖出：每周二10:02
        # 每周二10:03执行：买入新股票补仓至目标数量
        run_weekly(strategy1_buy, 2, '10:03')                 # 买入：每周二10:03
        # 每日10:00执行：根据配置的止损策略执行止盈止损
        run_daily(strategy1_sell_stocks, time='10:00')        # 止盈止损：每日10:00
        # 每日14:20执行：盘中检查涨停股表现、天量、换手率异常，余额补仓
        run_daily(strategy1_trade_afternoon, time='14:20')    # 盘中检查：14:20
        # 每日14:55执行：盘中检查涨停股表现、天量、换手率异常，余额补仓
        run_daily(strategy1_trade_afternoon, time='14:55')    # 盘中检查：14:55
        # 每日14:50执行：如果处于空仓期，清空所有持仓
        run_daily(strategy1_close_account, '14:50')           # 空仓期清仓：14:50

    # ========== 策略2定时任务 ==========
    # 只有当策略2的资金占比大于0时才配置定时任务
    if g.strategy_etf_2000_proportion > 0:
        # 每日14:45执行：资金再平衡（处理2023.9.28前后资金分配问题）
        run_daily(strategy2_capital_balance, '14:40')  # 资金平衡：14:45
        # 每日14:49执行：筛选符合反弹条件的ETF，卖出满足条件的持仓
        run_daily(strategy2_sell, '14:45')             # 卖出：14:49
        # 每日14:50执行：买入符合反弹条件的ETF
        run_daily(strategy2_buy, '14:47')              # 买入：14:50

    # ========== 策略3定时任务 ==========
    # 只有当策略3的资金占比大于0时才配置定时任务
    if g.portfolio_value_proportion[2] > 0:
        # 每日10:29执行：执行卖出操作 (Strictly consistent with etf_rota_pro.py)
        run_daily(strategy3_sell, '10:20')          # 卖出：10:29
        # 每日10:30执行：执行买入操作 (Strictly consistent with etf_rota_pro.py)
        run_daily(strategy3_buy, '10:22')           # 买入：10:30

    # ========== 公共定时任务 ==========
    # 每日15:01执行：记录各策略每日收益并绘制曲线，预览次日ETF动量排名
    run_daily(make_record, '15:01')      # 记录收益曲线
    # 每日15:02执行：打印当前投资组合的总资产和持仓详情表格
    run_daily(print_summary, '15:02')    # 打印持仓总览
