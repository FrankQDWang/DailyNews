from libs.integrations.telegram_client import split_message


def test_split_message_short() -> None:
    msg = 'hello world'
    chunks = split_message(msg, chunk_size=20)
    assert chunks == [msg]


def test_split_message_long() -> None:
    msg = '\n'.join([f'line-{idx}' for idx in range(100)])
    chunks = split_message(msg, chunk_size=80)
    assert len(chunks) > 1
    assert ''.join(chunks).replace('\n', '') != ''
