import re
import inspect
from docstring_parser import parse
from typing import List, Optional, Dict, Callable, Annotated
import datetime
import time
import os
import dashscope

from web.utils.analysis_runner import run_stock_analysis
import streamlit as st
import akshare as ak

class ToolExecutor:
    """工具执行器，用于管理和执行各种分析工具"""

    def __init__(self):
        """初始化工具执行器，注册所有可用工具"""
        # 工具注册表，键为工具名称，值为对应的执行方法
        self.tools = {
            '个股股票分析工具': self.execute_stock_analysis_tool,
            '基金分析工具': self.execute_fund_analysis_tool,
            # '机构经营情况分析工具': self.deposit_analyze
            # 在这里添加新工具，格式: '工具名称': 执行方法
        }

    def get_available_tools(self):
        """获取所有可用工具的列表"""
        return list(self.tools.keys())

    @staticmethod
    def get_tool_metadata(tool_func):
        """提取工具函数的元信息（名称、描述、参数列表）"""
        # 1. 基础信息：函数名和 docstring 摘要
        tool_name = tool_func.__name__
        docstring = inspect.getdoc(tool_func) or ""
        parsed_doc = parse(docstring)  # 解析docstring
        tool_description = parsed_doc.short_description or "无描述"

        # 2. 提取参数信息：结合函数签名和docstring参数描述
        sig = inspect.signature(tool_func)  # 获取函数签名
        parameters = []
        for param_name, param in sig.parameters.items():
            # 从签名中获取参数类型、默认值
            param_type = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "未指定"
            default_value = param.default if param.default != inspect.Parameter.empty else "必填"

            # 从docstring中获取参数描述（适配Google风格的Args）
            param_desc = ""
            for doc_param in parsed_doc.params:
                if doc_param.arg_name == param_name:
                    param_desc = doc_param.description or "无描述"
                    break

            parameters.append({
                "name": param_name,
                "type": param_type,
                "default": default_value,
                "description": param_desc
            })

        return {
            "name": tool_name,
            "description": tool_description,
            "parameters": parameters
        }

    def generate_available_tools(self):
        """生成包含参数信息的可用工具列表"""
        # 修复：获取工具函数而不是工具名称字符串
        tool_list = []

        # 枚举所有工具（名称和对应的函数）
        for idx, (tool_display_name, tool_func) in enumerate(self.tools.items(), 1):
            metadata = ToolExecutor.get_tool_metadata(tool_func)
            # 格式化工具基本信息
            tool_info = [
                f"{idx}. 工具名称：{tool_display_name}",  # 使用显示名称
                f"   工具描述：{metadata['description']}",
                "   参数列表："
            ]
            # 格式化参数信息
            for param in metadata["parameters"]:
                param_line = (
                    f"   - {param['name']}（类型：{param['type']}，"
                    f"默认值：{param['default']}）：{param['description']}"
                )
                tool_info.append(param_line)
            tool_list.append("\n".join(tool_info))

        return "# 可用工具列表（含参数说明）\n" + "\n\n".join(tool_list)

    def execute(self, tool_name, parameters, step_content, progress_callback=None):
        """
        执行指定的工具

        Args:
            tool_name: 工具名称
            parameters: 工具参数
            step_content: 步骤内容（作为参数提取的备选来源）
            progress_callback: 进度回调函数

        Returns:
            工具执行结果报告
        """
        if tool_name not in self.tools:
            return f"错误：未知工具 '{tool_name}'，无法执行。可用工具：{', '.join(self.get_available_tools())}"

        # 调用对应的工具执行方法
        try:
            return self.tools[tool_name](parameters, step_content, progress_callback)
        except Exception as e:
            return f"执行工具 '{tool_name}' 时发生错误: {str(e)}"

    def _extract_stock_symbols(self, parameters: Dict, step_content: str) -> List[str]:
        """从参数或步骤文本中提取6位数字的股票代码"""
        candidates = []
        # 1. 从parameters中提取（优先）
        if isinstance(parameters, dict) and "stock_symbols" in parameters:
            param_value = parameters["stock_symbols"]
            if isinstance(param_value, list):
                candidates.extend([str(code) for code in param_value])
            else:
                candidates.append(str(param_value))  # 支持单个代码的情况

        # 2. 从step_content中提取（补充）
        if not candidates and step_content:
            candidates.append(step_content)

        # 3. 过滤有效代码（6位数字）
        valid_codes = list(set(re.findall(r"\b\d{6}\b", ",".join(candidates))))  # 去重+匹配6位数字
        return sorted(valid_codes)  # 排序后返回

    def _extract_fund_symbols(self, parameters: Dict, step_content: str) -> List[str]:
        """从参数或步骤文本中提取6位数字的基金代码"""
        candidates = []
        # 1. 从parameters中提取（优先）
        if isinstance(parameters, dict) and "fund_symbols" in parameters:
            param_value = parameters["fund_symbols"]
            if isinstance(param_value, list):
                candidates.extend([str(code) for code in param_value])
            else:
                candidates.append(str(param_value))  # 支持单个代码的情况

        # 2. 从step_content中提取（补充）
        if not candidates and step_content:
            candidates.append(step_content)

        # 3. 过滤有效代码（6位数字）
        valid_codes = list(set(re.findall(r"\b\d{6}\b", ",".join(candidates))))  # 去重+匹配6位数字
        return sorted(valid_codes)  # 排序后返回

    def execute_stock_analysis_tool(
            self,
            parameters: Dict[str, List[str]],
            step_content: str,
            progress_callback: Optional[Callable[[str, float], None]] = None
    ):
        """
        个股股票分析工具，支持批量分析股票。

        Args:
            parameters: 工具参数字典，推荐包含键 "stock_symbols"，值为股票代码列表（如 ["600000", "600036"]）
            step_content: 步骤描述文本，若parameters中无股票代码，将从文本中提取6位数字代码
            progress_callback: 进度回调函数，接收两个参数：进度信息（str）和进度值（0-1的float）

        Returns:
            整合后的股票分析报告，包含每只股票的市场、基本面等分析内容
        """
        # 提取股票代码
        stock_symbols = self._extract_stock_symbols(parameters, step_content)
        if not stock_symbols:
            return "错误：未找到有效的A股股票代码（需为6位数字），无法执行分析。"

        # 获取LLM配置
        llm_provider = st.session_state.llm_config.get('llm_provider', 'dashscope')
        llm_model = st.session_state.llm_config.get('llm_model', 'qwen-plus')

        all_analysis = []
        total = len(stock_symbols)

        for i, code in enumerate(stock_symbols, 1):
            # 进度反馈
            if progress_callback:
                progress = i / total
                progress_callback(f"正在分析股票 {code}（{i}/{total}）", progress)

            try:
                # 执行股票分析
                analysis_result = run_stock_analysis(
                    stock_symbol=code,
                    analysis_date=str(datetime.date.today()),
                    analysts=['fundamentals'],
                    research_depth=1,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    market_type='A股',
                )
            except Exception as e:
                all_analysis.append(f"### 个股分析: {code}\n分析失败：{str(e)}")
                continue

            # 处理分析结果
            raw_reports = []
            if 'state' in analysis_result:
                state = analysis_result['state']
                report_types = [
                    'market_report', 'fundamentals_report',
                    'sentiment_report', 'news_report',
                ]
                for report_type in report_types:
                    if report_type in state:
                        raw_reports.append(
                            f"#### {report_type.replace('_', ' ').title()}\n{state[report_type]}")

            # 添加决策推理
            decision_reasoning = ""
            if 'decision' in analysis_result and 'reasoning' in analysis_result['decision']:
                decision_reasoning = f"#### 核心决策结论\n{analysis_result['decision']['reasoning']}"

            # 整合报告
            full_raw_report = "\n\n".join(raw_reports + [decision_reasoning])
            all_analysis.append(
                f"### 个股分析: {code}\n{full_raw_report if full_raw_report else '无分析结果'}")

        return "\n\n".join(all_analysis)

    def execute_fund_analysis_tool(
        self,
        parameters: Dict[str, List[str]],
        step_content: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ):
        """
        基金分析工具，支持批量分析基金。

        Args:
            parameters: 工具参数字典，推荐包含键 "fund_symbols"，值为基金代码列表（如 ["290012", "485119"]）
            step_content: 步骤描述文本，若parameters中无基金代码，将从文本中提取6位数字代码
            progress_callback: 进度回调函数，接收两个参数：进度信息（str）和进度值（0-1的float）

        Returns:
            整合后的基金分析报告，包含每只基金的市场、基本面等分析内容
        """
        # 提取基金代码
        fund_symbols = self._extract_fund_symbols(parameters, step_content)
        if not fund_symbols:
            return "错误：未找到有效的基金代码（需为6位数字），无法执行分析。"

        # 获取LLM配置
        llm_provider = st.session_state.llm_config.get('llm_provider', 'dashscope')
        llm_model = st.session_state.llm_config.get('llm_model', 'qwen-plus')

        all_analysis = []
        total = len(fund_symbols)

        for i, code in enumerate(fund_symbols, 1):
            # 进度反馈
            if progress_callback:
                progress = i / total
                progress_callback(f"正在分析基金 {code}（{i}/{total}）", progress)

            try:
                # 执行基金分析
                analysis_result = run_fund_analysis(
                    fund_symbol=code )
            except Exception as e:
                all_analysis.append(f"### 基金分析: {code}\n分析失败：{str(e)}")
                continue

            all_analysis.append(
                f"### 基金分析: {code}\n{analysis_result if analysis_result else '无分析结果'}")

        return "\n\n".join(all_analysis)

def run_fund_analysis(fund_symbol):
    # 构建报告头
    result = f"【基金代码】: {fund_symbol}\n"

    # 1. 基本数据
    try:
        basic_info = ak.fund_individual_basic_info_xq(symbol=fund_symbol)
        result += "【基本数据】:\n" + basic_info.to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【基本数据】获取失败: {str(e)}\n\n"

    # 2. 基金评级
    try:
        fund_rating_all_df = ak.fund_rating_all()
        result += "【基金评级】:\n" + fund_rating_all_df[
            fund_rating_all_df['代码'] == fund_symbol
            ].to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【基金评级】获取失败: {str(e)}\n\n"

    # 3. 业绩表现（前5条）
    try:
        achievement = ak.fund_individual_achievement_xq(symbol=fund_symbol)
        result += "【业绩表现】:\n" + achievement.head(5).to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【业绩表现】获取失败: {str(e)}\n\n"

    # 4. 净值估算（特殊处理全量请求）
    try:
        fund_value_df = ak.fund_value_estimation_em(symbol="全部")
        result += "【净值估算】:\n" + fund_value_df[
            fund_value_df['基金代码'] == fund_symbol
            ].to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【净值估算】获取失败: {str(e)}\n\n"

    # 5. 数据分析
    try:
        analysis = ak.fund_individual_analysis_xq(symbol=fund_symbol)
        result += "【数据分析】:\n" + analysis.to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【数据分析】获取失败: {str(e)}\n\n"

    # 6. 盈利概率
    try:
        profit_prob = ak.fund_individual_profit_probability_xq(symbol=fund_symbol)
        result += "【盈利概率】:\n" + profit_prob.to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【盈利概率】获取失败: {str(e)}\n\n"

    # 7. 持仓资产比例
    try:
        detail_hold = ak.fund_individual_detail_hold_xq(symbol=fund_symbol)
        result += "【持仓资产比例】:\n" + detail_hold.to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【持仓资产比例】获取失败: {str(e)}\n\n"

    # 8. 行业配置（2025年数据）
    try:
        industry_alloc = ak.fund_portfolio_industry_allocation_em(symbol=fund_symbol, date="2025")
        result += "【行业配置】:\n" + industry_alloc.to_string(index=False) + "\n\n"
        time.sleep(1)
    except Exception as e:
        result += f"【行业配置】获取失败: {str(e)}\n\n"

    # 9. 基金持仓（2025年数据）
    try:
        portfolio_hold = ak.fund_portfolio_hold_em(symbol=fund_symbol, date="2025")
        result += "【基金持仓】:\n" + portfolio_hold.to_string(index=False) + "\n"
        time.sleep(1)
    except Exception as e:
        result += f"【基金持仓】获取失败: {str(e)}\n"

    print(result)

    system_message = (
        f"你是一位专业的基金基本面分析师。\n"
        f"任务：对（基金代码：{fund_symbol}）进行全面基本面分析\n"
        "📊 **强制要求：**\n"
        "按以下框架输出结构化报告：\n\n"

        "### 一、基金产品基础分析\n"
        "- **基金公司实力**：管理规模排名、权益投资能力评级、风控体系完善度\n"
        "- **基金经理**：从业年限、历史年化回报、最大回撤控制能力（近3年）、投资风格稳定性\n"
        "- **产品特性**：基金类型(股票/混合/债券)、运作方式(开放式/封闭式)、规模变动趋势(警惕＜1亿清盘风险)\n"
        "- **费率结构**：管理费+托管费总成本、浮动费率机制(如有)、申购赎回费率\n\n"

        "### 二、风险收益特征分析\n"
        "- **核心指标**：\n"
        "  • 夏普比率(＞1为优)、卡玛比率(年化收益/最大回撤，＞0.5合格)\n"
        "  • 波动率(同类排名后30%为佳)、下行捕获率(＜100%表明抗跌)\n"
        "- **极端风险控制**：\n"
        "  • 最大回撤率(数值绝对值越小越好)及修复时长\n"
        "  • 股灾/熊市期间表现(如2022年回撤幅度 vs 沪深300)\n\n"

        "### 三、长期业绩评估\n"
        "- **收益维度**：\n"
        "  • 3年/5年年化收益率(需扣除费率)、超额收益(Alpha)\n"
        "  • 业绩持续性：每年排名同类前50%的年份占比\n"
        "- **基准对比**：\n"
        "  • 滚动3年跑赢业绩比较基准的概率\n"
        "  • 不同市场环境适应性(如2023成长牛 vs 2024价值修复行情表现)\n\n"

        "### 四、综合价值评估\n"
        "- **持仓穿透估值**：\n"
        "  • 股票部分：前十大重仓股PE/PB分位数(行业调整后)\n"
        "  • 债券部分：信用债利差水平、利率债久期风险\n"
        "- **组合性价比**：\n"
        "  • 股债净资产比价(E/P - 10年国债收益率)\n"
        "  • 场内基金需分析折溢价率(＞1%警惕高估)\n"
        f"- **绝对价值锚点**：给出合理净值区间依据：\n"
        "  当前净值水平 vs 历史波动区间(30%分位以下为低估)\n\n"

        "### 五、投资决策建议\n"
        "- **建议逻辑**：\n"
        "  • 综合夏普比率＞1.2+卡玛比率＞0.7+净值处30%分位→'买入'\n"
        "  • 规模激增(＞100亿)+重仓股估值＞70%分位→'减持'\n"
        "- **强制输出**：中文操作建议(买入/增持/持有/减持/卖出)\n"

        "🚫 **禁止事项**：\n"
        "- 禁止假设数据\n"
        "- 禁止使用英文建议(buy/sell/hold)\n"
    )

    user_prompt = (f"你现在拥有以下基金的真实数据，请严格依赖真实数据（注意！每条数据必须强制利用到来进行分析），"
                   f"绝不编造其他数据，对（基金代码：{fund_symbol}）进行全面分析，给出非常详细格式化的报告:\n")
    user_prompt += result

    messages = [
        {'role': 'system', 'content': system_message},
        {'role': 'user', 'content': user_prompt}
    ]
    response = dashscope.Generation.call(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
        api_key=os.getenv('DASHSCOPE_API_KEY'),
        model="qwen-plus-latest",
        # 此处以qwen-plus-latest为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=messages,
        result_format='message'
    )
    print(response.output.choices[0].message.content)

    return response.output.choices[0].message.content
