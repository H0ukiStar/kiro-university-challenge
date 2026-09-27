"""aws-eip-cleaner の未利用 EIP 抽出とリージョン調査を提供するモジュール。

本モジュールの ``extract_unused_eips`` は AWS API に依存しない純粋ロジック層の関数で
あり、``describe_addresses`` 相当のアドレス集合から、いずれのリソースにも関連付けられて
いない（Association_ID を持たない）EIP を ``UnusedEip`` として抽出する。
``scan_region`` は AWS API を介して単一リージョンを調査する I/O 層の関数であり、
純粋ロジック層の ``extract_unused_eips`` を利用しつつ、API 失敗を失敗結果へ隔離する。
"""

import logging

from botocore.exceptions import ClientError
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import AddressTypeDef

from aws_eip_cleaner.models import RegionScanResult, UnusedEip

logger = logging.getLogger(__name__)


def extract_unused_eips(
    addresses: list[AddressTypeDef], region: str
) -> list[UnusedEip]:
    """アドレス集合から未利用 EIP を抽出する。

    ``AssociationId`` が未設定または空文字であるアドレスを未利用とみなし、
    元アドレスの ``AllocationId`` / ``PublicIp`` とリージョンを保持した
    ``UnusedEip`` に変換する。未利用 EIP は定義上いずれのリソースにも
    関連付けられていないため、``association_id`` は常に None とする。

    Parameters
    ----------
    addresses : list[AddressTypeDef]
        ``describe_addresses`` 相当のアドレス集合。
    region : str
        アドレスが属するリージョン。

    Returns
    -------
    list[UnusedEip]
        抽出した未利用 EIP のリスト。該当がなければ空リスト。
    """
    unused: list[UnusedEip] = []
    for address in addresses:
        # AssociationId が欠損（未設定）または空文字なら関連付けなし＝未利用とみなす。
        if address.get("AssociationId"):
            continue
        unused.append(
            UnusedEip(
                # TypedDict のキーは欠損しうるため、欠損時は空文字にフォールバックする。
                allocation_id=address.get("AllocationId", ""),
                public_ip=address.get("PublicIp", ""),
                region=region,
                association_id=None,
            )
        )
    return unused


def scan_region(client: EC2Client, region: str) -> RegionScanResult:
    """単一リージョンを調査し、未利用 EIP を列挙する。

    ``describe_addresses`` で当該リージョンのアドレスを全件取得し、
    ``extract_unused_eips`` で未利用 EIP を抽出して成功結果を返す。
    API 呼び出しが失敗した場合は例外を捕捉し、それまでに部分取得した結果は
    破棄したうえで、エラー内容を保持した失敗結果を返す。失敗を結果値として
    表現することで、呼び出し側（並列調査）が 1 リージョンの失敗を他リージョンへ
    波及させずに継続できる。

    Parameters
    ----------
    client : EC2Client
        調査対象リージョンに紐づく EC2 クライアント。
    region : str
        調査対象リージョン。

    Returns
    -------
    RegionScanResult
        成功時は抽出した未利用 EIP を保持し、失敗時は ``error`` に
        エラー内容を保持した調査結果。
    """
    try:
        response = client.describe_addresses()
    except ClientError as exc:
        logger.warning("リージョンの調査に失敗しました（region=%s）: %s", region, exc)
        return RegionScanResult(region=region, unused_eips=[], error=str(exc))

    addresses: list[AddressTypeDef] = list(response.get("Addresses", []))
    unused_eips = extract_unused_eips(addresses, region)
    logger.debug(
        "リージョンの調査が完了しました（region=%s, 未利用 EIP=%d 件）",
        region,
        len(unused_eips),
    )
    return RegionScanResult(region=region, unused_eips=unused_eips)
