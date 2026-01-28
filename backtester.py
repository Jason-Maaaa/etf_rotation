"""
回测引擎模块
实现完整的回测功能，包括手续费计算、净值计算、最大回撤、夏普比率等关键指标
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class OrderType(Enum):
    """订单类型"""
    BUY = "买入"
    SELL = "卖出"


@dataclass
class Order:
    """订单数据类"""
    date: str
    code: str
    name: str
    order_type: OrderType
    price: float
    quantity: int
    reason: str = ""
    
    @property
    def amount(self) -> float:
        """计算订单金额"""
        return self.price * self.quantity


@dataclass
class Position:
    """持仓数据类"""
    code: str
    name: str
    quantity: int
    entry_price: float
    entry_date: str
    
    @property
    def market_value(self) -> float:
        """计算市值（需要传入当前价格）"""
        return 0.0  # 占位，实际使用时需要传入价格
    
    def get_market_value(self, current_price: float) -> float:
        """根据当前价格计算市值"""
        return self.quantity * current_price


class Backtester:
    """回测引擎类"""
    
    def __init__(
        self,
        initial_capital: float = 1000000.0,
        commission_rate: float = 0.0003,  # 万三手续费
        min_commission: float = 5.0,  # 最低手续费5元
        slippage: float = 0.0,  # 滑点（默认无滑点）
        benchmark_code: Optional[str] = None  # 基准代码（如沪深300）
    ):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            commission_rate: 手续费率（默认万三）
            min_commission: 最低手续费
            slippage: 滑点（小数形式，如0.001表示0.1%）
            benchmark_code: 基准代码（用于计算相对收益）
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.slippage = slippage
        self.benchmark_code = benchmark_code
        
        # 回测状态
        self.cash = initial_capital
        self.position: Optional[Position] = None
        self.orders: List[Order] = []
        self.equity_curve: List[Dict] = []  # 净值曲线
        self.trades: List[Dict] = []  # 交易记录
        
    def calculate_commission(self, amount: float) -> float:
        """
        计算手续费
        
        Args:
            amount: 交易金额
            
        Returns:
            手续费金额
        """
        commission = amount * self.commission_rate
        return max(commission, self.min_commission)
    
    def apply_slippage(self, price: float, order_type: OrderType) -> float:
        """
        应用滑点
        
        Args:
            price: 原始价格
            order_type: 订单类型
            
        Returns:
            考虑滑点后的价格
        """
        if order_type == OrderType.BUY:
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)
    
    def execute_order(
        self,
        date: str,
        code: str,
        name: str,
        order_type: OrderType,
        price: float,
        quantity: int,
        reason: str = ""
    ) -> bool:
        """
        执行订单
        
        Args:
            date: 交易日期
            code: ETF代码
            name: ETF名称
            order_type: 订单类型
            price: 价格
            quantity: 数量
            reason: 交易原因
            
        Returns:
            是否执行成功
        """
        # 应用滑点
        execution_price = self.apply_slippage(price, order_type)
        amount = execution_price * quantity
        
        if order_type == OrderType.BUY:
            # 买入逻辑
            commission = self.calculate_commission(amount)
            total_cost = amount + commission
            
            if total_cost > self.cash:
                # 资金不足，调整数量
                available_cash = self.cash - commission
                if available_cash <= 0:
                    return False
                quantity = int(available_cash / execution_price)
                if quantity <= 0:
                    return False
                amount = execution_price * quantity
                total_cost = amount + commission
            
            # 如果有持仓，先卖出
            if self.position is not None:
                self._close_position(date, execution_price)
            
            # 执行买入
            self.cash -= total_cost
            self.position = Position(
                code=code,
                name=name,
                quantity=quantity,
                entry_price=execution_price,
                entry_date=date
            )
            
            order = Order(
                date=date,
                code=code,
                name=name,
                order_type=order_type,
                price=execution_price,
                quantity=quantity,
                reason=reason
            )
            self.orders.append(order)
            
        else:
            # 卖出逻辑
            if self.position is None or self.position.code != code:
                return False
            
            commission = self.calculate_commission(amount)
            net_proceeds = amount - commission
            
            # 计算盈亏
            pnl = (execution_price - self.position.entry_price) * quantity
            pnl_ratio = (execution_price / self.position.entry_price) - 1
            
            # 记录交易
            trade_record = {
                'date': date,
                'code': code,
                'name': name,
                'entry_date': self.position.entry_date,
                'entry_price': self.position.entry_price,
                'exit_date': date,
                'exit_price': execution_price,
                'quantity': quantity,
                'pnl': pnl,
                'pnl_ratio': pnl_ratio,
                'commission': commission,
                'reason': reason
            }
            self.trades.append(trade_record)
            
            # 更新现金
            self.cash += net_proceeds
            
            # 清空持仓
            self.position = None
            
            order = Order(
                date=date,
                code=code,
                name=name,
                order_type=order_type,
                price=execution_price,
                quantity=quantity,
                reason=reason
            )
            self.orders.append(order)
        
        return True
    
    def _close_position(self, date: str, price: float):
        """平仓当前持仓"""
        if self.position is None:
            return
        
        amount = price * self.position.quantity
        commission = self.calculate_commission(amount)
        net_proceeds = amount - commission
        
        pnl = (price - self.position.entry_price) * self.position.quantity
        pnl_ratio = (price / self.position.entry_price) - 1
        
        trade_record = {
            'date': date,
            'code': self.position.code,
            'name': self.position.name,
            'entry_date': self.position.entry_date,
            'entry_price': self.position.entry_price,
            'exit_date': date,
            'exit_price': price,
            'quantity': self.position.quantity,
            'pnl': pnl,
            'pnl_ratio': pnl_ratio,
            'commission': commission,
            'reason': '回测结束平仓'
        }
        self.trades.append(trade_record)
        
        self.cash += net_proceeds
        self.position = None
    
    def update_equity(self, date: str, current_price: Optional[float] = None):
        """
        更新净值曲线
        
        Args:
            date: 日期
            current_price: 当前价格（如果有持仓）
        """
        if self.position is not None and current_price is not None:
            position_value = self.position.get_market_value(current_price)
        else:
            position_value = 0.0
        
        total_equity = self.cash + position_value
        net_value = total_equity / self.initial_capital
        
        self.equity_curve.append({
            'date': date,
            'cash': self.cash,
            'position_value': position_value,
            'total_equity': total_equity,
            'net_value': net_value,
            'return': (net_value - 1.0) * 100  # 收益率（百分比）
        })
    
    def get_statistics(self) -> Dict:
        """
        计算回测统计指标
        
        Returns:
            包含各种统计指标的字典
        """
        if not self.equity_curve:
            return {}
        
        df_equity = pd.DataFrame(self.equity_curve)
        df_equity['date'] = pd.to_datetime(df_equity['date'])
        df_equity = df_equity.sort_values('date').reset_index(drop=True)
        
        # 计算收益率序列
        returns = df_equity['net_value'].pct_change().dropna()
        
        # 总收益率
        total_return = (df_equity['net_value'].iloc[-1] - 1.0) * 100
        
        # 年化收益率
        days = (df_equity['date'].iloc[-1] - df_equity['date'].iloc[0]).days
        years = days / 365.0
        if years > 0:
            annual_return = ((df_equity['net_value'].iloc[-1] ** (1.0 / years)) - 1.0) * 100
        else:
            annual_return = 0.0
        
        # 最大回撤
        cumulative = df_equity['net_value']
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100
        
        # 夏普比率（假设无风险利率为3%）
        risk_free_rate = 0.03
        if len(returns) > 0 and returns.std() > 0:
            excess_returns = returns - (risk_free_rate / 252)  # 日无风险利率
            sharpe_ratio = np.sqrt(252) * excess_returns.mean() / returns.std()
        else:
            sharpe_ratio = 0.0
        
        # 胜率
        if self.trades:
            winning_trades = [t for t in self.trades if t['pnl'] > 0]
            win_rate = len(winning_trades) / len(self.trades) * 100
        else:
            win_rate = 0.0
        
        # 平均盈亏
        avg_win = 0.0
        avg_loss = 0.0
        if self.trades:
            wins = [t['pnl'] for t in self.trades if t['pnl'] > 0]
            losses = [t['pnl'] for t in self.trades if t['pnl'] < 0]
            avg_win = np.mean(wins) if wins else 0.0
            avg_loss = np.mean(losses) if losses else 0.0
        
        # 交易次数
        trade_count = len(self.trades)
        
        # 总手续费
        total_commission = sum([t['commission'] for t in self.trades])
        
        return {
            'initial_capital': self.initial_capital,
            'final_equity': df_equity['total_equity'].iloc[-1],
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'win_rate': win_rate,
            'trade_count': trade_count,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_commission': total_commission,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        }
    
    def get_equity_dataframe(self) -> pd.DataFrame:
        """
        获取净值曲线DataFrame
        
        Returns:
            包含净值曲线的DataFrame
        """
        if not self.equity_curve:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date').reset_index(drop=True)
    
    def get_trades_dataframe(self) -> pd.DataFrame:
        """
        获取交易记录DataFrame
        
        Returns:
            包含交易记录的DataFrame
        """
        if not self.trades:
            return pd.DataFrame()
        
        return pd.DataFrame(self.trades)
    
    def reset(self):
        """重置回测引擎"""
        self.cash = self.initial_capital
        self.position = None
        self.orders = []
        self.equity_curve = []
        self.trades = []
