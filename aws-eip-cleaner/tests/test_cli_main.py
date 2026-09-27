"""``cli.main`` の 0 件境界・終了コードに対する統合テスト。

AWS へアクセスせず ``main`` のオーケストレーションを検証するため、cli モジュールへ
取り込まれた認証解決・リージョン解決・並列調査・クライアント生成・解放の各関数を
monkeypatch で差し替える。0 件時の終了コード 0 と対象なしメッセージ、解放失敗・
調査失敗時の非ゼロ終了、全件成功時の終了コード 0 を capsys とともに確認する。
"""

import pytest

from aws_eip_cleaner import cli
from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import AggregatedResult, UnusedEip


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


def _make_aggregated(
    unused_eips: list[UnusedEip] | None = None,
    succeeded_regions: list[str] | None = None,
    failed_regions: dict[str, str] | None = None,
) -> AggregatedResult:
    """テスト用の集約結果を生成する。

    Parameters
    ----------
    unused_eips : list[UnusedEip] | None, optional
        検出した未利用 EIP。None の場合は空リストとする。
    succeeded_regions : list[str] | None, optional
        調査に成功したリージョン。None の場合は ``["us-east-1"]`` とする。
    failed_regions : dict[str, str] | None, optional
        調査に失敗したリージョンとエラー内容。None の場合は空とする。

    Returns
    -------
    AggregatedResult
        生成した集約結果。
    """
    return AggregatedResult(
        unused_eips=unused_eips if unused_eips is not None else [],
        succeeded_regions=(
            succeeded_regions if succeeded_regions is not None else ["us-east-1"]
        ),
        failed_regions=failed_regions if failed_regions is not None else {},
    )


def _patch_common(
    monkeypatch: pytest.MonkeyPatch, aggregated: AggregatedResult
) -> None:
    """認証解決・リージョン解決・並列調査を固定値へ差し替える。

    ``resolve_session`` はダミーセッションを、``resolve_target_regions`` は固定の
    リージョンリストを、``scan_regions`` は与えた集約結果を返すよう置換する。これにより
    AWS へアクセスせずに ``main`` の分岐を制御できる。

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        差し替えに用いる monkeypatch フィクスチャ。
    aggregated : AggregatedResult
        ``scan_regions`` の戻り値として注入する集約結果。
    """
    monkeypatch.setattr(cli, "resolve_session", lambda profile: object())
    monkeypatch.setattr(
        cli, "resolve_target_regions", lambda regions, session: ["us-east-1"]
    )
    monkeypatch.setattr(cli, "scan_regions", lambda scan_fn, regions: aggregated)


def test_zero_eips_dry_run_returns_zero_and_shows_total(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 件・dry-run で終了コード 0 を返し、合計 0 件が表示されることを検証する。

    Validates: Requirements 6.3, 7.3
    """
    _patch_common(monkeypatch, _make_aggregated())

    exit_code = cli.main(["--dry-run"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "合計: 0 件" in out


def test_zero_eips_yes_returns_zero_and_shows_no_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 件・yes モードで終了コード 0 を返し、対象なしメッセージが出ることを検証する。

    Validates: Requirements 6.3, 9.6
    """
    _patch_common(monkeypatch, _make_aggregated())

    exit_code = cli.main(["--yes"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "合計: 0 件" in out


def test_zero_eips_interactive_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 件・対話モードで入力なしに終了コード 0 を返すことを検証する。

    Validates: Requirements 6.3
    """
    _patch_common(monkeypatch, _make_aggregated())

    exit_code = cli.main([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "合計: 0 件" in out


def test_release_failure_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """解放失敗時に非ゼロ（1）の終了コードを返すことを検証する。

    Validates: Requirements 9.4
    """
    _patch_common(monkeypatch, _make_aggregated(unused_eips=[_make_eip(1)]))
    monkeypatch.setattr(cli, "create_ec2_client", lambda session, region: object())

    def failing_release(client: object, eip: UnusedEip) -> None:
        raise EipReleaseError("解放に失敗しました")

    monkeypatch.setattr(cli, "release_eip", failing_release)

    exit_code = cli.main(["--yes"])

    assert exit_code == 1


def test_scan_failure_returns_nonzero_even_with_zero_eips(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 件でも調査失敗があれば非ゼロの終了コードを返すことを検証する。

    Validates: Requirements 6.3
    """
    _patch_common(
        monkeypatch,
        _make_aggregated(succeeded_regions=[], failed_regions={"us-west-2": "boom"}),
    )

    exit_code = cli.main(["--dry-run"])

    assert exit_code != 0


def test_all_success_yes_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """全件解放成功・yes モードで終了コード 0 を返すことを検証する。

    Validates: Requirements 9.6
    """
    _patch_common(
        monkeypatch, _make_aggregated(unused_eips=[_make_eip(1), _make_eip(2)])
    )
    monkeypatch.setattr(cli, "create_ec2_client", lambda session, region: object())
    monkeypatch.setattr(cli, "release_eip", lambda client, eip: None)

    exit_code = cli.main(["--yes"])

    assert exit_code == 0
