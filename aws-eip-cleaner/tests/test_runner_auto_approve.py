"""``runner.run_auto_approve`` に対するユニットテスト。

総数・成功/失敗件数の表示、0 件時のメッセージと集計、部分失敗時の継続と集計を
capsys / 擬似解放関数で検証する。
"""

import pytest

from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import UnusedEip
from aws_eip_cleaner.runner import run_auto_approve


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


def test_shows_total_and_result_counts(capsys: pytest.CaptureFixture[str]) -> None:
    """総数と成功/失敗件数が表示され、集計が正しいことを検証する。

    Validates: Requirements 9.2, 9.3
    """
    eips = [_make_eip(i) for i in range(3)]

    summary = run_auto_approve(eips, lambda eip: None)

    assert summary.succeeded == 3
    assert summary.failed == 0
    out = capsys.readouterr().out
    assert "解放対象: 3 件" in out
    assert "解放成功: 3 件" in out
    assert "解放失敗: 0 件" in out


def test_empty_shows_no_target_message(capsys: pytest.CaptureFixture[str]) -> None:
    """0 件時に対象なしメッセージを表示し ReleaseSummary(0, 0) を返すことを検証する。

    Validates: Requirements 9.6
    """
    summary = run_auto_approve([], lambda eip: None)

    assert summary.succeeded == 0
    assert summary.failed == 0
    out = capsys.readouterr().out
    assert "解放対象の EIP はありません。" in out


def test_partial_failure_continues_and_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """一部が EipReleaseError でも継続し、成功/失敗が正しく集計されることを検証する。

    Validates: Requirements 9.2, 9.3
    """
    eips = [_make_eip(i) for i in range(4)]
    failing_ids = {eips[1].allocation_id, eips[3].allocation_id}

    def release_fn(eip: UnusedEip) -> None:
        if eip.allocation_id in failing_ids:
            raise EipReleaseError("解放に失敗しました")

    summary = run_auto_approve(eips, release_fn)

    assert summary.succeeded == 2
    assert summary.failed == 2
    out = capsys.readouterr().out
    assert "解放成功: 2 件" in out
    assert "解放失敗: 2 件" in out


def test_partial_failure_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """解放失敗時に allocation_id を含む ERROR ログが出力されることを検証する。

    Validates: Requirements 9.4, 10.3
    """
    eip = _make_eip(7)

    def release_fn(target: UnusedEip) -> None:
        raise EipReleaseError("boom")

    with caplog.at_level("ERROR"):
        summary = run_auto_approve([eip], release_fn)

    assert summary.failed == 1
    assert any(
        eip.allocation_id in record.getMessage() and record.levelname == "ERROR"
        for record in caplog.records
    )
