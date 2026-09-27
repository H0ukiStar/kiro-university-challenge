"""``credentials`` モジュールの認証失敗系とリトライ設定に対するユニットテスト。

プロファイル不在・認証失敗時の例外変換と、``create_ec2_client`` が生成する
クライアントに標準リトライ設定が適用されることを検証する。boto3 の挙動は
moto や monkeypatch で差し替え、実 AWS API は呼び出さない。
"""

from pathlib import Path

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from pytest import MonkeyPatch

from aws_eip_cleaner.credentials import (
    _RETRY_CONFIG,
    create_ec2_client,
    resolve_session,
)
from aws_eip_cleaner.errors import CredentialResolutionError, ProfileNotFoundError


def test_resolve_session_raises_profile_not_found_for_missing_profile(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """存在しないプロファイル指定で例外が送出されることを検証する。

    プロファイルが解決できない場合に ``ProfileNotFoundError`` が送出される
    ことを確認する。

    Parameters
    ----------
    tmp_path : Path
        共有認証情報ファイルを配置するための一時ディレクトリ。
    monkeypatch : MonkeyPatch
        共有認証情報ファイルの場所を環境変数経由で差し替えるためのフィクスチャ。
    """
    # プロファイルを一切含まない空の認証情報ファイルを指すことで、確実に不在状態を作る。
    credentials_file = tmp_path / "credentials"
    credentials_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials_file))

    with pytest.raises(ProfileNotFoundError):
        resolve_session("does-not-exist")


def test_resolve_session_wraps_no_credentials_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """認証情報不在の例外が変換されることを検証する。

    ``NoCredentialsError`` が ``CredentialResolutionError`` へ変換されて
    送出されることを確認する。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``Session`` 生成時に ``NoCredentialsError`` を送出させるためのフィクスチャ。
    """

    def _raise_no_credentials(*args: object, **kwargs: object) -> None:
        raise NoCredentialsError

    monkeypatch.setattr(boto3.session, "Session", _raise_no_credentials)

    with pytest.raises(CredentialResolutionError):
        resolve_session(None)


def test_resolve_session_wraps_credential_client_error(
    monkeypatch: MonkeyPatch,
) -> None:
    """認証系エラーが変換されることを検証する。

    認証失敗を表す ``ClientError`` が ``CredentialResolutionError`` へ
    変換されて送出されることを確認する。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``Session`` 生成時に認証系 ``ClientError`` を送出させるためのフィクスチャ。
    """
    error = ClientError(
        {"Error": {"Code": "AuthFailure", "Message": "auth failed"}},
        "GetCallerIdentity",
    )

    def _raise_client_error(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(boto3.session, "Session", _raise_client_error)

    with pytest.raises(CredentialResolutionError):
        resolve_session(None)


def test_create_ec2_client_applies_standard_retry_config(
    monkeypatch: MonkeyPatch,
) -> None:
    """クライアント生成に標準リトライ設定が渡されることを検証する。

    ``session.client`` に ``ec2`` サービス・対象リージョン・標準リトライ設定の
    ``Config`` が渡されることを確認する。渡される ``Config`` は実装が保持する
    ``max_attempts=3`` / ``mode="standard"`` の設定であり、botocore はこれを
    ``mode="standard"`` かつ ``total_max_attempts=4``（初回 1 回＋リトライ 3 回）へ
    正規化する。

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        ``session.client`` を差し替えて呼び出し引数を捕捉するためのフィクスチャ。
    """
    captured: dict[str, object] = {}

    def _fake_client(
        service_name: str,
        region_name: str,
        config: Config,
    ) -> object:
        captured["service_name"] = service_name
        captured["region_name"] = region_name
        captured["config"] = config
        return object()

    session = boto3.session.Session()
    monkeypatch.setattr(session, "client", _fake_client)

    create_ec2_client(session, "ap-northeast-1")

    assert captured["service_name"] == "ec2"
    assert captured["region_name"] == "ap-northeast-1"
    config = captured["config"]
    assert isinstance(config, Config)
    # 実装が保持する標準リトライ設定がそのまま渡されていること。
    assert config is _RETRY_CONFIG
    # 正規化後は最大 3 回のリトライ（総試行 4 回）・standard モードになる。
    assert getattr(config, "retries") == {"mode": "standard", "total_max_attempts": 4}
