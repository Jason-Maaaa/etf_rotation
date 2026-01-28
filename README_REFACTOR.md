# 量化交易框架 - 模块化重构说明

## 📁 目录结构

```
nope/
├── data_loader.py      # 数据加载模块（已优化）
├── indicators.py       # 技术指标计算模块（已存在）
├── backtester.py       # 回测引擎模块（新建）
├── strategy.py         # 策略模块（新建）
├── visualizer.py       # 可视化模块（新建）
├── main.py             # 框架入口（新建）
├── etf_config.py       # ETF池配置（已存在）
├── log.txt             # 历史数据文件
└── README_REFACTOR.md  # 本文档
```

## 🎯 模块说明

### 1. data_loader.py
**功能**：负责解析 `log.txt`，将其转换为 Pandas DataFrame

**关键特性**：
- 支持解析开盘价、10:30价格、14:30价格、14:50价格、收盘价
- 提供按ETF代码、日期范围查询数据的方法
- 支持获取指定时间点的价格（核心功能）

**主要方法**：
- `parse_log_file()`: 解析整个日志文件
- `get_etf_data()`: 获取指定ETF的历史数据
- `get_price_at_time()`: 获取指定日期和时间点的价格

### 2. indicators.py
**功能**：封装技术指标计算

**关键特性**：
- 移动平均线（MA）
- 动量计算（基于线性回归）
- 年化波动率
- RSI指标
- ETF综合得分计算

**主要方法**：
- `ma()`: 计算移动平均
- `calculate_momentum()`: 计算动量得分
- `get_annualized_vol()`: 计算年化波动率
- `calculate_etf_score()`: 计算ETF综合得分

### 3. backtester.py
**功能**：完整的回测引擎

**关键特性**：
- 支持手续费计算（可配置费率）
- 支持滑点模拟
- 自动计算净值曲线
- 计算最大回撤、夏普比率等关键指标
- 记录所有交易明细

**主要类**：
- `Backtester`: 回测引擎主类
- `Order`: 订单数据类
- `Position`: 持仓数据类

**主要方法**：
- `execute_order()`: 执行订单
- `update_equity()`: 更新净值
- `get_statistics()`: 获取统计指标

### 4. strategy.py
**功能**：策略定义和实现

**关键特性**：
- 策略基类 `BaseStrategy`（可扩展）
- ETF轮动策略 `ETFRotationStrategy`（基于原有逻辑）
- 支持10:30和14:50时间点价格处理

**主要类**：
- `BaseStrategy`: 策略基类（抽象类）
- `ETFRotationStrategy`: ETF轮动策略实现

**策略逻辑**：
- 动量计算（25天周期）
- 均线过滤（20日均线）
- 市场情绪风控
- 硬止损（-7%）
- 波动率控仓

### 5. visualizer.py
**功能**：数据可视化

**关键特性**：
- 净值曲线绘制
- 回撤曲线绘制
- 买卖点标注
- 统计指标可视化
- 综合分析图表

**主要方法**：
- `plot_equity_curve()`: 绘制净值曲线
- `plot_drawdown()`: 绘制回撤曲线
- `plot_equity_with_trades()`: 净值曲线+交易点
- `plot_statistics()`: 统计指标图表
- `plot_comprehensive()`: 综合分析图表

### 6. main.py
**功能**：框架入口，串联整个流程

**主要功能**：
- 命令行参数解析
- 数据加载
- 策略执行
- 回测运行
- 结果保存
- 可视化展示

## 🚀 使用方法

### 基本用法

```bash
# 运行回测
python main.py --start-date 2020-01-01 --end-date 2023-12-31 --pool core

# 指定初始资金和手续费
python main.py \
    --start-date 2020-01-01 \
    --end-date 2023-12-31 \
    --pool core \
    --capital 1000000 \
    --commission 0.0003 \
    --slippage 0.001

# 保存结果到指定目录
python main.py \
    --start-date 2020-01-01 \
    --end-date 2023-12-31 \
    --pool core \
    --output-dir ./backtest_results

# 不绘制图表（仅计算）
python main.py \
    --start-date 2020-01-01 \
    --end-date 2023-12-31 \
    --pool core \
    --no-plot
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--start-date` | 回测开始日期（必填） | - |
| `--end-date` | 回测结束日期（必填） | - |
| `--pool` | ETF池名称（core/full） | core |
| `--capital` | 初始资金 | 1000000 |
| `--commission` | 手续费率 | 0.0003（万三） |
| `--min-commission` | 最低手续费 | 5.0 |
| `--slippage` | 滑点 | 0.0 |
| `--output-dir` | 输出目录 | None |
| `--no-plot` | 不绘制图表 | False |

### 编程方式使用

```python
from main import run_backtest

# 运行回测
backtester, statistics = run_backtest(
    start_date="2020-01-01",
    end_date="2023-12-31",
    pool_name="core",
    initial_capital=1000000.0,
    output_dir="./results",
    plot=True
)

# 获取净值曲线
equity_df = backtester.get_equity_dataframe()

# 获取交易记录
trades_df = backtester.get_trades_dataframe()

# 查看统计指标
print(statistics)
```

## 📊 输出结果

运行回测后，如果指定了 `--output-dir`，会在该目录下生成：

1. **equity_curve.csv**: 净值曲线数据
2. **trades.csv**: 交易记录明细
3. **statistics.json**: 统计指标（JSON格式）
4. **backtest_comprehensive.png**: 综合分析图表
5. **equity_with_trades.png**: 净值曲线与交易点图表

## 🔧 扩展开发

### 添加新策略

1. 继承 `BaseStrategy` 类
2. 实现 `generate_signal()` 方法
3. 在 `main.py` 中使用新策略

示例：

```python
from strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def generate_signal(self, date: str, current_position: Optional[Dict] = None) -> Dict:
        # 实现你的策略逻辑
        return {
            'action': 'buy',  # 或 'sell', 'hold'
            'code': '159915',
            'name': '创业板ETF',
            'price': 3.5,
            'quantity': 1000,
            'reason': '我的策略信号'
        }
```

### 添加新指标

在 `indicators.py` 中添加新的静态方法：

```python
@staticmethod
def my_indicator(prices: np.ndarray, period: int) -> float:
    # 实现你的指标计算
    return result
```

## 📝 注意事项

1. **数据格式**：确保 `log.txt` 格式正确，包含必要的价格字段
2. **时间点**：策略使用14:50价格作为买入/卖出价格，确保数据中有该字段
3. **ETF池配置**：在 `etf_config.py` 中配置ETF池
4. **内存使用**：大量数据回测时注意内存占用

## 🐛 常见问题

### Q: 回测结果中没有交易？
A: 检查策略信号生成逻辑，确保有符合条件的ETF

### Q: 图表中文显示乱码？
A: 确保系统安装了中文字体，或修改 `visualizer.py` 中的字体设置

### Q: 数据加载失败？
A: 检查 `log.txt` 文件路径和格式是否正确

## 📈 性能优化建议

1. 对于长期回测，考虑使用数据缓存
2. 可以并行计算多个ETF的得分
3. 使用向量化操作替代循环

## 🔄 与原代码的对应关系

| 原代码（etf_rotation.py） | 新模块 |
|-------------------------|--------|
| `get_realtime_data()` | `data_loader.py` |
| `calculate_momentum()` | `indicators.py` |
| `run_strategy()` | `strategy.py` + `backtester.py` |
| 持仓管理函数 | `backtester.py` |
| 日志打印 | `visualizer.py` |

## 📚 下一步计划

- [ ] 添加更多技术指标
- [ ] 支持多策略组合
- [ ] 实时交易接口
- [ ] 风险指标增强
- [ ] 参数优化功能
