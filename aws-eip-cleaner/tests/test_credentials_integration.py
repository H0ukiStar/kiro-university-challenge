"""``credentials`` モジュールの認証成功系に対する moto 統合テスト。

moto の ``mock_aws`` で AWS API をモックしたうえで、profile 未指定（標準チェーン）
と profile 指定の双方で ``resolve_session`` → ``create_ec2_client`` が成功し、
利用可能な ``EC2Client`` が得られることを検証する。
"""

from pathlib import Path

from moto import mock_aws
from pytest import MonkeyPatch

from aws_eip_cleaner.credentials import create_ec2_client, resolve_session


@mock_aws
def test_resolve_and_create_client_succeeds_without_profile() -> None:
    """プロファイル未指定（標準チェーン）で生成が成功することを検証する。

    profile が None のとき標準の認証チェーンで Session が生成され、
    そこから利用可能な EC2Client が得られることを確認する。
    """
    session = resolve_session(None)

    client = create_ec2_client(session, "us-east-1")

    # 実際に API を呼び出せる有効なクライアントであることを確認する。
    assert client.meta.region_name == "us-east-1"
    assert client.describe_addresses()["Addresses"] == []


@mock_aws
def test_resolve_and_create_client_succeeds_with_profile(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """プロファイル指定で Session とクライアント生成が成功することを検証する。

    Parameters
    ----------
    tmp_path : Path
        共有認証情報ファイルを配置するための一時ディレクトリ。
    monkeypatch : MonkeyPatch
        共有認証情報ファイルの場所を環境変数経由で差し替えるためのフィクスチャ。
    """
    # 指定プロファイルが解決できるよう、認証情報を持つプロファイルを用意する。
    credentials_file = tmp_path / "credentials"
    credentials_file.write_text(
        "[integration]\naws_access_key_id = testing\naws_secret_access_key = testing\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials_file))

    session = resolve_session("integration")

    client = create_ec2_client(session, "us-west-2")

    assert client.meta.region_name == "us-west-2"
    assert client.describe_addresses()["Addresses"] == []
