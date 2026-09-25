# 決策紀錄

## 2026-09-25 事件分組模型與門檻（spec §6.2）

資料：`tests/fixtures/cluster_calibration.yaml`，4 組必須合併（共 8 對）、10 則彼此不同的事件。
方法：`python scripts/calibrate_clusters.py --model <模型>`，用實際分組邏輯掃 0.40–0.94 的門檻，
數「漏併」（該合併卻分開的對數）與「誤併」（不同事件被併在一起的對數）。誤併優先壓到 0。

| 模型 | 最佳門檻 | 漏併 | 誤併 | 備註 |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2（spec 原訂） | 0.74–0.76 | 5 | 0 | 0.68 時漏併 3、誤併 2 |
| multilingual-e5-small | 0.92 | 3 | 2 | 所有配對都在 0.8 以上，分不開 |
| paraphrase-multilingual-mpnet-base-v2 | 0.72–0.74 | 3 | 0 | |
| **LaBSE** | **0.66–0.68** | **3** | **0** | 採用，門檻取 0.67 |

**結論**：採用 `sentence-transformers/LaBSE`，門檻 0.67。只看標題時，沒有任何模型能做到零錯誤。
LaBSE 在不誤併的前提下漏併最少。

**最難的案例**
- 該合併卻合不起來：CFTC 主席談「大規模代幣化」的中英文報導、SoFi 第三篇評論文。
  上線後既有報導會帶 AI 翻的 `title_zh` 一起比對，跨語言的情況應該會改善。
- 容易誤併：a16z 與 CryptoRank 兩則 RWA 永續合約交易量數據；英國與加拿大銀行的代幣化存款新聞。

**何時重跑**：換模型、fixture 增加案例，或上線兩週後發現重複分組明顯偏多或偏少。

## AI 摘要抽查（spec §12）

上線後第一次每日執行完成時，抽 10 則 `summary_by='ai'` 的新聞，人工比對原文，確認沒有編造數字或機構。
