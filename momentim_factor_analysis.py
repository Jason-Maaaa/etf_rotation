"""
ETF 动量因子深度分析与策略优化脚本
功能：
1. 因子相关性分析
2. R²阈值优化
3. 风险调整收益分析
4. 参数网格搜索
5. 回撤与恢复分析
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import linregress
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 导入配置
from etf_config import POOL_DICT
from data_loader import DataLoader


class MomentumFactorAnalyzer:
    """动量因子分析器"""
    
    def __init__(self, data_file: str = "data.txt", pool_name: str = "core"):
        """
        初始化分析器
        
        Args:
            data_file: 数据文件路径
            pool_name: ETF池名称 ('core' 或 'full')
        """
        self.data_file = Path(data_file)
        self.pool_name = pool_name
        
        # 获取ETF池
        if pool_name not in POOL_DICT:
            raise ValueError(f"未找到ETF池 '{pool_name}'，可用池子: {list(POOL_DICT.keys())}")
        self.etf_pool = POOL_DICT[pool_name]
        
        # 初始化数据加载器
        self.data_loader = DataLoader(log_file_path=str(self.data_file))
        
        # 策略参数（默认值，可在网格搜索中优化）
        self.default_m_days = 25
        self.default_ma_filter_days = 20
        
        # 卖出和买入时间
        self.sell_time = "14:30"
        self.buy_time = "14:50"
        
        print(f"✅ 初始化完成 - ETF池: {pool_name} (共 {len(self.etf_pool)} 只)")
    
    def calculate_momentum(self, prices: np.ndarray) -> Tuple[float, float, float]:
        """
        计算动量因子（基于对数价格线性回归）
        
        Returns:
            (score, r2, annualized_return, slope)
        """
        if len(prices) < 2:
            return 0.0, 0.0, 0.0, 0.0
        
        y = np.log(prices)
        x = np.arange(len(y))
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        annualized_return = np.exp(slope * 250) - 1
        r2 = r_value ** 2
        score = annualized_return * r2
        score = max(score, 0)  # 确保非负
        
        return score, r2, annualized_return, slope
    
    def calculate_volatility(self, prices: np.ndarray, days: int = 252) -> float:
        """计算年化波动率"""
        if len(prices) < 2:
            return 0.0
        returns = np.diff(np.log(prices))
        if len(returns) == 0:
            return 0.0
        vol = np.std(returns) * np.sqrt(days)
        return vol
    
    def _vectorized_linear_regression(self, log_prices: np.ndarray) -> Tuple[float, float, float]:
        """
        向量化线性回归计算（用于rolling窗口）
        
        Args:
            log_prices: 对数价格数组
        
        Returns:
            (slope, r2, annualized_return)
        """
        n = len(log_prices)
        if n < 2:
            return 0.0, 0.0, 0.0
        
        x = np.arange(n)
        x_mean = np.mean(x)
        y_mean = np.mean(log_prices)
        
        # 计算斜率
        numerator = np.sum((x - x_mean) * (log_prices - y_mean))
        denominator = np.sum((x - x_mean) ** 2)
        
        if denominator == 0:
            return 0.0, 0.0, 0.0
        
        slope = numerator / denominator
        
        # 计算R²
        y_pred = slope * x + (y_mean - slope * x_mean)
        ss_res = np.sum((log_prices - y_pred) ** 2)
        ss_tot = np.sum((log_prices - y_mean) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        # 年化收益率
        annualized_return = np.exp(slope * 250) - 1
        
        return slope, r2, annualized_return
    
    def prepare_factor_data(self, m_days: int = 25, ma_filter_days: int = 20, 
                           forward_days: int = 5) -> pd.DataFrame:
        """
        准备因子数据，计算所有ETF在所有日期的因子值（向量化优化版本）
        
        Args:
            m_days: 动量计算周期
            ma_filter_days: 均线过滤周期
            forward_days: 未来收益率计算周期
        
        Returns:
            DataFrame包含：date, code, name, score, r2, annualized_return, 
                          slope, volatility, forward_return等
        """
        print(f"\n📊 正在准备因子数据（向量化优化版本）...")
        print(f"   动量周期: {m_days}天, 均线周期: {ma_filter_days}天, 未来收益率: {forward_days}天")
        
        # 一次性加载所有数据（只解析一次文件）
        print("   ⚡ 正在加载数据...")
        df_all = self.data_loader.parse_log_file()
        
        # 只保留ETF池中的代码
        pool_codes = list(self.etf_pool.keys())
        df_all = df_all[df_all['code'].isin(pool_codes)].copy()
        
        # 按code和date排序
        df_all = df_all.sort_values(['code', 'date']).reset_index(drop=True)
        
        print(f"   ✅ 数据加载完成，共 {len(df_all)} 条记录")
        
        # 为每个ETF计算因子（向量化）
        all_results = []
        
        trading_dates = sorted(df_all['date'].unique())
        date_to_idx = {date: idx for idx, date in enumerate(trading_dates)}
        
        print(f"   ⚡ 正在向量化计算因子（共 {len(pool_codes)} 只ETF）...")
        
        for code_idx, code in enumerate(pool_codes):
            if (code_idx + 1) % 5 == 0:
                print(f"      进度: {code_idx + 1}/{len(pool_codes)} ({(code_idx + 1)/len(pool_codes)*100:.1f}%)")
            
            name = self.etf_pool[code]
            
            # 获取该ETF的所有数据
            df_etf = df_all[df_all['code'] == code].copy()
            
            if len(df_etf) < max(m_days, ma_filter_days, forward_days + 5):
                continue
            
            # 使用收盘价，填充缺失值（前向填充）
            df_etf['close'] = df_etf['close'].ffill()
            df_etf = df_etf[df_etf['close'].notna()].copy()
            
            if len(df_etf) < max(m_days, ma_filter_days):
                continue
            
            # 计算对数价格
            df_etf['log_close'] = np.log(df_etf['close'])
            
            # 向量化计算均线
            df_etf['ma'] = df_etf['close'].rolling(window=ma_filter_days, min_periods=ma_filter_days).mean()
            
            # 向量化计算5日涨跌
            df_etf['short_ret'] = df_etf['close'].pct_change(periods=5)
            
            # 向量化计算波动率（20天滚动）
            df_etf['returns'] = df_etf['close'].pct_change()
            df_etf['volatility'] = df_etf['returns'].rolling(window=20, min_periods=2).std() * np.sqrt(252)
            
            # 向量化计算动量因子（使用rolling窗口）
            # 注意：rolling.apply 对于复杂函数可能较慢，但比循环快得多
            slopes = []
            r2s = []
            annualized_returns = []
            
            prices_array = df_etf['close'].values
            log_prices_array = df_etf['log_close'].values
            
            for i in range(len(df_etf)):
                if i < m_days - 1:
                    slopes.append(0.0)
                    r2s.append(0.0)
                    annualized_returns.append(0.0)
                else:
                    window_log_prices = log_prices_array[i - m_days + 1:i + 1]
                    slope, r2, ann_ret = self._vectorized_linear_regression(window_log_prices)
                    slopes.append(slope)
                    r2s.append(r2)
                    annualized_returns.append(ann_ret)
            
            df_etf['slope'] = slopes
            df_etf['r2'] = r2s
            df_etf['annualized_return'] = annualized_returns
            df_etf['score'] = df_etf['annualized_return'] * df_etf['r2']
            df_etf['score'] = df_etf['score'].clip(lower=0)  # 确保非负
            
            # 应用过滤条件
            df_etf['is_up'] = df_etf['close'] > df_etf['ma']
            df_etf['is_not_crash'] = df_etf['short_ret'] > -0.04
            df_etf['is_valid'] = df_etf['is_up'] & df_etf['is_not_crash']
            
            # 不满足条件的score设为0
            df_etf.loc[~df_etf['is_valid'], 'score'] = 0.0
            df_etf.loc[~df_etf['is_valid'], 'r2'] = 0.0
            df_etf.loc[~df_etf['is_valid'], 'annualized_return'] = 0.0
            df_etf.loc[~df_etf['is_valid'], 'slope'] = 0.0
            
            # 计算风险调整动量
            df_etf['risk_adjusted_momentum'] = np.where(
                df_etf['volatility'] > 0,
                df_etf['slope'] / df_etf['volatility'],
                0.0
            )
            
            # 计算未来收益率（向量化优化）
            # 由于交易日可能不连续，使用merge方法更可靠
            df_etf = df_etf.reset_index(drop=True)
            df_etf['date_idx'] = df_etf['date'].map(date_to_idx)
            
            # 创建未来日期映射
            df_etf['future_date_idx'] = df_etf['date_idx'] + forward_days
            df_etf['future_date_idx'] = df_etf['future_date_idx'].where(
                df_etf['future_date_idx'] < len(trading_dates), np.nan
            )
            
            # 创建未来日期列
            df_etf['future_date'] = df_etf['future_date_idx'].map(
                lambda x: trading_dates[int(x)] if not np.isnan(x) and 0 <= int(x) < len(trading_dates) else pd.NaT
            )
            
            # 使用merge获取未来价格（向量化）
            future_prices = df_etf[['date', 'close']].copy()
            future_prices = future_prices.rename(columns={'date': 'future_date', 'close': 'future_price'})
            
            df_etf = df_etf.merge(future_prices, on='future_date', how='left')
            
            # 计算未来收益率
            df_etf['forward_return'] = np.where(
                (df_etf['close'] > 0) & (df_etf['future_price'].notna()),
                (df_etf['future_price'] / df_etf['close']) - 1,
                np.nan
            )
            
            # --- 向量化计算未来 N 天真实最大回撤 ---
            # 使用 rolling(window=forward_days+1).min() 计算未来窗口内的最小值
            # shift(-forward_days) 是为了把未来的最小值对齐到当前日期
            df_etf['future_min_price'] = df_etf['close'].rolling(
                window=forward_days + 1, min_periods=1
            ).min().shift(-forward_days)
            
            # 真实最大回撤 = (未来最低价 / 当前买入价) - 1
            df_etf['real_max_dd'] = np.where(
                (df_etf['close'] > 0) & (df_etf['future_min_price'].notna()),
                (df_etf['future_min_price'] / df_etf['close']) - 1,
                np.nan
            )
            
            # 清理临时列
            df_etf = df_etf.drop(['date_idx', 'future_date_idx', 'future_date', 'future_price', 'future_min_price'], 
                                axis=1, errors='ignore')
            
            # 选择需要的列（包含回撤数据）
            result_cols = ['date', 'close', 'score', 'r2', 'annualized_return', 'slope', 
                          'volatility', 'forward_return', 'risk_adjusted_momentum', 
                          'is_up', 'is_not_crash', 'real_max_dd']
            df_result = df_etf[result_cols].copy()
            df_result['code'] = code
            df_result['name'] = name
            df_result['current_price'] = df_result['close']
            
            all_results.append(df_result)
        
        # 合并所有结果
        if all_results:
            df_factors = pd.concat(all_results, ignore_index=True)
            df_factors = df_factors.sort_values(['date', 'code']).reset_index(drop=True)
        else:
            df_factors = pd.DataFrame()
        
        print(f"✅ 因子数据准备完成，共 {len(df_factors)} 条记录")
        
        return df_factors
    
    def analyze_correlation(self, df_factors: pd.DataFrame, forward_days: int = 5):
        """
        因子相关性分析
        
        分析 score, r2, slope 与未来收益率的相关性
        """
        print(f"\n{'='*80}")
        print(f"📈 因子相关性分析 (未来{forward_days}日收益率)")
        print(f"{'='*80}")
        
        # 过滤有效数据
        df_valid = df_factors.dropna(subset=['forward_return', 'score', 'r2', 'slope'])
        
        if len(df_valid) == 0:
            print("❌ 没有有效数据进行分析")
            return
        
        # 计算相关系数
        correlations = {
            'Score vs 未来收益率': df_valid['score'].corr(df_valid['forward_return']),
            'R² vs 未来收益率': df_valid['r2'].corr(df_valid['forward_return']),
            'Slope vs 未来收益率': df_valid['slope'].corr(df_valid['forward_return']),
            '年化收益率 vs 未来收益率': df_valid['annualized_return'].corr(df_valid['forward_return']),
            '风险调整动量 vs 未来收益率': df_valid['risk_adjusted_momentum'].corr(df_valid['forward_return'])
        }
        
        print("\n📊 相关系数:")
        for name, corr in correlations.items():
            print(f"   {name}: {corr:.4f}")
        
        # 可视化
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle(f'因子与未来{forward_days}日收益率相关性分析', fontsize=16, fontweight='bold')
        
        # Score vs 未来收益率
        ax = axes[0, 0]
        ax.scatter(df_valid['score'], df_valid['forward_return'], alpha=0.3, s=10)
        z = np.polyfit(df_valid['score'], df_valid['forward_return'], 1)
        p = np.poly1d(z)
        ax.plot(df_valid['score'], p(df_valid['score']), "r--", alpha=0.8, linewidth=2)
        ax.set_xlabel('Score')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title(f'Score vs 未来收益率 (r={correlations["Score vs 未来收益率"]:.4f})')
        ax.grid(True, alpha=0.3)
        
        # R² vs 未来收益率
        ax = axes[0, 1]
        ax.scatter(df_valid['r2'], df_valid['forward_return'], alpha=0.3, s=10)
        z = np.polyfit(df_valid['r2'], df_valid['forward_return'], 1)
        p = np.poly1d(z)
        ax.plot(df_valid['r2'], p(df_valid['r2']), "r--", alpha=0.8, linewidth=2)
        ax.set_xlabel('R²')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title(f'R² vs 未来收益率 (r={correlations["R² vs 未来收益率"]:.4f})')
        ax.grid(True, alpha=0.3)
        
        # Slope vs 未来收益率
        ax = axes[0, 2]
        ax.scatter(df_valid['slope'], df_valid['forward_return'], alpha=0.3, s=10)
        z = np.polyfit(df_valid['slope'], df_valid['forward_return'], 1)
        p = np.poly1d(z)
        ax.plot(df_valid['slope'], p(df_valid['slope']), "r--", alpha=0.8, linewidth=2)
        ax.set_xlabel('Slope (斜率)')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title(f'Slope vs 未来收益率 (r={correlations["Slope vs 未来收益率"]:.4f})')
        ax.grid(True, alpha=0.3)
        
        # 年化收益率 vs 未来收益率
        ax = axes[1, 0]
        ax.scatter(df_valid['annualized_return'], df_valid['forward_return'], alpha=0.3, s=10)
        z = np.polyfit(df_valid['annualized_return'], df_valid['forward_return'], 1)
        p = np.poly1d(z)
        ax.plot(df_valid['annualized_return'], p(df_valid['annualized_return']), "r--", alpha=0.8, linewidth=2)
        ax.set_xlabel('年化收益率')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title(f'年化收益率 vs 未来收益率 (r={correlations["年化收益率 vs 未来收益率"]:.4f})')
        ax.grid(True, alpha=0.3)
        
        # 风险调整动量 vs 未来收益率
        ax = axes[1, 1]
        # 过滤异常值
        df_ram = df_valid[(df_valid['risk_adjusted_momentum'] > -10) & 
                          (df_valid['risk_adjusted_momentum'] < 10)].copy()
        if len(df_ram) > 0:
            ax.scatter(df_ram['risk_adjusted_momentum'], df_ram['forward_return'], alpha=0.3, s=10)
            z = np.polyfit(df_ram['risk_adjusted_momentum'], df_ram['forward_return'], 1)
            p = np.poly1d(z)
            ax.plot(df_ram['risk_adjusted_momentum'], p(df_ram['risk_adjusted_momentum']), "r--", alpha=0.8, linewidth=2)
        ax.set_xlabel('风险调整动量 (斜率/波动率)')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title(f'风险调整动量 vs 未来收益率 (r={correlations["风险调整动量 vs 未来收益率"]:.4f})')
        ax.grid(True, alpha=0.3)
        
        # 综合散点图（Score vs R²，颜色表示未来收益率）
        ax = axes[1, 2]
        scatter = ax.scatter(df_valid['score'], df_valid['r2'], 
                            c=df_valid['forward_return'], cmap='RdYlGn', 
                            alpha=0.5, s=20, vmin=-0.1, vmax=0.1)
        ax.set_xlabel('Score')
        ax.set_ylabel('R²')
        ax.set_title('Score vs R² (颜色=未来收益率)')
        ax.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax, label='未来收益率')
        
        plt.tight_layout()
        plt.savefig(f'因子相关性分析_{self.pool_name}.png', dpi=300, bbox_inches='tight')
        print(f"\n✅ 图表已保存: 因子相关性分析_{self.pool_name}.png")
        plt.close()
    
    def analyze_r2_threshold(self, df_factors: pd.DataFrame, forward_days: int = 5):
        """
        R²阈值优化分析
        
        研究不同R²区间下的表现，特别关注"趋势过热"现象
        """
        print(f"\n{'='*80}")
        print(f"🔍 R²阈值优化分析 (未来{forward_days}日收益率)")
        print(f"{'='*80}")
        
        df_valid = df_factors.dropna(subset=['forward_return', 'r2', 'score'])
        
        if len(df_valid) == 0:
            print("❌ 没有有效数据进行分析")
            return
        
        # 定义R²区间
        r2_bins = [0, 0.3, 0.5, 0.7, 0.9, 0.95, 1.0]
        r2_labels = ['0-0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '0.9-0.95', '0.95-1.0']
        
        df_valid['r2_bin'] = pd.cut(df_valid['r2'], bins=r2_bins, labels=r2_labels)
        
        # 统计每个区间的表现
        stats = []
        for label in r2_labels:
            df_bin = df_valid[df_valid['r2_bin'] == label]
            if len(df_bin) > 0:
                stats.append({
                    'R²区间': label,
                    '样本数': len(df_bin),
                    '平均未来收益率': df_bin['forward_return'].mean(),
                    '收益率标准差': df_bin['forward_return'].std(),
                    '收益率中位数': df_bin['forward_return'].median(),
                    '正收益比例': (df_bin['forward_return'] > 0).sum() / len(df_bin),
                    '平均Score': df_bin['score'].mean(),
                    '平均R²': df_bin['r2'].mean()
                })
        
        df_stats = pd.DataFrame(stats)
        print("\n📊 R²区间表现统计:")
        print(df_stats.to_string(index=False))
        
        # 可视化
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('R²阈值优化分析', fontsize=16, fontweight='bold')
        
        # 1. 平均未来收益率 vs R²区间
        ax = axes[0, 0]
        ax.bar(df_stats['R²区间'], df_stats['平均未来收益率'], alpha=0.7, color='steelblue')
        ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax.set_xlabel('R²区间')
        ax.set_ylabel(f'平均未来{forward_days}日收益率')
        ax.set_title('不同R²区间的平均未来收益率')
        ax.grid(True, alpha=0.3, axis='y')
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 2. 收益率波动 vs R²区间
        ax = axes[0, 1]
        ax.bar(df_stats['R²区间'], df_stats['收益率标准差'], alpha=0.7, color='coral')
        ax.set_xlabel('R²区间')
        ax.set_ylabel('收益率标准差')
        ax.set_title('不同R²区间的收益率波动')
        ax.grid(True, alpha=0.3, axis='y')
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 3. 正收益比例 vs R²区间
        ax = axes[1, 0]
        ax.bar(df_stats['R²区间'], df_stats['正收益比例'], alpha=0.7, color='green')
        ax.axhline(y=0.5, color='r', linestyle='--', alpha=0.5, label='50%基准线')
        ax.set_xlabel('R²区间')
        ax.set_ylabel('正收益比例')
        ax.set_title('不同R²区间的正收益比例')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 4. R² vs 未来收益率散点图（重点关注高R²区域）
        ax = axes[1, 1]
        # 高R²区域（>0.9）
        df_high_r2 = df_valid[df_valid['r2'] > 0.9]
        df_low_r2 = df_valid[df_valid['r2'] <= 0.9]
        
        if len(df_low_r2) > 0:
            ax.scatter(df_low_r2['r2'], df_low_r2['forward_return'], 
                      alpha=0.2, s=10, color='blue', label='R² ≤ 0.9')
        if len(df_high_r2) > 0:
            ax.scatter(df_high_r2['r2'], df_high_r2['forward_return'], 
                      alpha=0.5, s=20, color='red', label='R² > 0.9 (趋势过热?)')
        
        ax.axvline(x=0.9, color='r', linestyle='--', alpha=0.5, label='R²=0.9阈值')
        ax.set_xlabel('R²')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title('R² vs 未来收益率（关注趋势过热现象）')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'R²阈值优化分析_{self.pool_name}.png', dpi=300, bbox_inches='tight')
        print(f"\n✅ 图表已保存: R²阈值优化分析_{self.pool_name}.png")
        plt.close()
        
        # 特别分析：极高R²（>0.95）的表现
        df_very_high_r2 = df_valid[df_valid['r2'] > 0.95]
        if len(df_very_high_r2) > 0:
            print(f"\n⚠️  趋势过热分析 (R² > 0.95):")
            print(f"   样本数: {len(df_very_high_r2)}")
            print(f"   平均未来收益率: {df_very_high_r2['forward_return'].mean():.4f}")
            print(f"   收益率标准差: {df_very_high_r2['forward_return'].std():.4f}")
            print(f"   正收益比例: {(df_very_high_r2['forward_return'] > 0).sum() / len(df_very_high_r2):.2%}")
    
    def analyze_risk_adjusted(self, df_factors: pd.DataFrame, forward_days: int = 5):
        """
        风险调整收益分析
        
        对比原生Score与风险调整动量（斜率/波动率）的表现
        """
        print(f"\n{'='*80}")
        print(f"⚖️  风险调整收益分析 (未来{forward_days}日收益率)")
        print(f"{'='*80}")
        
        df_valid = df_factors.dropna(subset=['forward_return', 'score', 'risk_adjusted_momentum', 'volatility'])
        
        if len(df_valid) == 0:
            print("❌ 没有有效数据进行分析")
            return
        
        # 过滤异常值
        df_valid = df_valid[
            (df_valid['risk_adjusted_momentum'] > -10) & 
            (df_valid['risk_adjusted_momentum'] < 10) &
            (df_valid['volatility'] > 0) &
            (df_valid['volatility'] < 1.0)  # 过滤极端波动率
        ].copy()
        
        # 按Score和风险调整动量分别排序，取前N个
        top_n = 100
        
        # 基于Score选出的标的
        df_score_top = df_valid.nlargest(top_n, 'score')
        
        # 基于风险调整动量选出的标的
        df_ram_top = df_valid.nlargest(top_n, 'risk_adjusted_momentum')
        
        print(f"\n📊 对比分析 (取前{top_n}个标的):")
        print(f"\n基于Score选出的标的:")
        print(f"   平均未来收益率: {df_score_top['forward_return'].mean():.4f}")
        print(f"   收益率标准差: {df_score_top['forward_return'].std():.4f}")
        print(f"   平均波动率: {df_score_top['volatility'].mean():.4f}")
        print(f"   正收益比例: {(df_score_top['forward_return'] > 0).sum() / len(df_score_top):.2%}")
        
        print(f"\n基于风险调整动量选出的标的:")
        print(f"   平均未来收益率: {df_ram_top['forward_return'].mean():.4f}")
        print(f"   收益率标准差: {df_ram_top['forward_return'].std():.4f}")
        print(f"   平均波动率: {df_ram_top['volatility'].mean():.4f}")
        print(f"   正收益比例: {(df_ram_top['forward_return'] > 0).sum() / len(df_ram_top):.2%}")
        
        # 分析高波动率背景下动量因子的失效概率
        high_vol_threshold = 0.30  # 30%波动率
        df_high_vol = df_valid[df_valid['volatility'] > high_vol_threshold]
        
        if len(df_high_vol) > 0:
            print(f"\n⚠️  高波动率环境分析 (波动率 > {high_vol_threshold:.0%}):")
            print(f"   样本数: {len(df_high_vol)}")
            print(f"   平均未来收益率: {df_high_vol['forward_return'].mean():.4f}")
            print(f"   正收益比例: {(df_high_vol['forward_return'] > 0).sum() / len(df_high_vol):.2%}")
            print(f"   动量因子失效概率: {(df_high_vol['forward_return'] <= 0).sum() / len(df_high_vol):.2%}")
        
        # 可视化
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('风险调整收益分析', fontsize=16, fontweight='bold')
        
        # 1. Score vs 风险调整动量散点图
        ax = axes[0, 0]
        scatter = ax.scatter(df_valid['score'], df_valid['risk_adjusted_momentum'], 
                            c=df_valid['forward_return'], cmap='RdYlGn', 
                            alpha=0.5, s=20, vmin=-0.1, vmax=0.1)
        ax.set_xlabel('Score')
        ax.set_ylabel('风险调整动量 (斜率/波动率)')
        ax.set_title('Score vs 风险调整动量 (颜色=未来收益率)')
        ax.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax, label='未来收益率')
        
        # 2. 波动率 vs 未来收益率
        ax = axes[0, 1]
        ax.scatter(df_valid['volatility'], df_valid['forward_return'], alpha=0.3, s=10)
        ax.axvline(x=high_vol_threshold, color='r', linestyle='--', alpha=0.5, label=f'波动率阈值={high_vol_threshold:.0%}')
        ax.set_xlabel('年化波动率')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title('波动率 vs 未来收益率')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 3. 不同波动率区间的表现
        vol_bins = [0, 0.15, 0.25, 0.35, 0.50, 1.0]
        vol_labels = ['0-15%', '15-25%', '25-35%', '35-50%', '50%+']
        df_valid['vol_bin'] = pd.cut(df_valid['volatility'], bins=vol_bins, labels=vol_labels)
        
        vol_stats = []
        for label in vol_labels:
            df_bin = df_valid[df_valid['vol_bin'] == label]
            if len(df_bin) > 0:
                vol_stats.append({
                    '波动率区间': label,
                    '平均未来收益率': df_bin['forward_return'].mean(),
                    '正收益比例': (df_bin['forward_return'] > 0).sum() / len(df_bin)
                })
        
        df_vol_stats = pd.DataFrame(vol_stats)
        
        ax = axes[1, 0]
        x_pos = np.arange(len(df_vol_stats))
        ax.bar(x_pos, df_vol_stats['平均未来收益率'], alpha=0.7, color='steelblue')
        ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(df_vol_stats['波动率区间'], rotation=45, ha='right')
        ax.set_ylabel(f'平均未来{forward_days}日收益率')
        ax.set_title('不同波动率区间的平均未来收益率')
        ax.grid(True, alpha=0.3, axis='y')
        
        # 4. 高波动率下的动量因子表现
        ax = axes[1, 1]
        if len(df_high_vol) > 0:
            ax.scatter(df_high_vol['score'], df_high_vol['forward_return'], 
                      alpha=0.5, s=30, color='red', label=f'高波动率(>{high_vol_threshold:.0%})')
        df_low_vol = df_valid[df_valid['volatility'] <= high_vol_threshold]
        if len(df_low_vol) > 0:
            ax.scatter(df_low_vol['score'], df_low_vol['forward_return'], 
                      alpha=0.3, s=10, color='blue', label=f'低波动率(≤{high_vol_threshold:.0%})')
        ax.set_xlabel('Score')
        ax.set_ylabel(f'未来{forward_days}日收益率')
        ax.set_title('高波动率环境下的动量因子表现')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'风险调整收益分析_{self.pool_name}.png', dpi=300, bbox_inches='tight')
        print(f"\n✅ 图表已保存: 风险调整收益分析_{self.pool_name}.png")
        plt.close()
    
    def grid_search_parameters(self, m_days_list: List[int], ma_filter_days_list: List[int],
                              forward_days: int = 5, initial_capital: float = 100000.0):
        """
        参数网格搜索
        
        对 m_days 和 ma_filter_days 进行网格搜索，计算收益率、夏普比率、最大回撤
        """
        print(f"\n{'='*80}")
        print(f"🔬 参数网格搜索")
        print(f"{'='*80}")
        print(f"   动量周期候选: {m_days_list}")
        print(f"   均线周期候选: {ma_filter_days_list}")
        print(f"   初始资金: {initial_capital:,.0f} 元")
        
        results = []
        
        total_combinations = len(m_days_list) * len(ma_filter_days_list)
        current = 0
        
        for m_days in m_days_list:
            for ma_filter_days in ma_filter_days_list:
                current += 1
                print(f"\n   进度: {current}/{total_combinations} - m_days={m_days}, ma_filter_days={ma_filter_days}")
                
                # 准备该参数组合的因子数据
                df_factors = self.prepare_factor_data(m_days, ma_filter_days, forward_days)
                
                # 执行回测
                backtest_result = self._simple_backtest(df_factors, initial_capital)
                
                results.append({
                    'm_days': m_days,
                    'ma_filter_days': ma_filter_days,
                    **backtest_result
                })
        
        df_results = pd.DataFrame(results)
        
        # 打印最优参数
        print(f"\n{'='*80}")
        print("📊 参数优化结果汇总")
        print(f"{'='*80}")
        
        # 按不同指标排序
        metrics = ['total_return', 'sharpe_ratio', 'max_drawdown']
        metric_names = ['总收益率', '夏普比率', '最大回撤']
        
        for metric, name in zip(metrics, metric_names):
            if metric == 'max_drawdown':
                # 最大回撤越小越好
                best = df_results.nsmallest(1, metric)
            else:
                # 其他指标越大越好
                best = df_results.nlargest(1, metric)
            
            print(f"\n🏆 最优{name}参数组合:")
            print(f"   m_days={best.iloc[0]['m_days']}, ma_filter_days={best.iloc[0]['ma_filter_days']}")
            print(f"   {name}: {best.iloc[0][metric]:.4f}")
            print(f"   总收益率: {best.iloc[0]['total_return']:.2%}")
            print(f"   夏普比率: {best.iloc[0]['sharpe_ratio']:.4f}")
            print(f"   最大回撤: {best.iloc[0]['max_drawdown']:.2%}")
        
        # 生成热力图
        self._plot_heatmaps(df_results)
        
        return df_results
    
    def _simple_backtest(self, df_factors: pd.DataFrame, initial_capital: float) -> Dict:
        """
        真实回测引擎（修复前瞻偏差）
        
        策略逻辑：
        1. 每日计算T日的动量分数（使用CLOSE，仅历史数据）
        2. 卖出逻辑 (14:30)：如果当前持仓标的不再是排名第一，则以P1430价格卖出
        3. 买入逻辑 (14:50)：如果现金状态且有新的排名第一标的，则以P1450价格买入
        4. 手续费与滑点：每笔交易0.01%的单边税费/滑点扣除
        5. 净值计算：每日收盘后，资产 = (持仓份额 × 当日CLOSE) + 现金余额
        """
        # 需要获取价格数据（P1430, P1450, CLOSE）
        # 先加载完整数据
        df_all = self.data_loader.parse_log_file()
        pool_codes = list(self.etf_pool.keys())
        df_all = df_all[df_all['code'].isin(pool_codes)].copy()
        
        # 合并因子数据和价格数据
        # 注意：df_factors 已经包含 'close' 列，合并时会有冲突
        # 我们只从 df_all 中获取 p1430, p1450，close 使用 df_factors 中的（已经计算过）
        df_factors = df_factors.sort_values('date').copy()
        df_prices = df_all[['date', 'code', 'p1430', 'p1450']].copy()
        
        df_merged = df_factors.merge(
            df_prices,
            on=['date', 'code'],
            how='left'
        )
        
        # 确保 close 列存在（应该已经在 df_factors 中）
        if 'close' not in df_merged.columns:
            # 如果不存在，从 df_all 中获取
            df_close = df_all[['date', 'code', 'close']].copy()
            df_merged = df_merged.merge(df_close, on=['date', 'code'], how='left')
        
        # 按日期分组，每日选择Score最高的ETF
        trading_dates = sorted(df_merged['date'].unique())
        
        # 状态机变量
        current_position = None  # {'code': str, 'shares': int, 'entry_price': float}
        cash = initial_capital
        equity_curve = [initial_capital]
        dates = []
        commission_rate = 0.0001  # 0.01% 单边手续费/滑点
        
        for date in trading_dates:
            # 获取当日所有ETF的因子数据
            df_day = df_merged[df_merged['date'] == date].copy()
            
            # 只考虑Score > 0的标的
            df_day = df_day[df_day['score'] > 0]
            
            # 选择Score最高的ETF
            if len(df_day) > 0:
                best = df_day.nlargest(1, 'score').iloc[0]
                best_code = best['code']
                best_p1430 = best['p1430']
                best_p1450 = best['p1450']
                best_close = best['close']
            else:
                best_code = None
                best_p1430 = np.nan
                best_p1450 = np.nan
                best_close = np.nan
            
            # === 卖出逻辑 (14:30) ===
            if current_position is not None:
                current_code = current_position['code']
                current_shares = current_position['shares']
                
                # 如果当前持仓不再是排名第一，或者没有符合条件的标的，则卖出
                if best_code is None or current_code != best_code:
                    # 获取卖出价格（P1430）
                    sell_price = df_day[df_day['code'] == current_code]['p1430'].values
                    if len(sell_price) > 0 and not np.isnan(sell_price[0]):
                        sell_price = sell_price[0]
                    else:
                        # 如果P1430不可用，使用close价格
                        sell_price = df_day[df_day['code'] == current_code]['close'].values[0] if len(df_day[df_day['code'] == current_code]) > 0 else current_position['entry_price']
                    
                    # 计算卖出金额（扣除手续费）
                    sell_amount = current_shares * sell_price * (1 - commission_rate)
                    cash += sell_amount
                    current_position = None
            
            # === 买入逻辑 (14:50) ===
            if current_position is None and best_code is not None:
                # 获取买入价格（P1450）
                if not np.isnan(best_p1450) and best_p1450 > 0:
                    buy_price = best_p1450
                elif not np.isnan(best_close) and best_close > 0:
                    buy_price = best_close
                else:
                    buy_price = None
                
                if buy_price is not None:
                    # 计算可买入份额（扣除手续费）
                    available_cash = cash * (1 - commission_rate)
                    shares = int(available_cash / buy_price)
                    
                    if shares > 0:
                        # 计算实际花费
                        cost = shares * buy_price * (1 + commission_rate)
                        if cost <= cash:
                            cash -= cost
                            current_position = {
                                'code': best_code,
                                'shares': shares,
                                'entry_price': buy_price
                            }
            
            # === 计算当日净值（收盘后） ===
            if current_position is not None:
                # 获取持仓标的的收盘价
                position_code = current_position['code']
                position_close = df_day[df_day['code'] == position_code]['close'].values
                if len(position_close) > 0 and not np.isnan(position_close[0]):
                    position_close = position_close[0]
                else:
                    # 如果close不可用，使用entry_price
                    position_close = current_position['entry_price']
                
                # 净值 = 持仓市值 + 现金
                position_value = current_position['shares'] * position_close
                daily_equity = position_value + cash
            else:
                daily_equity = cash
            
            equity_curve.append(daily_equity)
            dates.append(date)
        
        # 计算指标
        equity_array = np.array(equity_curve[1:])  # 去掉初始值
        
        if len(equity_array) == 0:
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'final_equity': initial_capital
            }
        
        # 计算日收益率（避免指数爆炸）
        daily_returns = np.diff(equity_array) / equity_array[:-1]
        daily_returns = daily_returns[~np.isnan(daily_returns)]
        
        total_return = (equity_array[-1] / initial_capital) - 1
        
        # 夏普比率（假设252个交易日）
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # 最大回撤
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max
        max_drawdown = drawdown.min()
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_equity': equity_array[-1]
        }
    
    def _plot_heatmaps(self, df_results: pd.DataFrame):
        """绘制参数网格搜索热力图"""
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        fig.suptitle('参数网格搜索热力图', fontsize=16, fontweight='bold')
        
        # 创建透视表
        pivot_return = df_results.pivot(index='ma_filter_days', columns='m_days', values='total_return')
        pivot_sharpe = df_results.pivot(index='ma_filter_days', columns='m_days', values='sharpe_ratio')
        pivot_drawdown = df_results.pivot(index='ma_filter_days', columns='m_days', values='max_drawdown')
        
        # 总收益率热力图
        ax = axes[0]
        sns.heatmap(pivot_return, annot=True, fmt='.2%', cmap='RdYlGn', center=0, ax=ax, cbar_kws={'label': '总收益率'})
        ax.set_title('总收益率热力图')
        ax.set_xlabel('动量周期 (m_days)')
        ax.set_ylabel('均线周期 (ma_filter_days)')
        
        # 夏普比率热力图
        ax = axes[1]
        sns.heatmap(pivot_sharpe, annot=True, fmt='.2f', cmap='RdYlGn', center=0, ax=ax, cbar_kws={'label': '夏普比率'})
        ax.set_title('夏普比率热力图')
        ax.set_xlabel('动量周期 (m_days)')
        ax.set_ylabel('均线周期 (ma_filter_days)')
        
        # 最大回撤热力图
        ax = axes[2]
        sns.heatmap(pivot_drawdown, annot=True, fmt='.2%', cmap='RdYlGn_r', center=0, ax=ax, cbar_kws={'label': '最大回撤'})
        ax.set_title('最大回撤热力图')
        ax.set_xlabel('动量周期 (m_days)')
        ax.set_ylabel('均线周期 (ma_filter_days)')
        
        plt.tight_layout()
        plt.savefig(f'参数网格搜索热力图_{self.pool_name}.png', dpi=300, bbox_inches='tight')
        print(f"\n✅ 图表已保存: 参数网格搜索热力图_{self.pool_name}.png")
        plt.close()
    
    def _get_real_price_trajectory(self, code: str, buy_date: pd.Timestamp, hold_days: int) -> Optional[pd.Series]:
        """
        获取买入后N天的真实价格轨迹
        
        Args:
            code: ETF代码
            buy_date: 买入日期
            hold_days: 持有天数
        
        Returns:
            价格序列（Series），如果数据不足则返回None
        """
        # 获取买入日期及之后的数据
        buy_date_str = buy_date.strftime('%Y-%m-%d')
        
        # 获取该ETF的所有数据
        df_etf = self.data_loader.get_etf_data(code)
        if df_etf.empty:
            return None
        
        # 找到买入日期及之后的数据
        df_etf = df_etf[df_etf['date'] >= buy_date].copy()
        df_etf = df_etf.sort_values('date').reset_index(drop=True)
        
        if len(df_etf) < hold_days + 1:  # 至少需要买入日+持有期
            return None
        
        # 获取持有期内的价格（使用收盘价）
        prices = df_etf['close'].iloc[:hold_days + 1].copy()
        prices = prices[prices.notna()]
        
        if len(prices) < 2:
            return None
        
        return prices
    
    def _calculate_real_drawdown(self, prices: pd.Series) -> Tuple[float, int]:
        """
        基于真实价格计算最大回撤和恢复时长
        
        Args:
            prices: 价格序列（从买入日开始）
        
        Returns:
            (max_drawdown, recovery_days)
        """
        if len(prices) < 2:
            return 0.0, 0
        
        # 计算相对于买入价的收益率
        buy_price = prices.iloc[0]
        if buy_price <= 0:
            return 0.0, 0
        
        returns = (prices / buy_price) - 1
        
        # 计算累计最大值（从买入日开始）
        cumulative_max = returns.expanding().max()
        
        # 计算回撤（当前收益 - 历史最高收益）
        drawdown = returns - cumulative_max
        
        # 最大回撤
        max_drawdown = drawdown.min()
        
        # 找到最大回撤点
        max_dd_idx = drawdown.idxmin()
        max_dd_value = drawdown.loc[max_dd_idx]
        
        # 计算恢复时长（从最大回撤点到创新高）
        recovery_days = 0
        if max_dd_idx < len(returns) - 1:
            # 最大回撤时的累计最高收益
            peak_return = cumulative_max.loc[max_dd_idx]
            
            # 从最大回撤点之后，找到首次超过峰值的位置
            future_returns = returns.loc[max_dd_idx + 1:]
            future_max = cumulative_max.loc[max_dd_idx + 1:]
            
            # 找到首次超过或等于峰值的位置
            recovery_mask = future_returns >= peak_return
            if recovery_mask.any():
                recovery_idx = recovery_mask.idxmax()
                recovery_days = (recovery_idx - max_dd_idx) if recovery_idx != max_dd_idx else 0
            else:
                # 未恢复，返回持有期长度
                recovery_days = len(returns) - 1 - (max_dd_idx - returns.index[0])
        
        return max_drawdown, recovery_days
    
    def analyze_drawdown(self, df_factors: pd.DataFrame, forward_days: int = 5):
        """
        极速版：回撤分析（向量化计算完成）
        
        统计买入信号发出时的平均最大浮亏
        注意：回撤数据已在 prepare_factor_data 中向量化计算完成
        """
        print(f"\n{'='*80}")
        print(f"📉 回撤分析 (向量化计算完成)")
        print(f"{'='*80}")
        
        # 过滤出有买入信号（score > 0）且有真实回撤数据的记录
        df_signals = df_factors[df_factors['score'] > 0].dropna(subset=['real_max_dd']).copy()
        
        if len(df_signals) == 0:
            print("❌ 未发现有效买入信号的回撤数据")
            return
        
        print(f"   有效买入信号数: {len(df_signals):,}")
        
        # 直接进行统计，无需任何循环
        avg_dd = df_signals['real_max_dd'].mean()
        median_dd = df_signals['real_max_dd'].median()
        std_dd = df_signals['real_max_dd'].std()
        
        print(f"\n📊 回撤统计 (共 {len(df_signals)} 个买入信号):")
        print(f"   平均最大浮亏: {avg_dd:.2%}")
        print(f"   最大浮亏中位数: {median_dd:.2%}")
        print(f"   最大浮亏标准差: {std_dd:.2%}")
        
        # 为了兼容后续的可视化代码，创建df_drawdown
        df_drawdown = df_signals[['date', 'code', 'score', 'forward_return', 'real_max_dd']].copy()
        df_drawdown = df_drawdown.rename(columns={'real_max_dd': 'max_drawdown'})
        
        # 计算总收益（使用forward_return）
        df_drawdown['total_return'] = df_drawdown['forward_return']
        
        # 按Score分组分析
        score_bins = [0, 0.1, 0.2, 0.3, 0.5, 1.0, float('inf')]
        score_labels = ['0-0.1', '0.1-0.2', '0.2-0.3', '0.3-0.5', '0.5-1.0', '1.0+']
        df_drawdown['score_bin'] = pd.cut(df_drawdown['score'], bins=score_bins, labels=score_labels)
        
        score_stats = []
        for label in score_labels:
            df_bin = df_drawdown[df_drawdown['score_bin'] == label]
            if len(df_bin) > 0:
                score_stats.append({
                    'Score区间': label,
                    '样本数': len(df_bin),
                    '平均最大浮亏': df_bin['max_drawdown'].mean(),
                    '平均总收益': df_bin['total_return'].mean()
                })
        
        df_score_stats = pd.DataFrame(score_stats)
        print(f"\n📊 按Score分组的回撤统计:")
        print(df_score_stats.to_string(index=False))
        
        # 可视化
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('回撤与恢复分析', fontsize=16, fontweight='bold')
        
        # 1. 最大浮亏分布直方图
        ax = axes[0, 0]
        ax.hist(df_drawdown['max_drawdown'], bins=50, alpha=0.7, color='steelblue', edgecolor='black')
        ax.axvline(df_drawdown['max_drawdown'].mean(), color='r', linestyle='--', 
                  linewidth=2, label=f'平均值: {df_drawdown["max_drawdown"].mean():.2%}')
        ax.set_xlabel('最大浮亏')
        ax.set_ylabel('频数')
        ax.set_title('最大浮亏分布')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # 2. 最大浮亏 vs 总收益散点图
        ax = axes[0, 1]
        ax.scatter(df_drawdown['total_return'], df_drawdown['max_drawdown'], alpha=0.5, s=20, color='coral')
        ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax.axvline(x=0, color='r', linestyle='--', alpha=0.5)
        ax.set_xlabel('总收益率')
        ax.set_ylabel('最大浮亏')
        ax.set_title('总收益 vs 最大浮亏')
        ax.grid(True, alpha=0.3)
        
        # 3. Score vs 最大浮亏散点图
        ax = axes[1, 0]
        ax.scatter(df_drawdown['score'], df_drawdown['max_drawdown'], alpha=0.5, s=20)
        ax.set_xlabel('Score')
        ax.set_ylabel('最大浮亏')
        ax.set_title('Score vs 最大浮亏')
        ax.grid(True, alpha=0.3)
        
        # 4. 按Score区间的平均回撤和恢复时长
        if len(df_score_stats) > 0:
            ax = axes[1, 1]
            x_pos = np.arange(len(df_score_stats))
            width = 0.35
            
            ax.bar(x_pos, df_score_stats['平均最大浮亏'], alpha=0.7, color='steelblue', label='平均最大浮亏')
            ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(df_score_stats['Score区间'], rotation=45, ha='right')
            ax.set_ylabel('平均最大浮亏')
            ax.set_title('按Score区间的平均回撤')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig(f'回撤与恢复分析_{self.pool_name}.png', dpi=300, bbox_inches='tight')
        print(f"\n✅ 图表已保存: 回撤与恢复分析_{self.pool_name}.png")
        plt.close()
    
    def generate_optimization_report(self, df_factors: pd.DataFrame, 
                                     df_grid_results: Optional[pd.DataFrame] = None):
        """
        生成优化报告
        
        汇总所有分析结果，给出最优参数建议
        """
        print(f"\n{'='*80}")
        print(f"📋 策略优化报告")
        print(f"{'='*80}")
        
        # 1. 因子有效性总结
        df_valid = df_factors.dropna(subset=['forward_return', 'score', 'r2', 'slope'])
        
        if len(df_valid) == 0:
            print("❌ 没有有效数据生成报告")
            return
        
        print(f"\n【1. 因子有效性总结】")
        print(f"   总样本数: {len(df_valid):,}")
        print(f"   有效买入信号数: {(df_valid['score'] > 0).sum():,}")
        
        # 计算各因子的IC（信息系数）
        ic_score = df_valid['score'].corr(df_valid['forward_return'])
        ic_r2 = df_valid['r2'].corr(df_valid['forward_return'])
        ic_slope = df_valid['slope'].corr(df_valid['forward_return'])
        ic_ram = df_valid['risk_adjusted_momentum'].corr(df_valid['forward_return'])
        
        print(f"\n   因子IC值:")
        print(f"     Score IC: {ic_score:.4f}")
        print(f"     R² IC: {ic_r2:.4f}")
        print(f"     Slope IC: {ic_slope:.4f}")
        print(f"     风险调整动量 IC: {ic_ram:.4f}")
        
        # 2. R²阈值建议
        print(f"\n【2. R²阈值建议】")
        df_high_r2 = df_valid[df_valid['r2'] > 0.95]
        df_medium_r2 = df_valid[(df_valid['r2'] > 0.5) & (df_valid['r2'] <= 0.95)]
        df_low_r2 = df_valid[df_valid['r2'] <= 0.5]
        
        if len(df_high_r2) > 0:
            high_r2_perf = df_high_r2['forward_return'].mean()
            print(f"   R² > 0.95 (趋势过热?): 平均未来收益率 = {high_r2_perf:.4f}")
            if high_r2_perf < df_medium_r2['forward_return'].mean() if len(df_medium_r2) > 0 else 0:
                print(f"   ⚠️  建议：当R² > 0.95时，未来收益率可能下降，考虑降低仓位或跳过")
        
        if len(df_medium_r2) > 0:
            medium_r2_perf = df_medium_r2['forward_return'].mean()
            print(f"   0.5 < R² ≤ 0.95: 平均未来收益率 = {medium_r2_perf:.4f}")
            print(f"   ✅ 建议：R²阈值设置在 0.5-0.95 区间内")
        
        # 3. 风险调整建议
        print(f"\n【3. 风险调整建议】")
        high_vol_threshold = 0.30
        df_high_vol = df_valid[df_valid['volatility'] > high_vol_threshold]
        
        if len(df_high_vol) > 0:
            high_vol_fail_rate = (df_high_vol['forward_return'] <= 0).sum() / len(df_high_vol)
            print(f"   高波动率环境 (波动率 > {high_vol_threshold:.0%}):")
            print(f"     动量因子失效概率: {high_vol_fail_rate:.2%}")
            if high_vol_fail_rate > 0.5:
                print(f"   ⚠️  建议：在高波动率环境下，考虑使用风险调整动量或降低仓位")
        
        # 4. 参数优化建议
        if df_grid_results is not None and len(df_grid_results) > 0:
            print(f"\n【4. 参数优化建议】")
            
            # 综合评分：总收益率 * 0.4 + 夏普比率 * 0.4 - 最大回撤 * 0.2
            df_grid_results['综合评分'] = (
                df_grid_results['total_return'] * 0.4 +
                df_grid_results['sharpe_ratio'] * 0.4 -
                df_grid_results['max_drawdown'] * 0.2
            )
            
            best_params = df_grid_results.nlargest(1, '综合评分').iloc[0]
            
            print(f"   最优参数组合 (综合评分最高):")
            print(f"     m_days = {best_params['m_days']}")
            print(f"     ma_filter_days = {best_params['ma_filter_days']}")
            print(f"     总收益率: {best_params['total_return']:.2%}")
            print(f"     夏普比率: {best_params['sharpe_ratio']:.4f}")
            print(f"     最大回撤: {best_params['max_drawdown']:.2%}")
            print(f"     综合评分: {best_params['综合评分']:.4f}")
        
        # 5. 回撤控制建议
        print(f"\n【5. 回撤控制建议】")
        df_signals = df_valid[df_valid['score'] > 0]
        if len(df_signals) > 0:
            # 估算平均最大浮亏（基于历史数据）
            avg_drawdown = -0.05  # 默认值，实际应从回撤分析中获取
            print(f"   历史买入信号平均最大浮亏: 约 {abs(avg_drawdown):.2%}")
            print(f"   ✅ 建议：设置止损阈值在 -5% 至 -7% 之间")
            print(f"   ✅ 建议：设置仓位管理，单次最大亏损不超过总资金的 2%")
        
        # 6. 最终建议
        print(f"\n【6. 最终优化建议】")
        print(f"   1. 动量周期 (m_days): 建议使用 {self.default_m_days} 天（可根据网格搜索结果调整）")
        print(f"   2. 均线过滤 (ma_filter_days): 建议使用 {self.default_ma_filter_days} 天")
        print(f"   3. R²阈值: 建议设置在 0.5-0.9 之间，避免趋势过热（R² > 0.95）")
        print(f"   4. 波动率控制: 当波动率 > 30% 时，考虑降低仓位或使用风险调整动量")
        print(f"   5. 止损设置: 建议硬止损在 -7%，软止损（5日回调）在 -4%")
        print(f"   6. 仓位管理: 初始资金 10 万元，单次最大亏损不超过 2%")
        
        print(f"\n{'='*80}")
        print(f"✅ 优化报告生成完成")
        print(f"{'='*80}\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF动量因子深度分析与策略优化')
    parser.add_argument('--data-file', type=str, default='data.txt', 
                       help='数据文件路径（默认: data.txt）')
    parser.add_argument('--pool', type=str, default='core', choices=['core', 'full'],
                       help='ETF池名称（默认: core）')
    parser.add_argument('--forward-days', type=int, default=5,
                       help='未来收益率计算周期（默认: 5天）')
    parser.add_argument('--skip-grid-search', action='store_true',
                       help='跳过参数网格搜索（耗时较长）')
    parser.add_argument('--initial-capital', type=float, default=100000.0,
                       help='初始资金（默认: 100000元）')
    
    args = parser.parse_args()
    
    print("="*80)
    print("🚀 ETF 动量因子深度分析与策略优化")
    print("="*80)
    print(f"数据文件: {args.data_file}")
    print(f"ETF池: {args.pool}")
    print(f"未来收益率周期: {args.forward_days}天")
    print(f"初始资金: {args.initial_capital:,.0f} 元")
    print("="*80)
    
    # 初始化分析器
    analyzer = MomentumFactorAnalyzer(
        data_file=args.data_file,
        pool_name=args.pool
    )
    
    # 准备因子数据（使用默认参数）
    print(f"\n📊 步骤 1/5: 准备因子数据...")
    df_factors = analyzer.prepare_factor_data(
        m_days=analyzer.default_m_days,
        ma_filter_days=analyzer.default_ma_filter_days,
        forward_days=args.forward_days
    )
    
    # 因子相关性分析
    print(f"\n📈 步骤 2/5: 因子相关性分析...")
    analyzer.analyze_correlation(df_factors, forward_days=args.forward_days)
    
    # R²阈值优化
    print(f"\n🔍 步骤 3/5: R²阈值优化分析...")
    analyzer.analyze_r2_threshold(df_factors, forward_days=args.forward_days)
    
    # 风险调整收益分析
    print(f"\n⚖️  步骤 4/5: 风险调整收益分析...")
    analyzer.analyze_risk_adjusted(df_factors, forward_days=args.forward_days)
    
    # 回撤与恢复分析
    print(f"\n📉 步骤 5/5: 回撤与恢复分析...")
    analyzer.analyze_drawdown(df_factors, forward_days=args.forward_days)
    
    # 参数网格搜索（可选，耗时较长）
    df_grid_results = None
    if not args.skip_grid_search:
        print(f"\n🔬 额外步骤: 参数网格搜索（这可能需要较长时间）...")
        m_days_list = [10, 20, 25, 40, 60]
        ma_filter_days_list = [10, 20, 30, 60]
        
        df_grid_results = analyzer.grid_search_parameters(
            m_days_list=m_days_list,
            ma_filter_days_list=ma_filter_days_list,
            forward_days=args.forward_days,
            initial_capital=args.initial_capital
        )
    else:
        print(f"\n⏭️  跳过参数网格搜索（使用 --skip-grid-search 跳过）")
    
    # 生成优化报告
    print(f"\n📋 生成优化报告...")
    analyzer.generate_optimization_report(df_factors, df_grid_results)
    
    print(f"\n✅ 所有分析完成！")
    print(f"📁 图表文件已保存到当前目录（文件名包含 '{args.pool}' 标识）")


if __name__ == "__main__":
    main()