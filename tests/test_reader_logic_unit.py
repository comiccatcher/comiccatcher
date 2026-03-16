from ui.reader_logic import (
    ReaderSession,
    clamp_index,
    index_from_progression,
    make_data_url,
    parse_reading_order,
    resolve_href,
)


def test_parse_reading_order_basic():
    manifest = {"readingOrder": [{"href": "/a.jpg"}, {"href": "/b.jpg", "type": "image/webp"}]}
    ro = parse_reading_order(manifest)
    assert isinstance(ro, list)
    assert len(ro) == 2
    assert ro[0]["href"] == "/a.jpg"


def test_parse_reading_order_ignores_invalid_entries():
    manifest = {"readingOrder": [{"nope": 1}, "x", None, {"href": "/ok.jpg"}]}
    ro = parse_reading_order(manifest)
    assert [x["href"] for x in ro] == ["/ok.jpg"]


def test_resolve_href_absolute_passthrough():
    assert (
        resolve_href("https://example.com/base", "https://cdn.example.com/a.jpg")
        == "https://cdn.example.com/a.jpg"
    )


def test_resolve_href_relative():
    assert resolve_href("https://example.com/base", "/x/y.jpg") == "https://example.com/x/y.jpg"


def test_make_data_url_shape():
    assert make_data_url("image/jpeg", "abc") == "data:image/jpeg;base64,abc"


def test_clamp_index_edges():
    assert clamp_index(-1, 10) == 0
    assert clamp_index(0, 10) == 0
    assert clamp_index(9, 10) == 9
    assert clamp_index(10, 10) == 9
    assert clamp_index(123, 0) == 0


def test_index_from_progression_matches_app_behavior():
    # int(0.0 * 10) = 0
    assert index_from_progression(0.0, 10) == 0
    # int(0.5 * 10) = 5
    assert index_from_progression(0.5, 10) == 5
    # int(0.999 * 10) = 9
    assert index_from_progression(0.999, 10) == 9
    # int(1.0 * 10) = 10 -> clamped to 9
    assert index_from_progression(1.0, 10) == 9


def test_reader_session_page_turns_are_bounded():
    ro = [{"href": f"/p/{i}.jpg"} for i in range(3)]
    s = ReaderSession(base_url="https://example.com/base", reading_order=ro)

    assert s.total == 3
    assert s.index == 0
    assert s.current_url() == "https://example.com/p/0.jpg"

    s.prev()
    assert s.index == 0  # bounded

    s.next()
    assert s.index == 1
    s.next()
    assert s.index == 2
    s.next()
    assert s.index == 2  # bounded


def test_reader_session_jump_and_progression():
    ro = [{"href": f"/p/{i}.jpg"} for i in range(10)]
    s = ReaderSession(base_url="https://example.com/base", reading_order=ro)

    s.jump(7)
    assert s.index == 7
    s.jump(999)
    assert s.index == 9
    s.jump(-123)
    assert s.index == 0

    s.set_progression(0.5)
    assert s.index == 5
    s.set_progression(1.0)
    assert s.index == 9


def test_reader_session_fuzz_inputs_do_not_break_state():
    import random

    ro = [{"href": f"/p/{i}.jpg"} for i in range(25)]
    s = ReaderSession(base_url="https://example.com/base", reading_order=ro)

    rng = random.Random(1337)
    for _ in range(5000):
        op = rng.choice(["next", "prev", "jump"])
        if op == "next":
            s.next()
        elif op == "prev":
            s.prev()
        else:
            s.jump(rng.randint(-100, 200))

        assert 0 <= s.index <= (s.total - 1)
