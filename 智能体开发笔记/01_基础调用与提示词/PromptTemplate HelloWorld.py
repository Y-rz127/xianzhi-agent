# 核心思想：提示词的组成 = 固定模板 + 动态变量
# 该代码演示了LangChain中PromptTemplate的两种创建方式、变量填充、默认值设置及内部属性查看

# 从langchain的提示词模块中导入PromptTemplate类，用于构建标准化提示词模板
from langchain.prompts import PromptTemplate

# 定义提示词模板字符串，使用大括号{}标记动态变量，后续可通过参数填充
# {domain}：领域变量，{language}：回答语言变量，{question}：用户问题变量
template = """
        你是一位专业的{domain}顾问，请用{language}回答：
        问题：{question}
        回答:
"""

# 通过类方法from_template创建prompt对象（此处注释掉，仅作演示）
# template：指定上面定义的模板字符串
# template_format="f-string"：指定模板格式化方式为f-string格式
# partial_variables={"domain":"机器学习"}：预先给domain变量设置固定默认值，后续无需重复传入
# PromptTemplate.from_template(template, template_format="f-string", partial_variables={"domain":"机器学习"})

# 通过构造方法（实例化）创建prompt对象，这是最常用的创建方式
prompt = PromptTemplate(
    # 指定要使用的提示词模板字符串
    template=template,
    # 声明模板中所有需要动态传入的输入变量，需与模板中的{变量名}一一对应
    input_variables=["domain","language","question"]
)

# 使用format方法填充模板中的所有占位符，传入对应变量的值，生成最终可直接使用的完整提示词
# 然后打印该完整提示词
print(prompt.format(domain="机器学习",language="中文",question="如何使用langchain?"))
# 打印prompt对象的输入变量列表，查看需要动态传入的变量名称
print(prompt.input_variables)




# 演示PromptTemplate中默认值（固定值）的设置方式
# 定义第二个提示词模板字符串，包含{analysis_type}（默认值变量）和{user_input}（动态输入变量）
template2 = """
    分析用户情绪（默认分析类型：{analysis_type}）
    用户输入:{user_input}
    分析结果
"""

# 实例化第二个PromptTemplate对象，演示partial_variables的使用
prompt2 = PromptTemplate(
    template=template2,  # 指定第二个提示词模板字符串
    input_variables=["user_input"],  # 仅声明需要动态传入的变量，不声明要设置默认值的analysis_type
    partial_variables={"analysis_type":"sentiment"},  # 设置固定默认值（前置变量），格式化前预先填充到模板，后续无需传入
    template_format = "f-string"  # 指定模板的格式化类型为f-string（支持Python的f-string语法）
)

# 打印prompt2对象本身，查看其基本信息
print(prompt2)
# 仅传入动态变量user_input的值，即可格式化生成完整提示词（analysis_type使用partial_variables中设置的默认值）
print(prompt2.format(user_input="今天天气不错"))

# 打印prompt2对象的各类内部变量，深入了解其属性
print(prompt2.input_variables)  # 打印需要动态传入的输入变量列表
print(prompt2.partial_variables)  # 打印预先设置的固定默认值（部分变量）字典
print(prompt2.template_format)  # 打印模板使用的格式化类型
print(prompt2.template)  # 打印原始的提示词模板字符串
print(prompt2.output_parser)  # 打印提示词输出解析器（默认None，可自定义设置用于解析大模型返回结果）
