# ====================== Pydantic 自定义字段校验演示（简洁注释） ======================
from pydantic import BaseModel, Field, field_validator

# 注释：单个字段（邮箱）自定义校验
# class User(BaseModel):
#     email: str
#     # field_validator("email")：给email字段绑定自定义校验器
#     @field_validator("email")
#     def email_validator(cls, v):  # cls：当前模型类，v：待校验的字段值
#         if "@" not in v:
#             raise ValueError("邮箱格式错误")  # 校验失败抛出异常
#         return v.lower() # 校验通过，返回小写格式化后的邮箱
#
# # 正确：邮箱包含@，校验通过
# user = User(email="1360491458@qq.com")
# print(user)
#
# # 错误：邮箱无@，触发校验异常
# user2 = User(email="laowang")
# print(user2)

# 注释：用户名长度 + 关键字校验
# class User(BaseModel):
#     name: str = Field(..., min_length=1, max_length=10)  # 字段长度约束
#     @field_validator("name")
#     def name_validator(cls, v):
#         if "admin" in v:  # 禁止用户名包含admin关键字
#             raise ValueError("用户名错误")
#         return v.lower()  # 返回小写用户名
#
# # 正确：用户名符合长度和关键字要求
# user = User(name="laowang")
# print(user)
# # 错误：用户名包含admin，触发异常
# user2 = User(name="admin")
# print(user2)

# 密码复杂程度自定义校验（多条件组合校验）
class User(BaseModel):
    password: str  # 待校验的密码字段
    # 给password字段绑定自定义校验器
    @field_validator("password")
    def password_validator(cls, v):
        errors = []  # 存储所有校验失败信息
        if len(v) < 8:
            errors.append("至少8个字符")  # 长度不足8位的错误
        if not any(c.isupper() for c in v):
            errors.append("至少1个大写字母")  # 无大写字母的错误
        if errors:
            # 多个错误用分号拼接，统一抛出
            raise ValueError(";".join(errors))
        return v  # 校验通过，返回原始密码

# 正确：密码满足长度和大写字母要求
user = User(password="Abc123456")
print(user.password)

# 错误：密码长度不足且无大写字母（注释状态，取消注释可触发异常）
# user2 = User(password="abc123")
# print(user2.password)

# 注释：多字段共享同一个校验逻辑（复用校验规则）
# class Product(BaseModel):
#     price: float
#     stock: int
#     # 给price和stock字段绑定同一个校验器
#     @field_validator("price", "stock")
#     def price_stock_validator(cls, v):
#         if v < 0:  # 校验数值不能为负数
#             raise ValueError("必须>=0")
#         return v  # 校验通过，返回原始值
#
# # 正确：price和stock均为非负数，校验通过
# product = Product(price=10.5, stock=10)
# print(product)
# # 错误：price和stock均为负数，触发异常
# product2 = Product(price=-10.5, stock=-10)
# print(product2)
