"""
技术指标计算模块
封装各种技术指标的计算，包括MA、RSI以及基于特定时间点的自定义动量指标
"""
import pandas as pd
import numpy as np
from scipy.stats import linregress
from typing import Optional, Tuple, Dict


class Indicators:
    """技术指标计算类"""
    
    @staticmethod
    def ma(prices: np.ndarray, period: int) -> float:
        """
        计算移动平均线
        
        Args:
            prices: 价格序列
            period: 周期
            
        Returns:
            移动平均值
        """
        if len(prices) < period:
            return np.nan
        return np.mean(prices[-period:])
    
    @staticmethod
    def calculate_momentum(prices: np.ndarray, debug: bool = False, symbol: str = "") -> Tuple[float, float, float]:
        """
        复刻 JoinQuant 动量算法
        使用线性回归计算价格趋势的强度和一致性
        
        Args:
            prices: 价格序列
            debug: 是否输出调试信息
            symbol: ETF代码（用于调试）
            
        Returns:
            (score, r2, annualized_return) 元组
            - score: 动量得分（年化收益率 * R²）
            - r2: 决定系数（拟合优度）
            - annualized_return: 年化收益率
        """
        if len(prices) < 2:
            return 0.0, 0.0, 0.0
        
        y = np.log(prices)
        x = np.arange(len(y))
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        annualized_return = np.exp(slope * 250) - 1
        r2 = r_value ** 2
        score = annualized_return * r2
        result = max(score, 0)
        
        if debug:
            print(f"      [DEBUG {symbol}] 动量计算:")
            print(f"        价格序列长度: {len(prices)}")
            print(f"        价格序列(最后5个): {prices[-5:]}")
            print(f"        对数价格序列(最后5个): {y[-5:]}")
            print(f"        斜率(slope): {slope:.6f}")
            print(f"        相关系数(r_value): {r_value:.6f}")
            print(f"        年化收益率: {annualized_return:.6f}")
            print(f"        R²: {r2:.6f}")
            print(f"        最终得分: {result:.4f}")
        
        return result, r2, annualized_return
    
    @staticmethod
    def get_annualized_vol(prices: np.ndarray, days: int = 252) -> float:
        """
        计算年化波动率
        
        Args:
            prices: 价格序列
            days: 年化天数（默认252个交易日）
            
        Returns:
            年化波动率
        """
        if len(prices) < 2:
            return 0.0
        returns = np.diff(np.log(prices))
        if len(returns) == 0:
            return 0.0
        vol = np.std(returns) * np.sqrt(days)
        return vol
    
    @staticmethod
    def rsi(prices: np.ndarray, period: int = 14) -> float:
        """
        计算相对强弱指标（RSI）
        
        Args:
            prices: 价格序列
            period: 计算周期（默认14）
            
        Returns:
            RSI值（0-100）
        """
        if len(prices) < period + 1:
            return np.nan
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def short_term_return(prices: np.ndarray, days: int = 5) -> float:
        """
        计算短期收益率
        
        Args:
            prices: 价格序列
            days: 计算天数（默认5天）
            
        Returns:
            收益率（小数形式，如0.05表示5%）
        """
        if len(prices) < days + 1:
            return 0.0
        return (prices[-1] / prices[-days-1]) - 1
    
    @staticmethod
    def calculate_etf_score(
        prices: np.ndarray,
        ma_period: int = 20,
        momentum_period: int = 25,
        short_ret_days: int = 5,
        short_ret_limit: float = -0.04,
        use_ma_filter: bool = True,
        debug: bool = False,
        symbol: str = ""
    ) -> Dict[str, float]:
        """
        计算ETF综合得分（基于原有策略逻辑）
        
        Args:
            prices: 价格序列（包含当前价格）
            ma_period: 均线周期
            momentum_period: 动量计算周期
            short_ret_days: 短期收益率计算天数
            short_ret_limit: 短期收益率下限阈值
            use_ma_filter: 是否使用均线过滤
            debug: 是否输出调试信息
            symbol: ETF代码（用于调试）
            
        Returns:
            字典，包含：
            - score: 得分
            - r2: 决定系数
            - annualized_return: 年化收益率
            - ma_value: 均线值
            - short_ret: 短期收益率
            - is_up: 是否在均线上方
            - is_not_crash: 是否未剧烈回调
        """
        if len(prices) < max(ma_period, momentum_period, short_ret_days + 1):
            return {
                "score": 0.0,
                "r2": 0.0,
                "annualized_return": 0.0,
                "ma_value": np.nan,
                "short_ret": 0.0,
                "is_up": False,
                "is_not_crash": False
            }
        
        current_price = prices[-1]
        ma_value = Indicators.ma(prices, ma_period)
        short_ret = Indicators.short_term_return(prices, short_ret_days)
        
        is_up = current_price > ma_value if not pd.isna(ma_value) else False
        is_not_crash = short_ret > short_ret_limit
        
        score = 0.0
        r2 = 0.0
        annualized_return = 0.0
        
        if (not use_ma_filter or is_up) and is_not_crash:
            momentum_prices = prices[-momentum_period:]
            score, r2, annualized_return = Indicators.calculate_momentum(
                momentum_prices, debug=debug, symbol=symbol
            )
        
        if debug:
            if not is_up:
                print(f"❌ 未通过均线过滤: 当前价格 {current_price:.4f} <= MA{ma_period} {ma_value:.4f}")
            if not is_not_crash:
                print(f"❌ 未通过5日涨跌过滤: 5日涨跌 {short_ret:.2%} <= 阈值 {short_ret_limit:.2%}")
        
        return {
            "score": round(score, 4),
            "r2": round(r2, 4),
            "annualized_return": round(annualized_return, 4),
            "ma_value": round(ma_value, 4) if not pd.isna(ma_value) else np.nan,
            "short_ret": round(short_ret, 4),
            "is_up": is_up,
            "is_not_crash": is_not_crash
        }
    
    @staticmethod
    def get_price_series_from_dataframe(
        df: pd.DataFrame,
        time_point: str = 'close',
        include_current: bool = True
    ) -> np.ndarray:
        """
        从DataFrame中提取价格序列
        
        Args:
            df: 包含价格数据的DataFrame
            time_point: 时间点，可选值：'open', 'p1030', 'p1430', 'p1450', 'close'
            include_current: 是否包含当前价格（最后一行）
            
        Returns:
            价格序列数组
        """
        if df.empty:
            return np.array([])
        
        # 选择价格列
        price_col = time_point if time_point in df.columns else 'close'
        
        if price_col not in df.columns:
            return np.array([])
        
        prices = df[price_col].values
        
        # 去除NaN值
        valid_prices = prices[~pd.isna(prices)]
        
        if not include_current and len(valid_prices) > 0:
            valid_prices = valid_prices[:-1]
        
        return valid_prices
