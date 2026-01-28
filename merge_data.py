#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将 data copy.txt 中的数据合并到 data.txt 中，按天进行合并
"""

import re
from collections import defaultdict

def parse_data_copy_file(filepath):
    """解析 data copy.txt 文件，提取每天的ETF数据"""
    daily_data = defaultdict(list)
    current_date = None
    in_data_section = False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 提取日期
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', line)
            if date_match:
                current_date = date_match.group(1)
            
            # 检查是否是表头行
            if 'DATE,CODE,NAME' in line:
                in_data_section = True
                continue
            
            # 检查是否是 DATA_START
            if 'DATA_START' in line:
                in_data_section = True
                continue
            
            # 检查是否是 DATA_END
            if 'DATA_END' in line:
                in_data_section = False
                continue
            
            # 检查是否是数据行（包含逗号分隔的数据）
            if in_data_section and 'INFO' in line and ',' in line:
                # 提取数据部分（在 "INFO  - " 之后）
                if 'INFO  - ' in line:
                    data_part = line.split('INFO  - ')[1]
                    parts = data_part.split(',')
                    if len(parts) >= 8:  # DATE,CODE,NAME,OPEN,P1030,P1430,P1450,CLOSE
                        daily_data[current_date].append(parts)
    
    return daily_data

def merge_data_files(data_copy_path, data_path, output_path):
    """合并两个数据文件"""
    # 解析 data copy.txt
    print("正在解析 data copy.txt...")
    copy_data = parse_data_copy_file(data_copy_path)
    print(f"从 data copy.txt 中提取了 {len(copy_data)} 天的数据")
    
    # 读取 data.txt 并合并
    print("正在读取并合并 data.txt...")
    output_lines = []
    current_date = None
    in_data_section = False
    header_written = False
    
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            original_line = line
            line_stripped = line.strip()
            
            if not line_stripped:
                output_lines.append(line)
                continue
            
            # 提取日期
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', line_stripped)
            if date_match:
                current_date = date_match.group(1)
            
            # 处理 DATA_START
            if 'DATA_START' in line_stripped:
                in_data_section = True
                header_written = False
                output_lines.append(original_line)
                continue
            
            # 处理 DATA_END
            if 'DATA_END' in line_stripped:
                # 在 DATA_END 之前，添加 data copy.txt 中该日期的数据
                if current_date and current_date in copy_data:
                    for data_row in copy_data[current_date]:
                        # 将逗号分隔的数据转换为制表符分隔，并保持格式
                        # 格式：DATE	CODE	NAME	OPEN	P1030	P1430	P1450	CLOSE
                        date_str = current_date
                        timestamp = f"{date_str} 15:05:00 - INFO  - "
                        tab_separated = '\t'.join(data_row)
                        output_lines.append(f"{timestamp}{tab_separated}\n")
                
                output_lines.append(original_line)
                in_data_section = False
                continue
            
            # 处理表头
            if 'DATE' in line_stripped and 'CODE' in line_stripped and 'NAME' in line_stripped:
                if not header_written:
                    output_lines.append(original_line)
                    header_written = True
                continue
            
            # 处理数据行
            if in_data_section and 'INFO' in line_stripped:
                output_lines.append(original_line)
                continue
            
            # 其他行直接添加
            output_lines.append(original_line)
    
    # 写入输出文件
    print(f"正在写入合并后的数据到 {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)
    
    print(f"合并完成！共处理 {len(output_lines)} 行数据")

if __name__ == '__main__':
    data_copy_path = '/Users/a58/Documents/58/nope/data copy.txt'
    data_path = '/Users/a58/Documents/58/nope/data.txt'
    output_path = '/Users/a58/Documents/58/nope/data.txt'
    
    # 先备份原文件
    import shutil
    backup_path = '/Users/a58/Documents/58/nope/data_backup.txt'
    print(f"正在备份原文件到 {backup_path}...")
    shutil.copy2(data_path, backup_path)
    
    merge_data_files(data_copy_path, data_path, output_path)
    print("完成！")
