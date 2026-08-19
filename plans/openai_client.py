import json
from urllib import error, request

from django.conf import settings
from rest_framework.exceptions import APIException


class OpenAIConfigurationError(APIException):
    status_code = 503
    default_code = "openai_configuration_error"
    default_detail = "OPEN_AI_API_KEY 환경변수가 설정되어 있지 않습니다."


class OpenAIClientError(APIException):
    status_code = 502
    default_code = "openai_client_error"
    default_detail = "OpenAI API 호출에 실패했습니다."


def _extract_output_text(response_json):
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks = []
    for output_item in response_json.get("output", []):
        for content in output_item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
            parsed = content.get("parsed")
            if parsed is not None:
                return json.dumps(parsed, ensure_ascii=False)
    return "\n".join(chunks).strip()


def create_structured_response(*, input_messages, schema, model=None):
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise OpenAIConfigurationError()

    payload = {
        "model": model or settings.OPENAI_MODEL,
        "input": input_messages,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "description": schema.get("description", ""),
                "strict": True,
                "schema": schema["schema"],
            }
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    api_request = request.Request(
        f"{settings.OPENAI_BASE_URL.rstrip('/')}/responses",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(api_request, timeout=settings.OPENAI_TIMEOUT_SECONDS) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenAIClientError(f"OpenAI API 오류({exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise OpenAIClientError(f"OpenAI API 연결 실패: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OpenAIClientError("OpenAI API 응답을 JSON으로 해석할 수 없습니다.") from exc

    output_text = _extract_output_text(response_json)
    if not output_text:
        raise OpenAIClientError("OpenAI API 응답에 출력 텍스트가 없습니다.")

    try:
        return json.loads(output_text), response_json
    except json.JSONDecodeError as exc:
        raise OpenAIClientError("OpenAI API 구조화 출력이 유효한 JSON이 아닙니다.") from exc
