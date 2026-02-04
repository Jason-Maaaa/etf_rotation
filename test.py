import akshare as ak
import pandas as pd
import requests
import time

# ======================== 测试1：历史数据成交量 ========================
# 1. 准备代码：腾讯接口通常需要带 sh/sz 前缀
# 159915 是深交所，所以是 sz159915
symbol = "sz159915"

print("=" * 80)
print(f"🚀 --- 测试1：腾讯历史行情接口测试 ({symbol}) ---")
print("=" * 80)

try:
    # 调用腾讯历史行情接口
    # 注意：该接口通常返回全量历史数据，不支持直接传 start_date
    df_hist = ak.stock_zh_a_hist_tx(symbol=symbol)
    
    if df_hist is not None and not df_hist.empty:
        print("✅ 成功读取到腾讯历史数据！")
        print(f"\n[列名列表]: \n{df_hist.columns.tolist()}")
        
        print("\n[最近 5 行数据样例]:")
        # 腾讯接口返回的列名通常是：date, open, high, low, close, amount, volume
        print(df_hist.tail(5))
        
        # 检查日期类型
        print(f"\n日期列类型: {df_hist['date'].dtype}")
        
        # ========== 重点：检查成交量字段 ==========
        print("\n" + "-" * 80)
        print("📊 【成交量字段检查】")
        print("-" * 80)
        
        if 'volume' in df_hist.columns:
            print(f"✅ 历史数据包含 'volume' 字段（成交量）")
            print(f"   最近5天的成交量数据：")
            print(df_hist[['date', 'close', 'volume']].tail(5))
            print(f"\n   成交量统计信息：")
            print(f"   - 平均值: {df_hist['volume'].mean():.2f}")
            print(f"   - 最大值: {df_hist['volume'].max():.2f}")
            print(f"   - 最小值: {df_hist['volume'].min():.2f}")
            print(f"   - 最近5天平均成交量: {df_hist['volume'].tail(5).mean():.2f}")
        else:
            print("❌ 历史数据不包含 'volume' 字段")
            print(f"   可用字段: {df_hist.columns.tolist()}")
        
        # 检查是否有 amount（成交额）字段
        if 'amount' in df_hist.columns:
            print(f"\n✅ 历史数据包含 'amount' 字段（成交额）")
        else:
            print(f"\n⚠️ 历史数据不包含 'amount' 字段（成交额）")
    else:
        print("❌ 接口返回数据为空，请检查代码或网络。")

except Exception as e:
    print(f"❌ 腾讯历史接口测试报错: {e}")
    import traceback
    traceback.print_exc()

# ======================== 测试2：实时数据成交量 ========================
print("\n\n" + "=" * 80)
print(f"🚀 --- 测试2：腾讯实时行情接口测试（包含成交量字段） ---")
print("=" * 80)

try:
    # 测试单个标的的实时数据
    test_symbol = "sz159915"  # 创业板ETF
    url = f"http://qt.gtimg.cn/q={test_symbol}"
    
    print(f"请求URL: {url}")
    resp = requests.get(url, timeout=5)
    
    if resp.status_code == 200:
        print("✅ 成功获取实时数据！")
        
        # 解析腾讯原始文本数据
        lines = resp.text.split(';')
        print(f"\n原始响应文本（前200字符）: {resp.text[:200]}")
        
        for line in lines:
            if test_symbol in line:
                parts = line.split('~')
                print(f"\n[字段总数]: {len(parts)} 个字段")
                print(f"[完整字段列表]:")
                for i, part in enumerate(parts):
                    if i < 20:  # 只显示前20个字段
                        print(f"  parts[{i}]: {part}")
                    elif i == 20:
                        print(f"  ... (还有 {len(parts) - 20} 个字段)")
                        break
                
                # ========== 重点：解析成交量相关字段 ==========
                print("\n" + "-" * 80)
                print("📊 【实时数据成交量字段解析】")
                print("-" * 80)
                
                # 腾讯实时接口字段说明（根据常见格式）：
                # parts[0]: 股票代码（带前缀，如 sz159915）
                # parts[1]: 股票名称
                # parts[2]: 6位代码（如 159915）
                # parts[3]: 最新价
                # parts[4]: 昨收
                # parts[5]: 今开
                # parts[6]: 成交量（手，注意单位是"手"，1手=100股）
                # parts[7]: 外盘
                # parts[8]: 内盘
                # parts[9]: 买一
                # parts[10]: 买一量
                # parts[30]: 成交额（元）
                
                if len(parts) > 6:
                    print(f"✅ 实时数据包含成交量字段")
                    print(f"   parts[6] (成交量-手): {parts[6]}")
                    print(f"   注意：单位是'手'，1手=100股，实际成交量 = {parts[6]} * 100")
                    
                    # 尝试转换为数值
                    try:
                        volume_shou = float(parts[6])  # 成交量（手）
                        volume_gu = volume_shou * 100  # 成交量（股）
                        print(f"   成交量（手）: {volume_shou:,.0f}")
                        print(f"   成交量（股）: {volume_gu:,.0f}")
                    except:
                        print(f"   ⚠️ 成交量字段无法转换为数值: {parts[6]}")
                else:
                    print(f"❌ 实时数据字段不足，无法获取成交量（只有 {len(parts)} 个字段）")
                
                if len(parts) > 30:
                    print(f"\n✅ 实时数据包含成交额字段")
                    print(f"   parts[30] (成交额-元): {parts[30]}")
                    try:
                        amount = float(parts[30])
                        print(f"   成交额（元）: {amount:,.2f}")
                    except:
                        print(f"   ⚠️ 成交额字段无法转换为数值: {parts[30]}")
                else:
                    print(f"\n⚠️ 实时数据字段不足，无法获取成交额（只有 {len(parts)} 个字段）")
                
                # ========== 构建完整的实时数据字典 ==========
                print("\n" + "-" * 80)
                print("📋 【实时数据完整解析示例】")
                print("-" * 80)
                
                spot_data = {
                    '代码': parts[2] if len(parts) > 2 else None,
                    '名称': parts[1] if len(parts) > 1 else None,
                    '最新价': float(parts[3]) if len(parts) > 3 and parts[3] else None,
                    '昨收': float(parts[4]) if len(parts) > 4 and parts[4] else None,
                    '今开': float(parts[5]) if len(parts) > 5 and parts[5] else None,
                    '成交量_手': float(parts[6]) if len(parts) > 6 and parts[6] else None,
                    '成交量_股': float(parts[6]) * 100 if len(parts) > 6 and parts[6] else None,
                    '成交额_元': float(parts[30]) if len(parts) > 30 and parts[30] else None,
                }
                
                print("解析后的实时数据字典：")
                for key, value in spot_data.items():
                    if value is not None:
                        if isinstance(value, float):
                            if '量' in key or '额' in key:
                                print(f"  {key}: {value:,.2f}")
                            else:
                                print(f"  {key}: {value:.3f}")
                        else:
                            print(f"  {key}: {value}")
                
                break
    else:
        print(f"❌ 实时行情返回状态码: {resp.status_code}")

except Exception as e:
    print(f"❌ 腾讯实时接口测试报错: {e}")
    import traceback
    traceback.print_exc()

# ======================== 测试3：对比历史成交量和实时成交量 ========================
print("\n\n" + "=" * 80)
print(f"🚀 --- 测试3：历史成交量 vs 实时成交量对比 ---")
print("=" * 80)

try:
    # 获取历史数据
    df_hist = ak.stock_zh_a_hist_tx(symbol=symbol)
    if df_hist is not None and not df_hist.empty and 'volume' in df_hist.columns:
        # 计算最近5天的平均成交量
        lookback_days = 5
        recent_volumes = df_hist['volume'].tail(lookback_days)
        avg_volume = recent_volumes.mean()
        
        print(f"✅ 历史成交量统计（最近 {lookback_days} 天）:")
        print(f"   平均成交量: {avg_volume:,.2f} 股")
        print(f"   最近5天成交量详情:")
        print(df_hist[['date', 'close', 'volume']].tail(lookback_days))
        
        # 获取实时成交量
        url = f"http://qt.gtimg.cn/q={symbol}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            lines = resp.text.split(';')
            for line in lines:
                if symbol in line:
                    parts = line.split('~')
                    if len(parts) > 6:
                        current_volume_shou = float(parts[6])
                        current_volume_gu = current_volume_shou * 100
                        
                        print(f"\n✅ 实时成交量:")
                        print(f"   当日成交量（手）: {current_volume_shou:,.0f}")
                        print(f"   当日成交量（股）: {current_volume_gu:,.0f}")
                        
                        # 计算成交量比值
                        if avg_volume > 0:
                            ratio = current_volume_gu / avg_volume
                            threshold = 2.0
                            print(f"\n📊 成交量对比分析:")
                            print(f"   历史平均成交量（最近{lookback_days}天）: {avg_volume:,.2f} 股")
                            print(f"   当日成交量: {current_volume_gu:,.2f} 股")
                            print(f"   成交量比值: {ratio:.2f} 倍")
                            print(f"   放量阈值: {threshold} 倍")
                            
                            if ratio > threshold:
                                print(f"   🚨 结论: 当日成交量 {ratio:.2f} 倍于历史平均，已触发放量限制！")
                            else:
                                print(f"   ✅ 结论: 当日成交量 {ratio:.2f} 倍，未触发放量限制")
                        break
    else:
        print("❌ 无法获取历史成交量数据，跳过对比")

except Exception as e:
    print(f"❌ 对比测试报错: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("🚀 --- 所有测试结束 ---")
print("=" * 80)