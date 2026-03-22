from ui.local_comicbox import generate_comic_labels

def test_generate_comic_labels_series_focus():
    meta = {
        "series": "Watchmen",
        "volume": "1986",
        "issue": "3",
        "title": "The Judge of All the Earth"
    }
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "Watchmen (1986) #3"
    assert secondary == "The Judge of All the Earth"

def test_generate_comic_labels_title_focus():
    meta = {
        "series": "Watchmen",
        "volume": "1986",
        "issue": "3",
        "title": "The Judge of All the Earth"
    }
    primary, secondary = generate_comic_labels(meta, "title")
    assert primary == "The Judge of All the Earth"
    assert secondary == "Watchmen (1986) #3"

def test_generate_comic_labels_volume_v():
    meta = {
        "series": "Avengers",
        "volume": "2",
        "issue": "1",
        "title": "Once an Avenger"
    }
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "Avengers v2 #1"
    assert secondary == "Once an Avenger"

def test_generate_comic_labels_no_title_fallback():
    meta = {
        "series": "Batman",
        "volume": "1",
        "issue": "1",
        "title": ""
    }
    # Even in title focus, if title is missing it should fallback to series info
    primary, secondary = generate_comic_labels(meta, "title")
    assert primary == "Batman v1 #1"
    assert secondary == ""

def test_generate_comic_labels_year_fallback():
    meta = {
        "series": "X-Men",
        "year": "1963",
        "issue": "1"
    }
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "X-Men (1963) #1"

def test_generate_comic_labels_no_series():
    meta = {
        "title": "Lone Story"
    }
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "Lone Story"
    assert secondary == ""

def test_generate_comic_labels_empty():
    meta = {}
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "Unknown Comic"
    assert secondary == ""

def test_generate_comic_labels_redundant_secondary():
    meta = {
        "series": "Batman",
        "title": "Batman",
        "issue": "1"
    }
    # In series focus, primary is "Batman #1". 
    # Secondary would be "Batman", which is redundant.
    primary, secondary = generate_comic_labels(meta, "series")
    assert primary == "Batman #1"
    assert secondary == ""
