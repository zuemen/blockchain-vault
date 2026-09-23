---
type: home
---

# HOME

> CLI：`make help` ｜ 抓取＋建站：`make update` ｜ 預覽：`make serve`

## 未讀事件（分數高者在前）
```dataview
TABLE score AS 分數, source_tier AS 來源, topics AS 主題
FROM "10-events"
WHERE status = "unread"
SORT score DESC
LIMIT 15
```

## 只看一手來源
```dataview
LIST
FROM "10-events"
WHERE source_tier = "primary"
SORT date DESC
LIMIT 10
```

## 還沒長大的概念（下週補這些）
```dataview
TABLE maturity AS 成熟度, updated AS 更新
FROM "20-concepts"
WHERE maturity != "stable"
SORT updated ASC
```

## 已引用過的事件（週報回溯用）
```dataview
TABLE used_in AS 用在哪
FROM "10-events"
WHERE used_in != []
SORT date DESC
```

## 主題入口
- [[MOC-RWA]]
- [[MOC-SSI-DID-VC]]
- [[MOC-ZK]]
- [[MOC-金融法規]]
