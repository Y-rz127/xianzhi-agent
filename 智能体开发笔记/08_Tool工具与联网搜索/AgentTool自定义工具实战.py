# ==================== Agent Tool 核心实战：自定义工具开发 ====================
# 导入LangChain工具开发核心模块：tool装饰器用于定义Agent可调用的工具
from langchain_core.tools import tool
# 导入Pydantic的Field：用于定义工具参数的约束（描述、必填等）
from pydantic import Field
# 导入BaseModel：作为工具参数校验的基类（Pydantic模型，用于参数结构化）
from unstructured_client.types import BaseModel

# -------------------- 第一步：定义工具参数校验模型 --------------------
# 继承BaseModel（Pydantic），为工具参数做结构化定义和校验
# 作用：告诉大模型工具需要哪些参数、参数类型、参数描述，同时校验输入参数的合法性
class CalculatorInput(BaseModel) :
    # 定义第一个参数a：int类型，Field(...)表示必填，description是给大模型看的参数说明
    a: int = Field(..., description="第一个参数（整数），用于乘法运算")
    # 定义第二个参数b：int类型，必填，描述第二个乘法参数
    b: int = Field(..., description="第二个参数（整数），用于乘法运算")

# -------------------- 第二步：使用@tool装饰器定义自定义工具 --------------------
# @tool装饰器：将普通Python函数转换为LangChain Agent可调用的工具
# 参数说明：
#   1. "multiply-tool"：工具唯一名称（大模型会通过该名称识别并调用工具）
#   2. args_schema=CalculatorInput：指定参数校验模型，约束输入参数的类型和结构
#   3. return_direct=False：返回模式，False表示Agent会基于工具结果继续生成文本；True表示直接返回工具结果
#   4. description：工具功能描述（给大模型看，告诉大模型这个工具的作用）
@tool("multiply-tool",
      args_schema=CalculatorInput,
      return_direct=False,
      description="该工具用于执行两个整数的乘法运算，输入两个整数a和b，返回a*b的结果")
def multiply(a:int, b: int) -> int:
    """
    工具核心逻辑：实现两个整数的乘法运算
    :param a: 第一个整数参数（由args_schema校验类型）
    :param b: 第二个整数参数（由args_schema校验类型）
    :return: 两个数相乘的结果（int类型）
    """
    return a * b

# -------------------- 第三步：查看工具的元信息（验证工具定义） --------------------
# 打印工具名称（对应@tool装饰器中第一个参数）
print("工具名称:" , multiply.name)
# 打印工具描述（对应@tool装饰器的description参数）
print("工具描述:" , multiply.description)
# 打印工具参数定义（由args_schema自动解析，展示参数名、类型、描述）
print("工具参数:" , multiply.args)
# 打印工具返回模式：return_direct=False表示Agent会基于工具结果继续推理；True则直接返回结果
# 适用场景：简单任务（如纯计算）设为True，复杂任务（需总结结果）设为False
print("工具返回模式:" , multiply.return_direct)
# 打印工具参数的详细Schema（JSON格式）：大模型会读取该Schema理解参数要求
print("工具详细Schema:", multiply.args_schema.model_json_schema())

# -------------------- 第四步：调用工具（模拟Agent调用逻辑） --------------------
# invoke方法：工具的标准调用方式，传入字典格式的参数（需匹配args_schema定义）
# 底层会先通过CalculatorInput校验参数类型（如传字符串会报错），再执行multiply函数
print("工具调用结果:", multiply.invoke({"a":2,"b":3}))  # 输出：6

# -------------------- 核心说明 --------------------
# 工具的详细约束（参数类型、描述、Schema）会传递给大模型，帮助大模型：
# 1. 判断何时需要调用该工具（比如用户问"2乘3等于多少"时）；
# 2. 正确构造参数（确保传入整数a和b，而非其他类型）；
# 3. 理解工具返回结果的含义，进而生成符合需求的回答。
