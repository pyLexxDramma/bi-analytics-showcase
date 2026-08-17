from __future__ import annotations

from pathlib import Path

from app.services import snapshot_export as se


def test_latest_snapshot_includes_msp_and_other(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "AI").mkdir()
    # 1С — самая новая календарная дата
    (web / "1с_10-08-2026_07-30_DK.json").write_text("{}", encoding="utf-8")
    (web / "1с_08-08-2026_07-30_DK.json").write_text("{}", encoding="utf-8")
    (web / "tessa_10-08-2026-00-00-rd.csv").write_text("a\n", encoding="utf-8")
    # MSP и other с другими датами — раньше выпадали из слепка
    (web / "AI" / "msp_esipovo5_11-08-2026.csv").write_text("project name\nЕсипово-5\n", encoding="utf-8")
    (web / "AI" / "msp_zhukovsky1_28-07-2026.csv").write_text("project name\nЖуковский\n", encoding="utf-8")
    (web / "AI" / "other_05-08-2026_07-00_resursi.csv").write_text("a\n", encoding="utf-8")
    (web / "AI" / "other_esipovo5_03.08.2026_rd.csv").write_text("a\n", encoding="utf-8")
    (web / "old.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(se, "WEB_DATA_DIR", web)
    monkeypatch.setattr(se, "_EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(se, "_LATEST_LINK", tmp_path / "exports" / "latest_snapshot.tar.gz")
    monkeypatch.setattr(se, "_LATEST_META", tmp_path / "exports" / "latest_snapshot.json")

    built = se.build_latest_snapshot_archive(force=True)
    assert built["ok"] is True
    assert built["mode"] == "dashboard_latest_per_family"
    names = {Path(p).name for p in built["files"]}
    assert "msp_esipovo5_11-08-2026.csv" in names
    assert "msp_zhukovsky1_28-07-2026.csv" in names
    assert "other_05-08-2026_07-00_resursi.csv" in names
    assert "other_esipovo5_03.08.2026_rd.csv" in names
    assert "1с_10-08-2026_07-30_DK.json" in names
    # старый 1С того же семейства не нужен
    assert "1с_08-08-2026_07-30_DK.json" not in names
    assert built["family_counts"]["msp"] >= 2
    assert built["family_counts"]["other_resursi"] >= 1
    assert se.latest_archive_path() is not None
    assert se.latest_archive_path().stat().st_size > 0


def test_dotted_rd_dates_recognized_in_web_loader():
    from web_loader import _max_date_in_stem, _generic_stem_family

    d = _max_date_in_stem("other_esipovo5_03.08.2026_rd")
    assert d is not None
    assert (d.year, d.month, d.day) == (2026, 8, 3)
    fam = _generic_stem_family("other_esipovo5_03.08.2026_rd")
    assert "03.08.2026" not in fam
    assert "*" in fam
