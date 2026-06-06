import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
INSTALL_PATH = ROOT / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("archivum_install", INSTALL_PATH)
install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(install)


def complete_env_values() -> dict[str, str]:
    values = install.DEFAULTS.copy()
    values.update(
        {
            "ANTHROPIC_API_KEY": "sk-ant-existing",
            "JWT_SECRET": "jwt-secret-existing",
            "OWNER_PASSWORD": "owner-password-existing",
            "MCP_API_KEY": "mcp-key-existing",
            "LLM_EXTRACTION_PROVIDER": "anthropic",
            "LLM_SYNTHESIS_PROVIDER": "anthropic",
            "LLM_MODEL": "claude-haiku-4-5-20251001",
            "LLM_SYNTHESIS_MODEL": "claude-sonnet-4-6",
            "EMBED_PROVIDER": "local",
            "EMBED_MODEL": "BAAI/bge-small-en-v1.5",
            "EMBED_DIM": "0",
        }
    )
    return values


class InstallerEnvTests(unittest.TestCase):
    def test_complete_env_does_not_need_configuration(self) -> None:
        self.assertFalse(install.env_needs_configuration(complete_env_values()))

    def test_missing_provider_api_key_needs_configuration(self) -> None:
        values = complete_env_values()
        values["ANTHROPIC_API_KEY"] = ""

        self.assertTrue(install.env_needs_configuration(values))

    def test_openrouter_env_with_shell_spacing_does_not_need_configuration(self) -> None:
        parsed = install.parse_env(
            """
            export OPENROUTER_API_KEY = sk-or-existing
            OPENROUTER_BASE_URL = https://openrouter.ai/api/v1
            JWT_SECRET = jwt-secret-existing
            OWNER_PASSWORD = owner-password-existing
            MCP_API_KEY = mcp-key-existing
            LLM_EXTRACTION_PROVIDER = openrouter
            LLM_SYNTHESIS_PROVIDER = openrouter
            LLM_MODEL = openrouter/auto
            LLM_SYNTHESIS_MODEL = openrouter/auto
            EMBED_PROVIDER = local
            EMBED_MODEL = BAAI/bge-small-en-v1.5
            EMBED_DIM = 0
            """
        )
        values = install.DEFAULTS.copy()
        values.update(parsed)

        self.assertFalse(install.env_needs_configuration(values))

    def test_write_env_never_wipes_existing_api_key_with_blank_value(self) -> None:
        env_path = ROOT / ".context" / "test-install.env"
        original_env_file = install.ENV_FILE
        env_path.write_text("OPENROUTER_API_KEY=sk-or-existing\n", encoding="utf-8")
        self.addCleanup(lambda: env_path.unlink(missing_ok=True))

        try:
            install.ENV_FILE = env_path
            install.write_env({"OPENROUTER_API_KEY": ""})
        finally:
            install.ENV_FILE = original_env_file

        self.assertIn("OPENROUTER_API_KEY=sk-or-existing\n", env_path.read_text(encoding="utf-8"))

    def test_write_env_never_appends_blank_duplicate_for_exported_api_key(self) -> None:
        env_path = ROOT / ".context" / "test-install-export.env"
        original_env_file = install.ENV_FILE
        env_path.write_text("export OPENROUTER_API_KEY=sk-or-existing\n", encoding="utf-8")
        self.addCleanup(lambda: env_path.unlink(missing_ok=True))

        try:
            install.ENV_FILE = env_path
            install.write_env({"OPENROUTER_API_KEY": ""})
        finally:
            install.ENV_FILE = original_env_file

        text = env_path.read_text(encoding="utf-8")
        self.assertIn("export OPENROUTER_API_KEY=sk-or-existing\n", text)
        self.assertNotIn("OPENROUTER_API_KEY=\n", text)

    def test_secret_default_preserves_existing_api_keys(self) -> None:
        self.assertEqual(install.secret_default("sk-ant-existing"), "sk-ant-existing")

    def test_secret_default_rejects_placeholder_api_keys(self) -> None:
        self.assertEqual(install.secret_default("sk-ant-..."), "")

    def test_main_skips_configuration_when_existing_env_is_kept_but_starts_stack(self) -> None:
        values = complete_env_values()

        with patch.object(install, "pause"), patch.object(install, "ensure_docker", return_value=["docker", "compose"]), patch.object(
            install, "read_env", return_value=values
        ), patch.object(install, "env_needs_configuration", return_value=False), patch.object(
            install, "ask_bool", side_effect=[False, True]
        ) as ask_bool, patch.object(
            install, "configure_access"
        ) as configure_access, patch.object(
            install, "configure_llms"
        ) as configure_llms, patch.object(
            install, "configure_embeddings"
        ) as configure_embeddings, patch.object(
            install, "summary"
        ) as summary, patch.object(
            install, "write_env"
        ) as write_env, patch.object(
            install, "start_stack", return_value=True
        ) as start_stack, patch.object(
            install, "print_finish"
        ):
            self.assertEqual(install.main([]), 0)

        configure_access.assert_not_called()
        configure_llms.assert_not_called()
        configure_embeddings.assert_not_called()
        summary.assert_not_called()
        write_env.assert_not_called()
        start_stack.assert_called_once_with(["docker", "compose"], use_images=True)
        self.assertEqual(ask_bool.call_args_list[0].args[0], "Reconfigure existing .env?")
        self.assertEqual(ask_bool.call_args_list[1].args[0], "Start Archivum now?")


if __name__ == "__main__":
    unittest.main()
