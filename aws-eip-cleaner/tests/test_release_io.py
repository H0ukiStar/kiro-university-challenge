"""``release`` モジュールの I/O 層に対する moto モック・ログユニットテスト。

``release_eip`` について、moto でモックした環境での Allocation_ID 指定による解放
（10.1）、リトライ不能な ``ClientError`` による 1 回での失敗確定と
``EipReleaseError`` への変換（10.5）、成功時 INFO ログおよび失敗時に送出される
例外への Allocation_ID の混入（10.2, 10.3）を検証する。boto3 の挙動は moto で
差し替え、実 AWS API は呼び出さない。
"""

import logging

import boto3
import pytest
from moto import mock_aws
from mypy_boto3_ec2.client import EC2Client

from aws_eip_cleaner.errors import EipReleaseError
from aws_eip_cleaner.models import UnusedEip
from aws_eip_cleaner.release import release_eip

_REGION = "us-east-1"


def _allocate_eip(client: EC2Client) -> UnusedEip:
    """``mock_aws`` 環境に EIP を 1 件割り当て、対応する ``UnusedEip`` を返す。

    Parameters
    ----------
    client : EC2Client
        EIP を割り当てる型付き EC2 クライアント。

    Returns
    -------
    UnusedEip
        割り当てた EIP を表す未利用 EIP。関連付けは行わないため未利用状態となる。
    """
    allocation = client.allocate_address(Domain="vpc")
    return UnusedEip(
        allocation_id=allocation["AllocationId"],
        public_ip=allocation["PublicIp"],
        region=_REGION,
    )


@mock_aws
def test_release_eip_releases_by_allocation_id() -> None:
    """Allocation_ID 指定で EIP が解放され、一覧から消えることを検証する。

    moto 上に割り当てた EIP に対して ``release_eip`` を実行し、解放後の
    ``describe_addresses`` に当該 Allocation_ID が現れないことを確認する。
    """
    client = boto3.client("ec2", region_name=_REGION)
    eip = _allocate_eip(client)

    release_eip(client, eip)

    remaining = [
        address.get("AllocationId")
        for address in client.describe_addresses()["Addresses"]
    ]
    assert eip.allocation_id not in remaining


@mock_aws
def test_release_eip_logs_allocation_id_on_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """成功時に INFO ログへ Allocation_ID が含まれることを検証する。

    Parameters
    ----------
    caplog : pytest.LogCaptureFixture
        ログ出力を捕捉するためのフィクスチャ。
    """
    client = boto3.client("ec2", region_name=_REGION)
    eip = _allocate_eip(client)

    with caplog.at_level(logging.INFO, logger="aws_eip_cleaner.release"):
        release_eip(client, eip)

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any(eip.allocation_id in r.getMessage() for r in info_records)


@mock_aws
def test_release_eip_wraps_non_retryable_error() -> None:
    """リトライ不能エラーで失敗確定し ``EipReleaseError`` へ変換されることを検証する。

    存在しない Allocation_ID を渡すと moto は ``InvalidAllocationID.NotFound``
    を返す。この種のエラーは botocore がリトライしないため 1 回の呼び出しで
    失敗が確定し、``EipReleaseError`` へ変換されて送出される。送出される例外
    メッセージには対象の Allocation_ID が含まれ、失敗時のログ・追跡に利用できる。
    """
    client = boto3.client("ec2", region_name=_REGION)
    missing = UnusedEip(
        allocation_id="eipalloc-00000000000000000",
        public_ip="203.0.113.1",
        region=_REGION,
    )

    with pytest.raises(EipReleaseError) as exc_info:
        release_eip(client, missing)

    assert missing.allocation_id in str(exc_info.value)
    assert isinstance(exc_info.value, RuntimeError)
