from ui.local_comicbox import flatten_comicbox, subtitle_from_flat


def test_flatten_comicbox_nested_shape():
    raw = {
        "comicbox": {
            "title": "Mysteries in Space",
            "series": {"name": "Swamp Thing"},
            "issue": {"name": "57", "number": 57},
            "date": {"year": 1987},
            "publisher": {"name": "Vertigo"},
            "credits": {
                "Alan Moore": {"roles": {"Writer": {}}},
                "Rick Veitch": {"roles": {"Penciller": {}}},
            },
            "page_count": 25,
            "summary": "foo",
            "volume": {"number": 1986},
        }
    }

    flat = flatten_comicbox(raw)
    assert flat["title"] == "Mysteries in Space"
    assert flat["series"] == "Swamp Thing"
    assert str(flat["issue"]) == "57"
    assert flat["year"] == 1987
    assert flat["publisher"] == "Vertigo"
    assert flat["writer"] == "Alan Moore"
    assert flat["penciller"] == "Rick Veitch"
    assert flat["page_count"] == 25

    assert subtitle_from_flat(flat) == "Swamp Thing #57 (1987)"

