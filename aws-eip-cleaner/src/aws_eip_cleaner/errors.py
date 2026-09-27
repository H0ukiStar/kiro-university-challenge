"""aws-eip-cleaner の例外階層を定義するモジュール。

本ツールが送出するすべての例外は基底例外 ``AwsEipCleanerError`` を継承する。
組み込み・ライブラリ由来の例外は素通しせず、ここで定義するツール固有例外へ
変換して送出することで、呼び出し側が一貫した方法で捕捉できるようにする。

一部の例外は用途に応じて標準例外（``ValueError`` / ``RuntimeError``）も
併せて継承し、意味的な分類（入力値の誤り／実行時の失敗）を型として表現する。
"""


class AwsEipCleanerError(Exception):
    """本ツールの基底例外。

    本ツールが送出するすべての例外はこのクラスを継承する。呼び出し側は
    この基底例外を捕捉することで、ツール由来のあらゆるエラーをまとめて
    処理できる。
    """


class OptionConflictError(AwsEipCleanerError):
    """両立しないオプションが指定された場合の例外。

    ``--yes`` と ``--dry-run`` のように同時指定できないオプションが
    指定されたときに送出する。
    """


class TooManyRegionsError(AwsEipCleanerError, ValueError):
    """``--region`` の指定回数が上限を超えた場合の例外。

    ``--region`` の指定回数（重複排除前）が上限（50 回）を超えたときに
    送出する。入力値の誤りを表すため ``ValueError`` も継承する。
    """


class InvalidRegionError(AwsEipCleanerError, ValueError):
    """``--region`` に無効なリージョン名が指定された場合の例外。

    アクセス可能なリージョン一覧に含まれないリージョン名が指定されたときに
    送出する。入力値の誤りを表すため ``ValueError`` も継承する。
    """


class RegionListingError(AwsEipCleanerError, RuntimeError):
    """アクセス可能なリージョン一覧の取得に失敗した場合の例外。

    リージョン一覧取得の API 呼び出しが失敗したときに送出する。実行時の
    失敗を表すため ``RuntimeError`` も継承する。
    """


class ProfileNotFoundError(AwsEipCleanerError):
    """指定された認証プロファイルが見つからない場合の例外。

    ``--profile`` で指定されたプロファイルが存在しないときに送出する。
    botocore の ``ProfileNotFound`` をこの例外へ変換する。
    """


class CredentialResolutionError(AwsEipCleanerError):
    """認証情報の解決に失敗した場合の例外。

    認証情報が見つからない、または認証系の API 呼び出しが失敗したときに
    送出する。botocore の ``NoCredentialsError`` や認証系の ``ClientError``
    をこの例外へ変換する。
    """


class RegionScanError(AwsEipCleanerError, RuntimeError):
    """単一リージョンの EIP 列挙に失敗した場合の例外。

    ``describe_addresses`` 相当の API 呼び出しが失敗したときに送出する。
    実行時の失敗を表すため ``RuntimeError`` も継承する。
    """


class EipReleaseError(AwsEipCleanerError, RuntimeError):
    """EIP の解放に失敗した場合の例外。

    ``release_address`` 相当の API 呼び出しが失敗したときに送出する。
    実行時の失敗を表すため ``RuntimeError`` も継承する。
    """
