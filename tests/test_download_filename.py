from api.download_manager import (
    _filename_from_content_disposition,
    _filename_from_url,
    _iterative_unquote_plus,
    _sanitize_filename,
)


def test_iterative_unquote_plus_double_encoded_leaf():
    leaf = "Swamp+Thing+%2523057+%25281987%2529.cbz"
    assert _iterative_unquote_plus(leaf) == "Swamp Thing #057 (1987).cbz"


def test_filename_from_url_decodes_double_encoding():
    url = "https://anville.duckdns.org:2700/codex/opds/bin/c/16107/download/Swamp+Thing+%2523057+%25281987%2529.cbz"
    assert _filename_from_url(url) == "Swamp Thing #057 (1987).cbz"


def test_content_disposition_filename_star():
    cd = "attachment; filename*=UTF-8''Swamp%20Thing%20%23057%20%281987%29.cbz"
    assert _filename_from_content_disposition(cd) == "Swamp Thing #057 (1987).cbz"


def test_sanitize_filename_keeps_hash_and_parens():
    assert _sanitize_filename("Swamp Thing #057 (1987).cbz") == "Swamp Thing #057 (1987).cbz"

