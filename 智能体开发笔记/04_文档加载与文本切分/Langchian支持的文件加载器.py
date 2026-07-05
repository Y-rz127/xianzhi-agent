# RAG支持的加载器
from langchain_community.document_loaders import (
    TextLoader, # 文本加载
    UnstructuredURLLoader,# 网页加载
    UnstructuredFileLoader,# 文件加载
    PyPDFLoader, # pdf加载
    Docx2txtLoader, # docx加载
    CSVLoader, # csv加载
    UnstructuredHTMLLoader  ,# html加载
    SeleniumURLLoader , # 动态加载
    WebBaseLoader, # 网页加载
    JSONLoader, # json加载
)
