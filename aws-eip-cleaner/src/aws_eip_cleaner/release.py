"""aws-eip-cleaner の EIP 解放処理を提供するモジュール。

本モジュールは I/O 層に属し、型付き ``EC2Client`` を介して ``release_address`` を
呼び出し、単一の未利用 EIP を解放する。リトライ可能エラーは ``create_ec2_client`` で
設定済みの botocore 標準リトライ機構が処理するため、本モジュールでは独自のリトライを
行わない。botocore 由来の例外は素通しせず、``aws_eip_cleaner.errors`` のツール固有
例外へ変換して送出する。
"""

import logging

from botocore.exceptions import ClientError
from mypy_boto3_ec2.client import EC2Client

from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import UnusedEip

logger = logging.getLogger(__name__)


def release_eip(client: EC2Client, eip: UnusedEip) -> None:
    """EIP を Allocation_ID を用いて解放する。

    ``release_address`` を Allocation_ID 指定で呼び出し、対象の未利用 EIP を
    解放する。リトライ可能エラーは botocore 標準リトライ機構が処理するため、
    それでもなお失敗した ``ClientError`` は ``EipReleaseError`` へ変換して
    送出する。リトライ不能エラーは botocore が再試行しないため、1 回の失敗で
    確定する。

    Parameters
    ----------
    client : EC2Client
        解放に使用する型付き EC2 クライアント。リトライ設定は生成時に適用済み。
    eip : UnusedEip
        解放対象の未利用 EIP。

    Returns
    -------
    None
        解放に成功した場合。

    Raises
    ------
    EipReleaseError
        ``release_address`` の呼び出しが失敗した場合。
    """
    try:
        client.release_address(AllocationId=eip.allocation_id)
    except ClientError as exc:
        raise EipReleaseError(f"EIP の解放に失敗しました: {eip.allocation_id}") from exc

    logger.info("EIP を解放しました: %s", eip.allocation_id)
