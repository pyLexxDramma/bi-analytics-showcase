from __future__ import annotations

from pathlib import Path

from app.services import snapshot_export as se


def test_latest_snapshot_date_picks_newest(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "1с_07-08-2026_07-30_DK.json").write_text("{}", encoding="utf-8")
    (web / "1с_08-08-2026_07-30_DK.json").write_text("{}", encoding="utf-8")
    (web / "tessa_08-08-2026-00-00-rd.csv").write_text("a\n", encoding="utf-8")
    (web / "old.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(se, "WEB_DATA_DIR", web)
    monkeypatch.setattr(se, "_EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(se, "_LATEST_LINK", tmp_path / "exports" / "latest_snapshot.tar.gz")
    monkeypatch.setattr(se, "_LATEST_META", tmp_path / "exports" / "latest_snapshot.json")

    assert se.latest_snapshot_date() == "08-08-2026"
    built = se.build_latest_snapshot_archive(force=True)
    assert built["ok"] is True
    assert built["snapshot_date"] == "08-08-2026"
    assert built["files_count"] == 2
    assert se.latest_archive_path() is not None
    assert se.latest_archive_path().stat().st_size > 0
