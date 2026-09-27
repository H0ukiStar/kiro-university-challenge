"""``scanner`` モジュールの I/O 層に対する moto モック・例外ユニットテスト。

``scan_region`` について、moto でモックした環境での未利用 EIP 全件列挙（5.1）と、
``describe_addresses`` の API 失敗時に例外を送出せず失敗扱いの ``RegionScanResult``
を返し部分結果を記録しないこと（5.5）を検証する。boto3 の挙動は moto や monkeypatch
で差し替え、実 AWS API は呼び出さない。
"""

import boto3
from botocore.exceptions import ClientError
from moto import mock_aws
from mypy_boto3_ec2.client import EC2Client
from pytest import MonkeyPatch

from aws_eip_cleaner.scanner import scan_region

_REGION = "us-east-1"


def _raise_client_error() -> object:
    """``describe_addresses`` の差し替え用に ``ClientError`` を送出する。

    Returns
    -------
    object
        戻り値は返らない（常に例外を送出する）。
    """
    raise ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
        "DescribeAddresses",
    )


@mock_aws
def test_scan_region_lists_all_and_extracts_unused() -> None:
    """割り当てた EIP を全件列挙し、未利用 EIP のみを抽出することを検証する。

    リージョンに複数の EIP を割り当て、うち 1 件を稼働中インスタンスへ関連付ける。
    ``scan_region`` が全件を走査したうえで、関連付けのない EIP のみを未利用として
    抽出し、関連付け済みの EIP は含めないことを確認する。
    """
    client: EC2Client = boto3.client("ec2", region_name=_REGION)

    # 未利用となる 2 件を割り当てる。
    unused_alloc_ids = {
        client.allocate_address(Domain="vpc")["AllocationId"] for _ in range(2)
    }

    # 関連付け済みの 1 件を用意する。稼働中インスタンスへ関連付けて利用中状態にする。
    images = client.describe_images()["Images"]
    instance = client.run_instances(
        ImageId=images[0]["ImageId"], MinCount=1, MaxCount=1
    )["Instances"][0]
    associated = client.allocate_address(Domain="vpc")
    client.associate_address(
        AllocationId=associated["AllocationId"], InstanceId=instance["InstanceId"]
    )

    result = scan_region(client, _REGION)

    assert result.succeeded
    assert result.error is None
    assert result.region == _REGION

    extracted_alloc_ids = {eip.allocation_id for eip in result.unused_eips}
    assert extracted_alloc_ids == unused_alloc_ids
    # 関連付け済みの EIP は未利用に含まれない。
    assert associated["AllocationId"] not in extracted_alloc_ids
    # 抽出された EIP はすべて調査対象リージョンに属し、関連付けを持たない。
    for eip in result.unused_eips:
        assert eip.region == _REGION
        assert eip.association_id is None


@mock_aws
def test_scan_region_returns_empty_when_no_addresses() -> None:
    """EIP が存在しないリージョンで空の成功結果を返すことを検証する。"""
    client: EC2Client = boto3.client("ec2", region_name=_REGION)

    result = scan_region(client, _REGION)

    assert result.succeeded
    assert result.error is None
    assert result.unused_eips == []


@mock_aws
def test_scan_region_wraps_api_failure_without_partial_result(
    monkeypatch: MonkeyPatch,
) -> None:
    """API 失敗時に例外を送出せず、部分結果を記録しない失敗結果を返すことを検証する。

    リージョンに未利用 EIP が存在していても、``describe_addresses`` が
    ``ClientError`` を送出する場合は ``scan_region`` が例外を送出せず、
    ``error`` が非 None かつ ``unused_eips`` が空の失敗結果を返すことを確認する。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``describe_addresses`` を差し替えて例外を送出させるためのフィクスチャ。
    """
    client: EC2Client = boto3.client("ec2", region_name=_REGION)

    # 失敗時に部分結果を記録しないことを検証するため、実際に EIP を割り当てておく。
    client.allocate_address(Domain="vpc")

    monkeypatch.setattr(client, "describe_addresses", _raise_client_error)

    result = scan_region(client, _REGION)

    assert not result.succeeded
    assert result.error is not None
    assert result.unused_eips == []
    assert result.region == _REGION
