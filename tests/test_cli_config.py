from pathlib import Path

from archivum import cli_config


def test_parse_env_kv_ignores_comments_and_invalid_lines():
    result = cli_config._parse_env_kv(
        [
            "# comment\n",
            "JWT_SECRET=abc\n",
            "OWNER_PASSWORD = spaced-out\n",
            "OPENROUTER_API_KEY=key=value\n",
            "not valid\n",
        ]
    )

    assert result == {
        "JWT_SECRET": "abc",
        "OPENROUTER_API_KEY": "key=value",
    }


def test_set_env_var_replaces_existing_key_once():
    lines = ["JWT_SECRET=old\n", "OWNER_PASSWORD=keep\n"]

    assert cli_config._set_env_var(lines, "JWT_SECRET", "new") == [
        "JWT_SECRET=new\n",
        "OWNER_PASSWORD=keep\n",
    ]


def test_set_env_var_appends_with_missing_trailing_newline():
    lines = ["JWT_SECRET=old"]

    assert cli_config._set_env_var(lines, "OWNER_PASSWORD", "new") == [
        "JWT_SECRET=old\n",
        "OWNER_PASSWORD=new\n",
    ]


def test_find_env_file_searches_up_from_start_path(tmp_path):
    root = tmp_path / "repo"
    nested = root / "apps" / "backend" / "archivum"
    nested.mkdir(parents=True)
    env_file = root / ".env"
    env_file.write_text("JWT_SECRET=abc\n", encoding="utf-8")

    assert cli_config._find_env_file(nested) == env_file


def test_find_env_file_returns_none_when_missing(tmp_path):
    assert cli_config._find_env_file(Path(tmp_path / "empty")) is None


def test_mask_secret_keeps_short_and_long_values_readable():
    assert cli_config._mask_secret("") == "<empty>"
    assert cli_config._mask_secret("short") == "sh...rt"
    assert cli_config._mask_secret("abcdefghijklmnopqrstuvwxyz") == "abcdef...wxyz"
