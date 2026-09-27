# aws-eip-safe-cleanup Power

未使用の AWS Elastic IP（EIP）を**安全に**検出・解放するための知識とワークフローをまとめた Kiro Power。MCP サーバは含まず、スキルとステアリングのみで構成する。

## 何を提供するか

- 未使用 EIP を安全に掃除するための標準ワークフロー（検出 → ドライラン → 対話確認 → 解放 → 集計）
- 課金の仕組みと「解放しないと止まらない」落とし穴
- 「未使用」の正確な判定基準と誤検出の罠（BYOIP・停止中インスタンス・allowlist / DNS など）
- 解放 API・リトライ・冪等性・不可逆性の扱い
- 誤削除を防ぐガードレールと AI エージェント向けの追加ルール
- AWS CLI / boto3 の実行チートシート

## 構成

```
aws-eip-safe-cleanup-power/
├── plugin.json                       # Power マニフェスト（Agent Plugins 形式）
├── README.md
├── dev.kiro/
│   └── steering/
│       └── eip-safety.md             # Kiro 向けの安全指針（inclusion: manual）
└── skills/
    └── safe-cleanup/
        ├── SKILL.md                  # 標準ワークフロー
        └── references/
            ├── eip-billing.md        # 課金の仕組み
            ├── detection-criteria.md # 未使用判定と罠
            ├── release-procedure.md  # 解放手順・リトライ・冪等性
            ├── safety-guardrails.md  # ガードレール／チェックリスト
            └── aws-cli-cheatsheet.md # CLI / boto3 例
```

## 使い方

このディレクトリを Kiro に取り込む。

1. Kiro の Powers パネルを開く
2. Add Custom Power → Import power from a folder
3. この `aws-eip-safe-cleanup-power/` フォルダを選択

取り込み後、「未使用 EIP を削除したい」「EIP の課金を止めたい」などのキーワードで自動的にロードされる。

## 関連

- 本リポジトリの `aws-eip-cleaner`（`../aws-eip-cleaner/`）は、このワークフローを CLI として実装したツール。
- 仕様は `.kiro/specs/aws-eip-cleaner/` を参照。

## 出典

`skills/safe-cleanup/references/eip-billing.md` 内に、AWS 公式ドキュメント等への参照リンクを記載している。各記述は原文を要約したもの。
