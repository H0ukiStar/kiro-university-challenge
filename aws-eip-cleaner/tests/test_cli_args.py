"""CLI の引数解析・検証のユニットテスト。

``build_parser`` / ``parse_args`` / ``validate_options`` を対象に、既定値の解決、
明示指定の解析、未知オプションや値不足時の ``SystemExit(2)`` と標準エラー出力、
``--help`` 時の ``SystemExit(0)`` と標準出力、オプション競合、``--region`` の
指定回数上限（境界値 50 の許容・51 の拒否）を検証する。
"""

import argparse

import pytest

from aws_eip_cleaner.cli import build_parser, parse_args, validate_options
from aws_eip_cleaner.errors import OptionConflictError, TooManyRegionsError


def _build_region_argv(count: int) -> list[str]:
    """``--region`` を指定回数分だけ並べた argv を構築する。

    上限検査は重複排除前の指定回数で行われるため、値はすべて同一で構わない。

    Parameters
    ----------
    count : int
        ``--region`` の指定回数。

    Returns
    -------
    list[str]
        ``["--region", "us-east-1", ...]`` を ``count`` 回並べたリスト。
    """
    argv: list[str] = []
    for _ in range(count):
        argv += ["--region", "us-east-1"]
    return argv


def test_parse_args_defaults() -> None:
    """引数なしのときに既定値が設定された名前空間を返すことを検証する。

    ``parse_args([])`` は ``region`` を空リスト、``profile`` を ``None``、``dry_run`` と
    ``yes`` を ``False`` とした名前空間を返す。

    Validates: Requirements 1.1, 1.5
    """
    args = parse_args([])

    assert args.region == []
    assert args.profile is None
    assert args.dry_run is False
    assert args.yes is False


def test_parse_args_explicit_values() -> None:
    """明示指定した各オプションが正しく解析されることを検証する。

    ``--region`` の繰り返し指定は指定順のリストとして、``--profile`` は文字列として、
    ``--dry-run`` は真として解析され、無指定の ``--yes`` は ``False`` のままとなる。

    Validates: Requirements 1.1, 1.5
    """
    args = parse_args(
        [
            "--region",
            "us-east-1",
            "--region",
            "us-west-2",
            "--profile",
            "prod",
            "--dry-run",
        ]
    )

    assert args.region == ["us-east-1", "us-west-2"]
    assert args.profile == "prod"
    assert args.dry_run is True
    assert args.yes is False


def test_parse_args_unknown_option_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """未知オプション指定時に ``SystemExit(2)`` と標準エラー出力を確認する。

    argparse の標準挙動に従い、未知オプションでは終了コード 2 で終了し、使用方法を
    標準エラー出力へ表示する。

    Validates: Requirements 1.2
    """
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--bogus"])

    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert captured.err != ""
    assert "usage" in captured.err.lower()


def test_parse_args_missing_value_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """値不足のとき ``SystemExit(2)`` と標準エラー出力を確認する。

    ``--region`` は値を必要とするため、値を伴わない指定では終了コード 2 で終了し、
    エラーメッセージを標準エラー出力へ表示する。

    Validates: Requirements 1.4
    """
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--region"])

    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert captured.err != ""


def test_parse_args_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` 指定時に ``SystemExit(0)`` と標準出力のヘルプを確認する。

    ヘルプ表示では終了コード 0 で終了し、標準出力に各オプション名が含まれる。

    Validates: Requirements 1.3
    """
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])

    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "--region" in captured.out
    assert "--profile" in captured.out
    assert "--dry-run" in captured.out
    assert "--yes" in captured.out


def test_validate_options_yes_and_dry_run_conflict() -> None:
    """``--yes`` と ``--dry-run`` の併用で ``OptionConflictError`` を確認する。

    ``validate_options`` は競合を検出して例外を送出するのみであり、解放抑止や終了
    コードの決定は ``main`` レベルの責務である。ここでは例外型のみを検証する。

    Validates: Requirements 9.5
    """
    args = parse_args(["--yes", "--dry-run"])

    with pytest.raises(OptionConflictError):
        validate_options(args)


def test_validate_options_region_boundary_50_accepted() -> None:
    """``--region`` を上限ちょうど（50 回）指定したとき例外を送出しないことを検証する。

    指定回数の上限は境界値そのもの（50）を許容するため、``validate_options`` は
    例外を送出しない。

    Validates: Requirements 2.3
    """
    args = parse_args(_build_region_argv(50))

    assert len(args.region) == 50
    validate_options(args)


def test_validate_options_region_boundary_51_rejected() -> None:
    """``--region`` を 51 回指定したとき ``TooManyRegionsError`` を確認する。

    指定回数が上限（50）を 1 つ超えると、``validate_options`` は
    ``TooManyRegionsError`` を送出する。

    Validates: Requirements 2.3
    """
    args = parse_args(_build_region_argv(51))

    with pytest.raises(TooManyRegionsError):
        validate_options(args)


def test_build_parser_returns_argument_parser() -> None:
    """``build_parser`` が ``ArgumentParser`` を返すことを検証する。

    Validates: Requirements 1.1
    """
    assert isinstance(build_parser(), argparse.ArgumentParser)
