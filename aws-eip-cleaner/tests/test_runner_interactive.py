"""``runner.run_interactive`` に対するユニットテスト。

擬似 ``input_fn`` を用いて、EOF による中断（残りが解放されないこと）と、解放失敗時の
継続（次の EIP へ進むこと）を検証する。
"""

from collections.abc import Callable

import pytest

from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import UnusedEip
from aws_eip_cleaner.runner import run_interactive


def _make_eip(index: int) -> UnusedEip:
    """テスト用の未利用 EIP を生成する。

    Parameters
    ----------
    index : int
        識別のための連番。割り当て ID とパブリック IP に反映する。

    Returns
    -------
    UnusedEip
        生成した未利用 EIP。
    """
    return UnusedEip(
        allocation_id=f"eipalloc-{index:04d}",
        public_ip=f"203.0.113.{index}",
        region="us-east-1",
    )


def _make_input_fn(responses: list[str | type[EOFError]]) -> Callable[[str], str]:
    """指定した応答を順に返す擬似 ``input_fn`` を生成する。

    要素が ``EOFError`` の場合はその呼び出しで ``EOFError`` を送出する。

    Parameters
    ----------
    responses : list[str | type[EOFError]]
        呼び出し順に返す応答（文字列）または ``EOFError`` 送出指示。

    Returns
    -------
    Callable[[str], str]
        擬似 ``input_fn``。
    """
    iterator = iter(responses)

    def input_fn(prompt: str) -> str:
        value = next(iterator)
        if value is EOFError:
            raise EOFError
        assert isinstance(value, str)
        return value

    return input_fn


def test_eof_aborts_and_skips_remaining() -> None:
    """EOF 発生後、残りの EIP が解放されないことを検証する。

    1 件目を承認して解放し、2 件目の確認で EOF が発生する。3 件目以降は解放されない。

    Validates: Requirements 8.6
    """
    eips = [_make_eip(i) for i in range(3)]
    released: list[UnusedEip] = []
    input_fn = _make_input_fn(["y", EOFError])

    summary = run_interactive(eips, input_fn, released.append)

    assert released == [eips[0]]
    assert summary.succeeded == 1
    assert summary.failed == 0


def test_release_failure_continues_to_next() -> None:
    """解放失敗（EipReleaseError）でも次の EIP へ進み集計されることを検証する。

    Validates: Requirements 8.7
    """
    eips = [_make_eip(i) for i in range(2)]
    input_fn = _make_input_fn(["y", "y"])

    def release_fn(eip: UnusedEip) -> None:
        if eip.allocation_id == eips[0].allocation_id:
            raise EipReleaseError("解放に失敗しました")

    summary = run_interactive(eips, input_fn, release_fn)

    assert summary.succeeded == 1
    assert summary.failed == 1


def test_release_failure_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """解放失敗時に allocation_id を含む ERROR ログが出力されることを検証する。

    Validates: Requirements 8.7
    """
    eip = _make_eip(5)
    input_fn = _make_input_fn(["y"])

    def release_fn(target: UnusedEip) -> None:
        raise EipReleaseError("boom")

    with caplog.at_level("ERROR"):
        summary = run_interactive([eip], input_fn, release_fn)

    assert summary.failed == 1
    assert any(
        eip.allocation_id in record.getMessage() and record.levelname == "ERROR"
        for record in caplog.records
    )


def test_rejected_eip_is_not_released() -> None:
    """拒否した EIP は解放されず、承認した EIP のみ解放されることを検証する。

    Validates: Requirements 8.7
    """
    eips = [_make_eip(i) for i in range(2)]
    released: list[UnusedEip] = []
    input_fn = _make_input_fn(["n", "y"])

    summary = run_interactive(eips, input_fn, released.append)

    assert released == [eips[1]]
    assert summary.succeeded == 1
    assert summary.failed == 0
