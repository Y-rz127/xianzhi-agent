# ====================== 核心功能：Pydantic 核心用法演示（数据校验、类型转换、JSON序列化/反序列化）
# 从 pydantic 库导入核心组件
# BaseModel：所有Pydantic模型的基类，提供数据校验、序列化等核心能力
# ValidationError：数据校验失败时抛出的异常类
# HttpUrl：专门用于校验URL格式合法性的特殊类型（必须带http/https协议头）
from pydantic import BaseModel, ValidationError, HttpUrl

# 1. 基础模型定义：包含必填字段、可选字段
class UserProfile(BaseModel):
    # 字符串类型字段，无默认值 → 必须字段（实例化时必须传入，否则校验失败）
    username: str
    # 整数类型字段，无默认值 → 必须字段
    age: int
    # str | None：类型为字符串或空值None；= None：设置默认值为None → 可选字段（实例化时可省略）
    email: str | None = None

# 实例化验证：传入所有必填字段，可选字段省略（自动使用默认值None），校验通过
user = UserProfile(username='alice', age=18)
print(user)  # 打印模型实例，输出字段名和对应值

# 自动类型转换：Pydantic 会自动尝试将传入值转换为字段声明的类型（此处"18"字符串自动转为int类型18）
# 注意：仅支持可安全转换的类型，如字符串数字转整数/浮点数，无法将非数字字符串转为整数
user2 = UserProfile(username='alice', age="18")
print(user2)  # 打印转换后的模型实例，age字段实际为int类型18

# 2. 实例化异常捕获：缺少必填字段/类型不匹配时，会抛出校验异常
try:
    # 错误：1. 缺少必填字段age；2. username传入整数123，不符合str类型要求
    UserProfile(username=123)
except ValidationError as e:  # 推荐捕获ValidationError（ValueError的子类，更精准）
    print(e.errors())  # 打印详细的校验错误信息（包含错误字段、错误类型、错误描述）

# 3. 特殊类型校验 + 默认值：演示URL格式校验、字段默认值
class WebSite(BaseModel):
    url: HttpUrl  # 特殊类型：校验URL格式（必须包含http/https协议头，否则校验失败）
    visit: int = 0  # 整数类型字段，设置默认值0 → 可选字段（实例化时可省略）
    tags : list[str] = []  # 字符串列表类型字段，设置默认值为空列表 → 可选字段

# 准备符合模型约束的合法数据（字典格式）
valid_data = {
    "url": "https://www.baidu.com",  # 完整URL（带https协议头），符合HttpUrl要求
    "visit": 100,  # 整数类型，符合要求
    "tags": ["python", "pydantic"]  # 字符串列表，符合要求
}

# 正确实例化：使用**解包字典传入参数，所有字段符合约束，校验通过
try:
    webSite = WebSite(**valid_data)
    print(webSite)  # 打印合法的WebSite模型实例
except ValidationError as e:
    print(e.errors())

# 错误实例化：URL缺少http/https协议头，不符合HttpUrl校验规则
try:
    # 错误：url传入"www.baidu.com"（仅域名，无协议头），违反HttpUrl格式要求
    webSite = WebSite(url = "www.baidu.com")
    print(webSite)
except ValidationError as e:
    print(e.errors())  # 打印URL格式错误的详细信息

# 4. JSON序列化与反序列化：演示模型与JSON字符串、字典的相互转换
class Item(BaseModel):
    name: str  # 字符串类型，必填字段
    price: float  # 浮点类型，必填字段

# 准备JSON格式字符串（模拟接口返回/文件读取的JSON数据）
data = """{"name":"apple","price":1.23}"""  # 字符串中的数字会被自动转换为对应数值类型
# 从JSON字符串解析并校验：model_validate_json 自动解析JSON字符串，校验数据合法性并转换为模型实例
# 特性：字符串数字（如"1.23"）会自动转换为浮点数/整数类型
item = Item.model_validate_json(data)
print(item)  # 打印解析后的Item模型实例

# 模型实例转为Python字典：model_dump 方法将模型转为键值对格式的字典（类似Java POJO转Map）
# 字典的key对应模型字段名，value对应模型字段值，方便Python内部数据处理
print(item.model_dump())

# 模型实例转为JSON格式字符串：model_dump_json 方法自动序列化模型为标准JSON字符串
# 方便数据传输（如接口返回）、文件持久化（如写入.json文件），无需手动调用json.dumps()
print(item.model_dump_json())
