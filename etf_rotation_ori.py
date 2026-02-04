import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import linregress
import time
import argparse
import sys
import json
import os
import random
from pathlib import Path
from etf_config import POOL_DICT
import requests

def fetch_em_hist(symbol, name, start_date=None, end_date=None, adjust="qfq"):
    """
    【东财源-历史数据】使用 ak.fund_etf_hist_em 获取 ETF 复权数据
    
    Args:
        symbol: ETF代码（6位数字，如 '159915'）
        name: ETF名称（用于日志）
        start_date: 开始日期字符串，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date: 结束日期字符串，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        adjust: 复权类型，'qfq' 表示前复权（默认）
    """
    try:
        # 东财接口需要完整的ETF代码（带市场前缀）
        # 自动识别市场前缀：1/0/3开头为深市，其他为沪市
        if symbol.startswith(('1', '0', '3')):
            full_symbol = f"sz{symbol}"  # 深市
        else:
            full_symbol = f"sh{symbol}"  # 沪市
        
        # 使用东财ETF历史数据接口
        # 注意：akshare 的 fund_etf_hist_em 接口参数可能因版本而异
        # 如果接口不支持 start_date/end_date，则获取全量数据后本地筛选
        try:
            # 尝试使用日期参数（如果接口支持）
            if start_date or end_date:
                start_str = start_date.replace("-", "") if start_date and "-" in start_date else (start_date if start_date else "20000101")
                end_str = end_date.replace("-", "") if end_date and "-" in end_date else (end_date if end_date else datetime.now().strftime("%Y%m%d"))
                df = ak.fund_etf_hist_em(
                    symbol=full_symbol, 
                    period="daily", 
                    start_date=start_str,
                    end_date=end_str,
                    adjust=adjust
                )
            else:
                # 如果没有指定日期，获取全量数据
                df = ak.fund_etf_hist_em(
                    symbol=full_symbol, 
                    period="daily", 
                    adjust=adjust
                )
        except TypeError:
            # 如果接口不支持日期参数，获取全量数据后本地筛选
            df = ak.fund_etf_hist_em(
                symbol=full_symbol, 
                period="daily", 
                adjust=adjust
            )
        
        if df is not None and not df.empty:
            # 统一列名以兼容脚本后续的 hist['收盘'] 等逻辑
            # 东财返回的列名可能已经是中文，检查并统一
            rename_dict = {}
            if '日期' in df.columns:
                pass  # 已经是中文列名
            elif 'date' in df.columns:
                rename_dict['date'] = '日期'
            
            if '开盘' not in df.columns and 'open' in df.columns:
                rename_dict['open'] = '开盘'
            if '收盘' not in df.columns and 'close' in df.columns:
                rename_dict['close'] = '收盘'
            if '最高' not in df.columns and 'high' in df.columns:
                rename_dict['high'] = '最高'
            if '最低' not in df.columns and 'low' in df.columns:
                rename_dict['low'] = '最低'
            if '成交量' not in df.columns and 'volume' in df.columns:
                rename_dict['volume'] = '成交量'
            if '成交额' not in df.columns and 'amount' in df.columns:
                rename_dict['amount'] = '成交额'
            
            if rename_dict:
                df.rename(columns=rename_dict, inplace=True)
            
            # 确保日期列存在并转换为datetime
            if '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'])
            else:
                print(f"⚠️ {name}({symbol}) 东财数据缺少日期列")
                return pd.DataFrame()
            
            # 在内存中进行日期筛选
            # 统一日期格式处理：支持 'YYYY-MM-DD' 和 'YYYYMMDD' 两种格式
            if start_date:
                # 如果是 YYYYMMDD 格式，转换为 YYYY-MM-DD
                if len(start_date) == 8 and '-' not in start_date:
                    start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
                df = df[df['日期'] >= pd.to_datetime(start_date)]
            if end_date:
                # 如果是 YYYYMMDD 格式，转换为 YYYY-MM-DD
                if len(end_date) == 8 and '-' not in end_date:
                    end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
                df = df[df['日期'] <= pd.to_datetime(end_date)]
            
            return df.sort_values('日期').reset_index(drop=True)
    except Exception as e:
        print(f"❌ {name}({symbol}) 东财历史接口报错: {e}")
    
    return pd.DataFrame()


def fetch_with_retry(symbol, name, max_retries=1, period="daily", adjust="qfq", start_date=None, end_date=None, source="tx"):
    """
    统一历史数据入口，根据 source 参数切换数据源
    - source="tx": 使用腾讯接口（默认）
    - source="em": 使用东财接口
    """
    if source == "em":
        # 使用东财接口
        for i in range(max_retries):
            try:
                # 随机延迟
                time.sleep(random.uniform(1, 2))
                df = fetch_em_hist(symbol, name, start_date=start_date, end_date=end_date, adjust=adjust)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                if i < max_retries - 1:
                    print(f"🔄 {name}({symbol}) 东财历史接口受阻，重试 {i+1}... 错误: {str(e)[:50]}")
        return pd.DataFrame()
    
    # 默认使用腾讯接口（原有逻辑）
    # 自动识别市场前缀
    full_symbol = f"sz{symbol}" if symbol.startswith(('1', '0', '3')) else f"sh{symbol}"
    
    for i in range(max_retries):
        try:
            # 随机延迟，腾讯接口虽然宽容，但也建议保留 2-4 秒间隔
            time.sleep(random.uniform(2, 4))
            
            # 使用腾讯全量历史接口
            df = ak.stock_zh_a_hist_tx(symbol=full_symbol)
            
            if df is not None and not df.empty:
                # 统一列名以兼容你脚本后续的 hist['收盘'] 等逻辑
                rename_dict = {
                    'date': '日期',
                    'open': '开盘',
                    'close': '收盘',
                    'high': '最高',
                    'low': '最低',
                    'amount': '成交额'
                }
                # 如果存在 volume 字段，也重命名为 成交量
                if 'volume' in df.columns:
                    rename_dict['volume'] = '成交量'
                df.rename(columns=rename_dict, inplace=True)
                
                df['日期'] = pd.to_datetime(df['日期'])
                
                # 在内存中进行日期筛选
                if start_date:
                    df = df[df['日期'] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df['日期'] <= pd.to_datetime(end_date)]
                
                return df.sort_values('日期').reset_index(drop=True)
        except Exception as e:
            if i < max_retries - 1:
                print(f"🔄 {name}({symbol}) 腾讯历史接口受阻，重试 {i+1}... 错误: {str(e)[:50]}")
    
    return pd.DataFrame()


def fetch_em_spot():
    """
    【东财实时源】使用 ak.stock_zh_a_spot_em 获取全市场快照并进行代码过滤
    """
    try:
        # 东财实时快照包含全量 A 股和 ETF
        df_spot_all = ak.stock_zh_a_spot_em()
        if df_spot_all is not None and not df_spot_all.empty:
            # 统一字段名映射（东财返回的列名可能是中文或英文，需要统一）
            # 检查列名并统一为中文
            column_mapping = {}
            if '代码' in df_spot_all.columns:
                pass  # 已经是中文
            elif 'code' in df_spot_all.columns:
                column_mapping['code'] = '代码'
            
            if '名称' not in df_spot_all.columns and 'name' in df_spot_all.columns:
                column_mapping['name'] = '名称'
            if '最新价' not in df_spot_all.columns and '最新' in df_spot_all.columns:
                column_mapping['最新'] = '最新价'
            elif '最新价' not in df_spot_all.columns and 'current' in df_spot_all.columns:
                column_mapping['current'] = '最新价'
            if '成交量' not in df_spot_all.columns and 'volume' in df_spot_all.columns:
                column_mapping['volume'] = '成交量'
            
            if column_mapping:
                df_spot_all.rename(columns=column_mapping, inplace=True)
            
            # 提取需要的列：代码、名称、最新价、成交量
            required_cols = ['代码', '名称', '最新价']
            if '成交量' in df_spot_all.columns:
                required_cols.append('成交量')
            
            # 检查必需的列是否存在
            missing_cols = [col for col in required_cols if col not in df_spot_all.columns]
            if missing_cols:
                print(f"⚠️ 东财实时数据缺少列: {missing_cols}")
                return None, None
            
            # 筛选出需要的列
            df_spot = df_spot_all[required_cols].copy()
            
            # 确保代码列为字符串类型，并统一格式（去除前缀，只保留6位代码）
            if '代码' in df_spot.columns:
                df_spot['代码'] = df_spot['代码'].astype(str).str.replace('sz', '').str.replace('sh', '').str.zfill(6)
            
            # 确保最新价为数值类型
            if '最新价' in df_spot.columns:
                df_spot['最新价'] = pd.to_numeric(df_spot['最新价'], errors='coerce')
            
            # 确保成交量为数值类型（如果存在）
            if '成交量' in df_spot.columns:
                df_spot['成交量'] = pd.to_numeric(df_spot['成交量'], errors='coerce')
            
            fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return df_spot, fetch_time
    except Exception as e:
        print(f"❌ 东财实时接口报错: {e}")
    
    return None, None


def fetch_spot_with_retry(max_retries=1, source="tx"):
    """
    统一实时行情入口，根据 source 参数切换数据源
    - source="tx": 使用腾讯接口（默认）
    - source="em": 使用东财接口
    """
    if source == "em":
        # 使用东财接口
        for i in range(max_retries):
            try:
                # 随机延迟
                time.sleep(random.uniform(1, 2))
                df_spot, fetch_time = fetch_em_spot()
                if df_spot is not None and not df_spot.empty:
                    return df_spot, fetch_time
            except Exception as e:
                if i < max_retries - 1:
                    print(f"🔄 东财实时接口受阻，重试 {i+1}/{max_retries}... 错误: {e}")
        return None, None
    
    # 默认使用腾讯接口（原有逻辑）
    # 1. 汇总池子里所有需要监控的代码
    symbols = []
    for pool in POOL_DICT.values():
        for code in pool.keys():
            prefix = "sz" if code.startswith(('1', '0', '3')) else "sh"
            symbols.append(f"{prefix}{code}")
    
    # 2. 构造腾讯批量查询 URL (这正是你 test.py 成功的拿数据方式)
    url = f"http://qt.gtimg.cn/q={','.join(list(set(symbols)))}"
    
    for i in range(max_retries):
        try:
            # 模拟人类随机停顿
            time.sleep(random.uniform(1.5, 3.0))
            
            # 直接使用 requests 发送请求
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                # 解析腾讯原始文本数据
                lines = resp.text.split(';')
                data_list = []
                for line in lines:
                    parts = line.split('~')
                    if len(parts) > 3:
                        spot_item = {
                            '代码': parts[2],      # 对应 159915 等 6 位代码
                            '名称': parts[1],      # 对应 创业板ETF 等
                            '最新价': float(parts[3]) # 对应当前现价
                        }
                        # 添加成交量字段（parts[6] 是成交量-手，需要转换为股）
                        if len(parts) > 6 and parts[6]:
                            try:
                                volume_shou = float(parts[6])  # 成交量（手）
                                volume_gu = volume_shou * 100  # 成交量（股）
                                spot_item['成交量'] = volume_gu
                            except (ValueError, TypeError):
                                pass  # 如果转换失败，跳过成交量字段
                        data_list.append(spot_item)
                
                df_spot = pd.DataFrame(data_list)
                fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return df_spot, fetch_time
            else:
                print(f"🔄 实时行情返回状态码: {resp.status_code}，正在重试 {i+1}...")
        except Exception as e:
            print(f"🔄 实时行情请求受阻，重试 {i+1}/{max_retries}... 错误: {e}")
            
    return None, None
HOLDING_FILE = Path(__file__).parent / "etf_holding.json"

# 初始持仓：2026年1月15日买入31900份创业板ETF
INITIAL_HOLDING = {
    "code": "159915",
    "name": "创业板ETF",
    "quantity": 31900,
    "entry_price": None,  # 将在首次运行时从历史数据获取
    "entry_date": "2026-01-15",
    "entry_time": "14:51"
}

STRATEGY_CONF = {
    "m_days": 25,                # 动量计算周期
    "ma_filter_days": 20,        # 均线过滤周期
    "sentiment_threshold": 0.15, # 情绪风控阈值
    "stock_sum": 1,              # 计划持仓数
    "short_ret_limit": -0.04,    # 5日剧烈回调阈值
    "stop_loss_threshold": -0.07, # 硬止损阈值（-7%）
    "volatility_threshold": 0.30, # 波动率控仓阈值（30%）
    "sell_time": "14:50",        # 默认卖出时间
    "buy_time": "14:51",         # 默认买入时间
    "use_weighted": True         # 是否使用加权回归（True=聚宽逻辑，False=普通回归）
}

# ======================== 持仓管理 ========================

def load_holding():
    """加载持仓记录"""
    if HOLDING_FILE.exists():
        try:
            with open(HOLDING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"⚠️ 加载持仓记录失败: {e}，将重新初始化")
            return None
    return None

def save_holding(holding_data):
    """保存持仓记录"""
    try:
        with open(HOLDING_FILE, 'w', encoding='utf-8') as f:
            json.dump(holding_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 保存持仓记录失败: {e}")

def initialize_holding():
    """初始化持仓记录"""
    holding_data = {
        "current_holding": {
            "code": INITIAL_HOLDING["code"],
            "name": INITIAL_HOLDING["name"],
            "quantity": INITIAL_HOLDING["quantity"],
            "entry_price": INITIAL_HOLDING["entry_price"],
            "entry_date": INITIAL_HOLDING["entry_date"],
            "entry_time": INITIAL_HOLDING["entry_time"]
        },
        "trade_history": [],
        "daily_log": [],  # 每日盈亏记录
        "last_update_date": None
    }
    return holding_data

def record_daily_status(holding_data, current_price=0.0, score=None, r2=None, annualized_return=None, pool_scores=None):
    """记录每日持仓状态（支持盘中多次运行更新）"""
    today = datetime.now().strftime("%Y-%m-%d")
    current_holding = holding_data["current_holding"]
    
    # 基础信息
    code = current_holding.get("code")
    name = current_holding.get("name")
    quantity = current_holding.get("quantity", 0)
    entry_price = current_holding.get("entry_price")
    
    # 计算盈亏
    market_value = 0.0
    unrealized_pnl = 0.0
    pnl_ratio = 0.0
    
    if code and quantity > 0:
        market_value = quantity * current_price
        if entry_price:
            unrealized_pnl = (current_price - entry_price) * quantity
            pnl_ratio = (current_price / entry_price) - 1
    
    # 格式化pool_scores：将得分转换为字典格式 {code: {score, r2, annualized_return}}
    formatted_pool_scores = None
    if pool_scores is not None:
        if isinstance(pool_scores, dict):
            # 如果已经是字典格式，检查是否是完整信息格式
            formatted_pool_scores = {}
            for k, v in pool_scores.items():
                if isinstance(v, dict):
                    # 已经是完整格式 {score, r2, annualized_return}
                    formatted_pool_scores[k] = {
                        "score": round(v.get("score", v.get("得分", 0)), 4) if v.get("score") is not None or v.get("得分") is not None else None,
                        "r2": round(v.get("r2", v.get("R2", 0)), 4) if v.get("r2") is not None or v.get("R2") is not None else None,
                        "annualized_return": round(v.get("annualized_return", v.get("年化收益率", 0)), 4) if v.get("annualized_return") is not None or v.get("年化收益率") is not None else None
                    }
                else:
                    # 旧格式，只有 score
                    formatted_pool_scores[k] = {
                        "score": round(v, 4) if v is not None else None,
                        "r2": None,
                        "annualized_return": None
                    }
        elif isinstance(pool_scores, list):
            # 如果是results列表格式
            formatted_pool_scores = {}
            for item in pool_scores:
                code = item["代码"]
                formatted_pool_scores[code] = {
                    "score": round(item["得分"], 4) if item.get("得分") is not None else None,
                    "r2": round(item.get("r2", item.get("R2", 0)), 4) if item.get("r2") is not None or item.get("R2") is not None else None,
                    "annualized_return": round(item.get("年化收益率", 0), 4) if item.get("年化收益率") is not None else None
                }
            
    record = {
        "date": today,
        "time": datetime.now().strftime("%H:%M:%S"),
        "code": code,
        "name": name,
        "quantity": quantity,
        "price": current_price,
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "pnl_ratio": round(pnl_ratio, 4),
        "score": round(score, 4) if score is not None else None,
        "r2": round(r2, 4) if r2 is not None else None,
        "annualized_return": round(annualized_return, 4) if annualized_return is not None else None,
        "pool_scores": formatted_pool_scores  # 池子中所有ETF的得分
    }
    
    # 检查是否已有今日记录
    daily_log = holding_data.get("daily_log", [])
    updated = False
    for i, item in enumerate(daily_log):
        if item["date"] == today:
            daily_log[i] = record
            updated = True
            break
            
    if not updated:
        daily_log.append(record)
        
    holding_data["daily_log"] = daily_log
    return holding_data

def calculate_etf_score_at_date(symbol, target_date, source="tx", pool_name="core"):
    """
    计算指定ETF在指定日期的得分
    
    Args:
        symbol: 股票代码
        target_date: 目标日期（datetime对象）
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
        pool_name: ETF池名称，'full'、'core' 或 'custom'，用于确定跌幅阈值
    """
    try:
        # 获取ETF名称（用于日志）
        name = symbol  # 如果没有名称映射，使用代码
        # 获取历史数据（获取足够多的数据用于计算）
        hist = fetch_with_retry(symbol, name, max_retries=5, source=source)
        if hist.empty:
            return None
        
        hist['日期'] = pd.to_datetime(hist['日期'])
        hist = hist.sort_values('日期')
        
        # 获取到目标日期为止的数据
        hist_up_to_date = hist[hist['日期'] <= pd.Timestamp(target_date)]
        if len(hist_up_to_date) < STRATEGY_CONF["m_days"]:
            return None
        
        # 获取目标日期的收盘价
        target_date_data = hist_up_to_date[hist_up_to_date['日期'].dt.date == target_date.date()]
        if target_date_data.empty:
            return None
        
        close_price = target_date_data.iloc[0]['收盘']
        prices = hist_up_to_date['收盘'].values
        
        # 需要至少25天数据来计算动量，至少20天来计算MA20
        if len(prices) < max(STRATEGY_CONF["m_days"], STRATEGY_CONF["ma_filter_days"], 5):
            return None
        
        # 风险过滤：近4日任意一天跌幅过大（根据pool参数设置不同阈值）
        if len(prices) >= 4:
            # 根据pool参数设置跌幅阈值
            if pool_name == "core":
                decline_threshold = 0.97  # 3%跌幅
            elif pool_name == "full":
                decline_threshold = 0.95  # 5%跌幅
            elif pool_name == "custom":
                decline_threshold = 0.95  # 自定义池使用5%跌幅
            else:
                decline_threshold = 0.95  # 默认3%
            
            # 检查过去4天内是否有任意一天跌幅超过阈值
            ratio1 = prices[-1] / prices[-2]  # 今天/昨天
            ratio2 = prices[-2] / prices[-3]  # 昨天/前天
            ratio3 = prices[-3] / prices[-4]  # 前天/大前天
            
            # 只要任意一天跌幅超过阈值就过滤
            if ratio1 < decline_threshold or ratio2 < decline_threshold or ratio3 < decline_threshold:
                return {
                    "score": None,
                    "r2": None,
                    "annualized_return": None,
                    "risk_filtered": True  # 标记为风险过滤
                }
        
        # 计算指标
        ma20 = np.mean(prices[-STRATEGY_CONF["ma_filter_days"]:])
        is_up = close_price > ma20
        
        # 计算得分
        score = 0
        r2 = 0
        annualized_return = 0
        if is_up:
            momentum_prices = prices[-STRATEGY_CONF["m_days"]:]
            # 传递加权配置参数
            use_weighted = STRATEGY_CONF.get("use_weighted", True)
            score, r2, annualized_return = calculate_momentum(momentum_prices, use_weighted=use_weighted)
        
        return {
            "score": round(score, 4),
            "r2": round(r2, 4),
            "annualized_return": round(annualized_return, 4)
        }
    except Exception as e:
        return None

def get_holding_at_date(trade_history, target_date_str):
    """根据trade_history推断指定日期的持仓信息
    返回: (code, name, quantity, entry_price, entry_date) 或 (None, None, 0, None, None)
    """
    if not trade_history:
        return None, None, 0, None, None
    
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    
    # 按日期和时间排序交易记录
    sorted_trades = sorted(trade_history, key=lambda x: (x["date"], x.get("time", "00:00")))
    
    current_code = None
    current_name = None
    current_quantity = 0
    current_entry_price = None
    current_entry_date = None
    
    for trade in sorted_trades:
        trade_date = datetime.strptime(trade["date"], "%Y-%m-%d").date()
        
        # 只处理目标日期之前的交易
        if trade_date > target_date:
            break
        
        if trade["action"] == "买入":
            current_code = trade["code"]
            current_name = trade["name"]
            current_quantity = trade["quantity"]
            current_entry_price = trade["price"]
            current_entry_date = trade["date"]
        elif trade["action"] == "卖出":
            if trade["code"] == current_code:
                # 卖出当前持仓
                current_code = None
                current_name = None
                current_quantity = 0
                current_entry_price = None
                current_entry_date = None
    
    return current_code, current_name, current_quantity, current_entry_price, current_entry_date

def backfill_daily_log(holding_data, pool_name="core", source="tx"):
    """
    补全缺失的历史每日记录
    
    Args:
        holding_data: 持仓数据字典
        pool_name: ETF池名称，'full'、'core' 或 'custom'
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
    """
    daily_log = holding_data.get("daily_log", [])
    current_holding = holding_data["current_holding"]
    trade_history = holding_data.get("trade_history", [])
    entry_date_str = current_holding.get("entry_date")
    
    if not entry_date_str:
        return holding_data

    # 获取ETF池
    if pool_name not in POOL_DICT:
        print(f"⚠️ 警告：未找到池子 '{pool_name}'，使用默认池子 'core'")
        pool_name = "core"
    etf_pool = POOL_DICT[pool_name]

    # 构建已存在日期的集合，用于快速查找
    existing_dates = {item["date"] for item in daily_log}
    
    # 确定补全的起始日期：从trade_history中最早的买入日期开始，如果没有则使用entry_date
    start_date_str = entry_date_str
    if trade_history:
        buy_trades = [t for t in trade_history if t["action"] == "买入"]
        if buy_trades:
            earliest_buy = min(buy_trades, key=lambda x: x["date"])
            start_date_str = earliest_buy["date"]
    
    entry_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    # 如果entry_date晚于昨天，无需补全
    if entry_date > yesterday:
        return holding_data
    
    # 计算需要补全的日期范围
    start_date = entry_date
    end_date = yesterday
    
    # 获取历史数据，用于判断哪些是交易日
    # 使用当前持仓的code来获取交易日历，如果当前没有持仓，使用trade_history中最后一个买入的code
    code = current_holding.get("code")
    if not code and trade_history:
        buy_trades = [t for t in trade_history if t["action"] == "买入"]
        if buy_trades:
            code = buy_trades[-1]["code"]  # 使用最后一个买入的code
    
    if not code:
        return holding_data
    
    try:
        # 获取包含区间的历史数据
        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")
        
        # 获取ETF名称（用于日志）
        name = current_holding.get("name", code)
        hist = fetch_with_retry(
            symbol=code, 
            name=name, 
            max_retries=5,
            start_date=start_date_str, 
            end_date=today.strftime("%Y%m%d"),
            source=source
        )
        if hist.empty:
            return holding_data
            
        hist['日期'] = pd.to_datetime(hist['日期'])
        hist = hist.sort_values('日期')
        # 获取交易日集合
        trading_dates = {row['日期'].date() for _, row in hist.iterrows()}
        
        # 检查是否有需要补全的日期（包括缺失日期和缺少字段的记录）
        need_backfill = False
        missing_dates = []
        incomplete_dates = []
        
        check_date = start_date
        while check_date <= end_date:
            check_str = check_date.strftime("%Y-%m-%d")
            check_date_obj = check_date.date()
            
            # 只检查交易日
            if check_date_obj not in trading_dates:
                check_date += timedelta(days=1)
                continue
            
            # 检查日期是否存在
            if check_str not in existing_dates:
                missing_dates.append(check_str)
                need_backfill = True
            else:
                # 检查已有记录是否缺少必要字段
                for item in daily_log:
                    if item["date"] == check_str:
                        if "pool_scores" not in item or item.get("pool_scores") is None:
                            incomplete_dates.append(check_str)
                            need_backfill = True
                        break
            
            check_date += timedelta(days=1)
        
        if not need_backfill:
            return holding_data
        
        # 打印补全信息
        if missing_dates:
            print(f"🔄 检测到历史记录缺失，正在补全日期: {', '.join(missing_dates)}")
        if incomplete_dates:
            print(f"🔄 检测到历史记录字段不完整，正在补全: {', '.join(incomplete_dates)}")
        print(f"   使用ETF池: 【{pool_name}】 (共 {len(etf_pool)} 只)")
        
        # 遍历区间内的每一天
        curr = start_date
        backfilled_count = 0
        updated_count = 0
        while curr <= end_date:
            curr_str = curr.strftime("%Y-%m-%d")
            curr_date_obj = curr.date()
            
            # 只处理交易日
            if curr_date_obj not in trading_dates:
                curr += timedelta(days=1)
                continue
            
            # 检查是否已存在记录
            existing_record = None
            record_index = None
            for i, item in enumerate(daily_log):
                if item["date"] == curr_str:
                    existing_record = item
                    record_index = i
                    break
            
            # 如果记录存在但缺少字段，需要更新
            if existing_record and ("pool_scores" not in existing_record or existing_record.get("pool_scores") is None):
                # 更新已有记录，补全缺失字段
                need_update = True
            elif existing_record:
                # 记录完整，跳过
                curr += timedelta(days=1)
                continue
            else:
                # 记录不存在，需要新建
                need_update = False
            
            # 查找当日数据（使用日期匹配，处理可能的时区问题）
            day_data = hist[hist['日期'].dt.date == curr_date_obj]
            
            if not day_data.empty:
                # 是交易日，生成或更新记录
                close_price = day_data.iloc[0]['收盘']
                
                # 计算当前持仓ETF在历史日期的得分
                score_result = calculate_etf_score_at_date(code, curr, source=source, pool_name=pool_name)
                score = score_result["score"] if score_result else None
                r2 = score_result["r2"] if score_result else None
                annualized_return = score_result["annualized_return"] if score_result else None
                
                # 计算池子中所有ETF在历史日期的得分、r2和年化收益率
                pool_scores = {}
                risk_filtered_count = 0
                print(f"   📊 计算 {curr_str} 池子中所有ETF得分...", end="")
                for symbol, name in etf_pool.items():
                    etf_score_result = calculate_etf_score_at_date(symbol, curr, source=source, pool_name=pool_name)
                    if etf_score_result:
                        if etf_score_result.get("risk_filtered"):
                            risk_filtered_count += 1
                        pool_scores[symbol] = {
                            "score": etf_score_result["score"],
                            "r2": etf_score_result["r2"],
                            "annualized_return": etf_score_result["annualized_return"],
                            "risk_filtered": etf_score_result.get("risk_filtered", False)
                        }
                    else:
                        pool_scores[symbol] = {
                            "score": None,
                            "r2": None,
                            "annualized_return": None,
                            "risk_filtered": False
                        }
                valid_count = len([s for s in pool_scores.values() if s.get('score') is not None])
                if risk_filtered_count > 0:
                    print(f" 完成 ({valid_count}/{len(etf_pool)} 个有效得分, ⚠️ {risk_filtered_count} 个风险过滤)")
                else:
                    print(f" 完成 ({valid_count}/{len(etf_pool)} 个有效得分)")
                
                # 根据trade_history推断该日期的持仓信息
                hist_code, hist_name, hist_quantity, hist_entry_price, hist_entry_date = get_holding_at_date(trade_history, curr_str)
                
                # 如果trade_history中没有找到，使用当前持仓（兼容旧数据）
                if hist_code is None:
                    hist_code = code
                    hist_name = current_holding.get("name")
                    hist_quantity = current_holding.get("quantity", 0)
                    hist_entry_price = current_holding.get("entry_price")
                    hist_entry_date = entry_date_str
                
                # 如果该日期没有持仓，跳过该日期
                if not hist_code or hist_quantity == 0:
                    curr += timedelta(days=1)
                    continue
                
                # 如果该日期持仓的ETF与当前持仓不同，需要重新计算该日期持仓ETF的得分
                if hist_code != code:
                    hist_score_result = calculate_etf_score_at_date(hist_code, curr, source=source, pool_name=pool_name)
                    score = hist_score_result["score"] if hist_score_result else None
                    r2 = hist_score_result["r2"] if hist_score_result else None
                    annualized_return = hist_score_result["annualized_return"] if hist_score_result else None
                
                # 计算市值和盈亏
                market_value = hist_quantity * close_price
                unrealized_pnl = 0.0
                pnl_ratio = 0.0
                if hist_entry_price:
                    unrealized_pnl = (close_price - hist_entry_price) * hist_quantity
                    pnl_ratio = (close_price / hist_entry_price) - 1
                
                record = {
                    "date": curr_str,
                    "time": STRATEGY_CONF["buy_time"] + ":00",  # 使用买入时间
                    "code": hist_code,
                    "name": hist_name,
                    "quantity": hist_quantity,
                    "price": float(close_price),
                    "market_value": round(market_value, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "pnl_ratio": round(pnl_ratio, 4),
                    "score": score,
                    "r2": r2,
                    "annualized_return": annualized_return,
                    "pool_scores": pool_scores  # 池子中所有ETF的得分
                }
                
                if need_update and record_index is not None:
                    # 更新已有记录，保留原有字段，只更新缺失的字段
                    existing_record.update({
                        "pool_scores": pool_scores,
                        "score": score if existing_record.get("score") is None else existing_record.get("score")
                    })
                    daily_log[record_index] = existing_record
                    updated_count += 1
                    score_info = f" | 得分: {score:.4f}" if score is not None else " | 得分: N/A"
                    print(f"   🔄 更新记录: {curr_str} 收盘价: {close_price:.3f} | 市值: {market_value:.2f} | 盈亏: {pnl_ratio:.2%}{score_info}")
                else:
                    # 新建记录
                    daily_log.append(record)
                    existing_dates.add(curr_str)  # 更新已存在日期集合
                    backfilled_count += 1
                    score_info = f" | 得分: {score:.4f}" if score is not None else " | 得分: N/A"
                    print(f"   ➕ 补全记录: {curr_str} 收盘价: {close_price:.3f} | 市值: {market_value:.2f} | 盈亏: {pnl_ratio:.2%}{score_info}")
            
            curr += timedelta(days=1)
        
        # 按日期排序daily_log，确保顺序正确
        daily_log.sort(key=lambda x: x["date"])
        holding_data["daily_log"] = daily_log
        save_holding(holding_data) # 及时保存
        
        if backfilled_count > 0 or updated_count > 0:
            msg_parts = []
            if backfilled_count > 0:
                msg_parts.append(f"补全 {backfilled_count} 条")
            if updated_count > 0:
                msg_parts.append(f"更新 {updated_count} 条")
            print(f"✅ 成功{'、'.join(msg_parts)}历史记录")
        
    except Exception as e:
        print(f"⚠️ 补全历史记录失败: {e}")
        import traceback
        traceback.print_exc()
        
    return holding_data

def get_entry_price_from_history(symbol, entry_date, source="tx"):
    """
    从历史数据获取指定日期的买入价格
    
    Args:
        symbol: 股票代码
        entry_date: 入场日期字符串，格式 'YYYY-MM-DD'
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
    """
    try:
        # 获取ETF名称（用于日志）
        name = symbol  # 如果没有名称映射，使用代码
        hist = fetch_with_retry(symbol, name, max_retries=5, source=source)
        if hist.empty:
            return None
        entry_date_obj = datetime.strptime(entry_date, "%Y-%m-%d")
        
        # 查找最接近的交易日
        hist['日期'] = pd.to_datetime(hist['日期'])
        hist = hist.sort_values('日期')
        
        # 找到等于或最接近entry_date的交易日
        mask = hist['日期'] <= entry_date_obj
        if mask.any():
            closest_row = hist[mask].iloc[-1]
            return closest_row['收盘']
        else:
            # 如果找不到，返回最早的数据
            return hist.iloc[0]['收盘']
    except Exception as e:
        print(f"⚠️ 获取历史买入价格失败: {e}")
        return None

def update_holding_price_if_needed(holding_data, source="tx"):
    """
    如果入场价格为空，从历史数据补全
    
    Args:
        holding_data: 持仓数据字典
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
    """
    if holding_data["current_holding"]["entry_price"] is None:
        code = holding_data["current_holding"]["code"]
        entry_date = holding_data["current_holding"]["entry_date"]
        entry_price = get_entry_price_from_history(code, entry_date, source=source)
        if entry_price:
            holding_data["current_holding"]["entry_price"] = float(entry_price)
            save_holding(holding_data)
            print(f"✅ 已补全入场价格: {code} 在 {entry_date} 的买入价为 {entry_price:.3f}")
    return holding_data

# ======================== 核心逻辑 ========================

def get_realtime_data(source="tx"):
    """获取实时快照并记录时间（使用带重试机制的抓取）
    
    Args:
        source: 数据源选择，'tx' 表示腾讯，'em' 表示东财
    """
    return fetch_spot_with_retry(max_retries=5, source=source)

def get_price_from_spot(df_spot, symbol, fallback_price=None):
    """从实时数据中安全获取价格，如果失败则返回备选价格"""
    if df_spot is None:
        return fallback_price
    
    spot_row = df_spot[df_spot['代码'] == symbol]
    if not spot_row.empty:
        return spot_row['最新价'].values[0]
    
    return fallback_price

def calculate_momentum(prices, debug=False, symbol="", use_weighted=True):
    """计算动量得分
    Args:
        prices: 价格序列
        debug: 是否打印调试模式
        symbol: 代码（用于debug打印）
        use_weighted: 是否使用加权线性回归（聚宽版逻辑），默认为True
    返回: (score, r2, annualized_return) 元组
    """
    y = np.log(prices)
    x = np.arange(len(y))
    
    if use_weighted:
        # === 加权线性回归 (聚宽Pro版逻辑) ===
        # 权重从1到2线性增加，越近的数据权重越大
        weights = np.linspace(1, 2, len(y))
        
        # 使用 polyfit 进行加权线性拟合 (deg=1 表示一次多项式即线性)
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        
        # 计算加权 R²
        # 1. 计算预测值
        y_pred = slope * x + intercept
        # 2. 计算加权残差平方和 (SS_res)
        ss_res = np.sum(weights * (y - y_pred) ** 2)
        # 3. 计算加权总平方和 (SS_tot)
        # 注意：聚宽原版代码使用的是普通均值 np.mean(y)，此处保持一致以复刻结果
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        
        r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0
        annualized_return = np.exp(slope * 250) - 1
        
        if debug:
            print(f"      [DEBUG {symbol}] 动量计算 (加权Weighted):")
    else:
        # === 普通线性回归 (原版逻辑) ===
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        annualized_return = np.exp(slope * 250) - 1
        r2 = r_value ** 2
        
        if debug:
            print(f"      [DEBUG {symbol}] 动量计算 (普通Ordinary):")

    score = annualized_return * r2
    result = max(score, 0)
    
    if debug:
        print(f"        价格序列长度: {len(prices)}")
        print(f"        价格序列(最后5个): {prices[-5:]}")
        print(f"        斜率(slope): {slope:.6f}")
        print(f"        年化收益率: {annualized_return:.6f}")
        print(f"        R²: {r2:.6f}")
        print(f"        最终得分: {result:.4f}")
    
    return result, r2, annualized_return

def get_annualized_vol(prices, days=252):
    """计算年化波动率"""
    if len(prices) < 2:
        return 0.0
    returns = np.diff(np.log(prices))
    if len(returns) == 0:
        return 0.0
    vol = np.std(returns) * np.sqrt(days)
    return vol

def calculate_position_size(base_quantity, volatility, volatility_threshold=0.30):
    """根据波动率计算仓位大小（超过阈值减半）"""
    if volatility > volatility_threshold:
        return int(base_quantity * 0.5)
    return base_quantity

def run_strategy(pool_name="full", debug=False, source="tx"):
    """
    运行ETF轮动策略
    
    Args:
        pool_name: ETF池名称，'full'、'core' 或 'custom'
        debug: 是否开启调试模式
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
    """
    # 加载持仓记录
    holding_data = load_holding()
    if holding_data is None:
        holding_data = initialize_holding()
        save_holding(holding_data)
        print("✅ 已初始化持仓记录")
    
    # 补全入场价格
    holding_data = update_holding_price_if_needed(holding_data, source=source)
    
    # 检查是否有初始持仓但没有对应的 trade_history 记录
    current_holding = holding_data["current_holding"]
    trade_history = holding_data.get("trade_history", [])
    if current_holding.get("code") and current_holding.get("entry_date") and len(trade_history) == 0:
        # 有初始持仓但没有交易记录，添加初始买入记录
        entry_date = current_holding.get("entry_date")
        entry_time = current_holding.get("entry_time", "14:51")
        holding_data["trade_history"].append({
            "date": entry_date,
            "time": entry_time,
            "action": "买入",
            "code": current_holding["code"],
            "name": current_holding.get("name", ""),
            "price": current_holding.get("entry_price", 0),
            "quantity": current_holding.get("quantity", 0),
            "reason": "初始持仓"
        })
        print(f"📝 已添加初始持仓交易记录: {current_holding.get('name')}({current_holding['code']})")
    
    current_holding = holding_data["current_holding"]
    CURRENT_HOLDING = current_holding["code"] if current_holding["code"] else None
    entry_price = current_holding.get("entry_price")
    entry_quantity = current_holding.get("quantity", 0)
    
    # 获取ETF池
    if pool_name not in POOL_DICT:
        print(f"❌ 错误：未找到名为 '{pool_name}' 的ETF池。")
        print(f"✅ 可用池子：{list(POOL_DICT.keys())}")
        return
    
    etf_pool = POOL_DICT[pool_name]
    
    print("="*60)
    print(f"🚀 策略启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 当前使用ETF池: 【{pool_name}】 (共 {len(etf_pool)} 只)")
    print(f"📡 数据源: 【{source.upper()}】 ({'腾讯' if source == 'tx' else '东财'})")
    
    # 显示当前持仓信息
    if CURRENT_HOLDING:
        holding_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
        entry_price_display = f"{entry_price:.3f}" if entry_price else "N/A"
        print(f"📦 当前持仓: {holding_name}({CURRENT_HOLDING}) | 数量: {entry_quantity} | 入场价: {entry_price_display}")
    
    # 1. 获取行情
    df_spot, data_time = get_realtime_data(source=source)
    print(f"📊 交易所行情时间: {data_time}")
    print("-" * 60)
    
    # 检查实时数据是否获取成功
    if df_spot is None:
        print("⚠️ 警告：无法获取实时行情数据，将使用历史数据的最新收盘价作为备选方案")
        print("   注意：此模式下计算结果可能不够准确，建议在网络正常时重新运行")

    results = []
    positive_count = 0

    # ========== 1. 正式开始逐标的打分 & 选股逻辑 ==========
    for symbol, name in etf_pool.items():
        # 获取历史数据（前复权）- 使用带重试机制的抓取函数
        try:
            hist_full = fetch_with_retry(symbol, name, max_retries=5, source=source)
            if hist_full.empty:
                print(f"⚠️ 警告：{name}({symbol}) 无法获取历史数据，跳过。")
                continue
            
            hist = hist_full.tail(40)  # 取最近40天
            
            # 获取当前价格：优先使用实时数据，失败则使用历史数据
            current_price = None
            if df_spot is not None:
                spot_row = df_spot[df_spot['代码'] == symbol]
                if not spot_row.empty:
                    current_price = spot_row['最新价'].values[0]
            
            # 如果实时数据不可用，使用历史数据的最新收盘价
            if current_price is None:
                if hist.empty:
                    print(f"⚠️ 警告：{name}({symbol}) 无法获取价格数据，跳过。")
                    continue
                current_price = hist['收盘'].iloc[-1]
                print(f"ℹ️  {name}({symbol}) 使用历史收盘价: {current_price:.3f}")
            
            if debug:
                print(f"\n{'='*60}")
                print(f"🔍 [DEBUG] 计算 {name}({symbol}) 的得分")
                print(f"{'='*60}")
                print(f"历史收盘价序列(最后10个): {hist['收盘'].values[-10:]}")
                print(f"实时价格: {current_price}")
            
            # 拼接实时价格进行指标计算
            # 保留所有历史收盘价（包括昨天的），然后追加今天的价格
            hist_closes = hist['收盘'].values  # 保留所有历史收盘价，包括昨天的
            prices = np.append(hist_closes, current_price)  # 追加今天的价格
            
            if debug:
                print(f"拼接后价格序列(最后10个): {prices[-10:]}")
                print(f"价格序列总长度: {len(prices)}")
            
            # 风险过滤：近4日任意一天跌幅过大（根据pool参数设置不同阈值）
            if len(prices) >= 4:
                # 根据pool参数设置跌幅阈值
                if pool_name == "core":
                    decline_threshold = 0.97  # 3%跌幅
                elif pool_name == "full":
                    decline_threshold = 0.95  # 5%跌幅
                elif pool_name == "custom":
                    decline_threshold = 0.95  # 自定义池使用5%跌幅
                else:
                    decline_threshold = 0.97  # 默认3%
                
                # 检查过去4天内是否有任意一天跌幅超过阈值
                ratio1 = prices[-1] / prices[-2]  # 今天/昨天
                ratio2 = prices[-2] / prices[-3]  # 昨天/前天
                ratio3 = prices[-3] / prices[-4]  # 前天/大前天
                
                # 打印调试信息（帮助排查问题）
                if debug:
                    threshold_pct = (1 - decline_threshold) * 100
                    print(f"  风险过滤检查:")
                    print(f"    近4日价格序列: {prices[-4:]}")
                    print(f"    价格比值: 今天/昨天={ratio1:.4f} (跌幅{(1-ratio1)*100:.2f}%), 昨天/前天={ratio2:.4f} (跌幅{(1-ratio2)*100:.2f}%), 前天/大前天={ratio3:.4f} (跌幅{(1-ratio3)*100:.2f}%)")
                    print(f"    跌幅阈值: {decline_threshold:.4f} ({threshold_pct:.0f}%)")
                
                # 检查过滤条件：只要过去4天中任意一天跌幅超过阈值就过滤
                # ratio1 < decline_threshold：今天跌幅超过阈值
                # ratio2 < decline_threshold：昨天跌幅超过阈值
                # ratio3 < decline_threshold：前天跌幅超过阈值
                threshold_pct = (1 - decline_threshold) * 100
                should_filter = False
                filter_reason = ""
                
                if ratio1 < decline_threshold:
                    should_filter = True
                    today_decline = (1 - ratio1) * 100
                    filter_reason = f"今日跌幅{today_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                elif ratio2 < decline_threshold:
                    should_filter = True
                    yesterday_decline = (1 - ratio2) * 100
                    filter_reason = f"昨日跌幅{yesterday_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                elif ratio3 < decline_threshold:
                    should_filter = True
                    day_before_decline = (1 - ratio3) * 100
                    filter_reason = f"前日跌幅{day_before_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                
                if should_filter:
                    print(f"⚠️ {name}({symbol}) 风险过滤: {filter_reason}，该标的被过滤")
                    print(f"   价格序列(最近4天): {prices[-4:]}")
                    print(f"   价格比值: 今天/昨天={ratio1:.4f} (跌幅{(1-ratio1)*100:.2f}%), 昨天/前天={ratio2:.4f} (跌幅{(1-ratio2)*100:.2f}%), 前天/大前天={ratio3:.4f} (跌幅{(1-ratio3)*100:.2f}%)")
                    continue
                elif debug:
                    # 即使没有触发过滤，也打印信息（仅debug模式）
                    print(f"  ✅ {name}({symbol}) 通过风险过滤检查")
            
            # 指标计算
            ma20 = np.mean(prices[-STRATEGY_CONF["ma_filter_days"]:])
            short_ret = (prices[-1] / prices[-5]) - 1
            
            if debug:
                print(f"\n指标计算:")
                print(f"  MA20计算用的价格(最后{STRATEGY_CONF['ma_filter_days']}个): {prices[-STRATEGY_CONF['ma_filter_days']:]}")
                print(f"  MA20: {ma20:.4f}")
                print(f"  当前价格: {current_price:.4f}")
                print(f"  是否在MA20之上: {current_price > ma20}")
                print(f"  5日涨跌计算: prices[-1]={prices[-1]:.4f} / prices[-5]={prices[-5]:.4f} - 1 = {short_ret:.4%}")
                print(f"  5日涨跌阈值: {STRATEGY_CONF['short_ret_limit']:.2%}")
                print(f"  是否通过5日涨跌过滤: {short_ret > STRATEGY_CONF['short_ret_limit']}")
            
            # 计算年化波动率
            annualized_vol = get_annualized_vol(prices[-20:])  # 使用最近60个交易日
            
            is_up = current_price > ma20
            is_not_crash = short_ret > STRATEGY_CONF["short_ret_limit"]
            
            score = 0
            r2 = 0
            annualized_return = 0
            if is_up and is_not_crash:
                momentum_prices = prices[-STRATEGY_CONF["m_days"]:]
                if debug:
                    print(f"\n动量计算:")
                    print(f"  使用最近{STRATEGY_CONF['m_days']}天的价格计算动量")
                
                # 传递加权配置参数
                use_weighted = STRATEGY_CONF.get("use_weighted", True)
                score, r2, annualized_return = calculate_momentum(momentum_prices, debug=debug, symbol=symbol, use_weighted=use_weighted)
                if score > 0: positive_count += 1
            elif debug:
                if not is_up:
                    print(f"\n❌ 未通过均线过滤: 当前价格 {current_price:.4f} <= MA20 {ma20:.4f}")
                if not is_not_crash:
                    print(f"❌ 未通过5日涨跌过滤: 5日涨跌 {short_ret:.2%} <= 阈值 {STRATEGY_CONF['short_ret_limit']:.2%}")
                print(f"最终得分: 0 (未通过过滤条件)")

            results.append({
                "代码": symbol, "名称": name, "价格": current_price,
                "MA20": round(ma20, 3), "5日涨跌": f"{short_ret:.2%}",
                "波动率": f"{annualized_vol:.2%}",
                "状态": "📈多头" if is_up else "📉破位",
                "得分": round(score, 4),
                "r2": round(r2, 4),
                "年化收益率": round(annualized_return, 4)
            })
            
            if debug:
                print(f"✅ 最终结果: 得分={score:.4f}, 状态={'📈多头' if is_up else '📉破位'}")
                print(f"{'='*60}\n")
        except Exception as e:
            print(f"❌ 处理 {name}({symbol}) 时出错: {e}")
            if debug:
                import traceback
                traceback.print_exc()

    # 2. 排名与风控
    if not results:
        print("❌ 没有成功计算任何标的。")
        return

    df_res = pd.DataFrame(results).sort_values(by="得分", ascending=False)
    sentiment_ratio = positive_count / len(etf_pool)
    is_safe = sentiment_ratio >= STRATEGY_CONF["sentiment_threshold"]

    # 3. 检查硬止损（如果当前有持仓）
    stop_loss_triggered = False
    if CURRENT_HOLDING and entry_price and df_spot is not None:
        current_spot = df_spot[df_spot['代码'] == CURRENT_HOLDING]
        if not current_spot.empty:
            current_holding_price = current_spot['最新价'].values[0]
            loss_ratio = (current_holding_price / entry_price) - 1
            if loss_ratio <= STRATEGY_CONF["stop_loss_threshold"]:
                stop_loss_triggered = True
                print(f"🛑 【硬止损触发】当前持仓从入场价 {entry_price:.3f} 下跌至 {current_holding_price:.3f}，跌幅 {loss_ratio:.2%}，超过 {STRATEGY_CONF['stop_loss_threshold']:.2%} 阈值！")
    
    # 3.5. 检查持仓ETF的跌幅（如果当前有持仓，任意一天跌幅超过阈值就清仓）
    decline_sell_triggered = False
    if CURRENT_HOLDING and not stop_loss_triggered:
        # 根据pool参数设置跌幅阈值
        if pool_name == "core":
            decline_threshold = 0.97  # 3%跌幅
        elif pool_name == "full":
            decline_threshold = 0.95  # 5%跌幅
        elif pool_name == "custom":
            decline_threshold = 0.95  # 自定义池使用5%跌幅
        else:
            decline_threshold = 0.97  # 默认3%
        
        # 获取持仓ETF的历史数据
        current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
        try:
            hist_full = fetch_with_retry(CURRENT_HOLDING, current_name, max_retries=5, source=source)
            if not hist_full.empty:
                hist = hist_full.tail(40)  # 取最近40天
                
                # 获取当前价格
                current_price = None
                if df_spot is not None:
                    spot_row = df_spot[df_spot['代码'] == CURRENT_HOLDING]
                    if not spot_row.empty:
                        current_price = spot_row['最新价'].values[0]
                
                if current_price is None:
                    if not hist.empty:
                        current_price = hist['收盘'].iloc[-1]
                
                if current_price is not None and len(hist) >= 4:
                    # 拼接价格序列
                    # 保留所有历史收盘价（包括昨天的），然后追加今天的价格
                    hist_closes = hist['收盘'].values  # 保留所有历史收盘价，包括昨天的
                    prices = np.append(hist_closes, current_price)  # 追加今天的价格
                    
                    # 检查跌幅清仓条件：只要过去4天中任意一天跌幅超过阈值就清仓
                    if len(prices) >= 4:
                        ratio1 = prices[-1] / prices[-2]  # 今天/昨天
                        ratio2 = prices[-2] / prices[-3]  # 昨天/前天
                        ratio3 = prices[-3] / prices[-4]  # 前天/大前天
                        
                        threshold_pct = (1 - decline_threshold) * 100
                        should_sell = False
                        sell_reason = ""
                        
                        # 只要任意一天跌幅超过阈值就清仓
                        if ratio1 < decline_threshold:
                            should_sell = True
                            today_decline = (1 - ratio1) * 100
                            sell_reason = f"今日跌幅{today_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                        elif ratio2 < decline_threshold:
                            should_sell = True
                            yesterday_decline = (1 - ratio2) * 100
                            sell_reason = f"昨日跌幅{yesterday_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                        elif ratio3 < decline_threshold:
                            should_sell = True
                            day_before_decline = (1 - ratio3) * 100
                            sell_reason = f"前日跌幅{day_before_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                        
                        if should_sell:
                            decline_sell_triggered = True
                            print(f"🛑 【跌幅清仓触发】当前持仓 {current_name}({CURRENT_HOLDING}) {sell_reason}！")
                            print(f"   价格序列(最近4天): {prices[-4:]}")
                            print(f"   价格比值: 今天/昨天={ratio1:.4f} (跌幅{(1-ratio1)*100:.2f}%), 昨天/前天={ratio2:.4f} (跌幅{(1-ratio2)*100:.2f}%), 前天/大前天={ratio3:.4f} (跌幅{(1-ratio3)*100:.2f}%)")
        except Exception as e:
            print(f"⚠️ 检查持仓跌幅时出错: {e}")

    # 4. 打印分析表格
    print(df_res.to_string(index=False))
    print("-" * 60)
    print(f"💡 市场情绪占比: {sentiment_ratio:.2%} | 风控阈值: {STRATEGY_CONF['sentiment_threshold']:.2%}")

    # 5. 生成建议操作指令
    print("\n📢 【操作建议】")
    
    top_target = df_res.iloc[0]
    top_code = top_target['代码']
    top_score = top_target['得分']
    top_volatility = float(top_target['波动率'].rstrip('%')) / 100
    
    # 计算建议仓位（根据当前持仓市值计算，考虑波动率控仓）
    if entry_quantity > 0 and CURRENT_HOLDING:
        # 获取当前持仓的最新价格来计算实际市值
        current_price = None
        if df_spot is not None:
            current_spot = df_spot[df_spot['代码'] == CURRENT_HOLDING]
            if not current_spot.empty:
                current_price = current_spot['最新价'].values[0]
        
        if current_price is not None:
            current_market_value = entry_quantity * current_price
            # 根据市值计算新标的的数量（保持相同的资金量）
            base_quantity = int(current_market_value / top_target['价格'])
        else:
            # 如果获取不到最新价格，使用入场价格估算
            if entry_price:
                current_market_value = entry_quantity * entry_price
                base_quantity = int(current_market_value / top_target['价格'])
            else:
                base_quantity = entry_quantity  # 降级使用数量
    else:
        # 没有持仓时，使用默认数量
        base_quantity = 31900
    
    suggested_quantity = calculate_position_size(
        base_quantity, 
        top_volatility, 
        STRATEGY_CONF["volatility_threshold"]
    )
    
    if stop_loss_triggered:
        # 硬止损优先
        current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"🛑 硬止损指令：【立即清仓】(在 {STRATEGY_CONF['sell_time']} 卖出 {current_name}({CURRENT_HOLDING})，数量: {entry_quantity})")
        
        # 记录交易
        sell_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
        if sell_price is None:
            print(f"⚠️ 警告：无法获取 {current_name}({CURRENT_HOLDING}) 的卖出价格，跳过交易记录")
        else:
            holding_data["trade_history"].append({
                "date": today,
                "time": STRATEGY_CONF["sell_time"],
                "action": "卖出",
                "code": CURRENT_HOLDING,
                "name": current_name,
                "price": sell_price,
                "quantity": entry_quantity,
                "reason": "硬止损触发"
            })
        
        # 清空持仓
        holding_data["current_holding"] = {
            "code": None,
            "name": None,
            "quantity": 0,
            "entry_price": None,
            "entry_date": None,
            "entry_time": None
        }
        holding_data["last_update_date"] = today
        save_holding(holding_data)
    
    elif decline_sell_triggered:
        # 跌幅清仓（任意一天跌幅超过阈值）
        current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
        today = datetime.now().strftime("%Y-%m-%d")
        # 根据pool参数计算阈值百分比
        if pool_name == "core":
            threshold_pct = (1 - 0.97) * 100  # 3%
        elif pool_name == "full":
            threshold_pct = (1 - 0.95) * 100  # 5%
        elif pool_name == "custom":
            threshold_pct = (1 - 0.95) * 100  # 5%
        else:
            threshold_pct = (1 - 0.97) * 100  # 默认3%
        print(f"🛑 跌幅清仓指令：【立即清仓】(在 {STRATEGY_CONF['sell_time']} 卖出 {current_name}({CURRENT_HOLDING})，数量: {entry_quantity})")
        
        # 记录交易
        sell_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
        if sell_price is None:
            print(f"⚠️ 警告：无法获取 {current_name}({CURRENT_HOLDING}) 的卖出价格，跳过交易记录")
        else:
            holding_data["trade_history"].append({
                "date": today,
                "time": STRATEGY_CONF["sell_time"],
                "action": "卖出",
                "code": CURRENT_HOLDING,
                "name": current_name,
                "price": sell_price,
                "quantity": entry_quantity,
                "reason": f"跌幅超过{threshold_pct:.0f}%"
            })
        
        # 清空持仓
        holding_data["current_holding"] = {
            "code": None,
            "name": None,
            "quantity": 0,
            "entry_price": None,
            "entry_date": None,
            "entry_time": None
        }
        holding_data["last_update_date"] = today
        save_holding(holding_data)
        
    elif not is_safe:
        if CURRENT_HOLDING:
            current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
            today = datetime.now().strftime("%Y-%m-%d")
            print(f"⚠️ 风险预警：全市场情绪过低！指令：【全部清仓】(在 {STRATEGY_CONF['sell_time']} 卖出 {current_name}({CURRENT_HOLDING})，数量: {entry_quantity})")
            
            # 记录交易
            sell_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
            if sell_price is None:
                print(f"⚠️ 警告：无法获取 {current_name}({CURRENT_HOLDING}) 的卖出价格，跳过交易记录")
            else:
                holding_data["trade_history"].append({
                    "date": today,
                    "time": STRATEGY_CONF["sell_time"],
                    "action": "卖出",
                    "code": CURRENT_HOLDING,
                    "name": current_name,
                    "price": sell_price,
                    "quantity": entry_quantity,
                    "reason": "市场情绪过低"
                })
            
            # 清空持仓
            holding_data["current_holding"] = {
                "code": None,
                "name": None,
                "quantity": 0,
                "entry_price": None,
                "entry_date": None,
                "entry_time": None
            }
            holding_data["last_update_date"] = today
            save_holding(holding_data)
        else:
            print("🟢 风险预警：全市场情绪过低。指令：【继续空仓】")
    
    elif top_score <= 0:
        if CURRENT_HOLDING:
            current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
            today = datetime.now().strftime("%Y-%m-%d")
            print(f"📉 信号衰减：无任何标的具备正向动量。指令：【卖出清仓】(在 {STRATEGY_CONF['sell_time']} 卖出 {current_name}({CURRENT_HOLDING})，数量: {entry_quantity})")
            
            # 记录交易
            sell_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
            if sell_price is None:
                print(f"⚠️ 警告：无法获取 {current_name}({CURRENT_HOLDING}) 的卖出价格，跳过交易记录")
            else:
                holding_data["trade_history"].append({
                    "date": today,
                    "time": STRATEGY_CONF["sell_time"],
                    "action": "卖出",
                    "code": CURRENT_HOLDING,
                    "name": current_name,
                    "price": sell_price,
                    "quantity": entry_quantity,
                    "reason": "无正向动量信号"
                })
            
            # 清空持仓
            holding_data["current_holding"] = {
                "code": None,
                "name": None,
                "quantity": 0,
                "entry_price": None,
                "entry_date": None,
                "entry_time": None
            }
            holding_data["last_update_date"] = today
            save_holding(holding_data)
        else:
            print("⚪ 信号提示：目前无合适入场标的。指令：【继续观望】")
            
    else:
        # 正常情况：不执行任何操作（不开仓，不换仓，不显示持仓信息）
        pass

    # 6. 记录每日状态（在策略运行结束前）
    # 获取当前持仓的最新价格和得分
    record_price = 0.0
    record_score = None
    record_r2 = None
    record_annualized_return = None
    if holding_data["current_holding"]["code"]:
        h_code = holding_data["current_holding"]["code"]
        h_entry_price = holding_data["current_holding"].get("entry_price")
        
        # 尝试从df_spot获取价格，失败则使用入场价
        record_price = get_price_from_spot(df_spot, h_code, h_entry_price)
        if record_price is None:
            record_price = h_entry_price if h_entry_price else 0.0
        
        # 从results中查找当前持仓的得分、r2和年化收益率
        for result in results:
            if result["代码"] == h_code:
                record_score = result["得分"]
                record_r2 = result.get("r2")
                record_annualized_return = result.get("年化收益率")
                break
    
    # 构建所有ETF的得分字典（用于记录），包含score、r2、annualized_return
    pool_scores_dict = {}
    for item in results:
        pool_scores_dict[item["代码"]] = {
            "score": item["得分"],
            "r2": item.get("r2"),
            "annualized_return": item.get("年化收益率")
        }
    
    # 先补全历史
    holding_data = backfill_daily_log(holding_data, pool_name, source=source)
    # 再更新今日
    holding_data = record_daily_status(holding_data, record_price, record_score, record_r2, record_annualized_return, pool_scores_dict)
    save_holding(holding_data)
    
    # 显示记录信息
    last_log = holding_data['daily_log'][-1]
    score_info = f" | 得分: {last_log['score']:.4f}" if last_log.get('score') is not None else " | 得分: N/A"
    pool_scores_count = len([s for s in last_log.get('pool_scores', {}).values() if s is not None]) if last_log.get('pool_scores') else 0
    pool_info = f" | 池子得分: {pool_scores_count}/{len(etf_pool)}" if last_log.get('pool_scores') else ""
    print(f"📝 每日记录已更新: {last_log['date']} 市值: {last_log['market_value']}{score_info}{pool_info}")

    print("="*60)

def debug_historical_date(target_date_str, pool_name="core", source="tx"):
    """
    调试指定历史日期的得分计算
    
    Args:
        target_date_str: 目标日期字符串，格式 'YYYY-MM-DD'
        pool_name: ETF池名称，'full'、'core' 或 'custom'
        source: 数据源选择，'tx' 表示腾讯（默认），'em' 表示东财
    """
    print(f"\n{'='*60}")
    print(f"🔍 调试历史日期: {target_date_str}")
    print(f"📡 数据源: 【{source.upper()}】 ({'腾讯' if source == 'tx' else '东财'})")
    print(f"{'='*60}\n")
    
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    
    # 获取ETF池
    if pool_name not in POOL_DICT:
        print(f"❌ 错误：未找到名为 '{pool_name}' 的ETF池。")
        return
    etf_pool = POOL_DICT[pool_name]
    
    for symbol, name in etf_pool.items():
        print(f"\n{'='*60}")
        print(f"🔍 [DEBUG] 计算 {name}({symbol}) 在 {target_date_str} 的得分")
        print(f"{'='*60}")
        
        try:
            # 获取历史数据 - 使用带重试机制的抓取函数
            hist = fetch_with_retry(symbol, name, max_retries=5, source=source)
            if hist.empty:
                print(f"❌ 无法获取历史数据")
                continue
            
            hist['日期'] = pd.to_datetime(hist['日期'])
            hist = hist.sort_values('日期')
            
            # 获取到目标日期为止的数据
            hist_up_to_date = hist[hist['日期'] <= pd.Timestamp(target_date)]
            if len(hist_up_to_date) < STRATEGY_CONF["m_days"]:
                print(f"❌ 数据不足，需要至少{STRATEGY_CONF['m_days']}天，实际只有{len(hist_up_to_date)}天")
                continue
            
            # 获取目标日期的收盘价（模拟14:51的价格，使用收盘价作为近似）
            target_date_data = hist_up_to_date[hist_up_to_date['日期'].dt.date == target_date.date()]
            if target_date_data.empty:
                print(f"❌ {target_date_str} 不是交易日")
                continue
            
            close_price = target_date_data.iloc[0]['收盘']
            prices = hist_up_to_date['收盘'].values
            
            print(f"历史收盘价序列(最后10个): {prices[-10:]}")
            print(f"目标日期收盘价: {close_price}")
            print(f"价格序列总长度: {len(prices)}")
            
            # 风险过滤：近4日任意一天跌幅过大（根据pool参数设置不同阈值）
            if len(prices) >= 4:
                # 根据pool参数设置跌幅阈值
                if pool_name == "core":
                    decline_threshold = 0.97  # 3%跌幅
                elif pool_name == "full":
                    decline_threshold = 0.95  # 5%跌幅
                elif pool_name == "custom":
                    decline_threshold = 0.95  # 自定义池使用5%跌幅
                else:
                    decline_threshold = 0.97  # 默认3%
                
                # 检查过去4天内是否有任意一天跌幅超过阈值
                ratio1 = prices[-1] / prices[-2]  # 今天/昨天
                ratio2 = prices[-2] / prices[-3]  # 昨天/前天
                ratio3 = prices[-3] / prices[-4]  # 前天/大前天
                
                # 检查是否有任意一天跌幅超过阈值
                should_filter = False
                filter_reason = ""
                threshold_pct = (1 - decline_threshold) * 100
                
                if ratio1 < decline_threshold:
                    should_filter = True
                    today_decline = (1 - ratio1) * 100
                    filter_reason = f"今日跌幅{today_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                elif ratio2 < decline_threshold:
                    should_filter = True
                    yesterday_decline = (1 - ratio2) * 100
                    filter_reason = f"昨日跌幅{yesterday_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                elif ratio3 < decline_threshold:
                    should_filter = True
                    day_before_decline = (1 - ratio3) * 100
                    filter_reason = f"前日跌幅{day_before_decline:.2f}%超过{threshold_pct:.0f}%阈值"
                
                print(f"\n风险过滤检查:")
                print(f"  近4日价格序列: {prices[-4:]}")
                print(f"  价格比值: 今天/昨天={ratio1:.4f} (跌幅{(1-ratio1)*100:.2f}%), 昨天/前天={ratio2:.4f} (跌幅{(1-ratio2)*100:.2f}%), 前天/大前天={ratio3:.4f} (跌幅{(1-ratio3)*100:.2f}%)")
                print(f"  跌幅阈值: {decline_threshold:.4f} ({threshold_pct:.0f}%)")
                
                if should_filter:
                    print(f"  ⚠️ 风险过滤: {filter_reason}，该标的被过滤")
                    print(f"\n✅ 最终结果: {name}({symbol}) 在 {target_date_str} 的得分 = N/A (风险过滤)")
                    continue
            
            # 计算指标
            ma20 = np.mean(prices[-STRATEGY_CONF["ma_filter_days"]:])
            short_ret = (prices[-1] / prices[-5]) - 1 if len(prices) >= 5 else 0
            
            print(f"\n指标计算:")
            print(f"  MA20计算用的价格(最后{STRATEGY_CONF['ma_filter_days']}个): {prices[-STRATEGY_CONF['ma_filter_days']:]}")
            print(f"  MA20: {ma20:.4f}")
            print(f"  目标日期价格: {close_price:.4f}")
            print(f"  是否在MA20之上: {close_price > ma20}")
            print(f"  5日涨跌计算: prices[-1]={prices[-1]:.4f} / prices[-5]={prices[-5]:.4f} - 1 = {short_ret:.4%}")
            print(f"  5日涨跌阈值: {STRATEGY_CONF['short_ret_limit']:.2%}")
            print(f"  是否通过5日涨跌过滤: {short_ret > STRATEGY_CONF['short_ret_limit']}")
            
            is_up = close_price > ma20
            is_not_crash = short_ret > STRATEGY_CONF["short_ret_limit"]
            
            score = 0
            r2 = 0
            annualized_return = 0
            if is_up and is_not_crash:
                momentum_prices = prices[-STRATEGY_CONF["m_days"]:]
                print(f"\n动量计算:")
                print(f"  使用最近{STRATEGY_CONF['m_days']}天的价格计算动量")
                # 传递加权配置参数
                use_weighted = STRATEGY_CONF.get("use_weighted", True)
                score, r2, annualized_return = calculate_momentum(momentum_prices, debug=True, symbol=symbol, use_weighted=use_weighted)
            else:
                if not is_up:
                    print(f"\n❌ 未通过均线过滤: 价格 {close_price:.4f} <= MA20 {ma20:.4f}")
                if not is_not_crash:
                    print(f"❌ 未通过5日涨跌过滤: 5日涨跌 {short_ret:.2%} <= 阈值 {STRATEGY_CONF['short_ret_limit']:.2%}")
                print(f"最终得分: 0 (未通过过滤条件)")
            
            print(f"\n✅ 最终结果: {name}({symbol}) 在 {target_date_str} 的得分 = {score:.4f}")
            
        except Exception as e:
            print(f"❌ 处理 {name}({symbol}) 时出错: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ETF轮动策略')
    parser.add_argument('--pool', type=str, default='core', help='选择ETF池: full (全量), core (核心), custom (自定义)')
    parser.add_argument('--debug', action='store_true', help='开启调试模式，显示详细计算过程')
    parser.add_argument('--source', type=str, default='tx', choices=['tx', 'em'], 
                       help='数据源选择: tx (腾讯，默认), em (东财)')
    parser.add_argument('--debug-date', type=str, help='调试指定历史日期，格式: YYYY-MM-DD，例如: 2026-01-15')
    args = parser.parse_args()
    
    if args.debug_date:
        debug_historical_date(args.debug_date, args.pool, source=args.source)
    else:
        run_strategy(args.pool, debug=args.debug, source=args.source)
