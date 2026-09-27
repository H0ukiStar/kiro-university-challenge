"""aws-eip-cleaner のリージョン間並列調査と結果集約を提供するモジュール。

本モジュールの ``compute_max_workers`` と ``aggregate`` は AWS API に依存しない純粋
ロジック層の関数である。``compute_max_workers`` は並列度を決定し、``aggregate`` は
各リージョンの調査結果を成功／失敗に分類して 1 つの集約結果に統合する。``scan_regions``
は ``ThreadPoolExecutor`` で各リージョンの調査関数を最大 16 並列で実行し、全完了後に
``aggregate`` で集約する I/O 結線層の関数である。
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def scan_regions(
    scan_fn: Callable[[str], RegionScanResult],
    regions: list[str],
) -> AggregatedResult:
    """各リージョンを最大 16 並列で調査し、全完了後に集約する。

    ``ThreadPoolExecutor`` で各リージョンの ``scan_fn`` を並行実行し、並列度は
    ``compute_max_workers`` により最大 16 に制限する。``as_completed`` で全 future の
    完了を待ってから ``aggregate`` を呼び、集約結果を返す。各 future 内の例外は
    ``scan_fn``（= ``scan_region``）が失敗結果 ``RegionScanResult(error=...)`` として
    返す設計のため、1 リージョンの失敗は他リージョンへ波及しない。

    Parameters
    ----------
    scan_fn : Callable[[str], RegionScanResult]
        単一リージョンを調査し調査結果を返す関数。
    regions : list[str]
        調査対象リージョン。1 件以上を前提とする。

    Returns
    -------
    AggregatedResult
        全リージョンの調査結果を成功／失敗に分類して統合した集約結果。
    """
    max_workers = compute_max_workers(len(regions))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(scan_fn, region) for region in regions]
        results = [future.result() for future in as_completed(futures)]
    return aggregate(results)
