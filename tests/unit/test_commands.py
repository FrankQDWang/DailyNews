from libs.core.schemas.commands import parse_command


def test_parse_command_with_arg() -> None:
    parsed = parse_command('/ask 最近一周 agents 趋势')
    assert parsed is not None
    assert parsed.name == 'ask'
    assert parsed.arg == '最近一周 agents 趋势'


def test_parse_command_with_bot_suffix() -> None:
    parsed = parse_command('/top@DailyNewsBot 24h')
    assert parsed is not None
    assert parsed.name == 'top'
    assert parsed.arg == '24h'


def test_parse_command_non_command() -> None:
    assert parse_command('hello') is None
