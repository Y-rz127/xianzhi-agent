# ====================== Pydantic 核心功能演示（简洁注释） ======================
from typing import Optional
from pydantic import BaseModel, Field

# 1. 必填字段演示
class User(BaseModel):
    # Field(...) 标记必填字段，title为字段说明
    name: str = Field(..., title="Name of the user")

# 正确：传入必填字段name
user = User(name="Alice")

# 错误：传入模型未定义的age字段，触发校验异常
user2 = User(name="Alice",age=18)
print(2)

# 2. 可选字段（带默认值）
class UserOptional(BaseModel):
    # Field指定默认值，实例化时可省略该字段
    name: str = Field("laowang", title="Name of the user")

user_optional = UserOptional()
print(user_optional.name)

# 3. 数值类型范围校验
class Product(BaseModel):
    price: float = Field(..., gt=0)  # gt=0：必须大于0
    stock: int = Field(..., ge=0)    # ge=0：必须大于等于0

# 正确：数值符合范围要求
product = Product(price=10.5, stock=10)
print(product)

# 错误：数值超出合法范围，捕获异常
try:
    Product(price=-10.5, stock=-10)
except ValueError as e:
    print(e.errors())

# 4. 嵌套模型校验（has-a关系）
class User(BaseModel):
    name: str = Field(...)
    address: Address = Field(...)  # 嵌套Address模型，必填

class Address(BaseModel):
    city: str = Field(..., min_length=1)  # city非空字符串
    country: str  # 默认必填

# 正确：嵌套模型字段符合要求
user = User(name="Alice", address=Address(city="Shanghai", country="China"))
print(user)

# 错误：city为空字符串，违反min_length约束
try:
    user = User(name="Alice", address=Address(city="", country="China"))
except ValueError as e:
    print(e.errors())

# 5. 明确可选字段
class User(BaseModel):
    name: str = Field(...)
    # Optional[str] + Field(None)：可选字段，默认值None
    email: Optional[str] = Field(None)

# 正确：省略可选字段email
user = User(name="Alice")
print(user)

# 6. 混合使用必填与带约束的可选字段
class Config(BaseModel):
    api_key: str = Field(..., title="Name of the user")  # 必填
    timeout: int = Field(10, ge=1)  # 可选，默认10，且值≥1

# 正确：省略timeout，使用默认值
config = Config(api_key="123456")
print(config)
assert config.timeout == 10  # 验证默认值

# 错误：缺少必填api_key，且timeout＜1
try:
    config = Config(timeout=-1)
except ValueError as e:
    print(e.errors())
