"""解放オーケストレーションを担うモジュール。

実行モード（dry-run / yes / 対話）ごとの分岐と、各モードでの一覧表示・確認・解放・
集計をまとめる。実際の解放処理（AWS API 呼び出し）や入力受付は ``release_fn`` /
``input_fn`` として注入で受け取り、本モジュール自身は AWS SDK に依存しない。これにより
モード分岐と集計ロジックを副作用なくテストできるようにしている。
"""

import logging
from collections.abc import Callable

from aws_eip_cleaner.confirm import ConfirmDecision, prompt_decision
from aws_eip_cleaner.display import print_eip_list
from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import ReleaseSummary, UnusedEip

logger = logging.getLogger(__name__)


def run_dry_run(eips: list[UnusedEip]) -> int:
    """dry-run モードを実行する。

    検出した未利用 EIP の一覧と総件数を標準出力へ表示するのみで、解放も対話確認も
    一切行わない。0 件の場合も一覧整形が対象なしの総件数を表示するため、追加の分岐は
    設けない。

    Parameters
    ----------
    eips : list[UnusedEip]
        表示対象の未利用 EIP のリスト。空リストも許容する。

    Returns
    -------
    int
        常に 0（dry-run は正常表示のため）。
    """
    print_eip_list(eips)
    return 0


def run_auto_approve(
    eips: list[UnusedEip],
    release_fn: Callable[[UnusedEip], None],
) -> ReleaseSummary:
    """一括承認（yes）モードを実行する。

    解放対象の総数を表示したうえで全件を ``release_fn`` で解放し、成功・失敗件数を
    集計して返す。解放が ``EipReleaseError`` で失敗した場合は捕捉し、割り当て ID と
    エラー内容を ERROR ログへ出力したうえで失敗件数に計上し、残りの対象の処理を
    継続する。対象が 0 件の場合は対象なしメッセージを表示し
    ``ReleaseSummary(succeeded=0, failed=0)`` を返す（終了コードの判定は
    呼び出し側の ``determine_exit_code`` に委ねる）。

    Parameters
    ----------
    eips : list[UnusedEip]
        解放対象の未利用 EIP のリスト。空リストも許容する。
    release_fn : Callable[[UnusedEip], None]
        1 件の EIP を解放する関数。解放失敗時は ``EipReleaseError`` を送出しうる。

    Returns
    -------
    ReleaseSummary
        解放に成功した件数と失敗した件数の集計。
    """
    if not eips:
        print("解放対象の EIP はありません。")
        return ReleaseSummary(succeeded=0, failed=0)

    print(f"解放対象: {len(eips)} 件")
    succeeded = 0
    failed = 0
    for eip in eips:
        try:
            release_fn(eip)
        except EipReleaseError as exc:
            failed += 1
            logger.error(
                "EIP の解放に失敗しました: allocation_id=%s error=%s",
                eip.allocation_id,
                exc,
            )
        else:
            succeeded += 1

    print(f"解放成功: {succeeded} 件, 解放失敗: {failed} 件")
    return ReleaseSummary(succeeded=succeeded, failed=failed)


def run_interactive(
    eips: list[UnusedEip],
    input_fn: Callable[[str], str],
    release_fn: Callable[[UnusedEip], None],
) -> ReleaseSummary:
    """対話モードを実行する。

    未利用 EIP を 1 件ずつ ``prompt_decision`` で確認し、承認（APPROVE）された分のみ
    ``release_fn`` で解放する。成功・失敗件数を集計して返す。``prompt_decision`` が
    ``EOFError`` を再送出した場合は中断とみなし、残りの EIP を解放せずにそれまでの集計を
    返す。解放が ``EipReleaseError`` で失敗した場合は捕捉し、割り当て ID とエラー内容を
    ERROR ログへ出力したうえで失敗件数に計上し、次の EIP へ進む。

    Parameters
    ----------
    eips : list[UnusedEip]
        確認・解放対象の未利用 EIP のリスト。空リストも許容する。
    input_fn : Callable[[str], str]
        確認プロンプトへの入力を受け取る関数。``prompt_decision`` へ委譲する。
    release_fn : Callable[[UnusedEip], None]
        1 件の EIP を解放する関数。解放失敗時は ``EipReleaseError`` を送出しうる。

    Returns
    -------
    ReleaseSummary
        解放に成功した件数と失敗した件数の集計。EOF による中断時は、中断時点までの集計。
    """
    succeeded = 0
    failed = 0
    for eip in eips:
        try:
            decision = prompt_decision(eip, input_fn)
        except EOFError:
            # 標準入力の終端は中断を意味するため、残りの EIP を解放せず打ち切る。
            break

        if decision is not ConfirmDecision.APPROVE:
            continue

        try:
            release_fn(eip)
        except EipReleaseError as exc:
            failed += 1
            logger.error(
                "EIP の解放に失敗しました: allocation_id=%s error=%s",
                eip.allocation_id,
                exc,
            )
        else:
            succeeded += 1

    return ReleaseSummary(succeeded=succeeded, failed=failed)
