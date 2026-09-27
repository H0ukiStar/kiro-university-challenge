"""aws-eip-cleaner のリージョン正規化・検証を提供するモジュール。

本モジュールのうち ``normalize_regions`` / ``validate_regions`` は AWS API に
依存しない純粋ロジック層の関数であり、指定リージョンの重複排除と有効性検証を担う。
アクセス可能なリージョン一覧の取得や調査対象リージョンの解決といった I/O を伴う処理も
本モジュールの I/O 層関数（``list_available_regions`` / ``resolve_target_regions``）で
提供する。I/O 層は botocore 由来の例外を素通しせず、``aws_eip_cleaner.errors`` の
ツール固有例外へ変換して送出する。
"""

import logging

from boto3.session import Session

from aws_eip_cleaner.errors import InvalidRegionError, RegionListingError

logger = logging.getLogger(__name__)


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


def list_available_regions(session: Session) -> list[str]:
    """アクセス可能な EC2 リージョン一覧を取得する。

    boto3 の ``Session.get_available_regions("ec2")`` を呼び出し、利用可能な
    EC2 リージョン名の一覧を返す。取得に失敗した場合は、その例外を
    ``RegionListingError`` へ変換して送出する。

    Parameters
    ----------
    session : Session
        リージョン一覧の取得に使用する boto3 セッション。

    Returns
    -------
    list[str]
        アクセス可能な EC2 リージョン名のリスト。

    Raises
    ------
    RegionListingError
        リージョン一覧の取得に失敗した場合。
    """
    try:
        regions = session.get_available_regions("ec2")
    except Exception as exc:
        raise RegionListingError(
            "アクセス可能なリージョン一覧の取得に失敗しました。"
        ) from exc

    logger.debug("アクセス可能なリージョンを %d 件取得しました。", len(regions))
    return regions


def resolve_target_regions(args_regions: list[str], session: Session) -> list[str]:
    """調査対象リージョンを決定する。

    ``args_regions`` が空でなければ ``normalize_regions`` で正規化し、
    ``list_available_regions`` で取得した利用可能集合に対して
    ``validate_regions`` で検証したうえで正規化結果を返す。空の場合は
    ``list_available_regions`` が返す全リージョンを返す。

    Parameters
    ----------
    args_regions : list[str]
        利用者が ``--region`` で指定したリージョン名のリスト。空の場合は
        全リージョンを対象とする。
    session : Session
        リージョン一覧の取得に使用する boto3 セッション。

    Returns
    -------
    list[str]
        調査対象とするリージョン名のリスト。

    Raises
    ------
    InvalidRegionError
        指定リージョンに利用可能集合へ含まれない値がある場合。
    RegionListingError
        リージョン一覧の取得に失敗した場合。
    """
    available = list_available_regions(session)

    if not args_regions:
        return available

    normalized = normalize_regions(args_regions)
    validate_regions(normalized, set(available))
    return normalized
