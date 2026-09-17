"""Validation and canonical routing for Anthropic-compatible providers."""
from urllib.parse import urlsplit, urlunsplit


def anthropic_base_url(value: str) -> str:
    """Accept a server root, /v1, or /v1/messages without duplicating paths.

    Do not accept credentials, query secrets, or fragments in an API address.
    Error messages deliberately do not include the supplied address.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError('API Base URL 不能为空')
    if any(ord(char) < 32 for char in value):
        raise ValueError('API 地址不能包含控制字符')
    value = value.strip()
    if any(char.isspace() for char in value) or '\\' in value:
        raise ValueError('API 地址不能包含空格或反斜杠')
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError('API 地址或端口格式无效') from None
    if (parsed.scheme not in {'http', 'https'} or not hostname
            or parsed.username is not None or parsed.password is not None
            or port == 0):
        raise ValueError('API 地址格式无效，请填写完整的 http/https 地址')
    if parsed.query or parsed.fragment:
        raise ValueError('API 地址不能包含查询参数或 # 片段；请将密钥填入 API Key')
    if parsed.scheme == 'http' and hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('远程 API 地址必须使用 HTTPS')
    path = parsed.path.rstrip('/')
    if path.endswith('/v1/messages'):
        path = path[:-len('/v1/messages')]
    elif path.endswith('/v1'):
        path = path[:-len('/v1')]
    return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))


def anthropic_messages_url(value: str) -> str:
    return anthropic_base_url(value) + '/v1/messages'
