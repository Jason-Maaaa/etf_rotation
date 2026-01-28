# ============================================================================
# 文件说明：ETF轮动策略 - 基于动量选股和均线过滤的量化交易策略
# ============================================================================
# 本策略参考了多个聚宽平台的策略文章，整合优化而成
# 核心思想：通过动量评分选择表现最好的ETF，结合均线过滤和成交量检测进行轮动交易
# ============================================================================

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

# ============================================================================
# 导入必要的库
# ============================================================================
from jqdata import *  # 聚宽平台的数据接口，提供行情数据、交易函数等核心功能
import datetime  # 日期时间处理库，用于日期计算和格式化
import math  # 数学函数库，用于指数、对数等数学运算
import numpy as np  # 数值计算库，用于数组操作、线性回归等
from scipy.optimize import minimize  # 科学计算库的优化函数（本代码中未实际使用）
from scipy.linalg import inv  # 科学计算库的线性代数函数（本代码中未实际使用）
import uuid  # 生成唯一标识符的库（本代码中未实际使用）



# ============================================================================
# QMT（迅投QMT）交易接口相关代码（已注释，如需实盘对接QMT可取消注释）
# ============================================================================
# from jqtoqmt import *  # 导入聚宽到QMT的桥接模块
# g.strategy = 'jq1'  # 策略名称标识
# order = qmt_order(order)  # 将聚宽的order函数包装为QMT订单函数
# order_target = qmt_order_target(order_target)  # 将聚宽的order_target函数包装为QMT订单函数
# order_value = qmt_order_value(order_value)  # 将聚宽的order_value函数包装为QMT订单函数
# order_target_value = qmt_order_target_value(order_target_value)  # 将聚宽的order_target_value函数包装为QMT订单函数





# ============================================================================
# ETF池配置 - 定义策略可交易的ETF列表
# ============================================================================
# 说明：XSHG表示上海证券交易所，XSHE表示深圳证券交易所
# 策略会从这个池子中选择动量最强的ETF进行轮动交易
# ============================================================================
etf_pool = [
    # ========== 境外市场ETF ==========
    "513100.XSHG",  # 纳指ETF - 跟踪纳斯达克100指数，投资美国科技股
    "159509.XSHE",  # 纳指科技ETF - 跟踪纳斯达克科技指数
    "513520.XSHG",  # 日经ETF - 跟踪日经225指数，投资日本股市
    "513030.XSHG",  # 德国ETF - 跟踪德国DAX30指数，投资德国股市
    
    # ========== 商品类ETF ==========
    "518880.XSHG",  # 黄金ETF - 跟踪黄金现货价格，避险资产
    "159980.XSHE",  # 有色ETF - 跟踪有色金属指数，投资铜、铝等金属
    "159985.XSHE",  # 豆粕ETF - 跟踪豆粕期货价格，投资农产品
    "159981.XSHE",  # 能源化工ETF - 跟踪能源化工指数
    #"159870.XSHE",   # 化工ETF（已注释，不参与轮动）
    "501018.XSHG",  # 南方原油 - 投资原油相关资产，跟踪原油价格
    
    # ========== 债券类ETF ==========
    "511090.XSHG",  # 30年国债ETF - 跟踪30年期国债，长期债券投资
    
    # ========== 港股ETF ==========
    "513130.XSHG",  # 恒生科技 - 跟踪恒生科技指数，投资港股科技股
    "513690.XSHG",  # 港股红利 - 跟踪港股红利指数，投资高分红港股
    
    # ========== 国内宽基ETF ==========
    "510180.XSHG",   # 上证180ETF - 跟踪上证180指数，大盘蓝筹股
    "159915.XSHE",   # 创业板ETF - 跟踪创业板指数，中小盘成长股
    
    # ========== 行业主题ETF ==========
    "510410.XSHG",   # 资源ETF - 跟踪资源类股票指数
    "515650.XSHG",   # 消费50ETF - 跟踪消费50指数，投资消费行业
    "512290.XSHG",   # 生物医药ETF - 跟踪生物医药指数，投资医药行业
    "588120.XSHG",   # 科创100ETF - 跟踪科创板100指数，投资科技创新企业
    "515070.XSHG",   # 人工智能ETF - 跟踪人工智能相关股票指数
    
    "159851.XSHE",   # 金融科技ETF - 跟踪金融科技指数
    "159637.XSHE",   # 新能源车ETF - 跟踪新能源汽车指数
    "516160.XSHG",   # 新能源ETF - 跟踪新能源指数，投资光伏、风电等
    
    "159550.XSHE",   # 互联网ETF - 跟踪互联网相关股票指数
    "512710.XSHG",   # 军工ETF - 跟踪军工行业指数
    "159692.XSHE",   # 证券ETF - 跟踪证券公司指数
    "512480.XSHG",   # 半导体ETF - 跟踪半导体行业指数
    "515250.XSHG",    # 智能汽车ETF - 跟踪智能汽车相关股票
    "159378.XSHE",     # 通用航空ETF - 跟踪通用航空行业指数
    "516510.XSHG",    # 云计算ETF - 跟踪云计算相关股票指数
    "515050.XSHG",     # 5G通信ETF - 跟踪5G通信相关股票指数
    "159995.XSHE",     # 芯片ETF - 跟踪芯片行业指数
    "515790.XSHG",     # 光伏ETF - 跟踪光伏产业指数
    "515000.XSHG"   # 科技ETF - 跟踪科技行业指数
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













# ============================================================================
# 全局变量定义
# ============================================================================
g_strategys = {}  # 存储所有策略的配置信息字典，用于策略管理和重启恢复

# 投资组合价值分配比例列表，[1]表示将100%的资金分配给第一个策略
# 如果有多个策略，可以设置为[0.5, 0.5]表示各分配50%
g_portfolio_value_proportion = [1]  # 测试版：当前只使用一个策略

# 记录每个子策略的持仓股票字典
# 格式：{策略索引: {股票代码: 持仓数量}}
# 例如：{0: {"513100.XSHG": 1000, "159915.XSHE": 500}}
g_positions = {i: {} for i in range(len(g_portfolio_value_proportion))}

g_weights = {}  # 全天候权重字典（预留，用于多策略权重分配）

# 交易通道标识，用于与ThsAutoTrader（同花顺自动交易）对接
# 需要与ThsAutoTrader中的channel保持一致才能正常通信
g.channel = 'etfld'



# ============================================================================
# 核心资产轮动策略相关参数配置
# ============================================================================
g_etf_rotation = {
    "index": 0,  # 策略索引，对应g_positions中的键值
    "name": "核心资产轮动策略",  # 策略名称，用于日志和显示
    "stock_sum": 1,  # 同时持有的ETF数量上限，1表示只持有一只ETF
    "hold_list": [],  # 当前持仓的ETF列表，由系统自动维护
    
    "min_money": 500,  # 最小交易金额（元），用于限制手续费，低于此金额不交易
    "etf_pool": etf_pool,  # ETF池列表，策略会从这个池子中选择标的
    
    "m_days": 25,  # 动量参考天数，用于计算ETF的动量评分（年化收益率和R²）
    
    # ========== 成交量检测参数 ==========
    "enable_volume_check": True,  # 是否启用成交量检测功能
    "volume_lookback": 5,  # 历史成交量参考天数，用于计算平均成交量
    "volume_threshold": 2.0,  # 放量阈值，当日成交量/历史平均成交量 > 2.0视为放量
    # 放量时：持仓ETF会被卖出，候选ETF会被排除买入
    
    # ========== 均线过滤参数 ==========
    "ma_filter_days": 20,  # 均线过滤天数，只选择当前价 >= N日均价的ETF
    "enable_ma_filter": True,  # 是否启用均线过滤功能
    # 均线过滤在动量计算之前执行，可以过滤掉处于下跌趋势的ETF
}



# ============================================================================
# 订单函数封装
# ============================================================================
def order_(context, security, vol):
    """
    封装聚宽的order函数，简化参数传递
    参数:
        context: 聚宽策略上下文对象，包含账户、持仓等信息
        security: 证券代码，如"513100.XSHG"
        vol: 交易数量，正数表示买入，负数表示卖出
    返回:
        订单对象，包含成交信息
    """
    o = order(security, vol)  # 调用聚宽平台的订单函数
    return o

    

    

# ============================================================================
# 初始化函数 - 策略启动时只执行一次
# ============================================================================
def initialize(context):
    """
    策略初始化函数，在策略启动时执行一次
    用于设置交易参数、滑点、手续费、定时任务等
    """
    
    # ========== 策略选项设置 ==========
    set_option("avoid_future_data", True)  # 打开防未来函数，避免使用未来数据导致回测不准确
    set_option("use_real_price", True)  # 开启动态复权模式，使用真实价格进行交易
    
    # ========== 日志设置 ==========
    log.info("初始函数开始运行且全局只运行一次")  # 输出初始化日志
    log.set_level('order', 'error')  # 订单日志级别设为error，只显示错误
    log.set_level('system', 'error')  # 系统日志级别设为error，只显示错误
    log.set_level('strategy', 'debug')  # 策略日志级别设为debug，显示详细信息
    
    # ========== 滑点设置 ==========
    # 滑点：实际成交价与预期价格的偏差，用于模拟真实交易
    set_slippage(FixedSlippage(0.0001), type="fund")  # 基金类标的滑点0.01%
    set_slippage(FixedSlippage(0.003), type="stock")  # 股票类标的滑点0.3%
    
    # ========== 交易成本设置（股票/ETF） ==========
    set_order_cost(
        OrderCost(
            open_tax=0,  # 买入印花税：0（A股买入不收印花税）
            close_tax=0.001,  # 卖出印花税：0.1%（A股卖出收0.1%印花税）
            open_commission=0.0003,  # 买入佣金：0.03%（万分之三）
            close_commission=0.0003,  # 卖出佣金：0.03%（万分之三）
            close_today_commission=0,  # 当日卖出佣金：0（ETF不支持T+0）
            min_commission=5,  # 最低佣金：5元（不足5元按5元收取）
        ),
        type="stock",  # 适用于股票和ETF
    )
    
    # ========== 交易成本设置（货币ETF） ==========
    # 货币ETF通常免收交易费用
    set_order_cost(
        OrderCost(
            open_tax=0,  # 买入印花税：0
            close_tax=0,  # 卖出印花税：0
            open_commission=0,  # 买入佣金：0
            close_commission=0,  # 卖出佣金：0
            close_today_commission=0,  # 当日卖出佣金：0
            min_commission=0,  # 最低佣金：0
        ),
        type="mmf",  # 货币市场基金类型
    )
    
    # ========== 定时任务设置 ==========
    if g_portfolio_value_proportion[0] > 0:  # 如果第一个策略的资金比例大于0
        # 10:29执行卖出操作（先卖后买，避免资金不足）
        run_daily(etf_rotation_sell, "10:29")
        # 10:30执行买入操作（卖出后立即买入新标的）
        run_daily(etf_rotation_buy, "10:30")
    
    # 14:59执行尾盘处理，清理未记录的持仓（如送股等）
    run_daily(end_trade, "14:59")



# ============================================================================
# 进程初始化函数 - 策略重启时执行
# ============================================================================
def process_initialize(context):
    """
    当策略进程重启时执行此函数
    用于恢复策略状态，重新初始化策略字典
    """
    print("重启程序")  # 输出重启提示
    global g_strategys  # 声明使用全局变量
    
    # 重新初始化策略字典，用于策略管理和状态恢复
    g_strategys = {
        "核心资产轮动策略": {
            "index": 0,  # 策略索引
            "name": "核心资产轮动策略"  # 策略名称
        }
    }





# ============================================================================
# 尾盘处理函数 - 每日14:59执行
# ============================================================================
def end_trade(context):
    """
    尾盘处理函数，用于清理未记录的持仓
    例如：送股、配股等导致持仓增加但未在g_positions中记录的情况
    """
    # 获取所有策略记录的持仓股票集合（使用集合推导式）
    # 遍历g_positions的所有值（每个策略的持仓字典），提取所有股票代码
    marked = {s for d in g_positions.values() for s in d}
    
    # 获取当前市场数据对象
    current_data = get_current_data()
    
    # 遍历账户中的所有持仓
    for stock in context.portfolio.positions:
        # 如果持仓不在策略记录的持仓中，说明是未记录的持仓（如送股）
        if stock not in marked:
            # 获取当前价格
            price = current_data[stock].last_price
            # 获取持仓总数量
            pos = context.portfolio.positions[stock].total_amount
            # 卖出全部未记录的持仓
            if my_order(context, stock, -pos, price, 0):
                log.info(f"卖出{stock}因送股未记录在持仓中", price, pos)





# ============================================================================
# 订单封装函数
# ============================================================================
def my_order(context, security, vol, price, target_position):
    """
    订单封装函数，统一订单接口
    参数:
        context: 策略上下文对象
        security: 证券代码
        vol: 交易数量（正数买入，负数卖出）
        price: 价格（预留参数，实际下单使用市价）
        target_position: 目标持仓（预留参数，未使用）
    返回:
        订单对象
    """
    o = order_(context, security, vol)  # 调用订单函数
    return o







# 核心资产轮动策略实现

def get_etf_rotation_total_value(context):

    index = g_etf_rotation["index"]

    if not g_positions[index]:

        return 0

    return sum(context.portfolio.positions[key].price * value 

              for key, value in g_positions[index].items())





def etf_rotation_order_target_value(context, security, value):
    """
    ETF轮动策略的目标市值下单函数
    根据目标市值调整持仓，自动计算买入/卖出数量并下单
    参数:
        context: 策略上下文对象
        security: 证券代码，如"513100.XSHG"
        value: 目标市值（元），0表示清仓
    返回:
        True表示下单成功，False表示下单失败或无需调整
    """
    strategy = g_etf_rotation  # 获取ETF轮动策略配置字典

    current_data = get_current_data()  # 获取当前市场数据对象，包含所有标的的实时信息



    # ========== 检查标的是否停牌、涨停、跌停 ==========
    # 停牌检查：如果标的停牌，无法交易
    if current_data[security].paused:  # paused属性为True表示停牌
        log.info(f"{security}: 今日停牌")  # 记录停牌日志
        return False  # 返回False，表示无法交易



    # 涨停检查：如果当前价格等于涨停价，无法买入
    if current_data[security].last_price == current_data[security].high_limit:  # high_limit为涨停价
        log.info(f"{security}: 当前涨停")  # 记录涨停日志
        return False  # 返回False，表示无法买入



    # 跌停检查：如果当前价格等于跌停价，无法卖出
    if current_data[security].last_price == current_data[security].low_limit:  # low_limit为跌停价
        log.info(f"{security}: 当前跌停")  # 记录跌停日志
        return False  # 返回False，表示无法卖出



    # ========== 获取当前标的的价格 ==========
    price = current_data[security].last_price  # last_price为最新成交价（实时价格）



    # ========== 获取当前策略的持仓数量 ==========
    # 从g_positions字典中获取该策略记录的持仓数量，如果不存在则返回0
    current_position = g_positions[strategy["index"]].get(security, 0)

    

    # ========== 获取所有策略中该标的的总持仓数量 ==========
    # 从账户实际持仓中获取总数量（可能被多个策略持有）
    # total_amount为总持仓数量（包括当日买入的不可卖出部分）
    current_position_all = context.portfolio.positions[security].total_amount if security in context.portfolio.positions else 0



    # ========== 计算目标持仓数量 ==========
    # 根据目标市值计算目标持仓数量
    # value / price 计算目标股数（可能为小数）
    # int() 向下取整
    # // 100 * 100 向下取整到100的倍数（A股交易以100股为1手）
    # 如果价格为0（异常情况），返回0
    target_position = (int(value / price) // 100) * 100 if price != 0 else 0



    # ========== 计算需要调整的数量 ==========
    # 目标持仓数量 - 当前持仓数量 = 需要调整的数量
    # 正数表示需要买入，负数表示需要卖出，0表示无需调整
    adjustment = target_position - current_position

    
    # 计算调整后的总持仓数量（用于记录，实际下单时使用adjustment）
    target_position_all = current_position_all + adjustment



    # ========== 检查是否当天买入卖出（T+1限制） ==========
    # closeable_amount为可卖出数量（排除当日买入的部分）
    # 如果adjustment < 0（需要卖出）且closeable_amount == 0（当日买入，不可卖出）
    closeable_amount = context.portfolio.positions[security].closeable_amount if security in context.portfolio.positions else 0
    if adjustment < 0 and closeable_amount == 0:  # 需要卖出但当日买入不可卖出
        log.info(f"{security}: 当天买入不可卖出")  # 记录日志
        return False  # 返回False，无法执行卖出操作



    # ========== 下单并更新持仓 ==========
    if adjustment != 0:  # 如果需要调整持仓（买入或卖出）
        # 调用订单函数，传入调整数量（正数买入，负数卖出）
        o = my_order(context, security, adjustment, price, target_position_all)
        
        if o:  # 如果订单对象存在（下单成功）
            # ========== 更新持仓数量 ==========
            # o.filled为实际成交数量（正数）
            # o.is_buy为True表示买入，False表示卖出
            # 如果是买入，filled为正数；如果是卖出，需要取负数
            filled = o.filled if o.is_buy else -o.filled
            
            # 更新g_positions中记录的持仓数量 = 原持仓 + 成交数量
            g_positions[strategy["index"]][security] = filled + current_position
            
            # ========== 如果当前持仓为零，移除该证券 ==========
            # 避免持仓字典中保留数量为0的条目
            if g_positions[strategy["index"]][security] == 0:
                g_positions[strategy["index"]].pop(security, None)  # 从字典中删除该证券
            
            # ========== 更新持有列表 ==========
            # 将g_positions字典的键（证券代码）转换为列表，更新策略的hold_list
            strategy["hold_list"] = list(g_positions[strategy["index"]].keys())
            
            return True  # 返回True，表示下单成功

    return False  # 如果adjustment == 0（无需调整）或下单失败，返回False









def get_etf_premium_rate_real(context, etf_code):
    """
    在实盘中计算ETF基金的溢价率
    ETF溢价率 = (ETF交易价格 - IOPV净值) / IOPV净值 × 100%
    溢价率>0表示ETF价格高于净值（溢价），溢价率<0表示ETF价格低于净值（折价）
    参数:
        context: 策略上下文对象
        etf_code: ETF代码，如 '510050.XSHG'
    返回:
        (premium_rate, etf_price, iopv): 溢价率（%）、ETF价格、IOPV净值
    """
    # ========== 获取ETF交易价格 ==========
    # get_price获取历史价格数据，使用前一个交易日的数据（避免使用当日未收盘数据）
    # context.previous_date为前一个交易日
    # iloc[-1]获取最后一行（即前一个交易日的数据）
    # ['close']获取收盘价
    etf_price = get_price(etf_code, start_date=context.previous_date, end_date=context.previous_date).iloc[-1]['close']

    # ========== 获取IOPV净值（基金参考净值） ==========
    # get_extras获取扩展数据，'unit_net_value'为基金单位净值
    # iloc[-1].values[0]获取最后一个交易日的数据值
    iopv = get_extras('unit_net_value', etf_code, start_date=context.previous_date, end_date=context.previous_date).iloc[-1].values[0]

    

    # ========== 计算溢价率 ==========
    # 如果IOPV存在且不为0，计算溢价率
    if iopv is not None and iopv != 0:
        # 溢价率 = (ETF价格 - IOPV净值) / IOPV净值 × 100%
        premium_rate = (etf_price - iopv) / iopv * 100
    else:
        # 如果IOPV不存在或为0，溢价率设为0（异常情况）
        premium_rate = 0



    return premium_rate, etf_price, iopv  # 返回溢价率、ETF价格、IOPV净值



























def etf_rotation_filter(context):
    """
    ETF轮动策略的过滤和评分函数
    通过均线过滤和动量评分，筛选出最适合轮动的ETF
    参数:
        context: 策略上下文对象
    返回:
        按得分降序排列的ETF代码列表（得分最高的在前）
    """
    strategy = g_etf_rotation  # 获取ETF轮动策略配置字典

    # ========== 步骤1：先对原始ETF池进行均线过滤（在动量计算前） ==========
    filtered_pool = strategy["etf_pool"]  # 原始ETF池，初始化为所有ETF

    if strategy["enable_ma_filter"]:  # 如果启用了均线过滤
        # 调用均线过滤函数，筛选出当前价 >= N日均价的ETF
        # 这样可以过滤掉处于下跌趋势的ETF，只保留上升趋势的ETF
        filtered_pool = filter_below_ma(
            stocks=filtered_pool,  # 待过滤的ETF列表
            days=strategy["ma_filter_days"]  # 均线天数（默认20日）
        )
        log.debug(f"均线过滤后剩余ETF数量：{len(filtered_pool)}（原始池：{len(strategy['etf_pool'])}）")

    

    # ========== 步骤2：仅对过滤后的ETF池计算动量评分 ==========
    # 创建DataFrame用于存储每个ETF的评分数据
    # index为ETF代码列表，columns为年化收益率、R²、得分
    data = pd.DataFrame(index=filtered_pool, 
                       columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()  # 获取当前市场数据对象

    
    # ========== 遍历ETF池，计算每个ETF的动量评分 ==========
    # ========== 遍历ETF池，计算每个ETF的动量评分 ==========
    # 注意：这里遍历的是strategy["etf_pool"]（原始ETF池），而不是filtered_pool
    # 这可能是代码的一个小问题，应该遍历filtered_pool以提高效率
    for etf in strategy["etf_pool"]:  # 遍历原始ETF池（注意：这里应该用filtered_pool，但代码中用的是strategy["etf_pool"]）
        # 移除成交量异常检查的所有代码（已注释掉的代码）
        

        # ========== 获取历史数据并计算当前价格 ==========
        # attribute_history获取历史数据，返回DataFrame
        # strategy["m_days"]为动量参考天数（默认25天）
        # "1d"表示日线数据
        # ["close", "high"]表示获取收盘价和最高价（这里只用到了close）
        df = attribute_history(etf, strategy["m_days"], "1d", ["close", "high"])
        
        # 将历史收盘价数组和当前价格合并，形成完整的价格序列
        # df["close"].values获取收盘价数组
        # current_data[etf].last_price获取当前最新价格
        prices = np.append(df["close"].values, current_data[etf].last_price)



        # ========== 设置参数用于线性回归 ==========
        # 对价格取对数，将价格变化转换为对数收益率（更符合金融理论）
        y = np.log(prices)  # y为对数价格序列
        
        # 创建时间序列索引（0, 1, 2, ..., n-1）
        x = np.arange(len(y))  # x为时间索引序列
        
        # 创建权重序列，从1到2线性递增
        # 权重越大，表示越近期的数据对回归的影响越大（时间加权）
        weights = np.linspace(1, 2, len(y))  # 权重序列，近期数据权重更大



        # ========== 计算年化收益率 ==========
        # np.polyfit进行加权线性回归，拟合 y = slope * x + intercept
        # w=weights表示使用权重，1表示一次多项式（线性回归）
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        
        # 年化收益率 = exp(slope * 250) - 1
        # slope为日对数收益率，乘以250个交易日得到年化对数收益率
        # exp()将对数收益率转换为普通收益率，减1得到净收益率
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1



        # ========== 计算R²（决定系数，衡量趋势的稳定性） ==========
        # R² = 1 - (残差平方和 / 总平方和)
        # R²越接近1，表示价格趋势越稳定（线性关系越强）
        
        # 计算残差平方和（实际值与拟合值的差的平方加权和）
        # y - (slope * x + intercept) 为残差（实际值 - 拟合值）
        ss_res = np.sum(weights * (y - (slope * x + intercept)) **2)
        
        # 计算总平方和（实际值与均值的差的平方加权和）
        # y - np.mean(y) 为实际值与均值的差
        ss_tot = np.sum(weights * (y - np.mean(y))** 2)
        
        # 计算R²，如果ss_tot为0（所有值相同），则R²设为0
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0



        # ========== 计算得分 ==========
        # 得分 = 年化收益率 × R²
        # 既考虑收益率（越高越好），又考虑趋势稳定性（R²越高越好）
        # 这样可以筛选出既有高收益又趋势稳定的ETF
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]



        # ========== 过滤近3日跌幅超过5%的ETF ==========
        # 如果最近3天中，任意一天的跌幅超过5%，则将得分设为0（排除）
        # prices[-1]/prices[-2] 为第1天相对第2天的涨跌幅
        # prices[-2]/prices[-3] 为第2天相对第3天的涨跌幅
        # prices[-3]/prices[-4] 为第3天相对第4天的涨跌幅
        # min()取最小值，如果最小值 < 0.95（跌幅>5%），则排除
        if len(prices) >= 4 and min(prices[-1]/prices[-2], prices[-2]/prices[-3], prices[-3]/prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0  # 将得分设为0，表示排除该ETF

        

        # ========== 以下为已注释的风控代码（预留功能） ==========
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

    

    # ========== 过滤ETF，并按得分降序排列 ==========
    # data.query("0 < score < 5") 过滤得分在0到5之间的ETF（排除异常值）
    # sort_values(by="score", ascending=False) 按得分降序排列（得分最高的在前）
    data = data.query("0 < score < 5").sort_values(by="score", ascending=False)
    
    # 返回ETF代码列表（DataFrame的index转换为列表）
    return data.index.tolist()







# ============================================================================
# 通用工具函数
# ============================================================================

def filter_untradeable_stock(stocks):
    """
    过滤出不可交易的股票/ETF（停牌、涨停、跌停）
    参数:
        stocks: 待过滤的标的列表
    返回:
        不可交易的标的列表（停牌或涨停或跌停的标的）
    """
    current_data = get_current_data()  # 获取当前市场数据对象

    # 使用列表推导式，筛选出停牌、涨停或跌停的标的
    return [
        stock  # 返回标的代码
        for stock in stocks  # 遍历标的列表
        # 条件：停牌 或 当前价格等于涨停价 或 当前价格等于跌停价
        if current_data[stock].paused or current_data[stock].last_price in 
           (current_data[stock].high_limit, current_data[stock].low_limit)
    ]





def check_etf_rotation_holdings(context):
    """
    检查ETF轮动策略的持仓，过滤掉连续涨停的标的
    参数:
        context: 策略上下文对象
    返回:
        可继续持有的ETF列表（排除连续涨停的标的）
    """
    strategy = g_etf_rotation  # 获取ETF轮动策略配置字典

    # 获取当前持仓的ETF代码列表（从g_positions字典中提取键）
    hold = list(g_positions[strategy["index"]].keys())

    if not hold:  # 如果无持仓
        return []  # 返回空列表

    current_data = get_current_data()  # 获取当前市场数据对象

    # filter_limitup_stock过滤连续涨停的标的（连续3天涨停）
    # 注意：此函数在代码中未定义，可能是聚宽平台的函数或需要自行实现
    filtered = filter_limitup_stock(hold, 3)

    # 返回可继续持有的ETF列表
    # 条件：不在连续涨停列表中 且 当前价格 < 涨停价（未涨停）
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
    用于检测是否放量，放量可能表示异常波动或主力操作
    参数:
        context: 策略上下文对象
        security: 证券代码
        lookback_days: 历史成交量参考天数（用于计算平均成交量）
        threshold: 放量阈值（当日成交量/历史平均成交量 > threshold视为放量）
    返回:
        若放量（>threshold）则返回比值，否则返回None，异常时返回None
    """
    try:
        # ========== 步骤1：获取历史成交量（N天平均） ==========
        # attribute_history获取历史数据
        # lookback_days为历史天数（默认5天）
        # '1d'表示日线数据
        # ['volume']表示获取成交量数据
        hist_data = attribute_history(security, lookback_days, '1d', ['volume'])

        # 如果历史数据为空或数据不足，返回None
        if hist_data.empty or len(hist_data) < lookback_days:
            return None

        # 计算历史平均成交量（N天的成交量平均值）
        avg_volume = hist_data['volume'].mean()



        # ========== 步骤2：获取当日实时成交量（分钟数据累加） ==========
        # 获取当日日期
        today = context.current_dt.date()
        
        # get_price获取分钟级数据，用于计算当日实时成交量
        df_vol = get_price(
            security,  # 证券代码
            start_date=today,  # 开始日期（当日）
            end_date=context.current_dt,  # 结束时间（当前时间）
            frequency='1m',  # 1分钟频率
            fields=['volume'],  # 获取成交量字段
            skip_paused=False,  # 不跳过停牌数据
            fq='pre',  # 前复权
            panel=True,  # 返回面板数据
            fill_paused=False  # 不填充停牌数据
        )

        # 如果分钟数据为空，返回None
        if df_vol is None or df_vol.empty:
            return None



        # 计算当日累计成交量（所有分钟数据的成交量之和）
        current_volume = df_vol['volume'].sum()
        
        # 计算成交量比值（当日成交量/历史平均成交量）
        volume_ratio = current_volume / avg_volume



        # ========== 步骤3：超过阈值视为放量 ==========
        # 如果成交量比值 > 阈值，返回比值（表示放量）
        # 否则返回None（表示未放量）
        return volume_ratio if volume_ratio > threshold else None
        
    except Exception as e:
        # 如果发生异常，记录警告日志并返回None
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





