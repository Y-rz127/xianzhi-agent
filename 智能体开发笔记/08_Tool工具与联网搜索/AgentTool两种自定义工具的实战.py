# ==================== Agent Tool 实战：两种自定义工具的方式 ====================
# 导入类型注解模块：Type 用于标注 args_schema 的类型（BaseModel的子类）
from typing import Type

# 导入LangChain工具核心基类：BaseTool是所有自定义工具的父类，定义了工具的核心规范
from langchain_core.tools import BaseTool
# 导入Pydantic核心模块：BaseModel用于参数结构化校验，Field用于参数描述/约束
from pydantic import BaseModel, Field


# -------------------- 方式1：快捷定义（注释掉的示例）：StructuredTool.from_function --------------------
# 该方式是「装饰器@tool」的底层实现，通过函数快速封装为工具，无需手动定义类
# 适合简单工具（仅需封装单个函数，无需自定义复杂逻辑）

# # 步骤1：定义参数校验模型（Pydantic），约束工具输入参数的类型和描述
# class CalculatorInput(BaseModel) :
#     a: int = Field(..., description="第一个参数（整数，必填）")
#     b: int = Field(..., description="第二个参数（整数，必填）")
#
# # 步骤2：定义工具核心逻辑函数
# def multiply(a:int, b: int) -> int:
#     """工具核心功能：实现两个整数的乘法运算"""
#     return a * b
#
# # 步骤3：将函数快速封装为StructuredTool（BaseTool的子类）
# multiply = StructuredTool.from_function(multiply)
#
# # 也可以在封装时自定义工具元信息（名称、描述、参数约束等）
# tools = [
#     StructuredTool.from_function(
#         func=multiply,          # 绑定工具核心函数
#         name="multiply",        # 自定义工具名称（大模型识别工具的标识）
#         description="乘法计算", # 工具描述（告诉大模型工具的用途）
#         args_schema=CalculatorInput, # 指定参数校验模型（约束输入）
#         return_direct=True,     # 返回模式：直接返回工具结果，Agent不额外推理
#     )
# ]
#
# # 打印工具元信息（验证工具定义）
# print("工具名称:" , multiply.name)
# print("工具描述:" , multiply.description)
# print("工具参数:" , multiply.args)  # 自动解析args_schema生成的参数列表
# print("工具返回模式:" , multiply.return_direct)
# # 打印参数详细Schema（JSON格式，供大模型读取参数要求）
# print("工具详细Schema:",multiply.args_schema.model_json_schema())
#
# # 调用工具（传入字典格式参数，自动校验类型）
# print(multiply.invoke({"a":2,"b":3}))  # 输出：6
# # 核心说明：工具的元信息（名称、描述、参数约束）会传递给大模型，帮助大模型判断何时调用、如何传参


# -------------------- 方式2：自定义类（推荐复杂场景）：继承 BaseTool 类 --------------------
# 该方式更灵活，可自定义工具的初始化、运行逻辑、额外属性等，适合复杂工具开发

# 步骤1：定义参数校验模型（Pydantic），约束工具输入参数
class CalculatorInput(BaseModel) :
    # Field描述参数含义（给大模型看），未加...表示非必填（若需必填需加 Field(..., description="")）
    a: int = Field(description="第一个乘法参数（整数）")
    b: int = Field(description="第二个乘法参数（整数）")

# 步骤2：自定义工具类（继承BaseTool，必须实现 _run 方法）
class CustomCalculatorTool(BaseTool) :
    # 工具核心元信息（固定属性，需显式定义）
    name : str = "custom_multiply_tool"  # 工具唯一名称（大模型识别用）
    description : str = "当你需要计算两个整数的乘法问题时使用该工具"  # 工具用途描述
    args_schema : Type[BaseModel] = CalculatorInput  # 绑定参数校验模型（Type[BaseModel]标注类型）
    return_direct : bool = True  # 返回模式：True=直接返回工具结果，False=Agent基于结果继续推理

    # 核心方法：_run（必须实现），定义工具的实际执行逻辑
    # 参数需与args_schema中的字段一一对应（a、b）
    def _run(self, a:int, b: int) -> int:
        """
        工具核心执行逻辑：实现两个整数的乘法运算
        :param a: 第一个整数参数（由args_schema校验类型）
        :param b: 第二个整数参数（由args_schema校验类型）
        :return: 两个数相乘的结果（int类型）
        """
        return a * b

# 步骤3：实例化自定义工具
multiply = CustomCalculatorTool()

# 步骤4：查看工具元信息（验证工具定义）
print("工具名称:" , multiply.name)  # 输出：custom_multiply_tool
print("工具描述:" , multiply.description)  # 输出：当你需要计算数学问题时使用
print("工具参数:" , multiply.args)  # 输出参数列表（从args_schema解析）
print("工具返回模式:" , multiply.return_direct)  # 输出：True
# 打印参数详细Schema（JSON格式，大模型会读取该信息理解参数要求）
print("工具详细Schema:", multiply.args_schema.model_json_schema())

# （可选）调用工具（需传入符合args_schema的参数字典）
# print(multiply.invoke({"a":2,"b":3}))  # 输出：6
