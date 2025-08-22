from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json

# 导入统一日志系统和分析模块日志装饰器
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
logger = get_logger("analysts.news")


def create_news_analyst(llm, toolkit):
    @log_analyst_module("news")
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            # 在线模式：优先使用实时新闻API
            # A 股市场工具
            logger.info(f"📊 [新闻分析师] 使用统一市场数据工具，自动识别股票类型")
            tools = [
                toolkit.get_company_news,  # 公司相关新闻
                toolkit.get_market_news,  # 市场相关新闻
            ]
        else:
            # 离线模式：使用缓存数据和搜索
            tools = [
                toolkit.get_company_news,  # 公司相关新闻
                toolkit.get_market_news,  # 市场相关新闻
            ]

        system_message = (
            "你是一位专业的新闻研究员，负责分析与公司和市场相关的新闻信息。请撰写一份全面的报告，重点关注以下方面：\n"
                "1. 公司新闻：重大事件、管理层变动、业务发展等\n"
                "2. 行业新闻：产业政策、技术突破、竞争格局等\n"
                "3. 市场新闻：宏观经济、监管政策、市场情绪等\n"
                "4. 公告解读：重要公告的详细分析和潜在影响\n\n"
                "请特别关注以下信息来源：\n"
                "- 公司公告和新闻发布\n"
                "- 行业协会和监管机构的政策文件\n"
                "- 主流财经媒体的深度报道\n"
                "- 市场分析师的研究报告\n\n"
                "不要简单地罗列新闻，而是要提供深入的分析和见解，帮助交易者理解新闻背后的影响。"
                "请在报告末尾添加一个 Markdown 表格，总结关键新闻及其潜在影响。"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位有用的AI助手，与其他助手协作。"
                    " 使用提供的工具来推进回答问题。"
                    " 如果您无法完全回答，没关系；具有不同工具的其他助手"
                    " 将从您停下的地方继续帮助。执行您能做的以取得进展。"
                    " 如果您或任何其他助手有最终交易提案：**买入/持有/卖出**或可交付成果，"
                    " 请在您的回应前加上最终交易提案：**买入/持有/卖出**，以便团队知道停止。"
                    " 您可以访问以下工具：{tool_names}。\n{system_message}"
                    "供您参考，当前日期是{current_date}。我们正在查看公司{ticker}。请用中文撰写所有分析内容。",
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
            "news_report": report,
        }

    return news_analyst_node
