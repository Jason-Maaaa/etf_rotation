"""
量化交易框架主入口
负责串联整个流程：数据加载 -> 策略执行 -> 回测 -> 可视化
"""
import argparse
import pandas as pd
from datetime import datetime
from typing import Optional

from data_loader import DataLoader
from strategy import ETFRotationStrategy
from backtester import Backtester, OrderType
from visualizer import Visualizer
from etf_config import POOL_DICT


def run_backtest(
    start_date: str,
    end_date: str,
    pool_name: str = "core",
    initial_capital: float = 1000000.0,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    slippage: float = 0.0,
    output_dir: Optional[str] = None,
    plot: bool = True
):
    """
    运行回测
    
    Args:
        start_date: 回测开始日期（格式：YYYY-MM-DD）
        end_date: 回测结束日期（格式：YYYY-MM-DD）
        pool_name: ETF池名称
        initial_capital: 初始资金
        commission_rate: 手续费率
        min_commission: 最低手续费
        slippage: 滑点
        output_dir: 输出目录（可选）
        plot: 是否绘制图表
    """
    print("=" * 80)
    print("量化交易框架 - 回测系统")
    print("=" * 80)
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"ETF池: {pool_name} (共 {len(POOL_DICT[pool_name])} 只)")
    print(f"初始资金: {initial_capital:,.0f} 元")
    print(f"手续费率: {commission_rate*10000:.2f} 万")
    print(f"滑点: {slippage*100:.2f}%")
    print("-" * 80)
    
    # 1. 初始化数据加载器
    print("📊 正在加载数据...")
    data_loader = DataLoader()
    
    # 获取交易日列表
    trading_dates = data_loader.get_trading_dates(start_date, end_date)
    if len(trading_dates) == 0:
        print("❌ 错误：在指定日期范围内没有找到交易日")
        return
    
    print(f"✅ 找到 {len(trading_dates)} 个交易日")
    
    # 2. 初始化策略
    print("🎯 正在初始化策略...")
    strategy = ETFRotationStrategy(
        data_loader=data_loader,
        pool_name=pool_name
    )
    print("✅ 策略初始化完成")
    
    # 3. 初始化回测引擎
    print("🔄 正在初始化回测引擎...")
    backtester = Backtester(
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        min_commission=min_commission,
        slippage=slippage
    )
    print("✅ 回测引擎初始化完成")
    
    # 4. 执行回测
    print("\n" + "=" * 80)
    print("开始回测...")
    print("=" * 80)
    
    current_position = None
    
    for i, date in enumerate(trading_dates):
        date_str = date.strftime("%Y-%m-%d")
        
        if (i + 1) % 50 == 0:
            print(f"进度: {i+1}/{len(trading_dates)} ({date_str})")
        
        # 生成交易信号
        signal = strategy.generate_signal(date_str, current_position)
        
        # 处理信号
        if signal['action'] == 'buy':
            # 买入
            success = backtester.execute_order(
                date=date_str,
                code=signal['code'],
                name=signal['name'],
                order_type=OrderType.BUY,
                price=signal['price'],
                quantity=signal['quantity'],
                reason=signal.get('reason', '')
            )
            
            if success:
                current_position = {
                    'code': signal['code'],
                    'name': signal['name'],
                    'quantity': signal['quantity'],
                    'entry_price': signal['price'],
                    'entry_date': date_str
                }
        
        elif signal['action'] == 'sell':
            # 卖出
            if current_position and current_position['code'] == signal['code']:
                success = backtester.execute_order(
                    date=date_str,
                    code=signal['code'],
                    name=signal['name'],
                    order_type=OrderType.SELL,
                    price=signal['price'],
                    quantity=signal['quantity'],
                    reason=signal.get('reason', '')
                )
                
                if success:
                    current_position = None
                
                # 检查是否有后续买入信号
                if 'next_action' in signal:
                    next_signal = signal['next_action']
                    if next_signal['action'] == 'buy':
                        success = backtester.execute_order(
                            date=date_str,
                            code=next_signal['code'],
                            name=next_signal['name'],
                            order_type=OrderType.BUY,
                            price=next_signal['price'],
                            quantity=next_signal['quantity'],
                            reason=next_signal.get('reason', '')
                        )
                        
                        if success:
                            current_position = {
                                'code': next_signal['code'],
                                'name': next_signal['name'],
                                'quantity': next_signal['quantity'],
                                'entry_price': next_signal['price'],
                                'entry_date': date_str
                            }
        
        # 更新净值（使用收盘价）
        if current_position:
            current_price = data_loader.get_price_at_time(
                current_position['code'],
                date_str,
                'close'
            )
        else:
            current_price = None
        
        backtester.update_equity(date_str, current_price)
    
    # 回测结束，平仓
    if current_position:
        last_date = trading_dates[-1].strftime("%Y-%m-%d")
        last_price = data_loader.get_price_at_time(
            current_position['code'],
            last_date,
            'close'
        )
        if not pd.isna(last_price):
            backtester.execute_order(
                date=last_date,
                code=current_position['code'],
                name=current_position['name'],
                order_type=OrderType.SELL,
                price=last_price,
                quantity=current_position['quantity'],
                reason='回测结束平仓'
            )
    
    print("\n" + "=" * 80)
    print("回测完成！")
    print("=" * 80)
    
    # 5. 计算统计指标
    print("\n📈 正在计算统计指标...")
    statistics = backtester.get_statistics()
    
    # 打印统计结果
    print("\n" + "=" * 80)
    print("回测统计结果")
    print("=" * 80)
    print(f"初始资金: {statistics['initial_capital']:,.0f} 元")
    print(f"最终权益: {statistics['final_equity']:,.0f} 元")
    print(f"总收益率: {statistics['total_return']:.2f}%")
    print(f"年化收益率: {statistics['annual_return']:.2f}%")
    print(f"最大回撤: {statistics['max_drawdown']:.2f}%")
    print(f"夏普比率: {statistics['sharpe_ratio']:.2f}")
    print(f"胜率: {statistics['win_rate']:.2f}%")
    print(f"交易次数: {statistics['trade_count']}")
    print(f"平均盈利: {statistics['avg_win']:.2f} 元")
    print(f"平均亏损: {statistics['avg_loss']:.2f} 元")
    print(f"盈亏比: {statistics['profit_factor']:.2f}")
    print(f"总手续费: {statistics['total_commission']:,.2f} 元")
    print("=" * 80)
    
    # 6. 保存结果
    if output_dir:
        import os
        from pathlib import Path
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存净值曲线
        equity_df = backtester.get_equity_dataframe()
        equity_file = output_path / "equity_curve.csv"
        equity_df.to_csv(equity_file, index=False, encoding='utf-8-sig')
        print(f"\n✅ 净值曲线已保存至: {equity_file}")
        
        # 保存交易记录
        trades_df = backtester.get_trades_dataframe()
        if not trades_df.empty:
            trades_file = output_path / "trades.csv"
            trades_df.to_csv(trades_file, index=False, encoding='utf-8-sig')
            print(f"✅ 交易记录已保存至: {trades_file}")
        
        # 保存统计指标
        import json
        stats_file = output_path / "statistics.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(statistics, f, ensure_ascii=False, indent=2)
        print(f"✅ 统计指标已保存至: {stats_file}")
    
    # 7. 可视化
    if plot:
        print("\n📊 正在生成可视化图表...")
        visualizer = Visualizer()
        
        equity_df = backtester.get_equity_dataframe()
        trades_df = backtester.get_trades_dataframe()
        
        # 绘制综合分析图
        save_path = None
        if output_dir:
            save_path = str(Path(output_dir) / "backtest_comprehensive.png")
        
        visualizer.plot_comprehensive(
            equity_df=equity_df,
            trades_df=trades_df,
            statistics=statistics,
            title=f"ETF轮动策略回测结果 ({start_date} 至 {end_date})",
            save_path=save_path
        )
        
        # 绘制净值曲线与交易点
        if output_dir:
            save_path = str(Path(output_dir) / "equity_with_trades.png")
        else:
            save_path = None
        
        visualizer.plot_equity_with_trades(
            equity_df=equity_df,
            trades_df=trades_df,
            title=f"净值曲线与交易点 ({start_date} 至 {end_date})",
            save_path=save_path
        )
    
    return backtester, statistics


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='量化交易框架 - 回测系统')
    
    parser.add_argument(
        '--start-date',
        type=str,
        required=True,
        help='回测开始日期（格式：YYYY-MM-DD）'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        required=True,
        help='回测结束日期（格式：YYYY-MM-DD）'
    )
    
    parser.add_argument(
        '--pool',
        type=str,
        default='core',
        choices=list(POOL_DICT.keys()),
        help='ETF池名称（默认：core）'
    )
    
    parser.add_argument(
        '--capital',
        type=float,
        default=1000000.0,
        help='初始资金（默认：1000000）'
    )
    
    parser.add_argument(
        '--commission',
        type=float,
        default=0.0003,
        help='手续费率（默认：0.0003，即万三）'
    )
    
    parser.add_argument(
        '--min-commission',
        type=float,
        default=5.0,
        help='最低手续费（默认：5.0）'
    )
    
    parser.add_argument(
        '--slippage',
        type=float,
        default=0.0,
        help='滑点（默认：0.0，即无滑点）'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='输出目录（可选）'
    )
    
    parser.add_argument(
        '--no-plot',
        action='store_true',
        help='不绘制图表'
    )
    
    args = parser.parse_args()
    
    # 运行回测
    run_backtest(
        start_date=args.start_date,
        end_date=args.end_date,
        pool_name=args.pool,
        initial_capital=args.capital,
        commission_rate=args.commission,
        min_commission=args.min_commission,
        slippage=args.slippage,
        output_dir=args.output_dir,
        plot=not args.no_plot
    )


if __name__ == "__main__":
    main()
