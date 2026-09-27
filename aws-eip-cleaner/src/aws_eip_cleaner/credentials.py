"""aws-eip-cleaner の認証解決とクライアント生成を提供するモジュール。

本モジュールは I/O 層に属し、boto3 の ``Session`` 生成と型付き ``EC2Client`` の
生成を担う。botocore 由来の例外は素通しせず、``aws_eip_cleaner.errors`` の
ツール固有例外へ変換して送出する。
"""

import logging

import boto3
from boto3.session import Session
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from mypy_boto3_ec2.client import EC2Client

from aws_eip_cleaner.errors import CredentialResolutionError, ProfileNotFoundError

logger = logging.getLogger(__name__)

# 認証失敗を表す ClientError のエラーコード。これらは認証情報の解決失敗として扱う。
_CREDENTIAL_ERROR_CODES = frozenset(
    {
        "AuthFailure",
        "UnauthorizedOperation",
        "AccessDenied",
        "AccessDeniedException",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "SignatureDoesNotMatch",
        "ExpiredToken",
        "ExpiredTokenException",
    }
)

# botocore 標準のリトライ設定。リトライ可能エラーを指数バックオフで最大 3 回試行する。
_RETRY_CONFIG = Config(retries={"max_attempts": 3, "mode": "standard"})


def resolve_session(profile: str | None) -> Session:
    """認証情報を解決し boto3 Session を返す。

    ``profile`` が None の場合は boto3 標準の認証チェーンを使用し、指定された
    場合はそのプロファイルを使用して ``Session`` を生成する。botocore 由来の
    例外はツール固有例外へ変換して送出する。

    Parameters
    ----------
    profile : str | None
        使用する認証プロファイル名。None の場合は標準の認証チェーンを使用する。

    Returns
    -------
    Session
        生成された boto3 セッション。

    Raises
    ------
    ProfileNotFoundError
        指定されたプロファイルが見つからない場合。
    CredentialResolutionError
        認証情報が見つからない、または認証系の API 呼び出しが失敗した場合。
    """
    try:
        session = boto3.session.Session(profile_name=profile)
    except ProfileNotFound as exc:
        raise ProfileNotFoundError(
            f"指定されたプロファイルが見つかりません: {profile}"
        ) from exc
    except NoCredentialsError as exc:
        raise CredentialResolutionError("認証情報を解決できませんでした。") from exc
    except ClientError as exc:
        if _is_credential_error(exc):
            raise CredentialResolutionError("認証情報の解決に失敗しました。") from exc
        raise

    logger.debug("boto3 セッションを生成しました（profile=%s）", profile)
    return session


def create_ec2_client(session: Session, region: str) -> EC2Client:
    """指定リージョンの型付き EC2 クライアントを生成する。

    botocore 標準のリトライ設定（``max_attempts=3`` / ``mode="standard"``）を
    適用したうえで、指定リージョンの ``EC2Client`` を生成する。

    Parameters
    ----------
    session : Session
        クライアント生成に使用する boto3 セッション。
    region : str
        クライアントを生成する対象リージョン。

    Returns
    -------
    EC2Client
        指定リージョンの型付き EC2 クライアント。
    """
    return session.client("ec2", region_name=region, config=_RETRY_CONFIG)


def _is_credential_error(exc: ClientError) -> bool:
    """ClientError が認証失敗を表すか判定する。

    エラーレスポンスのエラーコードが認証失敗を示すコードに該当するかで判定する。

    Parameters
    ----------
    exc : ClientError
        判定対象の ClientError。

    Returns
    -------
    bool
        認証失敗を表す場合は True、そうでなければ False。
    """
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _CREDENTIAL_ERROR_CODES
