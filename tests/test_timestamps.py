from archivum.timestamps import normalise_timestamp


def test_sqlite_default_format_sorts_with_application_writes():
    # The bug this guards: compared as raw strings, the space-separated SQLite
    # default sorts before every 'T'-separated ISO write regardless of time.
    sqlite_default = "2026-08-19 09:00:00"
    application_write = "2026-08-19T08:13:45.541209+00:00"

    assert sqlite_default < application_write  # wrong, and why we normalise
    assert normalise_timestamp(sqlite_default) > normalise_timestamp(application_write)


def test_naive_values_are_treated_as_utc():
    assert normalise_timestamp("2026-08-19 09:00:00") == "2026-08-19T09:00:00+00:00"


def test_offsets_are_converted_to_utc():
    assert normalise_timestamp("2026-08-19T10:00:00+02:00") == "2026-08-19T08:00:00+00:00"


def test_zulu_suffix_is_accepted():
    assert normalise_timestamp("2026-08-19T09:00:00Z") == "2026-08-19T09:00:00+00:00"


def test_empty_and_unparseable_values_are_safe():
    assert normalise_timestamp(None) == ""
    assert normalise_timestamp("") == ""
    assert normalise_timestamp("   ") == ""
    # Unparseable input is passed through rather than dropped, so a bad row is
    # visible in the feed instead of silently vanishing.
    assert normalise_timestamp("not a date") == "not a date"
