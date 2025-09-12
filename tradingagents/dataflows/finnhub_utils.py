# 导入必要的模块
import json  # 用于处理JSON格式的数据
import os    # 用于文件路径操作


def get_data_in_range(ticker, start_date, end_date, data_type, data_dir, period=None):
    """
    从本地磁盘获取已保存和处理的FinnHub数据
    
    这个函数不是直接调用FinnHub API，而是从本地JSON文件中读取预先下载的数据
    
    参数说明:
        ticker (str): 股票代码，例如 'AAPL' 代表苹果公司
        start_date (str): 开始日期，格式为 YYYY-MM-DD，例如 '2024-01-01'
        end_date (str): 结束日期，格式为 YYYY-MM-DD，例如 '2024-01-31'
        data_type (str): 要获取的数据类型，可以是以下之一：
            - 'insider_trans': 内部交易数据
            - 'SEC_filings': SEC文件数据
            - 'news_data': 新闻数据
            - 'insider_senti': 内部人员情绪数据
            - 'fin_as_reported': 财务报告数据
        data_dir (str): 数据保存的目录路径
        period (str): 报告周期，默认为None。如果指定，应该是 'annual'（年度）或 'quarterly'（季度）
    
    返回值:
        dict: 过滤后的数据字典，键为日期，值为该日期的数据列表
    """

    # 根据是否有报告周期来构建文件路径
    if period:
        # 如果有报告周期，文件名包含周期信息
        data_path = os.path.join(
            data_dir,                    # 数据目录
            "finnhub_data",             # FinnHub数据子目录
            data_type,                  # 数据类型子目录
            f"{ticker}_{period}_data_formatted.json",  # 文件名格式：股票代码_周期_数据格式.json
        )
    else:
        # 如果没有报告周期，使用默认文件名
        data_path = os.path.join(
            data_dir, "finnhub_data", data_type, f"{ticker}_data_formatted.json"
        )

    # 打开并读取JSON文件
    data = open(data_path, "r")  # 以只读模式打开文件
    data = json.load(data)       # 将JSON文件内容解析为Python字典

    # 根据日期范围过滤数据
    # 只保留在指定日期范围内且有数据的条目
    filtered_data = {}
    for key, value in data.items():
        # key是日期字符串，value是该日期的数据列表
        # 检查日期是否在范围内，且数据不为空
        if start_date <= key <= end_date and len(value) > 0:
            filtered_data[key] = value  # 将符合条件的数据添加到结果中
    
    return filtered_data  # 返回过滤后的数据
