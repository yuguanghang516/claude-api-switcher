"""Validate gateway request types before routing or making network requests."""


def request_error(payload):
    if not isinstance(payload, dict):
        return "JSON 请求必须是对象"
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        return "模型名称必须是非空文本"
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) for m in messages):
        return "messages 必须是非空的消息对象列表"
    if "stream" in payload and not isinstance(payload["stream"], bool):
        return "stream 必须是 true 或 false，不能使用字符串"
    if "max_tokens" in payload:
        value = payload["max_tokens"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return "max_tokens 必须是正整数"
    return ""
