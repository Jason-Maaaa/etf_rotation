# ======================== 导入模块 ========================
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from scipy.stats import linregress
import time
import argparse
import sys
import json
import os
from pathlib import Path
from etf_config import POOL_DICT

# 尝试导入 efinance（可选依赖）
try:
    import efinance as ef
    EFINANCE_AVAILABLE = True
except ImportError:
    EFINANCE_AVAILABLE = False
    print("⚠️ efinance 未安装，将跳过 efinance 数据源。如需使用，请执行: pip install efinance")

# ======================== 配置区 ========================

# 持仓记录文件路径（根据pool_name动态生成，避免不同池子互相污染）
def get_holding_file(pool_name="core"):
    """根据pool_name返回对应的持仓文件路径"""
    filename = f"etf_holding_{pool_name}.json"
    return Path(__file__).parent / filename

# 缓存文件路径
def get_cache_file():
    """返回历史数据缓存文件路径"""
    return Path(__file__).parent / "etf_history_cache.json"

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
    "buy_time": "14:51"          # 默认买入时间
}

# ======================== 持仓管理 ========================

def load_holding(pool_name="core"):
    """加载持仓记录（支持从旧文件迁移）"""
    holding_file = get_holding_file(pool_name)
    if holding_file.exists():
        try:
            with open(holding_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"⚠️ 加载持仓记录失败: {e}，将重新初始化")
            return None
    
    # 兼容性处理：如果新文件不存在，尝试从旧的 etf_holding.json 迁移（仅对 core pool）
    if pool_name == "core":
        old_file = Path(__file__).parent / "etf_holding.json"
        if old_file.exists():
            try:
                print(f"🔄 检测到旧的持仓文件，正在迁移到 etf_holding_{pool_name}.json...")
                with open(old_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 保存到新文件
                save_holding(data, pool_name)
                print(f"✅ 迁移完成！旧的 etf_holding.json 已迁移到 etf_holding_{pool_name}.json")
                return data
            except Exception as e:
                print(f"⚠️ 迁移旧文件失败: {e}，将重新初始化")
                return None
    
    return None

def save_holding(holding_data, pool_name="core"):
    """保存持仓记录"""
    try:
        holding_file = get_holding_file(pool_name)
        with open(holding_file, 'w', encoding='utf-8') as f:
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

def calculate_etf_score_at_date(symbol, target_date):
    """计算指定ETF在指定日期的得分"""
    try:
        # 获取历史数据（获取足够多的数据用于计算）
        hist = get_etf_history_with_fallback(symbol=symbol, period="daily", adjust="qfq")
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
        
        # 计算指标
        ma20 = np.mean(prices[-STRATEGY_CONF["ma_filter_days"]:])
        short_ret = (prices[-1] / prices[-5]) - 1 if len(prices) >= 5 else 0
        
        is_up = close_price > ma20
        is_not_crash = short_ret > STRATEGY_CONF["short_ret_limit"]
        
        # 计算得分
        score = 0
        r2 = 0
        annualized_return = 0
        if is_up and is_not_crash:
            momentum_prices = prices[-STRATEGY_CONF["m_days"]:]
            score, r2, annualized_return = calculate_momentum(momentum_prices)
        
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

def backfill_daily_log(holding_data, pool_name="core"):
    """补全缺失的历史每日记录"""
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
        
        hist = get_etf_history_with_fallback(symbol=code, period="daily", start_date=start_date_str, end_date=today.strftime("%Y%m%d"), adjust="qfq")
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
                score_result = calculate_etf_score_at_date(code, curr)
                score = score_result["score"] if score_result else None
                r2 = score_result["r2"] if score_result else None
                annualized_return = score_result["annualized_return"] if score_result else None
                
                # 计算池子中所有ETF在历史日期的得分、r2和年化收益率
                pool_scores = {}
                print(f"   📊 计算 {curr_str} 池子中所有ETF得分...", end="")
                for symbol, name in etf_pool.items():
                    etf_score_result = calculate_etf_score_at_date(symbol, curr)
                    if etf_score_result:
                        pool_scores[symbol] = {
                            "score": etf_score_result["score"],
                            "r2": etf_score_result["r2"],
                            "annualized_return": etf_score_result["annualized_return"]
                        }
                    else:
                        pool_scores[symbol] = {
                            "score": None,
                            "r2": None,
                            "annualized_return": None
                        }
                print(f" 完成 ({len([s for s in pool_scores.values() if s.get('score') is not None])}/{len(etf_pool)} 个有效得分)")
                
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
                    hist_score_result = calculate_etf_score_at_date(hist_code, curr)
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
        save_holding(holding_data, pool_name) # 及时保存
        
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

# ======================== 缓存管理 ========================

def safe_parse_datetime(date_value):
    """
    安全解析日期，支持多种格式：
    - 字符串日期（如 "2024-01-01"）
    - 秒级时间戳（如 1323388800）
    - 毫秒级时间戳（如 1323388800000）
    - 纳秒级时间戳（如 1323388800000000000）
    """
    if pd.isna(date_value):
        return None
    
    # 直接处理 datetime/Timestamp/date 对象
    if isinstance(date_value, (datetime, pd.Timestamp)):
        return date_value
    if isinstance(date_value, date):
        try:
            return pd.to_datetime(date_value)
        except:
            return None

    # 如果是字符串，先尝试判断是否为纯数字
    if isinstance(date_value, str):
        # 移除可能的小数点
        clean_str = date_value.replace('.', '')
        if clean_str.isdigit():
            # 是纯数字字符串，转换为float处理
            try:
                date_value = float(date_value)
            except:
                pass
        else:
            # 非数字字符串，尝试直接解析
            try:
                return pd.to_datetime(date_value, errors='coerce')
            except Exception:
                return None
    
    # 尝试转换为数字（可能是时间戳）
    try:
        timestamp = float(date_value)
        
        # 判断时间戳的级别
        # 纳秒级（> 1e16）- 扩大范围以包含 19 位数
        if timestamp > 1e16:
            timestamp = timestamp / 1e9
        # 微秒级/毫秒级混合区
        elif timestamp > 1e11: 
             # 此时 1e11 秒约 3170 年，1970+3170=5140年。
             # 通常毫秒级是 13 位 (1e12)，秒级 10 位 (1e9)
             # 所以 > 1e11 几乎肯定是毫秒
            timestamp = timestamp / 1e3
        
        # 转换为 datetime
        return pd.to_datetime(timestamp, unit='s', errors='coerce')
    except Exception:
        # 如果都失败了，尝试让 pandas 自动解析（带coerce）
        try:
            return pd.to_datetime(date_value, errors='coerce')
        except Exception:
            return None

def load_cache():
    """加载历史数据缓存"""
    cache_file = get_cache_file()
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                return cache
        except Exception as e:
            print(f"⚠️ 加载缓存失败: {e}，将重新创建")
            return {}
    return {}

def save_cache(cache):
    """保存历史数据缓存"""
    try:
        cache_file = get_cache_file()
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存缓存失败: {e}")

def get_cached_data(symbol):
    """从缓存中获取指定ETF的数据，返回DataFrame"""
    cache = load_cache()
    if symbol in cache:
        data = cache[symbol]
        dates = data.get('dates', [])
        closes = data.get('closes', [])
        if dates and closes:
            # 安全转换日期
            try:
                df = pd.DataFrame({
                    '日期': pd.to_datetime(dates, errors='coerce'),
                    '收盘': closes
                })
                df = df.dropna(subset=['日期'])
                df = df.sort_values('日期')
                return df
            except Exception as e:
                print(f"⚠️ get_cached_data 解析日期失败: {e}")
                return pd.DataFrame()
    return pd.DataFrame()

def update_cache(symbol, hist_df):
    """更新缓存：将新的历史数据合并到缓存中"""
    if hist_df.empty or '日期' not in hist_df.columns or '收盘' not in hist_df.columns:
        return
    
    cache = load_cache()
    
    # 获取现有缓存数据
    if symbol in cache:
        try:
            cached_dates = [pd.to_datetime(d, errors='coerce') for d in cache[symbol]['dates']]
            # 过滤 NaT
            valid_indices = [i for i, d in enumerate(cached_dates) if pd.notna(d)]
            cached_dates = [cached_dates[i] for i in valid_indices]
            cached_closes = [cache[symbol]['closes'][i] for i in valid_indices if i < len(cache[symbol]['closes'])]
        except Exception as e:
            print(f"⚠️ update_cache 解析旧缓存日期失败: {e}")
            cached_dates = []
            cached_closes = []
    else:
        cached_dates = []
        cached_closes = []
    
    # 转换新数据
    hist_df = hist_df.copy()
    # 确保日期列是 datetime 类型（处理 datetime.date 对象）
    if '日期' in hist_df.columns:
        # 如果已经是 datetime 类型，直接使用；否则转换
        if hist_df['日期'].dtype == 'object':
            # 可能是 datetime.date 对象，需要转换
            hist_df['日期'] = pd.to_datetime(hist_df['日期'], errors='coerce')
        else:
            hist_df['日期'] = pd.to_datetime(hist_df['日期'], errors='coerce')
    
    # 确保获取的是 Series，如果返回 DataFrame 则使用 squeeze() 转换
    date_col = hist_df['日期']
    close_col = hist_df['收盘']
    if isinstance(date_col, pd.DataFrame):
        date_col = date_col.squeeze()
    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.squeeze()
    
    # 使用 iloc 逐个访问日期值，避免 .values 可能导致的类型转换问题
    # 确保日期是 Timestamp 对象
    new_dates = []
    for idx in range(len(date_col)):
        d = date_col.iloc[idx]
        if pd.isna(d):
            continue
        # 统一转换为 Timestamp
        if isinstance(d, (pd.Timestamp, datetime)):
            new_dates.append(d)
        elif isinstance(d, date):
            new_dates.append(pd.to_datetime(d))
        else:
            # 尝试转换
            try:
                dt = pd.to_datetime(d, errors='coerce')
                if pd.notna(dt):
                    new_dates.append(dt)
            except:
                pass
    
    new_closes = close_col.values.tolist()
    
    # 确保日期和收盘价数量一致
    min_len = min(len(new_dates), len(new_closes))
    new_dates = new_dates[:min_len]
    new_closes = new_closes[:min_len]
    
    # 合并数据（去重，保留最新）
    merged_data = {}
    for date, close in zip(cached_dates + new_dates, cached_closes + new_closes):
        # 统一转换为 Timestamp，然后格式化为字符串
        if isinstance(date, (pd.Timestamp, datetime)):
            date_str = date.strftime('%Y-%m-%d')
        elif isinstance(date, date):
            date_str = date.strftime('%Y-%m-%d')
        elif isinstance(date, str):
            # 如果是字符串，尝试解析
            try:
                dt = pd.to_datetime(date, errors='coerce')
                if pd.notna(dt):
                    date_str = dt.strftime('%Y-%m-%d')
                else:
                    # 可能是时间戳字符串，使用 safe_parse_datetime
                    dt = safe_parse_datetime(date)
                    if dt is not None and pd.notna(dt):
                        date_str = dt.strftime('%Y-%m-%d')
                    else:
                        continue  # 跳过无效日期
            except:
                continue  # 跳过无效日期
        else:
            # 其他类型，尝试转换
            try:
                dt = pd.to_datetime(date, errors='coerce')
                if pd.notna(dt):
                    date_str = dt.strftime('%Y-%m-%d')
                else:
                    continue
            except:
                continue
        # 处理 close 可能是列表的情况
        if isinstance(close, (list, tuple, np.ndarray)):
            # 如果是列表/数组，取第一个元素
            close = close[0] if len(close) > 0 else 0.0
        try:
            merged_data[date_str] = float(close)
        except (ValueError, TypeError) as e:
            print(f"⚠️ 更新缓存时转换价格失败: {close} (类型: {type(close)}), 错误: {e}")
            # 跳过无效数据
            continue
    
    # 转换为列表并排序
    sorted_dates = []
    try:
        # 打印调试信息
        if merged_data:
            sample_keys = list(merged_data.keys())[:5]
            print(f"🔍 [DEBUG update_cache] {symbol} merged_data 的键样例: {sample_keys}")
            print(f"   键的类型: {[type(k) for k in sample_keys]}")
        
        sorted_dates = sorted([pd.to_datetime(d) for d in merged_data.keys()])
    except Exception as e:
         print(f"⚠️ 更新缓存时日期排序失败: {e}")
         # 打印更多调试信息
         if merged_data:
             print(f"   merged_data 的键: {list(merged_data.keys())[:10]}")
         # 尝试使用 safe_parse_datetime 解析
         valid_dates = []
         for d in merged_data.keys():
             try:
                 dt = safe_parse_datetime(d)
                 if dt is not None and pd.notna(dt):
                     valid_dates.append(dt)
             except Exception as ex:
                 print(f"   ⚠️ 解析日期 '{d}' 失败: {ex}")
                 pass
         sorted_dates = sorted(valid_dates)

    sorted_closes = []
    for d in sorted_dates:
        d_str = d.strftime('%Y-%m-%d')
        if d_str in merged_data:
             sorted_closes.append(merged_data[d_str])
        else:
             # Fallback if strftime format doesn't match keys exactly (unlikely if keys loops worked)
             pass
    
    # 更新缓存
    cache[symbol] = {
        'dates': [d.strftime('%Y-%m-%d') for d in sorted_dates],
        'closes': sorted_closes,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    save_cache(cache)

def get_etf_history_with_fallback(symbol, period="daily", adjust="qfq", start_date=None, end_date=None, use_cache=True):
    """
    获取ETF历史数据（多数据源降级 + 缓存机制）
    
    Args:
        symbol: ETF代码
        period: 周期
        adjust: 复权方式
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        use_cache: 是否使用缓存（默认True）
    
    Returns:
        DataFrame
    """
    # ======================== 缓存检查 ========================
    cached_df = pd.DataFrame()
    cache_latest_date = None
    cache_earliest_date = None
    
    if use_cache:
        cached_df = get_cached_data(symbol)
        if not cached_df.empty:
            cached_df['日期'] = pd.to_datetime(cached_df['日期'])
            cached_df = cached_df.sort_values('日期')
            cache_earliest_date = cached_df['日期'].iloc[0]
            cache_latest_date = cached_df['日期'].iloc[-1]
            print(f"📦 缓存中找到 {symbol} 的数据，日期范围: {cache_earliest_date.strftime('%Y-%m-%d')} 至 {cache_latest_date.strftime('%Y-%m-%d')}，共 {len(cached_df)} 条")
            
            # 检查请求的数据范围是否完全在缓存中
            need_fetch = False
            if start_date:
                start_dt = pd.to_datetime(start_date)
                if start_dt < cache_earliest_date:
                    need_fetch = True  # 需要获取更早的数据
            if end_date:
                end_dt = pd.to_datetime(end_date)
                if end_dt > cache_latest_date:
                    need_fetch = True  # 需要获取更新的数据
            
            # 如果请求的数据范围完全在缓存中，直接返回缓存数据
            if not need_fetch and not cached_df.empty:
                result_df = cached_df.copy()
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    result_df = result_df[result_df['日期'] >= start_dt]
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    result_df = result_df[result_df['日期'] <= end_dt]
                print(f"✅ 请求的数据范围完全在缓存中，直接返回缓存数据: {symbol}")
                return result_df
    
    # 计算需要获取的日期范围（增量更新）
    fetch_start_date = None
    if cache_latest_date:
        # 从缓存最新日期的下一天开始获取
        fetch_start_date = (cache_latest_date + timedelta(days=1)).strftime('%Y-%m-%d')
        # 如果指定了start_date且早于缓存最早日期，需要获取更早的数据
        if start_date:
            start_dt = pd.to_datetime(start_date)
            if start_dt < cache_earliest_date:
                fetch_start_date = start_date
    elif start_date:
        fetch_start_date = start_date
    
    # ======================== akshare 优先 ========================
    # 优先使用东财接口
    new_hist = pd.DataFrame()
    try:
        # 如果有缓存，只获取增量数据；否则获取全部数据
        if fetch_start_date:
            # 增量更新：只获取新数据
            new_hist = ak.fund_etf_hist_em(symbol=symbol, period=period, start_date=fetch_start_date, end_date=end_date, adjust=adjust)
            if not new_hist.empty:
                print(f"✅ 使用 akshare(东财) 接口获取增量数据: {symbol} (从 {fetch_start_date} 开始)")
        else:
            # 首次获取或缓存无效：获取全部数据
            if start_date and end_date:
                new_hist = ak.fund_etf_hist_em(symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust=adjust)
            else:
                new_hist = ak.fund_etf_hist_em(symbol=symbol, period=period, adjust=adjust)
            if not new_hist.empty:
                print(f"✅ 使用 akshare(东财) 接口获取历史数据: {symbol}")
        
        # 处理返回的数据
        if not new_hist.empty:
            # 确保列名正确
            if '日期' not in new_hist.columns:
                # 尝试重命名
                for col in new_hist.columns:
                    if 'date' in col.lower() or '日期' in str(col):
                        new_hist = new_hist.rename(columns={col: '日期'})
                        break
            if '收盘' not in new_hist.columns:
                for col in new_hist.columns:
                    if 'close' in col.lower() or '收盘' in str(col):
                        new_hist = new_hist.rename(columns={col: '收盘'})
                        break
            
            if '日期' in new_hist.columns and '收盘' in new_hist.columns:
                # 使用安全的日期解析函数
                new_hist['日期'] = new_hist['日期'].apply(safe_parse_datetime)
                # 过滤掉无效日期
                new_hist = new_hist[new_hist['日期'].notna()]
                new_hist = new_hist.sort_values('日期')
                
                # 合并缓存数据和新数据
                if not cached_df.empty:
                    # 合并数据，去重（保留新数据）
                    combined_df = pd.concat([cached_df, new_hist], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=['日期'], keep='last')
                    combined_df = combined_df.sort_values('日期')
                    
                    # 更新缓存
                    if use_cache:
                        update_cache(symbol, combined_df)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        combined_df = combined_df[combined_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        combined_df = combined_df[combined_df['日期'] <= end_dt]
                    
                    return combined_df
                else:
                    # 没有缓存，直接使用新数据并更新缓存
                    if use_cache:
                        update_cache(symbol, new_hist)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        new_hist = new_hist[new_hist['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        new_hist = new_hist[new_hist['日期'] <= end_dt]
                    
                    return new_hist
    except Exception as e:
        print(f"⚠️ akshare(东财) 接口失败: {e}，尝试新浪接口...")
    
    # 降级到新浪接口
    new_hist = pd.DataFrame()
    try:
        # 新浪接口需要转换代码格式：159915 -> sz159915 或 sh510300
        if symbol.startswith('15') or symbol.startswith('16'):
            sina_symbol = f"sz{symbol}"
        else:
            sina_symbol = f"sh{symbol}"
        
        # 使用正确的函数名
        new_hist = ak.fund_etf_hist_sina(symbol=sina_symbol)
        
        if not new_hist.empty:
            # 打印原始数据用于调试
            print(f"🔍 [DEBUG 新浪接口] {symbol} 原始数据:")
            print(f"   列名: {list(new_hist.columns)}")
            print(f"   数据形状: {new_hist.shape}")
            if len(new_hist) > 0:
                # 找到日期列
                date_col_name = None
                for col in new_hist.columns:
                    if 'date' in col.lower() or '日期' in str(col) or 'time' in col.lower() or '时间' in str(col):
                        date_col_name = col
                        break
                if date_col_name:
                    print(f"   日期列名: {date_col_name}")
                    print(f"   日期列前5个值: {new_hist[date_col_name].head(5).tolist()}")
                    print(f"   日期列数据类型: {new_hist[date_col_name].dtype}")
                    print(f"   日期列第一个值的类型: {type(new_hist[date_col_name].iloc[0])}")
                    print(f"   日期列第一个值的值: {repr(new_hist[date_col_name].iloc[0])}")
        
        if not new_hist.empty:
            # Rename columns if needed
            column_mapping = {}
            for col in new_hist.columns:
                if 'date' in col.lower() or '日期' in col: column_mapping[col] = '日期'
                elif 'close' in col.lower() or '收盘' in col: column_mapping[col] = '收盘'
                elif 'open' in col.lower() or '开盘' in col: column_mapping[col] = '开盘'
                elif 'high' in col.lower() or '最高' in col: column_mapping[col] = '最高'
                elif 'low' in col.lower() or '最低' in col: column_mapping[col] = '最低'
                elif 'volume' in col.lower() or '成交量' in col: column_mapping[col] = '成交量'
            
            if column_mapping: 
                new_hist = new_hist.rename(columns=column_mapping)
            
            if '日期' in new_hist.columns and '收盘' in new_hist.columns:
                # 使用安全的日期解析函数
                new_hist['日期'] = new_hist['日期'].apply(safe_parse_datetime)
                # 过滤掉无效日期
                new_hist = new_hist[new_hist['日期'].notna()]
                new_hist = new_hist.sort_values('日期')
                
                # 如果有缓存，只保留增量数据
                if not cached_df.empty and cache_latest_date:
                    new_hist = new_hist[new_hist['日期'] > cache_latest_date]
                    if not new_hist.empty:
                        print(f"✅ 使用 akshare(新浪) 接口获取增量数据: {symbol} ({sina_symbol})")
                    else:
                        print(f"ℹ️  akshare(新浪) 接口无新数据，使用缓存: {symbol}")
                        # 筛选日期范围后返回缓存
                        result_df = cached_df.copy()
                        # 确保缓存数据包含必需的列
                        if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                            print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                            return pd.DataFrame()
                        if start_date:
                            start_dt = pd.to_datetime(start_date)
                            result_df = result_df[result_df['日期'] >= start_dt]
                        if end_date:
                            end_dt = pd.to_datetime(end_date)
                            result_df = result_df[result_df['日期'] <= end_dt]
                        return result_df
                else:
                    print(f"✅ 使用 akshare(新浪) 接口获取历史数据: {symbol} ({sina_symbol})")
                
                # 合并缓存数据和新数据
                if not cached_df.empty and not new_hist.empty:
                    combined_df = pd.concat([cached_df, new_hist], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=['日期'], keep='last')
                    combined_df = combined_df.sort_values('日期')
                    
                    if use_cache:
                        update_cache(symbol, combined_df)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        combined_df = combined_df[combined_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        combined_df = combined_df[combined_df['日期'] <= end_dt]
                    
                    return combined_df
                elif not new_hist.empty:
                    if use_cache:
                        update_cache(symbol, new_hist)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        new_hist = new_hist[new_hist['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        new_hist = new_hist[new_hist['日期'] <= end_dt]
                    
                    return new_hist
                elif not cached_df.empty:
                    # 新数据为空，返回缓存
                    result_df = cached_df.copy()
                    # 确保缓存数据包含必需的列
                    if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                        print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                        return pd.DataFrame()
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        result_df = result_df[result_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        result_df = result_df[result_df['日期'] <= end_dt]
                    return result_df
        else:
            # 新浪接口返回空数据，如果有缓存则返回缓存
            if not cached_df.empty:
                print(f"⚠️ akshare(新浪) 接口返回空数据: {symbol}，使用缓存数据")
                result_df = cached_df.copy()
                # 确保缓存数据包含必需的列
                if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                    print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                    return pd.DataFrame()
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    result_df = result_df[result_df['日期'] >= start_dt]
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    result_df = result_df[result_df['日期'] <= end_dt]
                return result_df
            print(f"⚠️ akshare(新浪) 接口返回空数据: {symbol}，尝试 efinance...")
    except Exception as e2:
        print(f"⚠️ akshare(新浪) 接口也失败: {e2}，尝试 efinance...")
    
    # ======================== efinance 备选 ========================
    if EFINANCE_AVAILABLE:
        try:
            # efinance 需要转换代码格式：159915 -> 159915(无需后缀，但基金需要区分)
            if symbol.startswith('15') or symbol.startswith('16'):
                 ef_symbol = symbol 
            elif symbol.startswith('50') or symbol.startswith('51') or symbol.startswith('56') or symbol.startswith('58'):
                 ef_symbol = symbol
            else:
                 ef_symbol = symbol

            # 尝试获取（增加重试机制）
            max_retries = 3
            hist = None
            last_error = None
            
            for attempt in range(max_retries):
                hist = None
                try:
                    # 方法1: 尝试使用 stock 模块（不带前缀）
                    try:
                        hist = ef.stock.get_quote_history(ef_symbol)
                        if hist is not None and not hist.empty:
                            break
                    except Exception as e1:
                        last_error = e1
                    
                    # 方法2: 尝试使用 fund 模块（如果存在）
                    if hist is None or hist.empty:
                        try:
                            if hasattr(ef, 'fund') and hasattr(ef.fund, 'get_quote_history'):
                                hist = ef.fund.get_quote_history(ef_symbol)
                                if hist is not None and not hist.empty:
                                    break
                        except Exception as e2:
                            last_error = e2
                    
                    # 方法3: 尝试添加市场前缀
                    if hist is None or hist.empty:
                        if symbol.startswith('15') or symbol.startswith('16'):
                            prefixed_symbol = f"sz{symbol}"
                        else:
                            prefixed_symbol = f"sh{symbol}"
                        
                        try:
                            hist = ef.stock.get_quote_history(prefixed_symbol)
                            if hist is not None and not hist.empty:
                                break
                        except Exception as e3:
                            last_error = e3
                    
                    # 如果所有方法都失败，且不是最后一次尝试，继续重试
                    if (hist is None or hist.empty) and attempt < max_retries - 1:
                        time.sleep(1 + attempt)  # 失败后等待 1s, 2s...
                        print(f"   Using efinance retry {attempt+1}/{max_retries} for {symbol}...")
                        continue
                    elif hist is None or hist.empty:
                        # 最后一次尝试也失败，抛出异常
                        error_msg = str(last_error) if last_error else "未知错误"
                        raise Exception(f"efinance 无法获取 {symbol} 的数据: {error_msg}")
                        
                except Exception as e_retry:
                    if attempt < max_retries - 1:
                        time.sleep(1 + attempt)
                        print(f"   Using efinance retry {attempt+1}/{max_retries} for {symbol}...")
                    else:
                        raise e_retry
            
            if hist is not None and not hist.empty:
                # 打印原始数据用于调试
                print(f"🔍 [DEBUG efinance接口] {symbol} 原始数据:")
                print(f"   列名: {list(hist.columns)}")
                print(f"   数据形状: {hist.shape}")
                if len(hist) > 0:
                    # 找到日期列
                    date_col_name = None
                    for col in hist.columns:
                        if '日期' in str(col) or 'date' in str(col).lower() or '时间' in str(col) or 'time' in str(col).lower():
                            date_col_name = col
                            break
                    if date_col_name:
                        print(f"   日期列名: {date_col_name}")
                        print(f"   日期列前5个值: {hist[date_col_name].head(5).tolist()}")
                        print(f"   日期列数据类型: {hist[date_col_name].dtype}")
                        print(f"   日期列第一个值的类型: {type(hist[date_col_name].iloc[0])}")
                        print(f"   日期列第一个值的值: {repr(hist[date_col_name].iloc[0])}")
                
                # efinance 返回的列名可能是：日期、收盘、开盘、最高、最低、成交量
                # 但也可能是其他格式，需要智能识别
                actual_columns = list(hist.columns)
                column_mapping = {}
                
                # 智能识别列名（支持多种可能的列名格式）
                for col in actual_columns:
                    col_str = str(col).strip()
                    col_lower = col_str.lower()
                    
                    # 日期列识别
                    if '日期' in col_str or 'date' in col_lower or '时间' in col_str or 'time' in col_lower:
                        if col_str != '日期':
                            column_mapping[col] = '日期'
                    # 收盘价列识别（基金使用"单位净值"）
                    elif '收盘' in col_str or 'close' in col_lower or '收盘价' in col_str or '单位净值' in col_str or '净值' in col_str:
                        if col_str != '收盘':
                            column_mapping[col] = '收盘'
                    # 开盘价列识别
                    elif '开盘' in col_str or 'open' in col_lower or '开盘价' in col_str:
                        if col_str != '开盘':
                            column_mapping[col] = '开盘'
                    # 最高价列识别
                    elif '最高' in col_str or 'high' in col_lower or '最高价' in col_str:
                        if col_str != '最高':
                            column_mapping[col] = '最高'
                    # 最低价列识别
                    elif '最低' in col_str or 'low' in col_lower or '最低价' in col_str:
                        if col_str != '最低':
                            column_mapping[col] = '最低'
                    # 成交量列识别
                    elif '成交量' in col_str or 'volume' in col_lower or 'vol' in col_lower or '成交' in col_str:
                        if col_str != '成交量':
                            column_mapping[col] = '成交量'
                
                # 执行列名重映射
                if column_mapping:
                    hist = hist.rename(columns=column_mapping)
                
                # 检查必需的列是否存在
                required_cols = ['日期', '收盘']
                missing_cols = [col for col in required_cols if col not in hist.columns]
                if missing_cols:
                    print(f"⚠️ efinance 返回数据缺少必需列: {missing_cols}，返回空数据")
                    return pd.DataFrame()
                
                # 确保日期列是datetime类型
                if '日期' in hist.columns:
                    # 使用安全的日期解析函数
                    hist['日期'] = hist['日期'].apply(safe_parse_datetime)
                    # 过滤掉无效日期
                    hist = hist[hist['日期'].notna()]
                    hist = hist.sort_values('日期')
                
                # 如果有缓存，只保留增量数据
                if not cached_df.empty and cache_latest_date:
                    hist = hist[hist['日期'] > cache_latest_date]
                    if not hist.empty:
                        print(f"✅ 使用 efinance 接口获取增量数据: {symbol}")
                    else:
                        print(f"ℹ️  efinance 接口无新数据，使用缓存: {symbol}")
                        # 返回缓存数据
                        result_df = cached_df.copy()
                        # 确保缓存数据包含必需的列
                        if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                            print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                            return pd.DataFrame()
                        if start_date:
                            start_dt = pd.to_datetime(start_date)
                            result_df = result_df[result_df['日期'] >= start_dt]
                        if end_date:
                            end_dt = pd.to_datetime(end_date)
                            result_df = result_df[result_df['日期'] <= end_dt]
                        return result_df
                else:
                    print(f"✅ 使用 efinance 接口获取历史数据: {symbol}")
                
                # 合并缓存数据和新数据
                if not cached_df.empty and not hist.empty:
                    combined_df = pd.concat([cached_df, hist], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=['日期'], keep='last')
                    combined_df = combined_df.sort_values('日期')
                    
                    if use_cache:
                        update_cache(symbol, combined_df)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        combined_df = combined_df[combined_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        combined_df = combined_df[combined_df['日期'] <= end_dt]
                    
                    return combined_df
                elif not hist.empty:
                    if use_cache:
                        update_cache(symbol, hist)
                    
                    # 筛选日期范围
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        hist = hist[hist['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        hist = hist[hist['日期'] <= end_dt]
                    
                    return hist
                elif not cached_df.empty:
                    # 新数据为空，返回缓存
                    result_df = cached_df.copy()
                    # 确保缓存数据包含必需的列
                    if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                        print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                        return pd.DataFrame()
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        result_df = result_df[result_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        result_df = result_df[result_df['日期'] <= end_dt]
                    return result_df
            else:
                # efinance 返回空数据，如果有缓存则返回缓存
                if not cached_df.empty:
                    print(f"⚠️ efinance 接口返回空数据: {symbol}，使用缓存数据")
                    result_df = cached_df.copy()
                    # 确保缓存数据包含必需的列
                    if '日期' not in result_df.columns or '收盘' not in result_df.columns:
                        print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
                        return pd.DataFrame()
                    if start_date:
                        start_dt = pd.to_datetime(start_date)
                        result_df = result_df[result_df['日期'] >= start_dt]
                    if end_date:
                        end_dt = pd.to_datetime(end_date)
                        result_df = result_df[result_df['日期'] <= end_dt]
                    return result_df
                print(f"⚠️ efinance 接口返回空数据: {symbol}")
                return pd.DataFrame()
        except Exception as e3:
            error_msg = str(e3)
            if "Connection" in error_msg:
                 print(f"⚠️ efinance 接口连接失败")
            else:
                 print(f"⚠️ efinance 接口失败: {e3}")
    
    # 所有接口都失败，如果有缓存则返回缓存
    if not cached_df.empty:
        print(f"⚠️ 所有接口都失败，使用缓存数据: {symbol}")
        result_df = cached_df.copy()
        # 确保缓存数据包含必需的列
        if '日期' not in result_df.columns or '收盘' not in result_df.columns:
            print(f"⚠️ 缓存数据格式错误，缺少必需列。实际列名: {list(result_df.columns)}")
            return pd.DataFrame()
        if start_date:
            start_dt = pd.to_datetime(start_date)
            result_df = result_df[result_df['日期'] >= start_dt]
        if end_date:
            end_dt = pd.to_datetime(end_date)
            result_df = result_df[result_df['日期'] <= end_dt]
        return result_df
    
    return pd.DataFrame()

def get_entry_price_from_history(symbol, entry_date):
    """从历史数据获取指定日期的买入价格"""
    try:
        hist = get_etf_history_with_fallback(symbol=symbol, period="daily", adjust="qfq")
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

def update_holding_price_if_needed(holding_data, pool_name="core"):
    """如果入场价格为空，从历史数据补全"""
    # 必须有代码才有必要补全价格
    code = holding_data["current_holding"].get("code")
    if code and holding_data["current_holding"]["entry_price"] is None:
        entry_date = holding_data["current_holding"]["entry_date"]
        # 确保 entry_date 存在
        if not entry_date:
            return holding_data
            
        entry_price = get_entry_price_from_history(code, entry_date)
        if entry_price:
            holding_data["current_holding"]["entry_price"] = float(entry_price)
            save_holding(holding_data, pool_name)
            print(f"✅ 已补全入场价格: {code} 在 {entry_date} 的买入价为 {entry_price:.3f}")
    return holding_data

# ======================== 核心逻辑 ========================

def get_realtime_data(codes=None):
    """
    获取实时快照并记录时间（多数据源降级）
    Args:
        codes: list, 可选，指定需要获取的ETF代码列表（不带后缀）
    """
    # ======================== akshare 优先 ========================
    # 优先使用东财接口
    try:
        df_spot = ak.fund_etf_spot_em()
        fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("✅ 使用 akshare(东财) 接口获取实时数据")
        return df_spot, fetch_time
    except Exception as e:
        print(f"⚠️ akshare(东财) 接口失败: {e}，尝试腾讯接口...")
        # 降级到腾讯接口
        try:
            # 腾讯接口返回的是股票数据，但也包含ETF
            df_spot = ak.stock_zh_a_spot_em()
            # 需要过滤出ETF代码（根据ETF池中的代码）
            fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("✅ 使用 akshare(腾讯) 接口获取实时数据")
            return df_spot, fetch_time
        except Exception as e2:
            print(f"⚠️ akshare(腾讯) 接口也失败: {e2}，尝试 efinance...")
    
    # ======================== efinance 备选 ========================
    if EFINANCE_AVAILABLE:
        try:
            # 构造查询列表：efinance 最好传入具体代码列表以提高稳定性和速度
            target_codes = None
            if codes:
                target_codes = list(codes)
            
            df_spot = ef.stock.get_latest_quote(target_codes)
            
            if df_spot is not None and isinstance(df_spot, pd.DataFrame) and not df_spot.empty:
                column_mapping = {
                    '股票代码': '代码',
                    '股票名称': '名称',
                    '最新价': '最新价',
                    '涨跌幅': '涨跌幅',
                    '成交量': '成交量',
                    '成交额': '成交额',
                }
                
                df_spot = df_spot.rename(columns=column_mapping)
                
                fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("✅ 使用 efinance 接口获取实时数据")
                return df_spot, fetch_time
            else:
                 print(f"⚠️ efinance 实时数据为空 (codes={target_codes})")

        except Exception as e:
            print(f"⚠️ efinance 实时接口失败: {e}")
    
    return None, None

def get_price_from_spot(df_spot, symbol, fallback_price=None):
    """从实时数据中安全获取价格，如果失败则返回备选价格"""
    if df_spot is None:
        return fallback_price
    
    spot_row = df_spot[df_spot['代码'] == symbol]
    if not spot_row.empty:
        return spot_row['最新价'].values[0]
    
    return fallback_price

def calculate_momentum(prices, debug=False, symbol=""):
    """复刻 JoinQuant 动量算法
    返回: (score, r2, annualized_return) 元组
    """
    # 确保 prices 是 numpy 数组且不为空
    if not isinstance(prices, np.ndarray):
        prices = np.array(prices)
    
    # 检查数组是否为空或只有一个元素
    if len(prices) < 2:
        if debug:
            print(f"      [DEBUG {symbol}] 动量计算: 价格序列长度不足 ({len(prices)} < 2)，返回 0")
        return 0.0, 0.0, 0.0
    
    # 确保所有价格都是正数（对数需要正数）
    if np.any(prices <= 0):
        if debug:
            print(f"      [DEBUG {symbol}] 动量计算: 价格序列包含非正数，返回 0")
        return 0.0, 0.0, 0.0
    
    # 转换为浮点数数组，确保类型正确
    prices = prices.astype(float)
    
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

def run_strategy(pool_name="full", debug=False):
    # 加载持仓记录（使用对应pool_name的文件）
    holding_data = load_holding(pool_name)
    if holding_data is None:
        holding_data = initialize_holding()
        save_holding(holding_data, pool_name)
        print(f"✅ 已初始化持仓记录（使用文件: etf_holding_{pool_name}.json）")
    
    # 补全入场价格
    holding_data = update_holding_price_if_needed(holding_data, pool_name)
    
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
    
    # 显示当前持仓信息
    if CURRENT_HOLDING:
        holding_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
        entry_price_display = f"{entry_price:.3f}" if entry_price else "N/A"
        print(f"📦 当前持仓: {holding_name}({CURRENT_HOLDING}) | 数量: {entry_quantity} | 入场价: {entry_price_display}")
    
    # 1. 获取行情
    # 提取所有需要查询的代码
    pool_codes = list(etf_pool.keys())
    df_spot, data_time = get_realtime_data(pool_codes)
    print(f"📊 交易所行情时间: {data_time}")
    print("-" * 60)
    
    # 检查实时数据是否获取成功
    if df_spot is None:
        print("⚠️ 警告：无法获取实时行情数据，将使用历史数据的最新收盘价作为备选方案")
        print("   注意：此模式下计算结果可能不够准确，建议在网络正常时重新运行")
    else:
        # 打印实时数据调试信息
        print(f"✅ 实时数据获取成功，共 {len(df_spot)} 条记录")
        if '代码' in df_spot.columns:
            print(f"🔍 实时数据中的代码样例: {df_spot['代码'].head(10).tolist()}")
        else:
            print(f"⚠️ 警告：实时数据中没有'代码'列，实际列名: {list(df_spot.columns)}")

    results = []
    positive_count = 0

    for symbol, name in etf_pool.items():
        # 获取历史数据（前复权）
        # 不指定 start_date，让函数自动处理增量更新：
        # - 如果缓存存在，只获取从缓存最新日期到今天的数据（增量更新）
        # - 如果缓存不存在，函数会获取全部数据，但我们在使用时会只取最近40天
        try:
            hist = get_etf_history_with_fallback(symbol=symbol, period="daily", adjust="qfq")
            if not hist.empty:
                # 只使用最近40天的数据进行计算
                hist = hist.tail(40)
            
            # 获取当前价格：优先使用实时数据，失败则使用历史数据
            current_price = None
            price_source = None
            if df_spot is not None:
                # 尝试精确匹配
                spot_row = df_spot[df_spot['代码'] == symbol]
                if not spot_row.empty:
                    current_price = spot_row['最新价'].values[0]
                    price_source = "实时数据"
                else:
                    # 尝试模糊匹配（可能代码格式不同）
                    # 检查是否有带后缀的代码（如 sz159915, sh510300）
                    for code_variant in [f"sz{symbol}", f"sh{symbol}", symbol]:
                        spot_row = df_spot[df_spot['代码'] == code_variant]
                        if not spot_row.empty:
                            current_price = spot_row['最新价'].values[0]
                            price_source = f"实时数据(匹配到: {code_variant})"
                            break
                    
                    # 如果还是找不到，尝试部分匹配
                    if current_price is None and '代码' in df_spot.columns:
                        # 检查代码列是否包含 symbol
                        mask = df_spot['代码'].astype(str).str.contains(symbol, regex=False)
                        if mask.any():
                            spot_row = df_spot[mask]
                            if not spot_row.empty:
                                current_price = spot_row['最新价'].values[0]
                                matched_code = spot_row['代码'].values[0]
                                price_source = f"实时数据(部分匹配到: {matched_code})"
            
            # 如果实时数据不可用，使用历史数据的最新收盘价
            if current_price is None:
                if hist.empty or '收盘' not in hist.columns:
                    print(f"⚠️ 警告：{name}({symbol}) 无法获取价格数据（历史数据为空或缺少'收盘'列），跳过。")
                    if not hist.empty:
                        print(f"   历史数据列名: {list(hist.columns)}")
                    continue
                current_price = hist['收盘'].iloc[-1]
                price_source = "历史收盘价(备选)"
                print(f"⚠️  {name}({symbol}) 无法从实时数据获取价格，使用历史收盘价: {current_price:.3f}")
            else:
                print(f"✅ {name}({symbol}) 使用{price_source}: {current_price:.3f}")
            
            # 检查历史数据是否有效
            if hist.empty or '收盘' not in hist.columns:
                print(f"⚠️ 警告：{name}({symbol}) 历史数据无效（为空或缺少'收盘'列），跳过。")
                if not hist.empty:
                    print(f"   历史数据列名: {list(hist.columns)}")
                continue
            
            if debug:
                print(f"\n{'='*60}")
                print(f"🔍 [DEBUG] 计算 {name}({symbol}) 的得分")
                print(f"{'='*60}")
                print(f"历史收盘价序列(最后10个): {hist['收盘'].values[-10:]}")
                print(f"实时价格: {current_price}")
            
            # 拼接实时价格进行指标计算
            hist_closes = hist['收盘'].values[:-1]  # 去掉最后一条（昨天的收盘价）
            prices = np.append(hist_closes, current_price)
            
            if debug:
                print(f"拼接后价格序列(最后10个): {prices[-10:]}")
                print(f"价格序列总长度: {len(prices)}")
            
            # 检查数据是否足够
            min_required_days = max(STRATEGY_CONF["ma_filter_days"], 5)  # 至少需要20天（MA20）或5天（5日涨跌）
            if len(prices) < min_required_days:
                print(f"⚠️ 警告：{name}({symbol}) 价格序列长度不足 ({len(prices)} < {min_required_days})，无法计算指标，跳过。")
                # 仍然添加到结果中，但使用默认值
                results.append({
                    "代码": symbol, "名称": name, "价格": current_price,
                    "MA20": np.nan, "5日涨跌": "nan%",
                    "波动率": "nan%",
                    "状态": "📉破位",
                    "得分": 0.0,
                    "r2": 0.0,
                    "年化收益率": 0.0
                })
                continue
            
            # 指标计算
            ma20 = np.mean(prices[-STRATEGY_CONF["ma_filter_days"]:])
            if len(prices) >= 5:
                short_ret = (prices[-1] / prices[-5]) - 1
            else:
                short_ret = 0.0
            
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
                # 确保 momentum_prices 是数组且长度足够
                if len(momentum_prices) < STRATEGY_CONF["m_days"]:
                    if debug:
                        print(f"\n⚠️ 动量计算: 价格序列长度不足 ({len(momentum_prices)} < {STRATEGY_CONF['m_days']})，跳过动量计算")
                    score, r2, annualized_return = 0, 0, 0
                else:
                    if debug:
                        print(f"\n动量计算:")
                        print(f"  使用最近{STRATEGY_CONF['m_days']}天的价格计算动量")
                    score, r2, annualized_return = calculate_momentum(momentum_prices, debug=debug, symbol=symbol)
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
        
        
        # 增加延时，避免触发接口频率限制 (从 0.3s 增加到 0.8s)
        time.sleep(0.8)

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
        save_holding(holding_data, pool_name)
        
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
            save_holding(holding_data, pool_name)
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
            save_holding(holding_data, pool_name)
        else:
            print("⚪ 信号提示：目前无合适入场标的。指令：【继续观望】")
            
    else:
        # 正常轮动逻辑
        if CURRENT_HOLDING == top_code:
            # 检查是否需要调整仓位（波动率控仓）
            current_holding_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
            if current_holding_price is not None:
                if entry_price:
                    pnl_ratio = (current_holding_price / entry_price) - 1
                    pnl_amount = (current_holding_price - entry_price) * entry_quantity
                    print(f"💎 策略保持：当前持仓 {etf_pool.get(top_code, top_code)} 排名第一。")
                    print(f"   📊 持仓盈亏: {pnl_ratio:.2%} | 盈亏金额: {pnl_amount:.2f}元")
                    
                    # 波动率控仓提示
                    if top_volatility > STRATEGY_CONF["volatility_threshold"]:
                        print(f"   ⚠️ 波动率警告: {top_volatility:.2%} > {STRATEGY_CONF['volatility_threshold']:.2%}，建议仓位减半至 {suggested_quantity} 份")
                    else:
                        print(f"   ✅ 波动率正常: {top_volatility:.2%}，建议保持当前仓位 {entry_quantity} 份")
                else:
                    print(f"💎 策略保持：当前持仓 {etf_pool.get(top_code, top_code)} 排名第一。指令：【坚定持有】")
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            if CURRENT_HOLDING:
                current_name = etf_pool.get(CURRENT_HOLDING, current_holding.get("name", CURRENT_HOLDING))
                current_price = get_price_from_spot(df_spot, CURRENT_HOLDING, entry_price)
                
                if current_price is None:
                    print(f"⚠️ 警告：无法获取 {current_name}({CURRENT_HOLDING}) 的卖出价格，使用入场价 {entry_price:.3f} 估算")
                    current_price = entry_price if entry_price else 0
                
                # 计算卖出盈亏
                if entry_price:
                    sell_pnl = (current_price / entry_price - 1) * entry_quantity * entry_price
                    print(f"🔄 调仓动作：")
                    print(f"   卖出: {current_name}({CURRENT_HOLDING}) 在 {STRATEGY_CONF['sell_time']}，价格: {current_price:.3f}，数量: {entry_quantity}")
                    if entry_price:
                        print(f"   卖出盈亏: {(current_price/entry_price-1):.2%} | 盈亏金额: {sell_pnl:.2f}元")
                
                # 记录卖出交易
                holding_data["trade_history"].append({
                    "date": today,
                    "time": STRATEGY_CONF["sell_time"],
                    "action": "卖出",
                    "code": CURRENT_HOLDING,
                    "name": current_name,
                    "price": current_price,
                    "quantity": entry_quantity,
                    "reason": "轮动调仓"
                })
            else:
                print(f"🛒 开仓信号：")
            
            # 买入新标的
            top_price = top_target['价格']
            vol_warning = ""
            if top_volatility > STRATEGY_CONF["volatility_threshold"]:
                vol_warning = f" | ⚠️ 波动率 {top_volatility:.2%} 超过阈值，仓位减半至 {suggested_quantity} 份"
            
            print(f"   买入: {top_target['名称']}({top_code}) 在 {STRATEGY_CONF['buy_time']}，价格: {top_price:.3f}，数量: {suggested_quantity}{vol_warning}")
            
            # 记录买入交易并更新持仓
            holding_data["trade_history"].append({
                "date": today,
                "time": STRATEGY_CONF["buy_time"],
                "action": "买入",
                "code": top_code,
                "name": top_target['名称'],
                "price": top_price,
                "quantity": suggested_quantity,
                "reason": "轮动调仓" if CURRENT_HOLDING else "开仓"
            })
            
            holding_data["current_holding"] = {
                "code": top_code,
                "name": top_target['名称'],
                "quantity": suggested_quantity,
                "entry_price": top_price,
                "entry_date": today,
                "entry_time": STRATEGY_CONF["buy_time"]
            }
            holding_data["last_update_date"] = today
            holding_data["last_update_date"] = today
            save_holding(holding_data, pool_name)

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
    holding_data = backfill_daily_log(holding_data, pool_name)
    # 再更新今日
    holding_data = record_daily_status(holding_data, record_price, record_score, record_r2, record_annualized_return, pool_scores_dict)
    save_holding(holding_data, pool_name)
    
    # 显示记录信息
    last_log = holding_data['daily_log'][-1]
    score_info = f" | 得分: {last_log['score']:.4f}" if last_log.get('score') is not None else " | 得分: N/A"
    pool_scores_count = len([s for s in last_log.get('pool_scores', {}).values() if s is not None]) if last_log.get('pool_scores') else 0
    pool_info = f" | 池子得分: {pool_scores_count}/{len(etf_pool)}" if last_log.get('pool_scores') else ""
    print(f"📝 每日记录已更新: {last_log['date']} 市值: {last_log['market_value']}{score_info}{pool_info}")

    print("="*60)

def debug_historical_date(target_date_str, pool_name="core"):
    """调试指定历史日期的得分计算"""
    print(f"\n{'='*60}")
    print(f"🔍 调试历史日期: {target_date_str}")
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
            # 获取历史数据
            hist = get_etf_history_with_fallback(symbol=symbol, period="daily", adjust="qfq")
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
                score, r2, annualized_return = calculate_momentum(momentum_prices, debug=True, symbol=symbol)
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
    parser.add_argument('--pool', type=str, default='core', help='选择ETF池: full (全量), core (核心)')
    parser.add_argument('--debug', action='store_true', help='开启调试模式，显示详细计算过程')
    parser.add_argument('--debug-date', type=str, help='调试指定历史日期，格式: YYYY-MM-DD，例如: 2026-01-15')
    args = parser.parse_args()
    
    if args.debug_date:
        debug_historical_date(args.debug_date, args.pool)
    else:
        run_strategy(args.pool, debug=args.debug)
