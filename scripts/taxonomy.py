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
