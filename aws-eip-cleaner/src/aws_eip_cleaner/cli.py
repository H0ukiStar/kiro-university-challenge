"""CLI の引数解析・オプション検証・全体オーケストレーションを担うモジュール。

本モジュールは、コマンドライン引数のパースからリージョン調査・解放処理の結線、
および最終的な終了コードの決定までを担当する。パーサ構築・オプション検証・
終了コード決定に加え、全体オーケストレーションを行う ``main`` を提供する。
"""

import argparse
import logging
from collections.abc import Callable

from boto3.session import Session
from mypy_boto3_ec2.client import EC2Client

from aws_eip_cleaner.credentials import create_ec2_client, resolve_session
from aws_eip_cleaner.display import print_eip_list
from aws_eip_cleaner.errors import (
    AwsEipCleanerError,
    OptionConflictError,
    TooManyRegionsError,
)
from aws_eip_cleaner.models import (
    AggregatedResult,
    RegionScanResult,
    ReleaseSummary,
    UnusedEip,
)
from aws_eip_cleaner.parallel import scan_regions
from aws_eip_cleaner.regions import resolve_target_regions
from aws_eip_cleaner.release import release_eip
from aws_eip_cleaner.runner import run_auto_approve, run_dry_run, run_interactive
from aws_eip_cleaner.scanner import scan_region

logger = logging.getLogger(__name__)

# 実装上、正常終了以外の状態はすべて 1 に集約する（設計の終了コード方針に準拠）。
_NONZERO_EXIT_CODE = 1

# ``--yes``/``--dry-run`` の併用は argparse の SystemExit(2) 系と整合させ 2 を返す。
_OPTION_CONFLICT_EXIT_CODE = 2

# ``--region`` の指定回数（重複排除前）の上限。境界値そのもの（50）は許容する。
_MAX_REGION_COUNT = 50


def determine_exit_code(release_summary: ReleaseSummary, scan_failed: bool) -> int:
    """解放結果と調査失敗の有無から終了コードを決定する。

    調査失敗が 1 件以上あるか、または解放失敗が 1 件以上ある場合は非ゼロを返す。
    いずれもなければ 0 を返す純粋関数である。

    Parameters
    ----------
    release_summary : ReleaseSummary
        解放処理の集計。``failed`` が解放失敗件数を表す。
    scan_failed : bool
        リージョン調査に失敗したリージョンが 1 件以上あるかどうか。

    Returns
    -------
    int
        正常時は 0、解放失敗または調査失敗があるときは非ゼロ（1）。
    """
    if scan_failed or release_summary.failed > 0:
        return _NONZERO_EXIT_CODE
    return 0


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数のパーサを構築する。

    ``--region`` / ``--profile`` / ``--dry-run`` / ``--yes`` の 4 オプションを
    定義したパーサを返す。各オプションには無指定時に適用される既定値を設定する。

    Returns
    -------
    argparse.ArgumentParser
        本ツール用に構成された引数パーサ。
    """
    parser = argparse.ArgumentParser(
        prog="aws-eip-cleaner",
        description="未割り当ての Elastic IP (EIP) を検出し、解放する CLI ツール。",
    )
    parser.add_argument(
        "--region",
        action="append",
        default=[],
        type=str,
        help="調査対象のリージョンを指定する（繰り返し指定可能）。無指定時はアクセス可能な全リージョンを対象とする。",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="使用する AWS 認証プロファイル名。無指定時は既定の認証情報解決に従う。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="解放を行わず、対象となる EIP の一覧を表示するのみとする。",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="確認プロンプトを省略し、対象の EIP を一括で解放する。",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解析する。

    未知のオプションや不正な値は argparse の標準挙動に委ねる（``SystemExit(2)`` を
    送出し、使用方法を標準エラー出力へ表示する）。``--help`` は標準出力へ表示し
    ``SystemExit(0)`` を送出する。これらは捕捉しない。

    Parameters
    ----------
    argv : list[str] | None, optional
        解析対象の引数リスト。``None`` の場合は ``sys.argv[1:]`` を用いる。

    Returns
    -------
    argparse.Namespace
        解析結果の名前空間。
    """
    parser = build_parser()
    return parser.parse_args(argv)


def validate_options(args: argparse.Namespace) -> None:
    """解析済みオプションの整合性を検証する。

    ``--yes`` と ``--dry-run`` の同時指定、および ``--region`` の指定回数上限
    （重複排除前）を検査する。問題がある場合はツール固有の例外を送出する。

    Parameters
    ----------
    args : argparse.Namespace
        ``parse_args`` で得た解析結果。

    Raises
    ------
    OptionConflictError
        ``--yes`` と ``--dry-run`` が同時に指定された場合。
    TooManyRegionsError
        ``--region`` の指定回数（重複排除前）が上限を超えた場合。
    """
    if args.yes and args.dry_run:
        raise OptionConflictError("--yes と --dry-run は同時に指定できません。")

    if len(args.region) > _MAX_REGION_COUNT:
        raise TooManyRegionsError(
            f"--region の指定回数が上限（{_MAX_REGION_COUNT} 回）を超えています。"
        )


def _build_release_fn(session: Session) -> Callable[[UnusedEip], None]:
    """リージョンごとにクライアントを再利用する解放関数を構築する。

    生成した ``EC2Client`` をリージョン単位でキャッシュし、同一リージョンの複数 EIP に
    対してクライアントを作り直さないようにする。返す関数は 1 件の未利用 EIP を受け取り、
    そのリージョンのクライアントで ``release_eip`` を呼び出す。

    Parameters
    ----------
    session : Session
        クライアント生成に使用する boto3 セッション。

    Returns
    -------
    Callable[[UnusedEip], None]
        1 件の未利用 EIP を解放する関数。
    """
    client_cache: dict[str, EC2Client] = {}

    def release_fn(eip: UnusedEip) -> None:
        client = client_cache.get(eip.region)
        if client is None:
            client = create_ec2_client(session, eip.region)
            client_cache[eip.region] = client
        release_eip(client, eip)

    return release_fn


def _scan_all_regions(session: Session, regions: list[str]) -> AggregatedResult:
    """対象リージョンを並列調査して集約結果を返す。

    リージョンごとに ``create_ec2_client`` でクライアントを生成し ``scan_region`` を
    呼び出す調査関数を構築し、``scan_regions`` で並列実行する。

    Parameters
    ----------
    session : Session
        クライアント生成に使用する boto3 セッション。
    regions : list[str]
        調査対象リージョンのリスト。

    Returns
    -------
    AggregatedResult
        全リージョンの調査結果を統合した集約結果。
    """

    def scan_fn(region: str) -> RegionScanResult:
        client = create_ec2_client(session, region)
        return scan_region(client, region)

    return scan_regions(scan_fn, regions)


def main(argv: list[str] | None = None) -> int:
    """CLI のエントリポイント。引数解析から解放処理までを結線し終了コードを返す。

    引数解析（``parse_args``）とオプション検証（``validate_options``）を行い、認証解決・
    リージョン解決・並列調査・一覧表示・実行モード別の解放を順に実行する。argparse
    起因の ``SystemExit``（不正オプションの 2 系、``--help`` の 0 系）は捕捉せず
    伝播させる。
    ``OptionConflictError`` は終了コード 2、その他のツール固有例外
    （``AwsEipCleanerError``）は ERROR ログ出力のうえ非ゼロ（1）を返す。

    Parameters
    ----------
    argv : list[str] | None, optional
        解析対象の引数リスト。``None`` の場合は ``sys.argv[1:]`` を用いる。

    Returns
    -------
    int
        プロセスの終了コード。正常時は 0、解放失敗・調査失敗時は非ゼロ、
        オプション競合時は 2。
    """
    args = parse_args(argv)

    try:
        validate_options(args)
    except OptionConflictError as exc:
        logger.error("%s", exc)
        return _OPTION_CONFLICT_EXIT_CODE
    except AwsEipCleanerError as exc:
        logger.error("%s", exc)
        return _NONZERO_EXIT_CODE

    try:
        session = resolve_session(args.profile)
        regions = resolve_target_regions(args.region, session)
        aggregated = _scan_all_regions(session, regions)

        print_eip_list(aggregated.unused_eips)

        if not aggregated.unused_eips:
            return determine_exit_code(
                ReleaseSummary(succeeded=0, failed=0), aggregated.has_scan_failure
            )

        if args.dry_run:
            run_dry_run(aggregated.unused_eips)
            return determine_exit_code(
                ReleaseSummary(succeeded=0, failed=0), aggregated.has_scan_failure
            )

        release_fn = _build_release_fn(session)
        if args.yes:
            summary = run_auto_approve(aggregated.unused_eips, release_fn)
        else:
            summary = run_interactive(
                aggregated.unused_eips, input_fn=input, release_fn=release_fn
            )

        return determine_exit_code(summary, aggregated.has_scan_failure)
    except AwsEipCleanerError as exc:
        logger.error("%s", exc)
        return _NONZERO_EXIT_CODE
