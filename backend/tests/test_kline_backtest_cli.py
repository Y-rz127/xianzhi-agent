"""关系回测 CLI（`scripts/kline_backtest.py --pair`）的契约测试。

为什么值得单开一个文件：`scripts/` **不在任何测试或架构守卫的扫描范围内**，
而这个脚本是**共振权重唯一的校准入口**（20 个诊断数字手机上摆不下，
只有控制台能摊开）。它此前零覆盖。

最该钉住的是**事件字典的键名**。CLI 从 JSON / DB 读出 camelCase 键
（`birthTimeA` / `ganzhiYear` …），`_backtest_pair_groups` 也按 camelCase 取。
键名对不上**不会抛错**：每条事件都落进「区间外」，于是 CLI 打印出一份
排版漂亮、逻辑自洽、基于 0 条样本的报告。用户会以为"数据不够"，
而不是"工具读不到我的数据"。`test_events_are_actually_used` 就是为此存在的。

第二该钉住的是**参数拦截**：`--pair` 下 `--dimension` / `--predictor` 是无效的，
拦下来（报错）比静默忽略好 —— 静默忽略会让人以为自己调过口径了。
"""

from __future__ import annotations

import functools
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@functools.lru_cache(maxsize=1)
def cli():
    """显式按路径加载 CLI 模块。

    不用 `import kline_backtest`：它与 `app.domain.kline_backtest` **同名**，
    一旦 `sys.path` 顺序变了就会静默加载到另一个模块 —— 测试照样"全绿"，
    却一行 CLI 代码都没跑到，是最坏的那种假绿。
    """
    spec = importlib.util.spec_from_file_location(
        "kline_cli_under_test", SCRIPTS_DIR / "kline_backtest.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 一对真实可建的盘。年份取 2015/2016 —— 两张盘都是 1980 年代出生，
# 1-100 虚岁的交集稳稳盖住这两年，不会因起运年不同而落到区间外。
SIDE_A = ("1985-01-05 00:00", "男")
SIDE_B = ("1986-03-20 14:30", "女")


def _event(ganzhi_year: int, polarity: int, relation: str = "夫妻", note: str = "") -> dict:
    return {
        "birthTimeA": SIDE_A[0],
        "genderA": SIDE_A[1],
        "birthTimeB": SIDE_B[0],
        "genderB": SIDE_B[1],
        "sect": 2,
        "yunSect": 1,
        "ganzhiYear": ganzhi_year,
        "polarity": polarity,
        "relation": relation,
        "note": note,
    }


def _write(tmp_path: Path, items: list[dict], name: str = "pair_events.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------- 端到端：离线 JSON 跑通整条 --pair ----------------
#
# 这是唯一能覆盖「键名 → 建盘 → 引擎 → 排版」全链路的测试，也是唯一
# 能发现 `_backtest_pair_groups` 与 CLI 之间字段约定断裂的地方。
# 建盘约 0.7s/对，一条用例的代价可以接受。


class TestPairCliEndToEnd:
    def test_events_are_actually_used(self, tmp_path, capsys):
        """键名对不上是**静默**失败：事件全变「区间外」，报告依然漂亮。

        已做变异验证（把 `ganzhiYear` 故意写成 `ganzhi_year`）：报告照旧打印
        回测窗口、按关系类型/按配对分组和两条告警，只有数字变成
        「0 条已用 / 2 条在共振区间外 / 涉及 0 对」。没有这条断言，
        这种断裂会一路绿着交到用户手里，而用户只会以为"我数据不够"。
        """
        path = _write(tmp_path, [_event(2015, 1), _event(2016, -1)])
        assert cli().main(["--pair", "--events", str(path), "--min-samples", "1"]) == 0
        out = capsys.readouterr().out
        assert "关系事件 2 条已用" in out
        assert "0 条在共振区间外" in out
        assert "0 条非法" in out

    def test_prints_term_diagnostics(self, tmp_path, capsys):
        """逐项诊断是本次功能的**真正产出**，不是附赠 —— 四项一个都不能少。"""
        path = _write(tmp_path, [_event(2015, 1), _event(2016, -1)])
        cli().main(["--pair", "--events", str(path), "--min-samples", "1"])
        out = capsys.readouterr().out
        assert "逐项诊断" in out
        for term in cli().KB.TERMS_ORDER:
            assert term in out, f"诊断表没打出 {term}"

    def test_reports_window_and_pair_denominator(self, tmp_path, capsys):
        """分母是「对」不是「张盘」，且必须把回测窗口说出来。

        窗口那行是在补一个真实的坑：图表按 max_dayun 画得比 AGE_SPAN 更远，
        用户录的晚年年份进不了回测，只看到"没有可用事件"会以为没存上。
        """
        path = _write(tmp_path, [_event(2015, 1), _event(2016, -1)])
        cli().main(["--pair", "--events", str(path), "--min-samples", "1"])
        out = capsys.readouterr().out
        assert "涉及 1 对" in out
        assert "回测窗口" in out
        assert f"1-{cli().KB.AGE_SPAN} 虚岁" in out

    def test_default_predictor_is_not_treated_as_violation(self, tmp_path, capsys):
        """`--predictor` 的默认值就是 close，默认值不该被当成"用户传了参数"。

        断言串要挑 "不接受" 这个前缀：报告正文里本来就有一句
        "（合盘只有共振一个预测源）"，拿它当判据会**无条件失败**。
        """
        path = _write(tmp_path, [_event(2015, 1)])
        assert cli().main(["--pair", "--events", str(path), "--min-samples", "1"]) == 0
        assert "--pair 不接受" not in capsys.readouterr().out


# ---------------- 参数契约 ----------------


class TestPairArgumentContract:
    """无效参数必须报错退出，而不是被忽略后照样给出一份"结果"。"""

    def test_rejects_auto_dimension(self):
        with pytest.raises(SystemExit) as exc:
            cli().main(["--pair", "--dimension", "auto"])
        assert exc.value.code == 2

    def test_rejects_predictor(self):
        with pytest.raises(SystemExit) as exc:
            cli().main(["--pair", "--predictor", "mean"])
        assert exc.value.code == 2

    def test_single_chart_still_accepts_both(self, tmp_path):
        """同一套参数在**单盘**下是合法的 —— 拦截只属于 `--pair`，别拦过头。

        注意单盘事件字典的键名是**混合**的：建盘参数 snake（`birth_time`/`gender`），
        事件字段 camel（`ganzhiYear`/`polarity`/`domain`）。这是 `list_kline_events`
        的原样返回，不是笔误 —— 而双盘（`birthTimeA`/`genderA`/`yunSect`）**全是 camel**。
        拿双盘的写法去填单盘，`_build_chart` 会拿到空生辰、报"出生时间为空"，
        所以这里刻意把两种形状都钉住。
        """
        path = _write(
            tmp_path,
            [
                {
                    "birth_time": SIDE_A[0],
                    "gender": SIDE_A[1],
                    "ganzhiYear": 2015,
                    "polarity": 1,
                    "domain": "career",
                }
            ],
        )
        assert cli().main(["--events", str(path), "--dimension", "auto"]) == 0


# ---------------- 空库分支 ----------------


class TestEmptyLibrary:
    def test_exits_2_with_entrypoint_hint(self, monkeypatch, capsys):
        """空库不是错误，是"还没数据"：退出码 2（可挂 CI）+ 指路，不要抛栈。"""
        monkeypatch.setattr(cli(), "_load_pair_events_from_db", list)
        assert cli().main(["--pair"]) == 2
        out = capsys.readouterr().out
        assert "关系事件库为空" in out
        assert "pair-events" in out

    def test_single_chart_message_does_not_say_relation(self, monkeypatch, capsys):
        """单盘分支的文案里不该混进"关系"二字 —— 照抄会让用户去录错表。"""
        monkeypatch.setattr(cli(), "_load_from_db", list)
        assert cli().main([]) == 2
        assert "关系" not in capsys.readouterr().out


# ---------------- 输入解析 ----------------


class TestLoadEvents:
    def test_accepts_bare_list(self, tmp_path):
        path = tmp_path / "bare.json"
        path.write_text(json.dumps([_event(2015, 1)], ensure_ascii=False), encoding="utf-8")
        assert len(cli()._load_events(str(path))) == 1

    def test_accepts_items_wrapper(self, tmp_path):
        path = _write(tmp_path, [_event(2015, 1)])
        assert len(cli()._load_events(str(path))) == 1

    def test_rejects_other_shapes(self, tmp_path):
        """`{"foo": 1}` 要当场报错，不能当成 0 条事件继续往下跑。"""
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"foo": 1}), encoding="utf-8")
        with pytest.raises(SystemExit):
            cli()._load_events(str(path))

    def test_dump_roundtrip(self, tmp_path, capsys):
        src = _write(tmp_path, [_event(2015, 1), _event(2016, -1)])
        dst = tmp_path / "out.json"
        assert cli().main(["--pair", "--events", str(src), "--dump", str(dst)]) == 0
        assert len(json.loads(dst.read_text(encoding="utf-8"))["items"]) == 2
        assert "已导出 2 条事件" in capsys.readouterr().out


# ---------------- 逐项诊断表的判定 ----------------
#
# 断言串必须挑得准：表头那行本身就含「相反」（"<=0 说明该项方向与现实相反"），
# 所以 `assert "相反" in text` 会**无条件通过**。要断言的是那句结论短语。


class TestTermRows:
    @staticmethod
    def _diag(term, mean_up, mean_down, delta, up=1, down=1, sign_ok=True) -> dict:
        return {
            "term": term,
            "meanUp": mean_up,
            "meanDown": mean_down,
            "delta": delta,
            "samplesUp": up,
            "samplesDown": down,
            "signOk": sign_ok,
        }

    def test_wrong_direction_points_at_the_weight(self):
        """delta<=0 是调权重的第一顺位，只给个负数不够，得说清往哪调。"""
        text = "\n".join(cli()._term_rows([self._diag("align", -1.0, 1.0, -2.0, sign_ok=False)]))
        assert "权重该先调这里" in text

    def test_insufficient_samples_is_not_a_verdict(self):
        """单侧没样本（signOk=None）只能说"样本不足" —— 把噪声叫成"相反"会误导调参。"""
        text = "\n".join(
            cli()._term_rows([self._diag("palace", None, None, None, up=0, down=0, sign_ok=None)])
        )
        assert "样本不足" in text
        assert "权重该先调这里" not in text

    def test_worst_term_comes_first(self):
        """表按 delta 升序：最该调的排最前，别让用户自己在四行里找。"""
        text = "\n".join(
            cli()._term_rows([self._diag("trend", 1.0, 1.0, 5.0), self._diag("align", 1.0, 1.0, -3.0)])
        )
        body = [ln for ln in text.splitlines() if ln.strip().startswith(("trend", "align"))]
        assert body[0].strip().startswith("align")

    def test_missing_samples_sink_to_the_bottom(self):
        """delta 为 None 的项没有可比性，不能混在中间冒充排序。"""
        text = "\n".join(
            cli()._term_rows(
                [
                    self._diag("palace", None, None, None, up=0, down=0, sign_ok=None),
                    self._diag("trend", 1.0, 1.0, 5.0),
                ]
            )
        )
        body = [ln for ln in text.splitlines() if ln.strip().startswith(("trend", "palace"))]
        assert body[0].strip().startswith("trend")
