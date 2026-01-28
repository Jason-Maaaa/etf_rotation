"""
策略模块
定义策略基类和ETF轮动策略的具体实现
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from data_loader import DataLoader
from indicators import Indicators
from etf_config import POOL_DICT


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, data_loader: DataLoader, pool_name: str = "core"):
        """
        初始化策略
        
        Args:
            data_loader: 数据加载器
            pool_name: ETF池名称
        """
        self.data_loader = data_loader
        self.pool_name = pool_name
        
        if pool_name not in POOL_DICT:
            raise ValueError(f"未找到ETF池: {pool_name}")
        
        self.etf_pool = POOL_DICT[pool_name]
    
    @abstractmethod
    def generate_signal(
        self,
        date: str,
        current_position: Optional[Dict] = None
    ) -> Dict:
        """
        生成交易信号
        
        Args:
            date: 当前日期
            current_position: 当前持仓信息，格式：{'code': str, 'quantity': int, 'entry_price': float}
            
        Returns:
            信号字典，包含：
            - action: 'buy', 'sell', 'hold'
            - code: ETF代码
            - name: ETF名称
            - price: 价格
            - quantity: 数量
            - reason: 交易原因
        """
        pass
    
    def get_price_at_time(
        self,
        code: str,
        date: str,
        time_point: str = 'p1450'
    ) -> float:
        """
        获取指定时间点的价格
        
        Args:
            code: ETF代码
            date: 日期
            time_point: 时间点，可选：'open', 'p1030', 'p1450', 'close'
            
        Returns:
            价格
        """
        return self.data_loader.get_price_at_time(code, date, time_point)


class ETFRotationStrategy(BaseStrategy):
    """ETF轮动策略（基于原有策略逻辑）"""
    
    def __init__(
        self,
        data_loader: DataLoader,
        pool_name: str = "core",
        m_days: int = 25,
        ma_filter_days: int = 20,
        sentiment_threshold: float = 0.15,
        stock_sum: int = 1,
        short_ret_limit: float = -0.04,
        stop_loss_threshold: float = -0.07,
        volatility_threshold: float = 0.30,
        sell_time: str = "p1450",  # 14:50卖出
        buy_time: str = "p1450",   # 14:51买入（实际使用14:50价格）
        base_quantity: int = 31900
    ):
        """
        初始化ETF轮动策略
        
        Args:
            data_loader: 数据加载器
            pool_name: ETF池名称
            m_days: 动量计算周期
            ma_filter_days: 均线过滤周期
            sentiment_threshold: 情绪风控阈值
            stock_sum: 计划持仓数
            short_ret_limit: 5日剧烈回调阈值
            stop_loss_threshold: 硬止损阈值
            volatility_threshold: 波动率控仓阈值
            sell_time: 卖出时间点
            buy_time: 买入时间点
            base_quantity: 基础持仓数量
        """
        super().__init__(data_loader, pool_name)
        
        self.m_days = m_days
        self.ma_filter_days = ma_filter_days
        self.sentiment_threshold = sentiment_threshold
        self.stock_sum = stock_sum
        self.short_ret_limit = short_ret_limit
        self.stop_loss_threshold = stop_loss_threshold
        self.volatility_threshold = volatility_threshold
        self.sell_time = sell_time
        self.buy_time = buy_time
        self.base_quantity = base_quantity
    
    def _get_price_series(
        self,
        code: str,
        date: str,
        lookback_days: int = 40,
        time_point: str = 'close'
    ) -> np.ndarray:
        """
        获取价格序列
        
        Args:
            code: ETF代码
            date: 当前日期
            lookback_days: 回溯天数
            time_point: 时间点
            
        Returns:
            价格序列
        """
        from datetime import timedelta
        end_date = datetime.strptime(date, "%Y-%m-%d")
        start_date = end_date - timedelta(days=lookback_days * 2)  # 多取一些以过滤非交易日
        
        df = self.data_loader.get_etf_data(
            code,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=date
        )
        
        if df.empty:
            return np.array([])
        
        # 选择价格列
        price_col = time_point if time_point in df.columns else 'close'
        if price_col not in df.columns:
            return np.array([])
        
        prices = df[price_col].values
        # 去除NaN值
        valid_prices = prices[~pd.isna(prices)]
        
        # 只取最后lookback_days个
        if len(valid_prices) > lookback_days:
            valid_prices = valid_prices[-lookback_days:]
        
        return valid_prices
    
    def _calculate_etf_scores(
        self,
        date: str,
        time_point: str = 'close'
    ) -> List[Dict]:
        """
        计算ETF池中所有ETF的得分
        
        Args:
            date: 当前日期
            time_point: 价格时间点
            
        Returns:
            ETF得分列表，按得分降序排列
        """
        results = []
        
        for code, name in self.etf_pool.items():
            try:
                # 获取历史价格序列
                prices = self._get_price_series(code, date, lookback_days=40, time_point=time_point)
                
                if len(prices) < max(self.m_days, self.ma_filter_days, 6):
                    results.append({
                        'code': code,
                        'name': name,
                        'price': np.nan,
                        'score': 0.0,
                        'r2': 0.0,
                        'annualized_return': 0.0,
                        'ma_value': np.nan,
                        'short_ret': 0.0,
                        'volatility': 0.0,
                        'is_up': False,
                        'is_not_crash': False
                    })
                    continue
                
                # 获取当前价格
                current_price = self.get_price_at_time(code, date, time_point)
                if pd.isna(current_price):
                    current_price = prices[-1] if len(prices) > 0 else np.nan
                
                # 拼接当前价格
                if not pd.isna(current_price) and len(prices) > 0:
                    if abs(prices[-1] - current_price) / prices[-1] > 0.1:  # 价格差异超过10%，使用新价格
                        price_series = np.append(prices[:-1], current_price)
                    else:
                        price_series = prices
                else:
                    price_series = prices
                
                if len(price_series) == 0:
                    continue
                
                # 计算指标
                score_result = Indicators.calculate_etf_score(
                    price_series,
                    ma_period=self.ma_filter_days,
                    momentum_period=self.m_days,
                    short_ret_days=5,
                    short_ret_limit=self.short_ret_limit,
                    use_ma_filter=True,
                    debug=False,
                    symbol=code
                )
                
                # 计算波动率
                volatility = Indicators.get_annualized_vol(price_series[-20:])
                
                results.append({
                    'code': code,
                    'name': name,
                    'price': current_price if not pd.isna(current_price) else price_series[-1],
                    'score': score_result['score'],
                    'r2': score_result['r2'],
                    'annualized_return': score_result['annualized_return'],
                    'ma_value': score_result['ma_value'],
                    'short_ret': score_result['short_ret'],
                    'volatility': volatility,
                    'is_up': score_result['is_up'],
                    'is_not_crash': score_result['is_not_crash']
                })
                
            except Exception as e:
                print(f"计算 {name}({code}) 得分时出错: {e}")
                continue
        
        # 按得分降序排列
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    def _calculate_position_size(
        self,
        base_quantity: int,
        volatility: float
    ) -> int:
        """
        根据波动率计算仓位大小
        
        Args:
            base_quantity: 基础数量
            volatility: 波动率
            
        Returns:
            调整后的数量
        """
        if volatility > self.volatility_threshold:
            return int(base_quantity * 0.5)
        return base_quantity
    
    def generate_signal(
        self,
        date: str,
        current_position: Optional[Dict] = None
    ) -> Dict:
        """
        生成交易信号
        
        Args:
            date: 当前日期
            current_position: 当前持仓
            
        Returns:
            信号字典
        """
        # 计算所有ETF得分
        scores = self._calculate_etf_scores(date, time_point='close')
        
        if not scores:
            return {
                'action': 'hold',
                'code': None,
                'name': None,
                'price': 0.0,
                'quantity': 0,
                'reason': '无可用数据'
            }
        
        # 统计正向得分数量
        positive_count = sum(1 for s in scores if s['score'] > 0)
        sentiment_ratio = positive_count / len(self.etf_pool) if len(self.etf_pool) > 0 else 0
        
        # 获取得分最高的ETF
        top_etf = scores[0]
        top_code = top_etf['code']
        top_score = top_etf['score']
        top_price = top_etf['price']
        top_volatility = top_etf['volatility']
        
        # 检查硬止损
        if current_position and current_position.get('code'):
            current_code = current_position['code']
            entry_price = current_position.get('entry_price')
            
            if entry_price:
                current_price = self.get_price_at_time(current_code, date, self.sell_time)
                if not pd.isna(current_price) and entry_price > 0:
                    loss_ratio = (current_price / entry_price) - 1
                    if loss_ratio <= self.stop_loss_threshold:
                        return {
                            'action': 'sell',
                            'code': current_code,
                            'name': self.etf_pool.get(current_code, current_code),
                            'price': current_price,
                            'quantity': current_position.get('quantity', 0),
                            'reason': f'硬止损触发（跌幅{loss_ratio:.2%}）'
                        }
        
        # 市场情绪风控
        if sentiment_ratio < self.sentiment_threshold:
            if current_position and current_position.get('code'):
                current_code = current_position['code']
                sell_price = self.get_price_at_time(current_code, date, self.sell_time)
                return {
                    'action': 'sell',
                    'code': current_code,
                    'name': self.etf_pool.get(current_code, current_code),
                    'price': sell_price,
                    'quantity': current_position.get('quantity', 0),
                    'reason': f'市场情绪过低（{sentiment_ratio:.2%} < {self.sentiment_threshold:.2%}）'
                }
            else:
                return {
                    'action': 'hold',
                    'code': None,
                    'name': None,
                    'price': 0.0,
                    'quantity': 0,
                    'reason': '市场情绪过低，继续空仓'
                }
        
        # 无正向动量信号
        if top_score <= 0:
            if current_position and current_position.get('code'):
                current_code = current_position['code']
                sell_price = self.get_price_at_time(current_code, date, self.sell_time)
                return {
                    'action': 'sell',
                    'code': current_code,
                    'name': self.etf_pool.get(current_code, current_code),
                    'price': sell_price,
                    'quantity': current_position.get('quantity', 0),
                    'reason': '无正向动量信号'
                }
            else:
                return {
                    'action': 'hold',
                    'code': None,
                    'name': None,
                    'price': 0.0,
                    'quantity': 0,
                    'reason': '无合适入场标的'
                }
        
        # 正常轮动逻辑
        if current_position and current_position.get('code') == top_code:
            # 持仓不变，但可能需要调整仓位
            return {
                'action': 'hold',
                'code': top_code,
                'name': top_etf['name'],
                'price': top_price,
                'quantity': current_position.get('quantity', 0),
                'reason': '当前持仓排名第一，继续持有'
            }
        else:
            # 需要调仓
            # 计算建议仓位
            if current_position and current_position.get('quantity', 0) > 0:
                # 根据当前持仓市值计算
                current_code = current_position.get('code')
                if current_code:
                    current_price = self.get_price_at_time(current_code, date, self.sell_time)
                    if not pd.isna(current_price):
                        current_market_value = current_price * current_position.get('quantity', 0)
                        base_quantity = int(current_market_value / top_price) if top_price > 0 else self.base_quantity
                    else:
                        base_quantity = self.base_quantity
                else:
                    base_quantity = self.base_quantity
            else:
                base_quantity = self.base_quantity
            
            suggested_quantity = self._calculate_position_size(base_quantity, top_volatility)
            
            # 先卖出当前持仓
            if current_position and current_position.get('code'):
                current_code = current_position['code']
                sell_price = self.get_price_at_time(current_code, date, self.sell_time)
                return {
                    'action': 'sell',
                    'code': current_code,
                    'name': self.etf_pool.get(current_code, current_code),
                    'price': sell_price,
                    'quantity': current_position.get('quantity', 0),
                    'reason': '轮动调仓（卖出）',
                    'next_action': {
                        'action': 'buy',
                        'code': top_code,
                        'name': top_etf['name'],
                        'price': self.get_price_at_time(top_code, date, self.buy_time),
                        'quantity': suggested_quantity,
                        'reason': '轮动调仓（买入）'
                    }
                }
            else:
                # 直接买入
                buy_price = self.get_price_at_time(top_code, date, self.buy_time)
                return {
                    'action': 'buy',
                    'code': top_code,
                    'name': top_etf['name'],
                    'price': buy_price if not pd.isna(buy_price) else top_price,
                    'quantity': suggested_quantity,
                    'reason': '开仓信号'
                }
