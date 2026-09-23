---
type: event
date: 2026-09-22
title: SoFi 成為首家在 Mastercard 網路上線穩定幣結算的全國性銀行
source_url: https://investors.sofi.com/news/news-details/2026/SoFi-Becomes-First-National-Bank-to-Go-Live-with-Stablecoin-Settlement-across-Mastercards-Global-Payments-Network/default.aspx
source_name: SoFi Investor Relations
source_tier: primary
topics: [穩定幣, 支付, 金融法規]
entities: ["[[SoFi]]", "[[Mastercard]]", "[[Visa]]", "[[Anchorage-Digital-Bank]]"]
regulations: []
concepts: ["[[結算]]", "[[cash-leg]]", "[[原子結算]]"]
score: 8
status: cited
used_in: ["日報 2026-09-23"]
---

## 一句話
SoFi Bank, N.A.（OCC 特許全國性銀行）以自家發行的 SoFiUSD（SOFID），在 Mastercard 網路上實際處理其卡計畫結算，年化量預計超過 250 億美元。

## 事實（只放可查證的）
- 2026/09/22 上線；SOFID 在 Ethereum 與 Solana，供給約 70% 在 Solana（約 2.33 億美元）、30% 在 Ethereum（約 1 億美元）
- SoFi 同時是**發幣人 + 卡計畫結算銀行 + 商戶收單行**
- 商戶不需持有 SOFID、不改系統，款項進 SoFi Bank 帳戶，可 24/7 免費提領
- SOFID 明載非 FDIC 保險、準備以現金為主
- 前例：Mastercard 2026/06/03 才開放穩定幣結算（支援 USDC、PYUSD、USDG、USDP、RLUSD、SoFiUSD，八條鏈）；Visa 2025/12/16 已在美上線 USDC 結算，Cross River Bank 與 Lead Bank 已在 Solana 上與 Visa 用 USDC 結算
- 發幣端前例：Anchorage Digital Bank（OCC 聯邦特許）2025/08 已是首家聯邦特許穩定幣發行機構，但走白標替別人發

## 我的判讀
- 「第一」有限定語：第一家**全國性銀行**在 **Mastercard** 網路上線，且用**自家法人發行的幣**。銀行用穩定幣與卡組織清算早了九個月
- 真正差異是**垂直整合**：三個角色同一家銀行 → 才敢一次把整個卡計畫搬過去
- **不是一刷一筆上鏈**：卡片架構三層分離（授權 → 清算對帳 → 結算），穩定幣只換掉第三層，所以是每個結算窗口、每對機構一筆鏈上轉帳
- 逐筆上鏈真正過不去的不是 gas（Solana 逐筆一年約十萬美元等級），是尖峰吞吐無法承諾 SLA、以及把每個商戶每筆金額寫在公鏈上（隱私與 PCI）
- 風險：銀行把部分負債從受保存款移到不受保的代幣負債，擠兌行為會不一樣；發行人與結算行同一人，沒有第三方制衡

## 未解
- 結算窗口頻率、誰付 gas、託管與法幣兌換機制，官方都沒公布（三層架構是依產業標準推論）
