"""aws-eip-cleaner のデータモデルを定義するモジュール。

未利用 EIP、単一リージョンの調査結果、全リージョンの集約結果、解放処理の集計を表す
不変データクラスを提供する。いずれも AWS API に依存しない純粋なデータ構造であり、
純粋ロジック層と I/O 層の双方から共有される。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UnusedEip:
    """未利用 EIP を表す不変データ。

    Attributes
    ----------
    allocation_id : str
        EIP の割り当て ID（eipalloc-xxxx）。
    public_ip : str
        パブリック IPv4 アドレス。
    region : str
        EIP が属するリージョン。
    association_id : str | None
        EIP の関連付け状態を表す Association_ID。未利用 EIP は定義上いずれのリソースにも
        関連付けられていないため常に None（関連付けなし）となる。
        一覧表示で「関連付け状態」を明示するために保持する。
    """

    allocation_id: str
    public_ip: str
    region: str
    association_id: str | None = None


@dataclass(frozen=True)
class RegionScanResult:
    """単一リージョンの調査結果。

    Attributes
    ----------
    region : str
        調査対象リージョン。
    unused_eips : list[UnusedEip]
        検出した未利用 EIP。失敗時は空。
    error : str | None
        調査に失敗した場合のエラー内容。成功時は None。
    """

    region: str
    unused_eips: list[UnusedEip]
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """調査が成功したかを返す。

        Returns
        -------
        bool
            error が None（成功）なら True。
        """
        return self.error is None


@dataclass(frozen=True)
class AggregatedResult:
    """全リージョンの集約結果。

    Attributes
    ----------
    unused_eips : list[UnusedEip]
        成功したリージョンの未利用 EIP を統合したもの。
    succeeded_regions : list[str]
        調査に成功したリージョン。
    failed_regions : dict[str, str]
        調査に失敗したリージョンとエラー内容の対応。
    """

    unused_eips: list[UnusedEip]
    succeeded_regions: list[str]
    failed_regions: dict[str, str] = field(default_factory=dict)

    @property
    def has_scan_failure(self) -> bool:
        """調査に失敗したリージョンが 1 件以上あるかを返す。

        Returns
        -------
        bool
            失敗リージョンが 1 件以上あれば True。
        """
        return len(self.failed_regions) > 0


@dataclass(frozen=True)
class ReleaseSummary:
    """解放処理の集計。

    Attributes
    ----------
    succeeded : int
        解放に成功した件数（0 以上）。
    failed : int
        解放に失敗した件数（0 以上）。
    """

    succeeded: int
    failed: int

    @property
    def total(self) -> int:
        """処理した総件数を返す。

        Returns
        -------
        int
            succeeded と failed の合計。
        """
        return self.succeeded + self.failed
