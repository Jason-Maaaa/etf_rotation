"""
可视化模块
使用 Matplotlib 绘制净值曲线、回撤曲线及买卖点标注
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from typing import Optional, List, Dict
from datetime import datetime

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class Visualizer:
    """可视化类"""
    
    def __init__(self, figsize: tuple = (15, 10)):
        """
        初始化可视化器
        
        Args:
            figsize: 图表大小
        """
        self.figsize = figsize
    
    def plot_equity_curve(
        self,
        equity_df: pd.DataFrame,
        benchmark_df: Optional[pd.DataFrame] = None,
        title: str = "净值曲线",
        save_path: Optional[str] = None
    ):
        """
        绘制净值曲线
        
        Args:
            equity_df: 净值DataFrame，必须包含 'date' 和 'net_value' 列
            benchmark_df: 基准净值DataFrame（可选），必须包含 'date' 和 'net_value' 列
            title: 图表标题
            save_path: 保存路径（可选）
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # 绘制策略净值
        ax.plot(
            equity_df['date'],
            equity_df['net_value'],
            label='策略净值',
            linewidth=2,
            color='#2E86AB'
        )
        
        # 绘制基准净值（如果有）
        if benchmark_df is not None and not benchmark_df.empty:
            ax.plot(
                benchmark_df['date'],
                benchmark_df['net_value'],
                label='基准净值',
                linewidth=2,
                color='#A23B72',
                linestyle='--'
            )
        
        # 绘制1.0基准线
        ax.axhline(y=1.0, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('净值', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存至: {save_path}")
        
        plt.show()
    
    def plot_drawdown(
        self,
        equity_df: pd.DataFrame,
        title: str = "回撤曲线",
        save_path: Optional[str] = None
    ):
        """
        绘制回撤曲线
        
        Args:
            equity_df: 净值DataFrame，必须包含 'date' 和 'net_value' 列
            title: 图表标题
            save_path: 保存路径（可选）
        """
        # 计算回撤
        cumulative = equity_df['net_value']
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100
        
        fig, ax = plt.subplots(figsize=self.figsize)
        
        # 填充回撤区域
        ax.fill_between(
            equity_df['date'],
            drawdown,
            0,
            color='#F18F01',
            alpha=0.3,
            label='回撤'
        )
        
        # 绘制回撤曲线
        ax.plot(
            equity_df['date'],
            drawdown,
            linewidth=1.5,
            color='#C73E1D'
        )
        
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('回撤 (%)', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存至: {save_path}")
        
        plt.show()
    
    def plot_equity_with_trades(
        self,
        equity_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        title: str = "净值曲线与交易点",
        save_path: Optional[str] = None
    ):
        """
        绘制净值曲线并标注买卖点
        
        Args:
            equity_df: 净值DataFrame
            trades_df: 交易记录DataFrame，必须包含 'date', 'code', 'pnl' 等列
            title: 图表标题
            save_path: 保存路径（可选）
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(self.figsize[0], self.figsize[1] * 1.2), sharex=True)
        
        # 上图：净值曲线和买卖点
        ax1.plot(
            equity_df['date'],
            equity_df['net_value'],
            label='策略净值',
            linewidth=2,
            color='#2E86AB'
        )
        
        ax1.axhline(y=1.0, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        
        # 标注买入点
        buy_trades = trades_df[trades_df['pnl'].isna() | (trades_df['pnl'] == 0)]  # 买入交易（pnl为0或NaN）
        if not buy_trades.empty:
            buy_dates = pd.to_datetime(buy_trades['date'])
            buy_values = []
            for date in buy_dates:
                equity_on_date = equity_df[equity_df['date'].dt.date == date.date()]
                if not equity_on_date.empty:
                    buy_values.append(equity_on_date.iloc[0]['net_value'])
                else:
                    buy_values.append(np.nan)
            
            ax1.scatter(
                buy_dates,
                buy_values,
                marker='^',
                color='green',
                s=100,
                label='买入',
                zorder=5,
                alpha=0.7
            )
        
        # 标注卖出点
        sell_trades = trades_df[trades_df['pnl'].notna() & (trades_df['pnl'] != 0)]
        if not sell_trades.empty:
            sell_dates = pd.to_datetime(sell_trades['date'])
            sell_values = []
            for date in sell_dates:
                equity_on_date = equity_df[equity_df['date'].dt.date == date.date()]
                if not equity_on_date.empty:
                    sell_values.append(equity_on_date.iloc[0]['net_value'])
                else:
                    sell_values.append(np.nan)
            
            # 根据盈亏着色
            colors = ['red' if pnl < 0 else 'blue' for pnl in sell_trades['pnl']]
            ax1.scatter(
                sell_dates,
                sell_values,
                marker='v',
                color=colors,
                s=100,
                label='卖出',
                zorder=5,
                alpha=0.7
            )
        
        ax1.set_ylabel('净值', fontsize=12)
        ax1.set_title(title, fontsize=14, fontweight='bold')
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # 下图：持仓代码
        if not trades_df.empty:
            # 创建持仓时间线
            position_changes = []
            current_code = None
            
            for _, trade in trades_df.iterrows():
                trade_date = pd.to_datetime(trade['date'])
                if '买入' in str(trade.get('reason', '')) or trade.get('pnl', 0) == 0:
                    current_code = trade.get('code', '')
                    position_changes.append({'date': trade_date, 'code': current_code, 'action': 'buy'})
                elif '卖出' in str(trade.get('reason', '')) or (trade.get('pnl', 0) != 0 and current_code):
                    position_changes.append({'date': trade_date, 'code': current_code, 'action': 'sell'})
                    current_code = None
            
            if position_changes:
                pos_df = pd.DataFrame(position_changes)
                codes = pos_df['code'].unique()
                code_to_y = {code: i for i, code in enumerate(codes)}
                
                for code in codes:
                    code_trades = pos_df[pos_df['code'] == code]
                    for _, trade in code_trades.iterrows():
                        if trade['action'] == 'buy':
                            # 找到下一个卖出点或结束
                            next_sell = pos_df[
                                (pos_df['date'] > trade['date']) & 
                                (pos_df['code'] == code) & 
                                (pos_df['action'] == 'sell')
                            ]
                            if not next_sell.empty:
                                end_date = next_sell.iloc[0]['date']
                            else:
                                end_date = equity_df['date'].iloc[-1]
                            
                            ax2.barh(
                                code_to_y[code],
                                (end_date - trade['date']).days,
                                left=trade['date'],
                                height=0.6,
                                alpha=0.6,
                                label=code if code not in [l.get_text() for l in ax2.get_yticklabels()] else ''
                            )
                
                ax2.set_yticks(range(len(codes)))
                ax2.set_yticklabels(codes)
                ax2.set_ylabel('持仓代码', fontsize=12)
                ax2.set_xlabel('日期', fontsize=12)
                ax2.grid(True, alpha=0.3, axis='x')
        
        # 格式化x轴日期
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存至: {save_path}")
        
        plt.show()
    
    def plot_statistics(
        self,
        statistics: Dict,
        title: str = "回测统计",
        save_path: Optional[str] = None
    ):
        """
        绘制统计指标图表
        
        Args:
            statistics: 统计指标字典
            title: 图表标题
            save_path: 保存路径（可选）
        """
        fig, axes = plt.subplots(2, 2, figsize=self.figsize)
        fig.suptitle(title, fontsize=16, fontweight='bold')
        
        # 提取关键指标
        metrics = {
            '总收益率': statistics.get('total_return', 0),
            '年化收益率': statistics.get('annual_return', 0),
            '最大回撤': statistics.get('max_drawdown', 0),
            '夏普比率': statistics.get('sharpe_ratio', 0),
            '胜率': statistics.get('win_rate', 0),
            '交易次数': statistics.get('trade_count', 0)
        }
        
        # 1. 收益率指标（柱状图）
        ax1 = axes[0, 0]
        return_metrics = ['总收益率', '年化收益率']
        values = [metrics[k] for k in return_metrics]
        colors = ['#2E86AB', '#A23B72']
        ax1.bar(return_metrics, values, color=colors, alpha=0.7)
        ax1.set_ylabel('收益率 (%)', fontsize=10)
        ax1.set_title('收益率指标', fontsize=12)
        ax1.grid(True, alpha=0.3, axis='y')
        
        # 2. 风险指标（柱状图）
        ax2 = axes[0, 1]
        risk_metrics = ['最大回撤', '夏普比率']
        values = [metrics[k] for k in risk_metrics]
        colors = ['#C73E1D', '#F18F01']
        ax2.bar(risk_metrics, values, color=colors, alpha=0.7)
        ax2.set_ylabel('数值', fontsize=10)
        ax2.set_title('风险指标', fontsize=12)
        ax2.grid(True, alpha=0.3, axis='y')
        
        # 3. 交易统计（饼图）
        ax3 = axes[1, 0]
        if statistics.get('trade_count', 0) > 0:
            win_count = int(statistics.get('win_rate', 0) / 100 * statistics.get('trade_count', 0))
            loss_count = statistics.get('trade_count', 0) - win_count
            if win_count + loss_count > 0:
                ax3.pie(
                    [win_count, loss_count],
                    labels=['盈利', '亏损'],
                    autopct='%1.1f%%',
                    colors=['#06A77D', '#C73E1D'],
                    startangle=90
                )
                ax3.set_title('交易盈亏分布', fontsize=12)
        
        # 4. 关键指标文本
        ax4 = axes[1, 1]
        ax4.axis('off')
        
        stats_text = f"""
        初始资金: {statistics.get('initial_capital', 0):,.0f} 元
        最终权益: {statistics.get('final_equity', 0):,.0f} 元
        总收益率: {statistics.get('total_return', 0):.2f}%
        年化收益率: {statistics.get('annual_return', 0):.2f}%
        最大回撤: {statistics.get('max_drawdown', 0):.2f}%
        夏普比率: {statistics.get('sharpe_ratio', 0):.2f}
        胜率: {statistics.get('win_rate', 0):.2f}%
        交易次数: {statistics.get('trade_count', 0)}
        总手续费: {statistics.get('total_commission', 0):,.2f} 元
        """
        
        ax4.text(
            0.1, 0.5,
            stats_text,
            fontsize=11,
            verticalalignment='center',
            family='monospace'
        )
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存至: {save_path}")
        
        plt.show()
    
    def plot_comprehensive(
        self,
        equity_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        statistics: Dict,
        title: str = "回测综合分析",
        save_path: Optional[str] = None
    ):
        """
        绘制综合分析图表（包含净值、回撤、交易点、统计）
        
        Args:
            equity_df: 净值DataFrame
            trades_df: 交易记录DataFrame
            statistics: 统计指标字典
            title: 图表标题
            save_path: 保存路径（可选）
        """
        fig = plt.figure(figsize=(self.figsize[0] * 1.2, self.figsize[1] * 1.5))
        gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
        
        # 1. 净值曲线
        ax1 = fig.add_subplot(gs[0, :])
        ax1.plot(
            equity_df['date'],
            equity_df['net_value'],
            label='策略净值',
            linewidth=2,
            color='#2E86AB'
        )
        ax1.axhline(y=1.0, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax1.set_ylabel('净值', fontsize=11)
        ax1.set_title('净值曲线', fontsize=12, fontweight='bold')
        ax1.legend(loc='best', fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        # 2. 回撤曲线
        ax2 = fig.add_subplot(gs[1, :])
        cumulative = equity_df['net_value']
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100
        ax2.fill_between(equity_df['date'], drawdown, 0, color='#F18F01', alpha=0.3)
        ax2.plot(equity_df['date'], drawdown, linewidth=1.5, color='#C73E1D')
        ax2.set_ylabel('回撤 (%)', fontsize=11)
        ax2.set_title('回撤曲线', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        # 3. 统计指标（左侧）
        ax3 = fig.add_subplot(gs[2, 0])
        ax3.axis('off')
        stats_text = f"""
        总收益率: {statistics.get('total_return', 0):.2f}%
        年化收益率: {statistics.get('annual_return', 0):.2f}%
        最大回撤: {statistics.get('max_drawdown', 0):.2f}%
        夏普比率: {statistics.get('sharpe_ratio', 0):.2f}
        胜率: {statistics.get('win_rate', 0):.2f}%
        交易次数: {statistics.get('trade_count', 0)}
        """
        ax3.text(0.1, 0.5, stats_text, fontsize=10, verticalalignment='center', family='monospace')
        ax3.set_title('关键指标', fontsize=12, fontweight='bold')
        
        # 4. 交易统计（右侧）
        ax4 = fig.add_subplot(gs[2, 1])
        if statistics.get('trade_count', 0) > 0:
            win_count = int(statistics.get('win_rate', 0) / 100 * statistics.get('trade_count', 0))
            loss_count = statistics.get('trade_count', 0) - win_count
            if win_count + loss_count > 0:
                ax4.pie(
                    [win_count, loss_count],
                    labels=['盈利', '亏损'],
                    autopct='%1.1f%%',
                    colors=['#06A77D', '#C73E1D'],
                    startangle=90
                )
                ax4.set_title('交易盈亏分布', fontsize=12, fontweight='bold')
        
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存至: {save_path}")
        
        plt.show()
