"""CLI の引数解析・オプション検証・全体オーケストレーションを担うモジュール。

本モジュールは、コマンドライン引数のパースからリージョン調査・解放処理の結線、
および最終的な終了コードの決定までを担当する。ここでは純粋ロジックである終了コード
決定のみを提供し、パーサ構築やオーケストレーションは後続タスクで実装する。
"""

from aws_eip_cleaner.models import ReleaseSummary

# 実装上、正常終了以外の状態はすべて 1 に集約する（設計の終了コード方針に準拠）。
_NONZERO_EXIT_CODE = 1


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
