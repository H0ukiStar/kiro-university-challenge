"""``confirm.prompt_decision`` の対話ロジックに対するユニットテスト。

擬似 ``input_fn`` を注入し、承認・拒否・無効入力の再試行・EOF 再送出といった
振る舞いを検証する。プロンプト文言には依存せず、戻り値と呼び出し回数のみを確認する。
"""

from collections.abc import Callable

import pytest

from aws_eip_cleaner.confirm import ConfirmDecision, prompt_decision
from aws_eip_cleaner.models import UnusedEip

_EIP = UnusedEip(
    allocation_id="eipalloc-xxxx",
    public_ip="203.0.113.1",
    region="us-east-1",
)


def _make_input_fn(responses: list[str]) -> tuple[Callable[[str], str], list[str]]:
    """指定した値を順に返す擬似 ``input_fn`` を生成する。

    呼び出しごとに ``responses`` の先頭から値を返し、渡されたプロンプト文字列を
    記録用リストへ蓄積する。呼び出し回数は記録用リストの長さで検証できる。

    Parameters
    ----------
    responses : list[str]
        呼び出し順に返す入力文字列のリスト。

    Returns
    -------
    tuple[Callable[[str], str], list[str]]
        擬似 ``input_fn`` と、呼び出し時のプロンプトを記録するリストの組。
    """
    calls: list[str] = []
    iterator = iter(responses)

    def input_fn(prompt: str) -> str:
        calls.append(prompt)
        return next(iterator)

    return input_fn, calls


def test_returns_reject_after_three_invalid_inputs() -> None:
    """無効入力が 3 回連続すると REJECT を返すことを検証する。

    Validates: Requirements 8.1, 8.5
    """
    input_fn, calls = _make_input_fn(["x", "x", "x"])

    decision = prompt_decision(_EIP, input_fn)

    assert decision is ConfirmDecision.REJECT
    assert len(calls) == 3


def test_returns_approve_immediately_on_yes() -> None:
    """``y`` 系の入力で即座に APPROVE を返し input_fn が 1 回だけ呼ばれる。

    Validates: Requirements 8.1, 8.5
    """
    for raw in ["y", "Y", " y "]:
        input_fn, calls = _make_input_fn([raw])

        decision = prompt_decision(_EIP, input_fn)

        assert decision is ConfirmDecision.APPROVE
        assert len(calls) == 1


def test_returns_reject_immediately_on_no() -> None:
    """``n`` の入力で即座に REJECT を返し input_fn が 1 回だけ呼ばれることを検証する。

    Validates: Requirements 8.1, 8.5
    """
    input_fn, calls = _make_input_fn(["n"])

    decision = prompt_decision(_EIP, input_fn)

    assert decision is ConfirmDecision.REJECT
    assert len(calls) == 1


def test_returns_approve_after_invalid_then_valid() -> None:
    """無効入力の後に有効入力を受け取ると 2 回目で APPROVE を返すことを検証する。

    Validates: Requirements 8.1, 8.5
    """
    input_fn, calls = _make_input_fn(["x", "y"])

    decision = prompt_decision(_EIP, input_fn)

    assert decision is ConfirmDecision.APPROVE
    assert len(calls) == 2


def test_reraises_eof_error() -> None:
    """input_fn の EOFError を prompt_decision がそのまま再送出することを検証する。

    Validates: Requirements 8.1, 8.5
    """

    def input_fn(prompt: str) -> str:
        raise EOFError

    with pytest.raises(EOFError):
        prompt_decision(_EIP, input_fn)
