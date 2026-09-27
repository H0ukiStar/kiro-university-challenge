"""aws-eip-cleaner の未利用 EIP 抽出を提供するモジュール。

本モジュールの ``extract_unused_eips`` は AWS API に依存しない純粋ロジック層の関数で
あり、``describe_addresses`` 相当のアドレス集合から、いずれのリソースにも関連付けられて
いない（Association_ID を持たない）EIP を ``UnusedEip`` として抽出する。
AWS API を介したリージョン単位の調査といった I/O を伴う処理は別途 I/O 層で提供する。
"""

from mypy_boto3_ec2.type_defs import AddressTypeDef

from aws_eip_cleaner.models import UnusedEip


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
