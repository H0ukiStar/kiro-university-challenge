# EIP の課金の仕組み

未使用 EIP を解放する動機は、ほぼ「課金の停止」に尽きる。判断を正しくするために、まず何にいくら課金されるのかを押さえる。

## いつ課金されるか

- AWS が提供するパブリック IPv4 アドレス（EIP を含む）は、**使用中（リソースに関連付け済み）でも、アイドル（アカウントに割り当てたまま未関連付け）でも課金対象**である（[Amazon EC2 の説明](http://aws.amazon.com/articles/1346) を要約）。
- 2024 年 2 月 1 日以降、AWS が割り当てるパブリック IPv4 アドレスに時間課金が導入された（[AWS 公式発表](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/) を要約）。料金は概ね 1 IP あたり 1 時間 0.005 USD 程度（[re:Post の回答](https://repost.aws/articles/ARknH_OR0cTvqoTfJrVGaB8A/why-am-i-seeing-charges-for-public-ipv4-addresses-when-i-am-under-the-aws-free-tier) を要約）。正確な最新料金は必ず公式の料金ページで確認すること。

> 単価は小さいが、複数アカウント・複数リージョンにまたがると累積して無視できない金額の無駄になる（[FinOps 観点の解説](https://www.binadox.com/blog/binadox-article-unassociated-elastic-ip-addresses/) を要約）。

コンプライアンスのため、上記はいずれも原文を要約したもの。

## 「解放しないと止まらない」という落とし穴

課金停止で最も多い誤解は次の 2 つ。

1. **インスタンスを終了しても EIP の課金は止まらない。** 終了済みインスタンスに紐づいていた EIP を解放し忘れると、実行中インスタンスに関連付いていなくても課金が続く（[AWS ナレッジセンター](https://aws.amazon.com/premiumsupport/knowledge-center/ec2-billing-terminated/) を要約）。対処は EIP の関連付け解除と解放。
2. **関連付け解除（disassociate）だけでは足りない。** IP を切り離しても、割り当て（allocation）を AWS に返却＝解放（release）しない限り課金は継続する（[re:Post の回答](https://repost.aws/questions/QUldaNjbjVQG-F98_om0h4dQ/i-am-getting-charged-for-unattached-static-ip-but-unattached-static-ip-already-deleted) を要約）。

## 課金されない/対象外のケース

- **BYOIP（Bring Your Own IP）で持ち込んだアドレス**は、AWS 提供の IPv4 課金の対象外（[AWS 公式発表](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/) を要約）。つまり「未関連付けだから」と機械的に解放すると、持ち込んだアドレス空間を失う恐れがある。BYOIP は解放候補から除外する。
- 無料利用枠の対象条件は時期・アカウントで変わる。料金ページで都度確認する。

## 監査に役立つ AWS 機能

- **Public IP Insights（VPC IP Address Manager / IPAM の一機能）**: アイドル・使用中のパブリック IPv4 を追跡し、コストの見積もりや最適化余地の特定に使える（[AWS 公式ブログ](https://aws.amazon.com/blogs/networking-and-content-delivery/identify-and-optimize-public-ipv4-address-usage-on-aws/) を要約）。大規模環境ではまず Insights で全体像を掴むとよい。

Content was rephrased for compliance with licensing restrictions.
