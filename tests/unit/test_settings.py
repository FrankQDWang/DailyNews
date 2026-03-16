from typing import cast

from libs.core.settings import Settings


def _base_env() -> dict[str, str]:
    return {
        'ASSISTANT_DB_URL': 'postgresql+asyncpg://u:p@localhost:5432/db',
        'TEMPORAL_HOST': 'localhost:7233',
        'DEEPSEEK_API_KEY': 'x',
        'MINIFLUX_BASE_URL': 'http://localhost:8080',
        'MINIFLUX_API_TOKEN': 'x',
        'TELEGRAM_BOT_TOKEN': 'x',
        'TELEGRAM_WEBHOOK_SECRET': 'secret',
        'TELEGRAM_TARGET_CHAT_ID': '-10001',
        'TELEGRAM_ADMIN_USER_IDS': '1,2,3',
        'INTERNAL_API_TOKEN': 'internal',
    }


def test_settings_admin_id_parse() -> None:
    settings = Settings.model_validate(_base_env())
    assert settings.telegram_admin_user_ids == [1, 2, 3]
    assert settings.telegram_target_chat_id == -10001
    assert settings.assistant_db_async_url == 'postgresql+asyncpg://u:p@localhost:5432/db'
    assert settings.assistant_db_sync_url == 'postgresql://u:p@localhost:5432/db'


def test_settings_postgres_scheme_normalization() -> None:
    env = _base_env()
    env['ASSISTANT_DB_URL'] = 'postgresql://u:p@db.internal:5432/railway?sslmode=disable'
    settings = Settings.model_validate(env)
    assert settings.assistant_db_async_url == 'postgresql+asyncpg://u:p@db.internal:5432/railway?sslmode=disable'
    assert settings.assistant_db_sync_url == 'postgresql://u:p@db.internal:5432/railway?sslmode=disable'


def test_settings_admin_id_parse_from_int() -> None:
    env = cast(dict[str, object], _base_env())
    env['TELEGRAM_ADMIN_USER_IDS'] = 7
    settings = Settings.model_validate(env)
    assert settings.telegram_admin_user_ids == [7]
