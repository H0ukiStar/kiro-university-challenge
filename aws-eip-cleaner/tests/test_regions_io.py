"""``regions`` モジュールの I/O 層に対する moto モック・例外ユニットテスト。

``list_available_regions`` / ``resolve_target_regions`` について、moto でモック
した環境での全リージョン取得（2.2）と、取得失敗時の ``RegionListingError`` への
変換（2.5）を検証する。``RegionListingError`` は ``RuntimeError`` を継承しており、
未捕捉のまま伝播すれば非ゼロ終了に至ることも併せて確認する。boto3 の挙動は moto や
monkeypatch で差し替え、実 AWS API は呼び出さない。
"""

import boto3
import pytest
from moto import mock_aws
from pytest import MonkeyPatch

from aws_eip_cleaner.errors import InvalidRegionError, RegionListingError
from aws_eip_cleaner.regions import (
    list_available_regions,
    resolve_target_regions,
)


@mock_aws
def test_list_available_regions_returns_all_regions() -> None:
    """アクセス可能な全 EC2 リージョンを取得できることを検証する。

    ``get_available_regions("ec2")`` の結果と一致する非空のリージョン一覧が
    得られ、代表的なリージョンが含まれることを確認する。
    """
    session = boto3.session.Session()

    regions = list_available_regions(session)

    assert regions == session.get_available_regions("ec2")
    assert regions
    assert "us-east-1" in regions


def test_list_available_regions_wraps_failure(monkeypatch: MonkeyPatch) -> None:
    """取得失敗時に ``RegionListingError`` へ変換されることを検証する。

    ``get_available_regions`` が例外を送出した場合、``RegionListingError`` へ
    変換されて送出されることを確認する。``RegionListingError`` は
    ``RuntimeError`` を継承しており、非ゼロ終了の原因となる。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``get_available_regions`` を差し替えて例外を送出させるためのフィクスチャ。
    """
    session = boto3.session.Session()

    def _raise(service_name: str) -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(session, "get_available_regions", _raise)

    with pytest.raises(RegionListingError):
        list_available_regions(session)

    # RuntimeError を継承しているため、未捕捉なら非ゼロ終了として扱える。
    assert issubclass(RegionListingError, RuntimeError)


@mock_aws
def test_resolve_target_regions_returns_all_when_unspecified() -> None:
    """リージョン無指定時に全リージョンが返ることを検証する。

    ``args_regions`` が空のとき ``list_available_regions`` の結果がそのまま
    調査対象として返ることを確認する。
    """
    session = boto3.session.Session()

    resolved = resolve_target_regions([], session)

    assert resolved == list_available_regions(session)


@mock_aws
def test_resolve_target_regions_normalizes_specified_regions() -> None:
    """指定リージョンが正規化されて返ることを検証する。

    重複を含む指定でも重複排除され、初出順を保った結果が返ることを確認する。
    """
    session = boto3.session.Session()

    resolved = resolve_target_regions(["us-east-1", "us-west-2", "us-east-1"], session)

    assert resolved == ["us-east-1", "us-west-2"]


@mock_aws
def test_resolve_target_regions_rejects_invalid_region() -> None:
    """利用可能集合に含まれない指定を拒否することを検証する。

    無効なリージョン名を含む指定に対して ``InvalidRegionError`` が送出される
    ことを確認する。
    """
    session = boto3.session.Session()

    with pytest.raises(InvalidRegionError):
        resolve_target_regions(["us-east-1", "not-a-region"], session)


def test_resolve_target_regions_propagates_listing_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """一覧取得失敗が ``RegionListingError`` として伝播することを検証する。

    リージョン指定の有無にかかわらず、内部で呼び出す ``get_available_regions``
    が失敗した場合は ``RegionListingError`` が伝播することを確認する。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``get_available_regions`` を差し替えて例外を送出させるためのフィクスチャ。
    """
    session = boto3.session.Session()

    def _raise(service_name: str) -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(session, "get_available_regions", _raise)

    with pytest.raises(RegionListingError):
        resolve_target_regions([], session)
