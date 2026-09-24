# 階段 1：taxonomy 與筆記 schema 驗證 施工計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立分類詞彙唯一來源 `taxonomy.yaml`，讓每篇筆記有永久 `id` 與出處 `origin`，並讓建站在 schema 錯誤時失敗，不再靜默忽略。

**Architecture:** 新增三個小模組：`taxonomy.py` 讀詞彙、`notes.py` 解析筆記、`validate.py` 檢查規則。一次性遷移腳本 `migrate_notes.py` 逐行修改 frontmatter，保留原本格式。`build_site.py` 在產生網站前先跑驗證，筆記頁顯示 `origin` 標籤。新聞管線與網址不動，那是階段 2、3 的事。

**Tech Stack:** Python 3.12（本機 3.13 也可）、PyYAML、Markdown、pytest。

**Spec:** `docs/superpowers/specs/2026-09-24-vault-v2-design.md`（§1.1、§4.2、§4.3、§4.5、§10 第 2 步）

## Global Constraints

- 程式要能在 Python 3.10 以上執行，不用 3.13 才有的語法。Cloudflare build 用 3.12。
- Cloudflare build 只安裝 `pyyaml markdown`，所以 `scripts/` 的正式程式不能依賴其他套件。pytest 只在開發時用。
- Windows 本機執行所有 Python 指令都要加 `PYTHONUTF8=1`，否則 cp950 會噴 UnicodeEncodeError。
- 含反斜線的程式碼用檔案寫入工具寫，不要經過 Bash heredoc，避免 `\\n` 被摺成 `\n`。
- **自動卡（`type: event` 且 `auto: true`）這一階段完全不動**。main 上的 bot 每天還在產生它們，階段 2 才會匯入 D1 並刪除。驗證與遷移都要跳過它們。
- `id` 格式：8 碼，字元集 `abcdefghijklmnopqrstuvwxyz234567`，建立後永不改。
- `origin` 只能是 `ai`、`ai-reviewed`、`human`；`ai-reviewed` 必須有 `reviewed` 日期。
- 使用者內容插入 HTML 一律先 `esc()`。
- 分支：`redesign/vault-v2`。不 push，除非使用者說可以。

---

## 檔案結構

| 檔案 | 動作 | 職責 |
|---|---|---|
| `taxonomy.yaml` | 新增 | 分類詞彙唯一來源（本階段只放驗證用得到的部分） |
| `scripts/taxonomy.py` | 新增 | `load_taxonomy()`：讀檔、檢查必要欄位 |
| `scripts/notes.py` | 新增 | `Note`、`parse_note()`、`iter_notes()`、`first_heading()`、`new_id()`、`is_legacy_auto()` |
| `scripts/validate.py` | 新增 | `Issue`、`validate_note()`、`validate_all()`、`report()`、CLI |
| `scripts/migrate_notes.py` | 新增 | `migrate_text()`、CLI（一次性，但可重跑） |
| `scripts/build_site.py` | 修改 | `main()` 先驗證；`collect()` 讀 `origin`／`reviewed`；byline 加 `origin_badge()`；CSS 加樣式 |
| `scripts/new_note.py` | 修改 | 抽出 `create_note()`，產生 `id`、`title`、`origin: human` |
| `templates/*.md` | 修改 | 加 `id`、`title`、`origin` 占位 |
| `requirements-dev.txt` | 新增 | `pyyaml`、`markdown`、`pytest` |
| `tests/conftest.py` | 新增 | 把 `scripts/` 加進 `sys.path`，提供 `tax` fixture |
| `tests/test_*.py` | 新增 | 各模組測試 |
| `docs/superpowers/specs/2026-09-24-vault-v2-design.md` | 修改 | §4.2 補 `effective_note` 欄位 |

---

### Task 1：測試環境與 taxonomy

**Files:**
- Create: `requirements-dev.txt`、`taxonomy.yaml`、`scripts/taxonomy.py`、`tests/conftest.py`、`tests/test_taxonomy.py`

**Interfaces:**
- Produces: `taxonomy.load_taxonomy(path: Path = ROOT / "taxonomy.yaml") -> dict`，錯誤時丟 `taxonomy.TaxonomyError(ValueError)`。回傳的 dict 至少有 `limits, topics, jurisdictions, tracks, stages, maturity, origins, watchlist` 八個 key。
- Produces: pytest fixture `tax`（真實的 `taxonomy.yaml` 內容）、`tmp_vault`（在 tmp_path 建好 6 個筆記資料夾的路徑）。

- [ ] **Step 1：建立 `requirements-dev.txt`**

```
pyyaml
markdown
pytest
```

執行：`PYTHONUTF8=1 python -m pip install -r requirements-dev.txt`
預期：安裝成功（本機原本缺 `markdown`）。

- [ ] **Step 2：建立 `tests/conftest.py`**

```python
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

NOTE_DIRS = ("10-events", "20-concepts", "30-entities", "40-regulations", "50-maps", "60-outputs")


@pytest.fixture
def tax():
    import taxonomy
    return taxonomy.load_taxonomy()


@pytest.fixture
def tmp_vault(tmp_path):
    for d in NOTE_DIRS:
        (tmp_path / d).mkdir()
    return tmp_path
```

- [ ] **Step 3：寫失敗的測試 `tests/test_taxonomy.py`**

```python
import pytest

import taxonomy


def test_real_taxonomy_loads(tax):
    assert "RWA" in tax["topics"]
    assert "支付" in tax["topics"]
    assert tax["stages"][3] == "已通過"
    assert tax["origins"] == ["ai", "ai-reviewed", "human"]
    assert {w["id"] for w in tax["watchlist"]} == {
        "chainlink", "kinexys", "jpmorgan", "fidelity", "bny", "fireblocks", "zk", "polygon"}


def test_missing_key_raises(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("topics: [RWA]\n", encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="缺少欄位"):
        taxonomy.load_taxonomy(p)


def test_duplicate_watch_id_raises(tmp_path, tax):
    import yaml
    bad = dict(tax, watchlist=[{"id": "a", "name": "A", "aliases": ["A"]},
                               {"id": "a", "name": "B", "aliases": ["B"]}])
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(taxonomy.TaxonomyError, match="watchlist id 重複"):
        taxonomy.load_taxonomy(p)
```

- [ ] **Step 4：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_taxonomy.py -v`
預期：FAIL，`ModuleNotFoundError: No module named 'taxonomy'`

- [ ] **Step 5：建立 `taxonomy.yaml`**

本階段只放驗證用得到的欄位。`jurisdictions` 的關鍵詞與 `scoring` 分別在階段 5、階段 2 搬進來。

```yaml
# 分類詞彙唯一來源。抓取、評分、標記、建站、驗證都只讀這一份。
# 筆記 frontmatter 的 topics / jurisdiction / tracks / maturity / origin 值必須出現在這裡。

limits:
  daily_top: 60       # 每天最多開幾個新事件分組（階段 2 起生效）
  min_score: 3

topics: [RWA, 穩定幣, 金融法規, SSI, ZK, 支付, 重點機構]

jurisdictions: [美國, 歐盟, 英國, 香港, 新加坡, 日本, 韓國, 台灣, 加拿大, 全球]

tracks: [穩定幣, 結算／存款代幣, 代幣化證券／RWA, 數位身分, 虛擬資產業者]

stages:
  1: 研議
  2: 草案
  3: 已通過
  4: 施行中
  5: 市場運作

maturity: [seed, growing, stable]

origins: [ai, ai-reviewed, human]

watchlist:
  - {id: chainlink,  name: Chainlink,            aliases: [Chainlink, CCIP]}
  - {id: kinexys,    name: Kinexys（原 Onyx）,    aliases: [Kinexys, Onyx by J.P. Morgan]}
  - {id: jpmorgan,   name: JPMorgan,             aliases: [JPMorgan, J.P. Morgan, JP Morgan, 摩根大通]}
  - {id: fidelity,   name: Fidelity,             aliases: [Fidelity, 富達]}
  - {id: bny,        name: BNY,                  aliases: [BNY, BNY Mellon, 紐約梅隆]}
  - {id: fireblocks, name: Fireblocks,           aliases: [Fireblocks]}
  - {id: zk,         name: Zero knowledge,       aliases: [zero knowledge, ZKP, zkEVM, 零知識]}
  - {id: polygon,    name: Polygon／Privado ID,  aliases: [Polygon, Polygon ID, Privado ID]}
```

- [ ] **Step 6：建立 `scripts/taxonomy.py`**

```python
"""讀 taxonomy.yaml：分類詞彙唯一來源。"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("limits", "topics", "jurisdictions", "tracks", "stages", "maturity", "origins", "watchlist")


class TaxonomyError(ValueError):
    pass


def load_taxonomy(path: Path = ROOT / "taxonomy.yaml") -> dict:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TaxonomyError(f"taxonomy.yaml 解析失敗：{e}") from e
    if not isinstance(data, dict):
        raise TaxonomyError("taxonomy.yaml 頂層必須是 key: value")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise TaxonomyError("taxonomy.yaml 缺少欄位：" + ", ".join(missing))
    ids = [w["id"] for w in data["watchlist"]]
    if len(ids) != len(set(ids)):
        raise TaxonomyError("watchlist id 重複")
    return data
```

- [ ] **Step 7：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_taxonomy.py -v`
預期：3 passed

- [ ] **Step 8：Commit**

```bash
git add requirements-dev.txt taxonomy.yaml scripts/taxonomy.py tests/conftest.py tests/test_taxonomy.py
git commit -m "feat: taxonomy.yaml 分類詞彙唯一來源與載入器"
```

---

### Task 2：筆記解析模組 `notes.py`

**Files:**
- Create: `scripts/notes.py`、`tests/test_notes.py`

**Interfaces:**
- Consumes: 無
- Produces:
  - `NOTE_DIRS: tuple[str, ...]`：`("10-events","20-concepts","30-entities","40-regulations","50-maps","60-outputs")`
  - `@dataclass Note(path: Path, fm: dict, body: str, error: str = "")`：`error` 非空代表 frontmatter 壞掉
  - `parse_note(path: Path) -> Note`：永不丟例外
  - `iter_notes(root: Path, dirs=NOTE_DIRS) -> Iterator[Note]`
  - `first_heading(body: str) -> str`：第一個任意層級的 Markdown 標題，沒有就回 `""`
  - `new_id(existing: set[str]) -> str`：8 碼，不在 `existing` 裡
  - `ID_RE`：`re.compile(r"^[a-z2-7]{8}$")`
  - `is_legacy_auto(note: Note) -> bool`

- [ ] **Step 1：寫失敗的測試 `tests/test_notes.py`**

```python
import notes


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_ok(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\ntype: concept\ntopics: [RWA]\n---\n# 標題\n內文\n"))
    assert n.error == ""
    assert n.fm == {"type": "concept", "topics": ["RWA"]}
    assert n.body.startswith("# 標題")


def test_parse_crlf(tmp_path):
    p = tmp_path / "a.md"
    p.write_bytes("---\r\ntype: moc\r\n---\r\n# X\r\n".encode("utf-8"))
    n = notes.parse_note(p)
    assert n.error == "" and n.fm["type"] == "moc"


def test_parse_missing_frontmatter(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "# 沒有 frontmatter\n"))
    assert n.error == "缺少 frontmatter"


def test_parse_bad_yaml_reports_error(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\ntitle: a: b: [\n---\nx\n"))
    assert n.error.startswith("YAML 解析失敗")
    assert n.fm == {}


def test_parse_non_mapping(tmp_path):
    n = notes.parse_note(write(tmp_path / "a.md", "---\n- a\n- b\n---\nx\n"))
    assert n.error == "frontmatter 不是 key: value 形式"


def test_first_heading():
    assert notes.first_heading("前言\n## 第二層標題\n# 一層\n") == "第二層標題"
    assert notes.first_heading("沒有標題") == ""


def test_new_id_format_and_unique():
    existing = set()
    for _ in range(200):
        i = notes.new_id(existing)
        assert notes.ID_RE.match(i)
        assert i not in existing
        existing.add(i)


def test_iter_notes_and_legacy(tmp_vault):
    write(tmp_vault / "10-events" / "a.md", "---\ntype: event\nauto: true\n---\nx\n")
    write(tmp_vault / "20-concepts" / "b.md", "---\ntype: concept\n---\nx\n")
    got = {n.path.name: n for n in notes.iter_notes(tmp_vault)}
    assert set(got) == {"a.md", "b.md"}
    assert notes.is_legacy_auto(got["a.md"]) is True
    assert notes.is_legacy_auto(got["b.md"]) is False
```

- [ ] **Step 2：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_notes.py -v`
預期：FAIL，`No module named 'notes'`

- [ ] **Step 3：建立 `scripts/notes.py`**

```python
"""筆記解析：所有腳本共用，壞掉的 frontmatter 會回報錯誤而不是靜默變成 {}。"""
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

NOTE_DIRS = ("10-events", "20-concepts", "30-entities", "40-regulations", "50-maps", "60-outputs")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
ID_RE = re.compile(r"^[a-z2-7]{8}$")


@dataclass
class Note:
    path: Path
    fm: dict
    body: str
    error: str = ""


def parse_note(path: Path) -> Note:
    raw = Path(path).read_text(encoding="utf-8")
    m = FM_RE.match(raw)
    if not m:
        return Note(path, {}, raw, "缺少 frontmatter")
    body = raw[m.end():]
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        first_line = str(e).splitlines()[0]
        return Note(path, {}, body, f"YAML 解析失敗：{first_line}")
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        return Note(path, {}, body, "frontmatter 不是 key: value 形式")
    return Note(path, fm, body)


def iter_notes(root: Path, dirs=NOTE_DIRS) -> Iterator[Note]:
    for d in dirs:
        for f in sorted((Path(root) / d).glob("*.md")):
            yield parse_note(f)


def first_heading(body: str) -> str:
    m = HEADING_RE.search(body)
    return m.group(1).strip() if m else ""


def new_id(existing: set) -> str:
    while True:
        i = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
        if i not in existing:
            return i


def is_legacy_auto(note: Note) -> bool:
    """main 上 bot 產生的舊格式自動卡：階段 2 匯入 D1 前不驗證、不遷移。"""
    return note.fm.get("type") == "event" and note.fm.get("auto") is True
```

`Path.read_text` 會把 CRLF 轉成 `\n`，所以 CRLF 測試不用特別處理。

- [ ] **Step 4：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_notes.py -v`
預期：8 passed

- [ ] **Step 5：Commit**

```bash
git add scripts/notes.py tests/test_notes.py
git commit -m "feat: notes.py 共用筆記解析，YAML 錯誤回報而非靜默忽略"
```

---

### Task 3：schema 驗證 `validate.py`

**Files:**
- Create: `scripts/validate.py`、`tests/test_validate.py`

**Interfaces:**
- Consumes: `notes.parse_note`、`notes.iter_notes`、`notes.is_legacy_auto`、`notes.ID_RE`、`notes.first_heading`；`taxonomy.load_taxonomy`
- Produces:
  - `@dataclass Issue(path: Path, level: str, msg: str)`：`level` 是 `"error"` 或 `"warning"`
  - `validate_note(note: Note, tax: dict) -> list[Issue]`：單篇規則，不含跨檔檢查
  - `validate_all(root: Path, tax: dict) -> list[Issue]`：單篇規則、`id` 重複、wikilink 懸空（warning）
  - `report(issues: list[Issue], root: Path) -> int`：印出，回傳 error 數
  - CLI：`python scripts/validate.py`，有 error 時 exit 1

規則（取自 spec §4.2、§4.5）：

| 規則 | 等級 |
|---|---|
| `note.error` 非空（缺 frontmatter、YAML 壞、非 mapping） | error |
| 舊自動卡（`is_legacy_auto`）只檢查上一條，其餘略過 | — |
| 缺 `id`、`type`、`title`、`origin`、`topics` | error |
| `id` 不符 `ID_RE` | error |
| `type` 不是該資料夾的類型（`10-events`→event、`20-concepts`→concept、`30-entities`→entity、`40-regulations`→regulation、`50-maps`→moc、`60-outputs`→output） | error |
| `origin` 不在 `tax["origins"]` | error |
| `origin: ai-reviewed` 但沒有 `reviewed` | error |
| `topics` 不是 list，或有值不在 `tax["topics"]` | error |
| 類型必填欄：concept `maturity, updated`；entity `jurisdiction, updated`；regulation `jurisdiction, updated`；moc `updated`；event `date`；output `kind, date` | error |
| `maturity` 不在 `tax["maturity"]` | error |
| `jurisdiction` 以 `/` 切開後任一段（去空白）不在 `tax["jurisdictions"]` | error |
| `tracks` 有值不在 `tax["tracks"]` | error |
| `stage` 存在但不是 1–5 的整數 | error |
| `review` 存在但不是 `待核對` 或 `已核對` | error |
| `effective_date` 存在且非空，但不是 date 物件、也不符 `^\d{4}(-\d{2}(-\d{2})?)?$` | error |
| `kind` 不是 `週報` 或 `講稿` | error |
| 兩篇以上筆記同一個 `id` | error（每篇各報一次） |
| wikilink `[[X]]` 找不到筆記（比對檔名與 `title`，不分大小寫；`news:`、`event:` 開頭略過） | warning |

- [ ] **Step 1：寫失敗的測試 `tests/test_validate.py`**

```python
import validate
from notes import parse_note

GOOD_CONCEPT = """---
type: concept
id: abcdefgh
title: 現金腿
origin: ai
topics: [RWA]
maturity: growing
updated: 2026-09-23
---
# 現金腿
連到 [[原子結算]] 與 [[news:12]]
"""


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def msgs(issues):
    return [i.msg for i in issues]


def test_good_concept_has_no_issues(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT))
    assert validate.validate_note(n, tax) == []


def test_bad_yaml_is_error(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", "---\ntitle: a: b: [\n---\n"))
    out = validate.validate_note(n, tax)
    assert out[0].level == "error" and out[0].msg.startswith("YAML 解析失敗")


def test_legacy_auto_card_skipped(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "10-events" / "a.md", "---\ntype: event\nauto: true\ntopics: [亂寫]\n---\n"))
    assert validate.validate_note(n, tax) == []


def test_missing_required_fields(tmp_vault, tax):
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", "---\ntype: concept\n---\n"))
    m = msgs(validate.validate_note(n, tax))
    for f in ("id", "title", "origin", "topics", "maturity", "updated"):
        assert f"缺少欄位 {f}" in m


def test_type_must_match_folder(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("type: concept", "type: entity")
    n = parse_note(write(tmp_vault / "20-concepts" / "x.md", text))
    assert "type 應為 concept（資料夾 20-concepts），實際是 entity" in msgs(validate.validate_note(n, tax))


def test_unknown_topic_and_origin(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("topics: [RWA]", "topics: [RWA, 亂寫]").replace("origin: ai", "origin: robot")
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "20-concepts" / "x.md", text)), tax))
    assert "topics 值不在 taxonomy：亂寫" in m
    assert "origin 值不合法：robot" in m


def test_ai_reviewed_needs_reviewed_date(tmp_vault, tax):
    text = GOOD_CONCEPT.replace("origin: ai", "origin: ai-reviewed")
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "20-concepts" / "x.md", text)), tax))
    assert "origin 是 ai-reviewed 但沒有 reviewed 日期" in m


def test_regulation_rules(tmp_vault, tax):
    text = """---
type: regulation
id: bcdefghi
title: 某法
origin: ai
topics: [金融法規]
jurisdiction: 香港 / 火星
updated: 2026-09-23
stage: 9
review: 大概
tracks: [穩定幣, 亂寫]
effective_date: 最快 2027Q1
---
"""
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "40-regulations" / "x.md", text)), tax))
    assert "jurisdiction 值不在 taxonomy：火星" in m
    assert "stage 必須是 1–5 的整數：9" in m
    assert "review 值不合法：大概" in m
    assert "tracks 值不在 taxonomy：亂寫" in m
    assert "effective_date 必須是 YYYY、YYYY-MM 或 YYYY-MM-DD：最快 2027Q1" in m


def test_effective_date_forms_ok(tmp_vault, tax):
    for v in ("2026-09-08", "2023-06", "2027", ""):
        text = f"""---
type: regulation
id: bcdefghi
title: 某法
origin: ai
topics: [金融法規]
jurisdiction: 全球
updated: 2026-09-23
effective_date: {v}
---
"""
        n = parse_note(write(tmp_vault / "40-regulations" / "x.md", text))
        assert validate.validate_note(n, tax) == [], v


def test_output_kind(tmp_vault, tax):
    text = """---
type: output
id: cdefghij
title: 週報
origin: human
topics: [RWA]
kind: 日報
date: 2026-09-18
---
"""
    m = msgs(validate.validate_note(parse_note(write(tmp_vault / "60-outputs" / "x.md", text)), tax))
    assert "kind 值不合法：日報" in m


def test_validate_all_duplicate_id_and_dangling_link(tmp_vault, tax):
    write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT)
    write(tmp_vault / "20-concepts" / "copy.md", GOOD_CONCEPT.replace("title: 現金腿", "title: 副本"))
    out = validate.validate_all(tmp_vault, tax)
    dup = [i for i in out if i.msg.startswith("id 重複")]
    assert len(dup) == 2 and all(i.level == "error" for i in dup)
    miss = [i for i in out if i.level == "warning"]
    assert any(i.msg == "wikilink 找不到筆記：[[原子結算]]" for i in miss)
    assert not any("news:12" in i.msg for i in out)


def test_link_resolves_by_title(tmp_vault, tax):
    write(tmp_vault / "20-concepts" / "cash-leg.md", GOOD_CONCEPT)
    write(tmp_vault / "20-concepts" / "atomic.md",
          GOOD_CONCEPT.replace("id: abcdefgh", "id: zzzzzzzz").replace("title: 現金腿", "title: 原子結算"))
    out = validate.validate_all(tmp_vault, tax)
    assert not any(i.msg == "wikilink 找不到筆記：[[原子結算]]" for i in out)


def test_report_returns_error_count(tmp_vault, capsys):
    issues = [validate.Issue(tmp_vault / "20-concepts" / "a.md", "error", "壞"),
              validate.Issue(tmp_vault / "20-concepts" / "b.md", "warning", "注意")]
    assert validate.report(issues, tmp_vault) == 1
    out = capsys.readouterr().out
    assert "20-concepts/a.md" in out and "壞" in out and "注意" in out
```

- [ ] **Step 2：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_validate.py -v`
預期：FAIL，`No module named 'validate'`

- [ ] **Step 3：建立 `scripts/validate.py`**

```python
#!/usr/bin/env python3
"""筆記 schema 驗證。建站第一步執行，有 error 就讓 build 失敗。

用法： python scripts/validate.py
"""
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import taxonomy
from notes import ID_RE, Note, is_legacy_auto, iter_notes

ROOT = Path(__file__).resolve().parent.parent
DIR_TYPE = {"10-events": "event", "20-concepts": "concept", "30-entities": "entity",
            "40-regulations": "regulation", "50-maps": "moc", "60-outputs": "output"}
COMMON = ("id", "type", "title", "origin", "topics")
BY_TYPE = {"concept": ("maturity", "updated"), "entity": ("jurisdiction", "updated"),
           "regulation": ("jurisdiction", "updated"), "moc": ("updated",),
           "event": ("date",), "output": ("kind", "date")}
REVIEW = ("待核對", "已核對")
KINDS = ("週報", "講稿")
PARTIAL_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


@dataclass
class Issue:
    path: Path
    level: str   # "error" | "warning"
    msg: str


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def validate_note(note: Note, tax: dict) -> list:
    out = []

    def err(msg):
        out.append(Issue(note.path, "error", msg))

    if note.error:
        err(note.error)
        return out
    if is_legacy_auto(note):
        return out
    fm = note.fm
    expected = DIR_TYPE.get(note.path.parent.name)
    kind = fm.get("type")
    for f in COMMON + BY_TYPE.get(kind, ()):
        if fm.get(f) in (None, ""):
            err(f"缺少欄位 {f}")
    if expected and kind and kind != expected:
        err(f"type 應為 {expected}（資料夾 {note.path.parent.name}），實際是 {kind}")
    if fm.get("id") and not ID_RE.match(str(fm["id"])):
        err(f"id 格式不對：{fm['id']}")
    origin = fm.get("origin")
    if origin and origin not in tax["origins"]:
        err(f"origin 值不合法：{origin}")
    if origin == "ai-reviewed" and not fm.get("reviewed"):
        err("origin 是 ai-reviewed 但沒有 reviewed 日期")
    if "topics" in fm and fm["topics"] is not None and not isinstance(fm["topics"], list):
        err("topics 必須是陣列")
    for t in _as_list(fm.get("topics")):
        if t not in tax["topics"]:
            err(f"topics 值不在 taxonomy：{t}")
    if fm.get("maturity") and fm["maturity"] not in tax["maturity"]:
        err(f"maturity 值不合法：{fm['maturity']}")
    if fm.get("jurisdiction"):
        for part in str(fm["jurisdiction"]).split("/"):
            part = part.strip()
            if part and part not in tax["jurisdictions"]:
                err(f"jurisdiction 值不在 taxonomy：{part}")
    for t in _as_list(fm.get("tracks")):
        if t not in tax["tracks"]:
            err(f"tracks 值不在 taxonomy：{t}")
    if "stage" in fm and fm["stage"] is not None:
        s = fm["stage"]
        if not (isinstance(s, int) and not isinstance(s, bool) and 1 <= s <= 5):
            err(f"stage 必須是 1–5 的整數：{s}")
    if fm.get("review") and fm["review"] not in REVIEW:
        err(f"review 值不合法：{fm['review']}")
    ed = fm.get("effective_date")
    if ed not in (None, "") and not isinstance(ed, dt.date) and not PARTIAL_DATE.match(str(ed)):
        err(f"effective_date 必須是 YYYY、YYYY-MM 或 YYYY-MM-DD：{ed}")
    if kind == "output" and fm.get("kind") and fm["kind"] not in KINDS:
        err(f"kind 值不合法：{fm['kind']}")
    return out


def validate_all(root: Path, tax: dict) -> list:
    all_notes = list(iter_notes(root))
    out = []
    for n in all_notes:
        out += validate_note(n, tax)

    by_id = {}
    for n in all_notes:
        if n.fm.get("id") and not is_legacy_auto(n):
            by_id.setdefault(str(n.fm["id"]), []).append(n)
    for i, group in by_id.items():
        if len(group) > 1:
            names = "、".join(g.path.name for g in group)
            for g in group:
                out.append(Issue(g.path, "error", f"id 重複：{i}（{names}）"))

    known = set()
    for n in all_notes:
        known.add(n.path.stem.lower())
        if n.fm.get("title"):
            known.add(str(n.fm["title"]).lower())
    for n in all_notes:
        if n.error:
            continue
        for m in WIKI_RE.finditer(n.body):
            target = m.group(1).strip()
            if target.startswith(("news:", "event:")):
                continue
            if target.lower() not in known:
                out.append(Issue(n.path, "warning", f"wikilink 找不到筆記：[[{target}]]"))
    return out


def report(issues: list, root: Path) -> int:
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    for label, group in (("錯誤", errors), ("警告", warnings)):
        for i in group:
            rel = i.path.relative_to(root).as_posix()
            print(f"[{label}] {rel}：{i.msg}")
    print(f"驗證完成：{len(errors)} 個錯誤、{len(warnings)} 個警告")
    return len(errors)


def main() -> int:
    tax = taxonomy.load_taxonomy()
    return 1 if report(validate_all(ROOT, tax), ROOT) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_validate.py -v`
預期：13 passed

- [ ] **Step 5：對真實 repo 跑一次，確認會抓出遷移前的問題**

執行：`PYTHONUTF8=1 python scripts/validate.py; echo "exit=$?"`
預期：大量「缺少欄位 id／title／origin」錯誤、`effective_date` 格式錯誤，以及 5 個 wikilink 警告（`[[結算]]`×2、`[[OCC]]`、`[[Proof]]`、`[[渣打]]`），`exit=1`。38 張自動卡不應出現在輸出裡。

- [ ] **Step 6：Commit**

```bash
git add scripts/validate.py tests/test_validate.py
git commit -m "feat: validate.py 筆記 schema 驗證"
```

---

### Task 4：遷移腳本 `migrate_notes.py`

**Files:**
- Create: `scripts/migrate_notes.py`、`tests/test_migrate.py`
- Modify: `docs/superpowers/specs/2026-09-24-vault-v2-design.md`（§4.2 regulation 一列）

**Interfaces:**
- Consumes: `notes.FM_RE`、`notes.first_heading`、`notes.new_id`、`notes.iter_notes`、`notes.is_legacy_auto`、`notes.parse_note`
- Produces:
  - `migrate_text(raw: str, stem: str, existing_ids: set, origin: str = "ai") -> str`：回傳新全文；會把新 id 加進 `existing_ids`；舊自動卡原樣回傳；可重跑，第二次不變
  - CLI：`python scripts/migrate_notes.py [--dry-run] [--human 檔名 ...]`

遷移規則（逐行處理 frontmatter，保留原本格式與順序）：
1. 刪掉 `keyword_hits`、`used_in` 兩個 key；`type: event` 另外刪 `status`。刪 key 時連同後面的縮排或 `- ` 續行一起刪。
2. 在 `type:` 那行後面依序補上缺的 `id`、`title`、`origin`。`title` 取正文第一個標題，沒有就用檔名，寫成 JSON 字串（加引號、`ensure_ascii=False`）。
3. `effective_date` 值不符 `YYYY[-MM[-DD]]`：
   - 開頭有合法日期（例如 `2026-09-01（提案日）`）→ `effective_date: 2026-09-01`，其餘文字（去掉外層全形括號）放 `effective_note`
   - 開頭沒有日期（例如 `最快 2027Q1`、`未定`）→ `effective_date:` 留空，原文放 `effective_note`

- [ ] **Step 1：更新 spec §4.2**

在 `docs/superpowers/specs/2026-09-24-vault-v2-design.md` 把 regulation 那一列的
`` `effective_date` 改成 ISO 日期或空值 ``
改成
`` `effective_date` 改成 `YYYY`／`YYYY-MM`／`YYYY-MM-DD` 或空值；原本的附註文字（例如「最晚」「提案日」）移到 `effective_note` ``

- [ ] **Step 2：寫失敗的測試 `tests/test_migrate.py`**

```python
from migrate_notes import migrate_text
from notes import ID_RE, FM_RE
import yaml


def fm_of(text):
    return yaml.safe_load(FM_RE.match(text).group(1))


CONCEPT = """---
type: concept
topics: [RWA, 支付]
maturity: growing
updated: 2026-09-23
---

# Cash leg（現金腿）

內文
"""

HUMAN_EVENT = """---
type: event
date: 2026-09-22
title: SoFi 穩定幣結算
source_url: https://example.com/a
topics: [RWA]
entities: ["[[SoFi]]"]
score: 8
status: cited
used_in: ["日報 2026-09-23"]
keyword_hits:
  - stablecoin
  - settle
---
## 一句話
x
"""


def test_concept_gets_id_title_origin():
    ids = set()
    out = migrate_text(CONCEPT, "cash-leg", ids)
    fm = fm_of(out)
    assert ID_RE.match(fm["id"]) and fm["id"] in ids
    assert fm["title"] == "Cash leg（現金腿）"
    assert fm["origin"] == "ai"
    lines = out.splitlines()
    assert lines[1] == "type: concept"
    assert lines[2].startswith("id: ")
    assert lines[3] == 'title: "Cash leg（現金腿）"'
    assert lines[4] == "origin: ai"
    assert out.endswith("# Cash leg（現金腿）\n\n內文\n")


def test_event_removes_fields_keeps_title():
    out = migrate_text(HUMAN_EVENT, "2026-09-22-sofi", set(), origin="human")
    fm = fm_of(out)
    for k in ("status", "used_in", "keyword_hits"):
        assert k not in fm
    assert fm["title"] == "SoFi 穩定幣結算"
    assert fm["origin"] == "human"
    assert fm["entities"] == ["[[SoFi]]"]
    assert "  - settle" not in out


def test_title_falls_back_to_stem():
    out = migrate_text("---\ntype: moc\ntopics: [ZK]\nupdated: 2026-09-23\n---\n沒有標題\n", "MOC-ZK", set())
    assert fm_of(out)["title"] == "MOC-ZK"


def test_idempotent():
    once = migrate_text(CONCEPT, "cash-leg", set())
    assert migrate_text(once, "cash-leg", set()) == once


def test_legacy_auto_untouched():
    raw = "---\ntype: event\nauto: true\nstatus: unread\n---\nx\n"
    assert migrate_text(raw, "a", set()) == raw


def reg(value):
    return f"---\ntype: regulation\ntopics: [金融法規]\njurisdiction: 美國\neffective_date: {value}\nupdated: 2026-09-23\n---\n# 法\n"


def test_effective_date_with_note():
    fm = fm_of(migrate_text(reg("2027-01-18（最晚）"), "x", set()))
    assert str(fm["effective_date"]) == "2027-01-18"
    assert fm["effective_note"] == "最晚"


def test_effective_date_without_date():
    fm = fm_of(migrate_text(reg("最快 2027Q1"), "x", set()))
    assert fm["effective_date"] is None
    assert fm["effective_note"] == "最快 2027Q1"


def test_effective_date_valid_untouched():
    for v in ("2026-09-08", "2023-06"):
        out = migrate_text(reg(v), "x", set())
        assert f"effective_date: {v}\n" in out
        assert "effective_note" not in out
```

- [ ] **Step 3：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_migrate.py -v`
預期：FAIL，`No module named 'migrate_notes'`

- [ ] **Step 4：建立 `scripts/migrate_notes.py`**

```python
#!/usr/bin/env python3
"""一次性遷移：補 id / title / origin，刪沒用的欄位，整理 effective_date。可重跑。

用法：
  python scripts/migrate_notes.py --dry-run
  python scripts/migrate_notes.py --human 2026-09-22-sofi-穩定幣結算-mastercard.md ...
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from notes import FM_RE, first_heading, is_legacy_auto, iter_notes, new_id, parse_note

ROOT = Path(__file__).resolve().parent.parent
REMOVE_ALWAYS = {"keyword_hits", "used_in"}
REMOVE_EVENT = {"status"}
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
DATE_PREFIX = re.compile(r"^(\d{4}(?:-\d{2}(?:-\d{2})?)?)(?!\d)(.*)$")
FULL_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _strip_note(s: str) -> str:
    s = s.strip()
    if s.startswith("（") and s.endswith("）"):
        s = s[1:-1]
    return s.strip()


def _fix_effective_date(value: str) -> list:
    v = value.strip()
    if v == "" or FULL_DATE.match(v):
        return [f"effective_date:{' ' + v if v else ''}"]
    m = DATE_PREFIX.match(v)
    if m and m.group(2).strip():
        return [f"effective_date: {m.group(1)}",
                f"effective_note: {json.dumps(_strip_note(m.group(2)), ensure_ascii=False)}"]
    return ["effective_date:", f"effective_note: {json.dumps(v, ensure_ascii=False)}"]


def migrate_text(raw: str, stem: str, existing_ids: set, origin: str = "ai") -> str:
    m = FM_RE.match(raw)
    if not m:
        return raw
    fm = yaml.safe_load(m.group(1)) or {}
    if fm.get("type") == "event" and fm.get("auto") is True:
        return raw
    body = raw[m.end():]   # 只拿來找標題
    remove = REMOVE_ALWAYS | (REMOVE_EVENT if fm.get("type") == "event" else set())

    out, skipping = [], False
    for line in m.group(1).split("\n"):
        km = KEY_RE.match(line)
        if km:
            skipping = km.group(1) in remove
            if skipping:
                continue
            if km.group(1) == "effective_date" and "effective_note" not in fm:
                out += _fix_effective_date(km.group(2))
                continue
        elif skipping and (line.startswith((" ", "\t", "-")) or line.strip() == ""):
            continue
        else:
            skipping = False
        out.append(line)

    add = []
    if not fm.get("id"):
        i = new_id(existing_ids)
        existing_ids.add(i)
        add.append(f"id: {i}")
    if not fm.get("title"):
        add.append(f"title: {json.dumps(first_heading(body) or stem, ensure_ascii=False)}")
    if not fm.get("origin"):
        add.append(f"origin: {origin}")
    if add:
        at = next(k for k, l in enumerate(out) if l.startswith("type:")) + 1
        out[at:at] = add
    # 開頭分隔線與「結尾分隔線＋正文」原樣保留，避免吃掉 frontmatter 後的空行
    return raw[:m.start(1)] + "\n".join(out) + raw[m.end(1):]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--human", nargs="*", default=[], help="這些檔名的 origin 設成 human")
    args = ap.parse_args(argv)

    all_notes = list(iter_notes(ROOT))
    ids = {str(n.fm["id"]) for n in all_notes if n.fm.get("id")}
    changed = 0
    for n in all_notes:
        if n.error or is_legacy_auto(n):
            continue
        raw = n.path.read_text(encoding="utf-8")
        origin = "human" if n.path.name in args.human else "ai"
        new = migrate_text(raw, n.path.stem, ids, origin)
        if new != raw:
            changed += 1
            print(("[試跑] " if args.dry_run else "") + n.path.relative_to(ROOT).as_posix())
            if not args.dry_run:
                n.path.write_text(new, encoding="utf-8")
    print(f"{'會' if args.dry_run else '已'}修改 {changed} 篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_migrate.py -v`
預期：8 passed

- [ ] **Step 6：Commit（只 commit 程式，還不動筆記）**

```bash
git add scripts/migrate_notes.py tests/test_migrate.py docs/superpowers/specs/2026-09-24-vault-v2-design.md
git commit -m "feat: migrate_notes.py 補 id/title/origin、刪無用欄位、整理 effective_date"
```

---

### Task 5：對真實筆記執行遷移（需要使用者決定）

**Files:**
- Modify: `10-events/` 5 張人寫卡、`20-concepts/*`、`30-entities/*`、`40-regulations/*`、`50-maps/*`、`60-outputs/*`

**Interfaces:**
- Consumes: Task 4 的 CLI、Task 3 的 CLI

- [ ] **Step 1：試跑**

執行：`PYTHONUTF8=1 python scripts/migrate_notes.py --dry-run`
預期：列出 42 篇（人寫事件 5＋概念 8＋機構 12＋法規 11＋MOC 4＋產出 2），`會修改 42 篇`。自動卡不應出現。

- [ ] **Step 2：停下來問使用者，下面 7 篇的 origin 各是什麼**

問題：「以下 7 篇你要標 `human`（你寫的）還是 `ai`（AI 寫的）？」逐篇列出：
- `10-events/2026-09-08-fincen-vdc-cip-faq.md`
- `10-events/2026-09-16-circle-arc-主網上線.md`
- `10-events/2026-09-16-香港施政報告-穩定幣結算資產.md`
- `10-events/2026-09-17-sec-代幣化證券創新豁免.md`
- `10-events/2026-09-22-sofi-穩定幣結算-mastercard.md`
- `60-outputs/2026-W38-週報-逐段口白對照.md`
- `60-outputs/2026-W38-週報-香港穩定幣結算資產.md`

其餘 35 篇依 spec 一律標 `ai`。

- [ ] **Step 3：正式執行**

把使用者回答 `human` 的檔名填進 `--human`（只填檔名，不含資料夾）：

執行：`PYTHONUTF8=1 python scripts/migrate_notes.py --human <檔名1> <檔名2> ...`
預期：`已修改 42 篇`

- [ ] **Step 4：確認可重跑**

執行：`PYTHONUTF8=1 python scripts/migrate_notes.py --dry-run`
預期：`會修改 0 篇`

- [ ] **Step 5：跑驗證**

執行：`PYTHONUTF8=1 python scripts/validate.py; echo "exit=$?"`
預期：`0 個錯誤`、5 個 wikilink 警告、`exit=0`。

如果還有錯誤，逐條處理：
- `jurisdiction` 或 `topics` 值不在 taxonomy → 值合理就加進 `taxonomy.yaml`，打錯就改筆記。兩種做法都寫進 commit 訊息。
- 其他錯誤 → 改筆記，不要放寬驗證規則。

- [ ] **Step 6：人工抽查 diff**

執行：`git diff --stat` 與 `git diff 40-regulations/美國-GENIUS-Act.md 20-concepts/cash-leg.md`
確認：
- 只有 frontmatter 改變，正文沒動
- 引號與陣列寫法保留原樣
- `effective_note` 內容正確

- [ ] **Step 7：Commit**

```bash
git add 10-events 20-concepts 30-entities 40-regulations 50-maps 60-outputs taxonomy.yaml
git commit -m "chore: 筆記遷移，補 id/title/origin，整理 effective_date

origin：35 篇標 ai；人寫卡與週報依使用者判定。"
```

---

### Task 6：建站接上驗證與 origin 標籤

**Files:**
- Modify: `scripts/build_site.py`：`collect()`（約 79–97 行）、`build_notes()` 的 byline（約 406–422 行）、`CSS` 字串結尾、`main()`（約 1063 行）
- Create: `tests/test_build_site.py`

**Interfaces:**
- Consumes: `validate.validate_all`、`validate.report`、`taxonomy.load_taxonomy`
- Produces: `build_site.origin_badge(n: dict) -> str`

- [ ] **Step 1：寫失敗的測試 `tests/test_build_site.py`**

```python
import pytest

import build_site


def test_origin_badge_ai():
    assert build_site.origin_badge({"origin": "ai", "reviewed": ""}) == \
        '<span class="origin origin-ai" title="AI 撰寫，尚未審閱">AI 草稿</span>'


def test_origin_badge_reviewed():
    assert build_site.origin_badge({"origin": "ai-reviewed", "reviewed": "2026-09-30"}) == \
        '<span class="origin origin-reviewed" title="AI 撰寫，已審閱">已審閱 2026-09-30</span>'


def test_origin_badge_human_and_missing():
    assert build_site.origin_badge({"origin": "human", "reviewed": ""}) == ""
    assert build_site.origin_badge({"origin": "", "reviewed": ""}) == ""


def test_origin_badge_escapes():
    out = build_site.origin_badge({"origin": "ai-reviewed", "reviewed": "<b>"})
    assert "<b>" not in out and "&lt;b&gt;" in out


def test_main_fails_on_schema_error(monkeypatch):
    import validate
    monkeypatch.setattr(validate, "validate_all",
                        lambda root, tax: [validate.Issue(build_site.ROOT / "20-concepts" / "x.md", "error", "壞")])
    with pytest.raises(SystemExit) as e:
        build_site.main()
    assert e.value.code == 1
```

- [ ] **Step 2：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_build_site.py -v`
預期：FAIL，`AttributeError: module 'build_site' has no attribute 'origin_badge'`

- [ ] **Step 3：修改 `collect()`**

在 `notes[slug] = dict(` 的欄位中，`review=fm.get("review", ""),` 後面加：

```python
                origin=str(fm.get("origin") or ""), reviewed=str(fm.get("reviewed") or ""),
```

- [ ] **Step 4：新增 `origin_badge()`**

放在 `def source_link(` 前面：

```python
ORIGIN_LABEL = {
    "ai": ("origin-ai", "AI 撰寫，尚未審閱", "AI 草稿"),
    "ai-reviewed": ("origin-reviewed", "AI 撰寫，已審閱", "已審閱"),
}


def origin_badge(n):
    """筆記出處標籤：human 或沒填不顯示。"""
    hit = ORIGIN_LABEL.get(n.get("origin", ""))
    if not hit:
        return ""
    cls, tip, label = hit
    if n.get("origin") == "ai-reviewed" and n.get("reviewed"):
        label = f"{label} {n['reviewed']}"
    return f'<span class="origin {cls}" title="{esc(tip)}">{esc(label)}</span>'
```

- [ ] **Step 5：byline 加標籤**

在 `build_notes()` 裡，`byline = [f"<time>...` 那行之後加：

```python
        badge = origin_badge(n)
        if badge:
            byline.append(badge)
```

- [ ] **Step 6：CSS 加樣式**

在 `CSS = """` 字串的結尾 `"""` 之前加：

```css
.origin{display:inline-block;font-size:.72rem;padding:.05rem .45rem;border-radius:3px;margin-left:.4rem;letter-spacing:.02em}
.origin-ai{background:#8883;color:inherit;border:1px dashed #888}
.origin-reviewed{background:#2a7a4b22;color:inherit;border:1px solid #2a7a4b}
```

- [ ] **Step 7：`main()` 先驗證**

在 `main()` 開頭（`OUT.mkdir(exist_ok=True)` 之前）加：

```python
    import taxonomy
    import validate
    if validate.report(validate.validate_all(ROOT, taxonomy.load_taxonomy()), ROOT):
        sys.exit(1)
```

`build_site.py` 以 `python scripts/build_site.py` 執行時，`scripts/` 已在 `sys.path`，import 不需要額外處理。

- [ ] **Step 8：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_build_site.py -v`
預期：5 passed

- [ ] **Step 9：完整建站**

執行：`PYTHONUTF8=1 python scripts/build_site.py`
預期：先印 `驗證完成：0 個錯誤、5 個警告`，再印 `✓ 網站已產生`。

檢查：
- `grep -l "origin-ai" site/n/*.html | wc -l` 應為 35＋（5 張人寫事件卡中標 `ai` 的張數）。60-outputs 不上網站，不算。
- 任取一張自動卡：`f=$(grep -l "^auto: true" 10-events/*.md | head -1); grep -c "origin-" "site/n/$(basename "$f" .md).html"` 應為 0

- [ ] **Step 10：Commit**

```bash
git add scripts/build_site.py tests/test_build_site.py
git commit -m "feat: 建站前先驗證 schema；筆記頁顯示 origin 標籤"
```

---

### Task 7：模板與 `new_note.py`

**Files:**
- Modify: `templates/concept.md`、`templates/entity.md`、`templates/regulation.md`、`templates/event.md`、`scripts/new_note.py`
- Create: `tests/test_new_note.py`

**Interfaces:**
- Consumes: `notes.new_id`、`notes.iter_notes`、`notes.parse_note`、`validate.validate_note`
- Produces: `new_note.create_note(root: Path, kind: str, title: str, today: str) -> Path`

- [ ] **Step 1：寫失敗的測試 `tests/test_new_note.py`**

```python
import shutil
from pathlib import Path

import pytest

import new_note
import validate
from notes import parse_note

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def vault_with_templates(tmp_vault):
    shutil.copytree(ROOT / "templates", tmp_vault / "templates")
    return tmp_vault


@pytest.mark.parametrize("kind", ["concept", "entity", "regulation", "event"])
def test_created_note_is_valid_except_user_fields(vault_with_templates, tax, kind):
    p = new_note.create_note(vault_with_templates, kind, "測試: 標題", "2026-09-25")
    n = parse_note(p)
    assert n.error == ""
    assert n.fm["title"] == "測試: 標題"
    assert n.fm["origin"] == "human"
    msgs = [i.msg for i in validate.validate_note(n, tax)]
    # 模板留空給人填的欄位才允許報錯
    allowed = {"缺少欄位 jurisdiction", "缺少欄位 topics"}
    assert set(msgs) <= allowed, msgs


def test_existing_file_refused(vault_with_templates):
    new_note.create_note(vault_with_templates, "concept", "重複", "2026-09-25")
    with pytest.raises(FileExistsError):
        new_note.create_note(vault_with_templates, "concept", "重複", "2026-09-25")


def test_ids_unique(vault_with_templates):
    a = parse_note(new_note.create_note(vault_with_templates, "concept", "甲", "2026-09-25")).fm["id"]
    b = parse_note(new_note.create_note(vault_with_templates, "concept", "乙", "2026-09-25")).fm["id"]
    assert a != b
```

- [ ] **Step 2：執行測試確認失敗**

執行：`PYTHONUTF8=1 python -m pytest tests/test_new_note.py -v`
預期：FAIL，`module 'new_note' has no attribute 'create_note'`

- [ ] **Step 3：更新四個模板的 frontmatter**

`templates/concept.md` 的 frontmatter 改成（正文不動）：

```yaml
---
type: concept
id: {{id}}
title: {{title}}
origin: human
topics: []
maturity: seed
updated: {{date}}
---
```

`templates/entity.md`：在 `type: entity` 下一行插入同樣三行 `id: {{id}}`、`title: {{title}}`、`origin: human`，其餘欄位保留。

`templates/regulation.md`：同上，在 `type: regulation` 下插入三行。

`templates/event.md` 的 frontmatter 整段換成（正文不動）：

```yaml
---
type: event
id: {{id}}
title: {{title}}
origin: human
date: {{date}}
source_url:
topics: []
---
```

- [ ] **Step 4：改寫 `scripts/new_note.py`**

```python
#!/usr/bin/env python3
"""從模板開新筆記。 用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題" """
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from notes import iter_notes, new_id

ROOT = Path(__file__).resolve().parent.parent
DEST = {"event": "10-events", "concept": "20-concepts",
        "entity": "30-entities", "regulation": "40-regulations"}
TZ = timezone(timedelta(hours=8))


def slug(t):
    t = unicodedata.normalize("NFKC", t).strip()
    return re.sub(r"[^\w一-鿿]+", "-", t).strip("-")[:60]


def create_note(root: Path, kind: str, title: str, today: str) -> Path:
    ids = {str(n.fm["id"]) for n in iter_notes(root) if n.fm.get("id")}
    tpl = (root / "templates" / f"{kind}.md").read_text(encoding="utf-8")
    tpl = (tpl.replace("{{date}}", today)
              .replace("{{id}}", new_id(ids))
              .replace("{{title}}", json.dumps(title, ensure_ascii=False)))
    tpl = tpl.replace("# 概念名稱", f"# {title}").replace("# 名稱", f"# {title}") \
             .replace("# 法規名稱", f"# {title}")
    name = f"{today}-{slug(title)}.md" if kind == "event" else f"{slug(title)}.md"
    p = root / DEST[kind] / name
    if p.exists():
        raise FileExistsError(p)
    p.write_text(tpl, encoding="utf-8")
    return p


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in DEST:
        sys.exit('用法： python3 scripts/new_note.py {event|concept|entity|regulation} "標題"')
    today = datetime.now(TZ).date().isoformat()
    try:
        print(create_note(ROOT, sys.argv[1], sys.argv[2], today))
    except FileExistsError as e:
        sys.exit(f"已存在：{e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5：執行測試確認通過**

執行：`PYTHONUTF8=1 python -m pytest tests/test_new_note.py -v`
預期：6 passed

如果 `entity`、`regulation` 的測試報出 `allowed` 以外的錯誤，例如模板的 `jurisdiction` 預設值不在 taxonomy：把模板裡該欄改成空值（`jurisdiction:`），不要放寬測試。

- [ ] **Step 6：Commit**

```bash
git add templates scripts/new_note.py tests/test_new_note.py
git commit -m "feat: 新筆記自動產生 id/title/origin，title 以 JSON 字串寫入避免冒號弄壞 YAML"
```

---

### Task 8：整體驗收

**Files:** 無新增

- [ ] **Step 1：全部測試**

執行：`PYTHONUTF8=1 python -m pytest -q`
預期：43 passed，0 failed

- [ ] **Step 2：驗證與建站**

執行：`PYTHONUTF8=1 python scripts/validate.py && PYTHONUTF8=1 python scripts/build_site.py`
預期：0 錯誤，建站成功。

- [ ] **Step 3：本機預覽抽查**

執行：`cd site && python -m http.server 8080`（背景執行）
打開以下三頁，確認 byline 有標籤、版面沒壞，深色模式也看得清楚：
- `http://localhost:8080/n/cash-leg.html` → 有「AI 草稿」
- `http://localhost:8080/n/美國-GENIUS-Act.html` → 有「AI 草稿」和「待核對」
- 任一張自動卡 → 沒有標籤

- [ ] **Step 4：確認 main 的 bot 格式仍通過驗證**

main 上的 bot 每天還在產生舊格式自動卡。執行：
`git fetch origin && git merge --no-commit --no-ff origin/main && PYTHONUTF8=1 python scripts/validate.py; git merge --abort`
預期：0 錯誤。如果 merge 有衝突，只 abort，不處理，記下來報告給使用者。

- [ ] **Step 5：回報使用者並停下**

回報：
- 測試數量
- 驗證結果
- 抽查頁面的狀況
- 新增和修改的檔案清單

然後詢問：要不要 push `redesign/vault-v2` 做 Cloudflare preview 部署？要不要合併進 main？**這兩件事都等使用者同意。**
