# ========================================
# 极简版MCP天气客户端（带详细注释）
# 核心功能：连接MCP服务端 → 调用LLM生成指令 → 调用天气工具 → 返回结果
# 适合新手理解核心流程，无冗余封装，线性逻辑清晰
# ========================================

# 导入Python内置标准库（核心必要）
import json  # 用于解析和生成JSON数据（LLM指令、工具参数均为JSON格式）
import asyncio  # 用于支持异步编程（MCP通信、HTTP请求均为异步操作）
import sys  # 用于获取命令行参数（传入MCP服务端脚本路径）
import os  # 用于读取环境变量（获取DashScope API密钥）

# 导入第三方库（核心必要）
import httpx  # 用于发送异步HTTP请求（调用通义千问LLM接口）

# 导入MCP框架核心模块（用于建立客户端与服务端通信）
from mcp import ClientSession  # MCP客户端会话对象，负责发送工具调用指令
from mcp.client.stdio import stdio_client  # MCP标准输入输出客户端，用于启动并连接服务端脚本

# ========================================
# 全局配置项（简化版，直接定义，无需封装到类中）
# ========================================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")  # 从环境变量读取通义千问API密钥（安全便捷）
TONGYI_MODEL = "qwen-plus"  # 通义千问模型名称，选择高性能通用模型qwen-plus
AMAP_TOOL_NAME = "get_weather"  # 我们要调用的MCP工具名称（对应服务端的天气查询工具）


# ========================================
# 步骤1：连接MCP服务端，建立通信通道
# ========================================
async def connect_mcp_server(server_script_path):
    """
    简化版：连接MCP服务端脚本，建立异步通信会话，验证目标工具是否可用
    核心作用：就像拨通电话，确认对方在线且能提供我们需要的服务（天气查询工具）
    Args:
        server_script_path: MCP服务端脚本路径（如weather.py）
    Returns:
        ClientSession: 初始化完成的MCP客户端会话对象（后续用于调用工具）
    Raises:
        ValueError: 若脚本格式不正确或目标工具不存在，抛出错误提示
    """
    # 第一步：验证服务端脚本格式（仅支持Python脚本，简化版不兼容JS）
    if not server_script_path.endswith(".py"):
        raise ValueError("简化版仅支持Python格式的MCP服务端脚本（.py文件）")

    # 第二步：启动MCP服务端脚本，建立标准输入输出（stdio）通信连接
    # stdio_client会自动执行python命令，启动传入的服务端脚本，并建立双向通信
    stdio_transport = await stdio_client(command="python", args=[server_script_path])
    stdio, write = stdio_transport  # 解包通信传输对象：stdio用于读取，write用于写入

    # 第三步：创建MCP客户端会话对象，完成会话初始化（握手协议）
    # 会话对象是后续调用工具的核心载体，负责封装通信细节
    session = ClientSession(stdio, write)
    await session.initialize()  # 初始化会话，与服务端完成协议握手

    # 第四步：验证目标工具（get_weather）是否在服务端的可用工具列表中
    tool_list_response = await session.list_tools()  # 获取服务端所有可用工具
    tool_names = [tool.name for tool in tool_list_response.tools]  # 提取工具名称列表

    # 若目标工具不存在，抛出错误并提示可用工具
    if AMAP_TOOL_NAME not in tool_names:
        raise ValueError(f"服务端未提供{AMAP_TOOL_NAME}工具，可用工具列表：{tool_names}")

    # 第五步：打印连接成功提示，返回初始化完成的会话对象
    print(f"✅ 已成功连接到MCP服务端，目标工具{AMAP_TOOL_NAME}可用")
    return session


# ========================================
# 步骤2：调用通义千问LLM，生成标准化工具调用指令
# ========================================
async def call_llm(user_query):
    """
    简化版：调用通义千问LLM，将用户自然语言查询转换为机器可识别的工具调用指令
    核心作用：就像翻译，把用户说的大白话（如"北京天气"）翻译成机器能懂的专业指令（JSON格式）
    Args:
        user_query: 用户输入的自然语言查询（如"北京天气"、"上海今天天气怎么样"）
    Returns:
        dict: 解析后的工具调用指令（含name和parameters），或错误信息字典
    """
    # 第一步：前置检查，验证API密钥是否配置
    if not DASHSCOPE_API_KEY:
        return {"error": "未配置DASHSCOPE_API_KEY环境变量，请先配置后再运行"}

    # 第二步：构建LLM系统提示词，强制LLM遵循固定输出格式
    # 简化版：只要求处理get_weather工具，输出标准JSON格式，无额外冗余内容
    system_prompt = f"""
    你的唯一任务是将用户输入转换为{AMAP_TOOL_NAME}工具的调用指令，严格遵守以下规则：
    1. 仅能调用{AMAP_TOOL_NAME}这一个工具，无需考虑其他工具
    2. 输出格式必须是纯JSON，无任何额外文本、注释或换行
    3. JSON格式固定为：{{"name": "{AMAP_TOOL_NAME}", "parameters": {{"city": "城市名"}}}}
    4. 从用户输入中提取城市名称，填入city参数，若未明确城市，默认填"北京"
    """

    # 第三步：构建LLM请求头，包含身份验证和数据格式声明
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",  # Bearer认证，传入API密钥
        "Content-Type": "application/json"  # 声明请求体为JSON格式
    }

    # 第四步：构建LLM请求体，包含模型名称、对话消息和生成参数
    payload = {
        "model": TONGYI_MODEL,  # 要调用的通义千问模型名称
        "messages": [  # 对话消息列表，遵循OpenAI兼容格式
            {"role": "system", "content": system_prompt},  # 系统提示，定义LLM的行为准则
            {"role": "user", "content": user_query}  # 用户输入，传递用户的自然语言查询
        ],
        "parameters": {"temperature": 0.0}  # 生成参数：温度设为0，确保输出结果稳定可预测
    }

    try:
        # 第五步：异步发送HTTP POST请求，调用通义千问LLM接口
        async with httpx.AsyncClient() as client:  # 异步HTTP客户端，自动管理连接生命周期
            response = await client.post(
                url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",  # 通义千问兼容OpenAI的API地址
                headers=headers,  # 传入请求头
                json=payload  # 传入请求体（自动序列化为JSON格式）
            )
            response.raise_for_status()  # 检查HTTP响应状态码，非2xx状态码抛出异常

        # 第六步：解析LLM返回结果，提取工具调用指令
        llm_response = response.json()  # 将HTTP响应体解析为字典
        # 提取LLM生成的核心内容（choices → 第一个结果 → message → content）
        tool_call_content = llm_response["choices"][0]["message"]["content"]
        # 将LLM返回的JSON字符串解析为字典，供后续调用工具使用
        return json.loads(tool_call_content)

    # 捕获所有可能的异常，返回友好错误提示
    except Exception as e:
        return {"error": f"LLM调用失败或返回格式错误，具体原因：{str(e)}"}


# ========================================
# 步骤3：调用MCP工具，执行天气查询并返回结果
# ========================================
async def call_mcp_tool(session, tool_name, parameters):
    """
    简化版：通过MCP会话对象调用指定工具，获取天气查询结果
    核心作用：就像把翻译好的指令传递给办事人员，等待办事结果并带回
    Args:
        session: 初始化完成的MCP ClientSession对象
        tool_name: 要调用的工具名称（如get_weather）
        parameters: 工具调用所需参数（如{"city": "北京"}）
    Returns:
        str: 工具执行结果（格式化的天气信息）或错误提示字符串
    """
    try:
        # 第一步：调用MCP工具，添加10秒超时控制，防止长时间阻塞
        # session.call_tool：发送工具调用指令给服务端，等待服务端执行并返回结果
        result = await asyncio.wait_for(
            session.call_tool(tool_name, parameters),  # 核心工具调用方法
            timeout=10  # 10秒超时，若服务端未响应则抛出超时异常
        )

        # 第二步：返回工具执行的核心内容（result.content为服务端返回的有效数据）
        return result.content

    # 捕获所有可能的异常，返回友好错误提示
    except Exception as e:
        return f"工具调用失败，具体原因：{str(e)}"


# ========================================
# 主流程：串联3个核心步骤，实现完整的天气查询功能
# ========================================
async def main():
    """
    极简版主流程：串联「连接MCP服务端」→「调用LLM生成指令」→「调用MCP工具」
    线性流程，无复杂嵌套，新手易理解
    """
    # 第一步：检查命令行参数是否完整（是否传入了MCP服务端脚本路径）
    if len(sys.argv) < 2:
        print("使用方法：python simple_client_with_comments.py <MCP服务端脚本路径>")
        print("示例：python simple_client_with_comments.py weather.py")
        return  # 参数不完整，直接退出程序

    try:
        # 第二步：连接MCP服务端，获取会话对象（步骤1）
        # sys.argv[1]：获取命令行中第二个参数（服务端脚本路径）
        mcp_session = await connect_mcp_server(sys.argv[1])

        # 第三步：打印欢迎信息，进入用户交互循环
        print("\n🤖 极简天气助手（已就绪，支持自然语言查询）")
        print("📌 示例查询：'北京天气'、'上海今天天气'")
        print("📌 输入'quit'或'退出'，即可结束程序")

        # 第四步：循环接收用户输入，处理查询请求（直到用户退出）
        while True:
            # 接收用户输入，去除首尾空格
            user_query = input("\n请输入你的天气查询：").strip()

            # 退出条件：用户输入quit、退出、bye等关键词
            if user_query.lower() in ["quit", "退出", "bye"]:
                print("👋 再见！程序已正常退出")
                break

            # 跳过空输入（用户直接按回车）
            if not user_query:
                continue

            # 第五步：调用LLM，将用户输入转换为工具调用指令（步骤2）
            tool_call_info = await call_llm(user_query)

            # 检查LLM调用是否出错，若出错则打印错误信息并继续下一轮循环
            if "error" in tool_call_info:
                print(f"❌ {tool_call_info['error']}")
                continue

            # 第六步：调用MCP工具，执行天气查询，获取结果（步骤3）
            weather_result = await call_mcp_tool(
                session=mcp_session,
                tool_name=tool_call_info["name"],
                parameters=tool_call_info["parameters"]
            )

            # 第七步：格式化打印天气查询结果
            print(f"\n📝 天气查询结果如下：")
            print("-" * 40)
            print(weather_result)
            print("-" * 40)

    # 捕获所有可能的全局异常，打印友好错误提示
    except Exception as e:
        print(f"❌ 程序运行出错，具体原因：{str(e)}")


# ========================================
# 程序入口：运行异步主流程
# ========================================
if __name__ == "__main__":
    # asyncio.run()：运行异步主函数，管理整个异步程序的生命周期
    asyncio.run(main())
