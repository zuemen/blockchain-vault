---
type: event
id: ojjq7psa
origin: ai
date: 2026-09-08
title: FinCEN 與四大銀行監理機關：可驗證數位憑證可用於 CIP 身分驗證
source_url: https://www.fincen.gov/news/news-releases/fincen-issues-frequently-asked-questions-regarding-treatment-verifiable-digital
source_name: FinCEN
source_tier: primary
topics: [SSI, 金融法規, ZK]
entities: ["[[FinCEN]]", "[[OCC]]", "[[Proof]]"]
regulations: ["[[FinCEN-VDC-CIP-FAQ]]"]
concepts: ["[[可驗證數位憑證-VDC]]", "[[選擇性揭露]]"]
score: 9
---

## 一句話
FinCEN 會同 Fed、FDIC、NCUA、OCC 更新 CIP FAQ，銀行與信合社可用州政府發行的 mDL 等可驗證數位憑證驗證自然人身分。性質是釋義而非新法，且明確「不要求也不禁止」。

## 事實（只放可查證的）
- 2026/09/08 發布，五機關聯名
- 政府發行的 VDC 若含照片等安全設計，算「文件驗證」；民間發行的憑證落入「非文件驗證」，銀行責任加重
- 銀行仍須：CIP 書面程序明文允許數位格式、驗簽章、維護信任清單（AAMVA Digital Trust Service）、撤銷檢查、驗證失敗接 SAR 流程
- **憑證型別／號碼／簽發地／有效期須留存 5 年**
- 2026/09/15 Proof 推出銀行用可攜式數位身分：X.509 + SD-JWT 選擇性揭露 + OID4VCI/OID4VP + 硬體金鑰綁定
- 缺口：僅 21 州 + 波多黎各支援 mDL；ISO/IEC 18013-7 規格換版中（2024 版撤回改 2025）

## 我的判讀
- 這則的價值不在「政府允許了」，而在**允許之後銀行實際要背什麼**
- 核心矛盾：SSI 賣點是 [[選擇性揭露]]（只證明年滿 18 而不給生日），但 CIP 要求留存憑證欄位 5 年 → ZKP／SD-JWT 的隱私優勢被抽掉一半
- 真正瓶頸不是密碼學，是**信任基礎設施**：信任清單、撤銷檢查、跨州覆蓋
- 分類是關鍵：政府發行 vs 民間發行走不同驗證路徑，這決定了商業模式空間

## 未解
- FAQ 原文 PDF 我還沒逐條核過（目前依二手分析）
- 留存要求與選擇性揭露的技術折衷，業界有沒有成熟做法
