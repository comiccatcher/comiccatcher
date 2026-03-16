import zipfile
from pathlib import Path

from ui.local_archive import list_cbz_pages, read_cbz_entry_bytes


def test_list_cbz_pages_sorts_and_filters(tmp_path: Path):
    cbz = tmp_path / "a.cbz"
    with zipfile.ZipFile(cbz, "w") as z:
        z.writestr("ComicInfo.xml", "<x/>")
        z.writestr("img/002.jpg", b"b")
        z.writestr("img/001.jpg", b"a")
        z.writestr("note.txt", b"x")

    pages = list_cbz_pages(cbz)
    assert [p.name for p in pages] == ["img/001.jpg", "img/002.jpg"]
    assert pages[0].index == 0
    assert pages[1].index == 1

    assert read_cbz_entry_bytes(cbz, "img/001.jpg") == b"a"

