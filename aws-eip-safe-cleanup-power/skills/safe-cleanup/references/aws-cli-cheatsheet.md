# AWS CLI / boto3 チートシート

未使用 EIP の検出・監査・解放でよく使うコマンド。読み取り専用の検出系は安全、`release-address` のみ破壊的。

## 検出（読み取り専用・安全）

単一リージョンの割り当て済み EIP を全件列挙する。

```bash
aws ec2 describe-addresses --region us-east-1
```

未使用候補（`AssociationId` を持たないもの）だけを抽出する。

```bash
aws ec2 describe-addresses --region us-east-1 \
  --query "Addresses[?AssociationId == null].[AllocationId, PublicIp, PublicIpv4Pool]" \
  --output table
```

BYOIP を除外して「amazon プールかつ未関連付け」だけを見る。

```bash
aws ec2 describe-addresses --region us-east-1 \
  --query "Addresses[?AssociationId == null && PublicIpv4Pool == 'amazon'].[AllocationId, PublicIp]" \
  --output table
```

## 全リージョン監査

有効なリージョン一覧を取得する。

```bash
aws ec2 describe-regions --query "Regions[].RegionName" --output text
```

全リージョンをループして未使用候補を洗い出す（bash 例）。

```bash
for region in $(aws ec2 describe-regions --query "Regions[].RegionName" --output text); do
  echo "== $region =="
  aws ec2 describe-addresses --region "$region" \
    --query "Addresses[?AssociationId == null && PublicIpv4Pool == 'amazon'].[AllocationId, PublicIp]" \
    --output text
done
```

## 解放（破壊的・不可逆・要確認）

VPC スコープの EIP を `AllocationId` で解放する。

```bash
aws ec2 release-address --allocation-id eipalloc-0123456789abcdef0 --region us-east-1
```

## boto3（Python）

```python
import boto3
from botocore.config import Config

session = boto3.Session(profile_name="my-profile")  # profile 未指定なら標準チェーン

# リトライ設定（スロットリング等を指数バックオフで最大 3 回）
config = Config(retries={"max_attempts": 3, "mode": "standard"})
ec2 = session.client("ec2", region_name="us-east-1", config=config)

# 検出（読み取り専用）
addresses = ec2.describe_addresses()["Addresses"]
unused = [
    a for a in addresses
    if not a.get("AssociationId") and a.get("PublicIpv4Pool") == "amazon"
]

# 解放（破壊的・要ユーザ承認）
for eip in unused:
    ec2.release_address(AllocationId=eip["AllocationId"])
```

## プロファイル / アカウント確認

実行前に、どのアカウント・どの権限で動いているかを確認する。

```bash
aws sts get-caller-identity --profile my-profile
```

## 必要な IAM 権限

- 検出のみ: `ec2:DescribeAddresses`, `ec2:DescribeRegions`
- 解放も行う: 上記に加え `ec2:ReleaseAddress`

最小権限で運用する。監査だけの担当者に `ec2:ReleaseAddress` を与えない。
