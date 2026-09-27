"""aws-eip-cleaner のリージョン間並列調査と結果集約を提供するモジュール。

本モジュールの ``compute_max_workers`` と ``aggregate`` は AWS API に依存しない純粋
ロジック層の関数である。``compute_max_workers`` は並列度を決定し、``aggregate`` は
各リージョンの調査結果を成功／失敗に分類して 1 つの集約結果に統合する。実際の並列調査
（``ThreadPoolExecutor`` による ``scan_region`` の実行）は後続タスクで別途提供する。
"""

from aws_eip_cleaner.models import AggregatedResult, RegionScanResult, UnusedEip


def compute_max_workers(region_count: int, limit: int = 16) -> int:
    """並列調査の並列度を決定する。

    調査対象リージョン数が上限を下回る場合はリージョン数を、上回る場合は上限を採用する。
    すなわち ``min(limit, region_count)`` を返す。

    Parameters
    ----------
    region_count : int
        調査対象リージョン数。1 以上を前提とする。
    limit : int, optional
        並列度の上限。既定は 16。

    Returns
    -------
    int
        採用する並列度。``min(limit, region_count)``。
    """
    return min(limit, region_count)


def aggregate(results: list[RegionScanResult]) -> AggregatedResult:
    """リージョン調査結果を 1 つの集約結果に統合する。

    各調査結果を成功（``error`` が None）と失敗（``error`` が非 None）に分類する。
    成功リージョンの未利用 EIP のみを入力順を保ったまま統合し、失敗リージョンの EIP は
    含めない。

    Parameters
    ----------
    results : list[RegionScanResult]
        各リージョンの調査結果。

    Returns
    -------
    AggregatedResult
        成功リージョン名の一覧、失敗リージョン名とエラー内容の対応、および成功リージョンの
        未利用 EIP を統合した集約結果。
    """
    unused_eips: list[UnusedEip] = []
    succeeded_regions: list[str] = []
    failed_regions: dict[str, str] = {}
    for result in results:
        if result.succeeded:
            succeeded_regions.append(result.region)
            unused_eips.extend(result.unused_eips)
        else:
            # error は str | None のため、dict の値型 str を空文字で担保する。
            failed_regions[result.region] = result.error or ""
    return AggregatedResult(
        unused_eips=unused_eips,
        succeeded_regions=succeeded_regions,
        failed_regions=failed_regions,
    )
