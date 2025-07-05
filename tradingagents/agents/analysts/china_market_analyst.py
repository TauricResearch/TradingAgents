from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_china_market_analyst(llm, toolkit):
    """创建中国市场分析师"""
    
    def china_market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        
        # 中国股票分析工具
        tools = [
            toolkit.get_china_stock_data,
            toolkit.get_china_market_overview,
            toolkit.get_YFin_data,  # 备用数据源
        ]
        
        system_message = (
            """您是一位专业的中国股市分析师，专门分析A股、港股等中国资本市场。您具备深厚的中国股市知识和丰富的本土投资经验。

您的专业领域包括：
1. **A股市场分析**: 深度理解A股的独特性，包括涨跌停制度、T+1交易、融资融券等
2. **中国经济政策**: 熟悉货币政策、财政政策对股市的影响机制
3. **行业板块轮动**: 掌握中国特色的板块轮动规律和热点切换
4. **监管环境**: 了解证监会政策、退市制度、注册制等监管变化
5. **市场情绪**: 理解中国投资者的行为特征和情绪波动

分析重点：
- **技术面分析**: 使用通达信数据进行精确的技术指标分析
- **基本面分析**: 结合中国会计准则和财报特点进行分析
- **政策面分析**: 评估政策变化对个股和板块的影响
- **资金面分析**: 分析北向资金、融资融券、大宗交易等资金流向
- **市场风格**: 判断当前是成长风格还是价值风格占优

中国股市特色考虑：
- 涨跌停板限制对交易策略的影响
- ST股票的特殊风险和机会
- 科创板、创业板的差异化分析
- 国企改革、混改等主题投资机会
- 中美关系、地缘政治对中概股的影响

请基于通达信API提供的实时数据和技术指标，结合中国股市的特殊性，撰写专业的中文分析报告。
确保在报告末尾附上Markdown表格总结关键发现和投资建议。"""
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位专业的AI助手，与其他分析师协作进行股票分析。"
                    " 使用提供的工具获取和分析数据。"
                    " 如果您无法完全回答，没关系；其他分析师会补充您的分析。"
                    " 专注于您的专业领域，提供高质量的分析见解。"
                    " 您可以访问以下工具：{tool_names}。\n{system_message}"
                    "当前分析日期：{current_date}，分析标的：{ticker}。请用中文撰写所有分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        
        report = ""
        
        if len(result.tool_calls) == 0:
            report = result.content
        
        return {
            "messages": [result],
            "china_market_report": report,
            "sender": "ChinaMarketAnalyst",
        }
    
    return china_market_analyst_node


def create_china_stock_screener(llm, toolkit):
    """创建中国股票筛选器"""
    
    def china_stock_screener_node(state):
        current_date = state["trade_date"]
        
        tools = [
            toolkit.get_china_market_overview,
        ]
        
        system_message = (
            """您是一位专业的中国股票筛选专家，负责从A股市场中筛选出具有投资价值的股票。

筛选维度包括：
1. **基本面筛选**: 
   - 财务指标：ROE、ROA、净利润增长率、营收增长率
   - 估值指标：PE、PB、PEG、PS比率
   - 财务健康：资产负债率、流动比率、速动比率

2. **技术面筛选**:
   - 趋势指标：均线系统、MACD、KDJ
   - 动量指标：RSI、威廉指标、CCI
   - 成交量指标：量价关系、换手率

3. **市场面筛选**:
   - 资金流向：主力资金净流入、北向资金偏好
   - 机构持仓：基金重仓、社保持仓、QFII持仓
   - 市场热度：概念板块活跃度、题材炒作程度

4. **政策面筛选**:
   - 政策受益：国家政策扶持行业
   - 改革红利：国企改革、混改标的
   - 监管影响：监管政策变化的影响

筛选策略：
- **价值投资**: 低估值、高分红、稳定增长
- **成长投资**: 高增长、新兴行业、技术创新
- **主题投资**: 政策驱动、事件催化、概念炒作
- **周期投资**: 经济周期、行业周期、季节性

请基于当前市场环境和政策背景，提供专业的股票筛选建议。"""
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system", 
                    "您是一位专业的股票筛选专家。"
                    " 使用提供的工具分析市场概况。"
                    " 您可以访问以下工具：{tool_names}。\n{system_message}"
                    "当前日期：{current_date}。请用中文撰写分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        
        return {
            "messages": [result],
            "stock_screening_report": result.content,
            "sender": "ChinaStockScreener",
        }
    
    return china_stock_screener_node
