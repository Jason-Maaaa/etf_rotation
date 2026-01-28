"""
使用示例：演示如何使用量化交易框架
"""
from data_loader import DataLoader
from strategy import ETFRotationStrategy
from backtester import Backtester, OrderType
from visualizer import Visualizer
import pandas as pd


def example_basic_usage():
    """基本使用示例"""
    print("=" * 80)
    print("示例1：基本使用")
    print("=" * 80)
    
    # 1. 初始化数据加载器
    data_loader = DataLoader()
    
    # 2. 获取ETF数据
    code = "159915"
    df = data_loader.get_etf_data(code, start_date="2023-01-01", end_date="2023-12-31")
    print(f"\n获取 {code} 的数据：")
    print(df.head())
    
    # 3. 获取特定时间点价格
    price = data_loader.get_price_at_time(code, "2023-06-15", "p1450")
    print(f"\n{code} 在 2023-06-15 的 14:50 价格: {price}")


def example_strategy_signal():
    """策略信号生成示例"""
    print("\n" + "=" * 80)
    print("示例2：策略信号生成")
    print("=" * 80)
    
    # 1. 初始化
    data_loader = DataLoader()
    strategy = ETFRotationStrategy(data_loader, pool_name="core")
    
    # 2. 生成交易信号
    date = "2023-06-15"
    signal = strategy.generate_signal(date, current_position=None)
    
    print(f"\n在 {date} 生成的交易信号：")
    print(f"  动作: {signal['action']}")
    print(f"  代码: {signal['code']}")
    print(f"  名称: {signal['name']}")
    print(f"  价格: {signal['price']}")
    print(f"  数量: {signal['quantity']}")
    print(f"  原因: {signal['reason']}")


def example_backtest():
    """回测示例"""
    print("\n" + "=" * 80)
    print("示例3：简单回测")
    print("=" * 80)
    
    # 1. 初始化回测引擎
    backtester = Backtester(
        initial_capital=1000000.0,
        commission_rate=0.0003,
        min_commission=5.0
    )
    
    # 2. 模拟一些交易
    backtester.execute_order(
        date="2023-01-10",
        code="159915",
        name="创业板ETF",
        order_type=OrderType.BUY,
        price=3.5,
        quantity=1000,
        reason="示例买入"
    )
    
    backtester.update_equity("2023-01-10", 3.5)
    backtester.update_equity("2023-01-11", 3.6)
    backtester.update_equity("2023-01-12", 3.4)
    
    backtester.execute_order(
        date="2023-01-12",
        code="159915",
        name="创业板ETF",
        order_type=OrderType.SELL,
        price=3.4,
        quantity=1000,
        reason="示例卖出"
    )
    
    backtester.update_equity("2023-01-12", 3.4)
    
    # 3. 获取统计结果
    statistics = backtester.get_statistics()
    print("\n回测统计：")
    print(f"  总收益率: {statistics['total_return']:.2f}%")
    print(f"  交易次数: {statistics['trade_count']}")
    print(f"  胜率: {statistics['win_rate']:.2f}%")
    
    # 4. 获取净值曲线
    equity_df = backtester.get_equity_dataframe()
    print(f"\n净值曲线（共 {len(equity_df)} 条记录）：")
    print(equity_df)


def example_indicators():
    """指标计算示例"""
    print("\n" + "=" * 80)
    print("示例4：指标计算")
    print("=" * 80)
    
    import numpy as np
    from indicators import Indicators
    
    # 模拟价格序列
    prices = np.array([3.0, 3.1, 3.2, 3.15, 3.3, 3.4, 3.35, 3.5, 3.6, 3.55])
    
    # 计算移动平均
    ma20 = Indicators.ma(prices, period=5)
    print(f"\n5日移动平均: {ma20:.4f}")
    
    # 计算动量
    score, r2, annual_return = Indicators.calculate_momentum(prices)
    print(f"动量得分: {score:.4f}")
    print(f"R²: {r2:.4f}")
    print(f"年化收益率: {annual_return:.4f}")
    
    # 计算波动率
    volatility = Indicators.get_annualized_vol(prices)
    print(f"年化波动率: {volatility:.4f}")
    
    # 计算ETF综合得分
    score_result = Indicators.calculate_etf_score(prices, ma_period=5, momentum_period=5)
    print(f"\nETF综合得分:")
    print(f"  得分: {score_result['score']:.4f}")
    print(f"  是否在均线上方: {score_result['is_up']}")
    print(f"  是否未剧烈回调: {score_result['is_not_crash']}")


if __name__ == "__main__":
    # 运行所有示例
    try:
        example_basic_usage()
        example_strategy_signal()
        example_backtest()
        example_indicators()
        
        print("\n" + "=" * 80)
        print("所有示例运行完成！")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ 示例运行出错: {e}")
        import traceback
        traceback.print_exc()
