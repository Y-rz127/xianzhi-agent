"""共享单例状态。

集中管理 Xianzhi、LoveApp、RAG Chain 的运行时实例，
供各子路由模块访问，避免循环导入。
"""
from __future__ import annotations

_xianzhi = None
_love_app = None
_rag_chain = None
_tarot_app = None


def set_instances(xianzhi, love_app, rag_chain=None, tarot_app=None):
    global _xianzhi, _love_app, _rag_chain, _tarot_app
    _xianzhi = xianzhi
    _love_app = love_app
    _rag_chain = rag_chain
    _tarot_app = tarot_app
