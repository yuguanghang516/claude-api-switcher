"""SSE relay with bounded parsing, truthful completion state and usage totals."""
import codecs
import json
import requests


def token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def usage_counts(usage, protocol="openai"):
    usage = usage if isinstance(usage, dict) else {}
    source, output = (("input_tokens", "output_tokens") if protocol == "anthropic"
                      else ("prompt_tokens", "completion_tokens"))
    incoming, outgoing = token_count(usage.get(source)), token_count(usage.get(output))
    return incoming, outgoing, max(incoming + outgoing, token_count(usage.get("total_tokens")))


def _frames(response):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending, lines = "", []
    size = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        pending += decoder.decode(chunk)
        if len(pending) + size > 2 * 1024 * 1024:
            raise ValueError("SSE event too large")
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                if lines:
                    yield lines
                lines, size = [], 0
            else:
                lines.append(line)
                size += len(line)
    decoder.decode(b"", final=True)
    # An unterminated event is not a completed message.
    if pending or lines:
        raise ValueError("Incomplete SSE event")


def relay_sse(response, protocol, completed):
    incoming = outgoing = total = 0
    status, error = "error", "流式连接提前结束；未收到完成事件"
    try:
        for lines in _frames(response):
            data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
            event = next((line[6:].strip() for line in lines if line.startswith("event:")), "")
            if event == "error":
                raise ValueError("Upstream SSE error")
            if data == "[DONE]" and protocol == "openai":
                status, error = "success", ""
                yield "data: [DONE]\n\n"
                return
            if data:
                parsed = json.loads(data)
                if not isinstance(parsed, dict) or parsed.get("error") or parsed.get("type") == "error":
                    raise ValueError("Invalid SSE data")
                usage = parsed.get("usage")
                if protocol == "anthropic" and parsed.get("type") == "message_start":
                    message = parsed.get("message", {})
                    usage = message.get("usage") if isinstance(message, dict) else None
                if isinstance(usage, dict):
                    new_input, new_output, new_total = usage_counts(usage, protocol)
                    incoming = max(incoming, new_input)
                    outgoing = max(outgoing, new_output)
                    total = max(total, new_total, incoming + outgoing)
                if protocol == "anthropic" and parsed.get("type") == "message_stop":
                    status, error = "success", ""
                    yield "\n".join(lines) + "\n\n"
                    return
            yield "\n".join(lines) + "\n\n"
        raise ValueError("Incomplete stream")
    except GeneratorExit:
        if status != "success":
            status, error = "error", "客户端在流式响应完成前断开连接"
        raise
    except (requests.RequestException, ValueError, UnicodeError):
        # Upstream exceptions/bodies may contain credentials; never echo them.
        status, error = "error", "上游流式响应中断或格式错误，请检查服务后重试"
        body = json.dumps({"type": "error", "error": {
            "type": "upstream_error", "message": error}}, ensure_ascii=False)
        yield f"event: error\ndata: {body}\n\n"
    finally:
        response.close()
        completed(incoming, outgoing, total, status, error)
