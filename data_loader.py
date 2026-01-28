"""
数据加载模块
负责解析 log.txt，将其转换为 Pandas DataFrame，并进行必要的预处理
"""
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import re


class DataLoader:
    """数据加载器类"""
    
    def __init__(self, log_file_path: Optional[str] = None):
        """
        初始化数据加载器
        
        Args:
            log_file_path: log.txt文件路径，如果为None则使用默认路径
        """
        if log_file_path is None:
            log_file_path = Path(__file__).parent / "log.txt"
        self.log_file_path = Path(log_file_path)
    
    def parse_log_file(self) -> pd.DataFrame:
        """
        解析log.txt文件，提取ETF数据（修复版）
        
        要求：
        1. 正确解析日志前缀格式
        2. 统一去掉 .XSHE 或 .XSHG 后缀，只保留6位数字代码
        3. 过滤掉所有 nan 值（标的未上市数据）
        
        Returns:
            DataFrame，包含以下列：
            - date: 日期
            - code: ETF代码（6位数字，去除交易所后缀）
            - name: ETF名称
            - open: 开盘价
            - p1030: 10:30价格
            - p1430: 14:30价格
            - p1450: 14:50价格
            - close: 收盘价
        """
        if not self.log_file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {self.log_file_path}")
        
        records = []
        current_date = None
        in_data_block = False
        
        # 正则表达式：匹配日志前缀 "2015-01-05 15:05:00 - INFO  - "
        log_prefix_pattern = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - INFO\s+- ')
        
        with open(self.log_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 检测数据块开始
                if 'DATA_START' in line:
                    in_data_block = True
                    # 从时间戳中提取日期
                    match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
                    if match:
                        current_date = match.group(1)
                    continue
                
                # 检测数据块结束
                if 'DATA_END' in line:
                    in_data_block = False
                    continue
                
                # 跳过表头行
                if 'DATE\tCODE' in line or not in_data_block:
                    continue
                
                # 解析数据行
                if current_date and in_data_block:
                    # 去掉日志前缀：使用正则表达式匹配并移除
                    data_line = log_prefix_pattern.sub('', line).strip()
                    
                    # 如果正则匹配失败，尝试字符串切割方法
                    if data_line == line and ' - ' in line:
                        parts = line.split(' - ')
                        if len(parts) >= 3:
                            data_line = parts[-1].strip()
                    
                    # 按制表符分割数据
                    parts = data_line.split('\t')
                    if len(parts) >= 8:
                        try:
                            # 提取日期（如果行中有日期则使用，否则使用块日期）
                            date_str = parts[0].strip() if parts[0].strip() else current_date
                            code_full = parts[1].strip()
                            name = parts[2].strip()
                            
                            # 清理代码：去除交易所后缀（.XSHE 或 .XSHG），只保留6位数字
                            if '.' in code_full:
                                code = code_full.split('.')[0]
                            else:
                                code = code_full
                            
                            # 确保代码是6位数字
                            if not code.isdigit() or len(code) != 6:
                                continue
                            
                            # 解析价格字段
                            def parse_price(val):
                                val_str = str(val).strip().lower()
                                if val_str == 'nan' or val_str == '' or val_str == 'none':
                                    return np.nan
                                try:
                                    price = float(val_str)
                                    # 过滤掉无效价格（<=0或过大）
                                    if price <= 0 or price > 10000:
                                        return np.nan
                                    return price
                                except (ValueError, TypeError):
                                    return np.nan
                            
                            open_price = parse_price(parts[3])
                            p1030 = parse_price(parts[4])
                            p1430 = parse_price(parts[5])
                            p1450 = parse_price(parts[6])
                            close_price = parse_price(parts[7]) if len(parts) > 7 else np.nan
                            
                            # 关键：过滤掉所有价格都是 nan 的记录（标的未上市）
                            if all(pd.isna([open_price, p1030, p1430, p1450, close_price])):
                                continue
                            
                            # 至少需要 close 价格不为空（用于因子计算）
                            if pd.isna(close_price):
                                continue
                            
                            record = {
                                'date': pd.to_datetime(date_str),
                                'code': code,
                                'name': name,
                                'open': open_price,
                                'p1030': p1030,
                                'p1430': p1430,
                                'p1450': p1450,
                                'close': close_price
                            }
                            
                            records.append(record)
                        except (IndexError, ValueError, Exception) as e:
                            # 跳过解析失败的行
                            continue
        
        if not records:
            raise ValueError("未能从日志文件中解析出任何数据")
        
        df = pd.DataFrame(records)
        
        # 按日期和代码排序
        df = df.sort_values(['date', 'code']).reset_index(drop=True)
        
        # 最终过滤：确保每条记录至少有一个有效价格
        # 这里我们已经在上面的循环中过滤了，但为了安全再检查一次
        df = df[df['close'].notna()].copy()
        
        return df
    
    def get_etf_data(self, code: str, start_date: Optional[str] = None, 
                     end_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取指定ETF的历史数据
        
        Args:
            code: ETF代码
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
        
        Returns:
            DataFrame，包含该ETF的历史数据
        """
        df = self.parse_log_file()
        
        # 过滤指定代码
        df = df[df['code'] == code].copy()
        
        # 日期过滤
        if start_date:
            start_dt = pd.to_datetime(start_date)
            df = df[df['date'] >= start_dt]
        
        if end_date:
            end_dt = pd.to_datetime(end_date)
            df = df[df['date'] <= end_dt]
        
        return df.reset_index(drop=True)
    
    def get_all_codes(self) -> List[str]:
        """
        获取所有ETF代码列表
        
        Returns:
            ETF代码列表
        """
        df = self.parse_log_file()
        return sorted(df['code'].unique().tolist())
    
    def get_trading_dates(self, start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> pd.DatetimeIndex:
        """
        获取交易日列表
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            交易日DatetimeIndex
        """
        df = self.parse_log_file()
        
        if start_date:
            start_dt = pd.to_datetime(start_date)
            df = df[df['date'] >= start_dt]
        
        if end_date:
            end_dt = pd.to_datetime(end_date)
            df = df[df['date'] <= end_dt]
        
        return pd.DatetimeIndex(sorted(df['date'].unique()))
    
    def get_price_at_time(self, code: str, date: str, time_point: str = 'close') -> float:
        """
        获取指定ETF在指定日期和时间点的价格
        
        Args:
            code: ETF代码
            date: 日期（格式：YYYY-MM-DD）
            time_point: 时间点，可选值：'open', 'p1030', 'p1430', 'p1450', 'close'
        
        Returns:
            价格，如果不存在则返回np.nan
        """
        df = self.get_etf_data(code, start_date=date, end_date=date)
        
        if df.empty:
            return np.nan
        
        target_date = pd.to_datetime(date)
        df_date = df[df['date'].dt.date == target_date.date()]
        
        if df_date.empty:
            return np.nan
        
        price_col = time_point if time_point in df.columns else 'close'
        price = df_date.iloc[0][price_col]
        
        return price if not pd.isna(price) else np.nan
    
    def get_pool_data(self, codes: List[str], start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        获取ETF池中所有ETF的数据
        
        Args:
            codes: ETF代码列表
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            字典，key为ETF代码，value为对应的DataFrame
        """
        pool_data = {}
        for code in codes:
            try:
                df = self.get_etf_data(code, start_date, end_date)
                if not df.empty:
                    pool_data[code] = df
            except Exception as e:
                print(f"警告：获取 {code} 数据失败: {e}")
        
        return pool_data


if __name__ == "__main__":
    # 测试代码
    loader = DataLoader()
    
    print("正在解析日志文件...")
    df = loader.parse_log_file()
    print(f"解析完成，共 {len(df)} 条记录")
    print(f"日期范围: {df['date'].min()} 至 {df['date'].max()}")
    print(f"ETF数量: {len(df['code'].unique())}")
    print("\n前5条记录:")
    print(df.head())
    
    print("\n所有ETF代码:")
    codes = loader.get_all_codes()
    print(codes[:10], "...")
    
    # 测试获取单个ETF数据
    if codes:
        test_code = codes[0]
        print(f"\n测试获取 {test_code} 的数据:")
        etf_df = loader.get_etf_data(test_code, start_date="2015-01-05", end_date="2015-01-10")
        print(etf_df.head())
