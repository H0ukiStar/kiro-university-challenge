"""aws-eip-cleaner のリージョン正規化・検証を提供するモジュール。

本モジュールのうち ``normalize_regions`` / ``validate_regions`` は AWS API に
依存しない純粋ロジック層の関数であり、指定リージョンの重複排除と有効性検証を担う。
アクセス可能なリージョン一覧の取得や調査対象リージョンの解決といった I/O を伴う処理は
別途 I/O 層で提供する。
"""

from aws_eip_cleaner.errors import InvalidRegionError


def normalize_regions(regions: list[str]) -> list[str]:
    """指定リージョンを重複排除して正規化する。

    重複する値は 1 件に統合し、初出の順序を保持したまま返す。

    Parameters
    ----------
    regions : list[str]
        正規化対象のリージョン名リスト（重複を含みうる）。

    Returns
    -------
    list[str]
        重複を除去し、初出順を保持したリージョン名リスト。
    """
    # dict はキーの挿入順を保持するため、初出順を維持したまま重複排除できる。
    return list(dict.fromkeys(regions))


def validate_regions(regions: list[str], available: set[str]) -> None:
    """全リージョンが利用可能集合に含まれることを検証する。

    ``regions`` の要素のうち ``available`` に含まれない値が 1 つでもあれば
    ``InvalidRegionError`` を送出する。すべて含まれる場合は何も返さない。

    Parameters
    ----------
    regions : list[str]
        検証対象のリージョン名リスト。
    available : set[str]
        利用可能なリージョン名の集合。

    Returns
    -------
    None
        すべてのリージョンが有効な場合。

    Raises
    ------
    InvalidRegionError
        ``available`` に含まれないリージョン名が 1 つ以上ある場合。
        メッセージには無効なリージョン名を含める。
    """
    # 初出順を保持しつつ無効値を重複なく収集し、メッセージの再現性を保つ。
    invalid = list(
        dict.fromkeys(region for region in regions if region not in available)
    )
    if invalid:
        raise InvalidRegionError(
            f"無効なリージョンが指定されました: {', '.join(invalid)}"
        )
