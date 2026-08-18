from rest_framework.views import exception_handler as drf_default_exception_handler


def custom_exception_handler(exc, context):
    """
    DRF가 처리하는 모든 예외(ValidationError, NotFound, AuthenticationFailed 등)를
    success_response/error_response와 같은 모양으로 통일해서 감싼다.
    settings.REST_FRAMEWORK["EXCEPTION_HANDLER"]에 등록해서 전역으로 적용됨 —
    각 view에서 따로 try/except 안 해도 된다.
    """
    response = drf_default_exception_handler(exc, context)
    if response is None:
        # DRF가 못 알아보는 예외(500 등)는 그대로 둔다 — Django의 기본 에러 처리에 맡김
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = detail["detail"]
        extra = {k: v for k, v in detail.items() if k != "detail"} or None
    else:
        message = detail
        extra = None

    response.data = {
        "success": False,
        "error": {
            "code": exc.__class__.__name__,
            "message": message,
            "details": extra,
        },
    }
    return response
