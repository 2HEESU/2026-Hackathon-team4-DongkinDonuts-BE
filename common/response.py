from rest_framework.response import Response


def success_response(data=None, message=None, status=200):
    """
    성공 응답 공통 포맷. EnvelopeMixin을 쓰는 view라면 이걸 직접 안 불러도
    자동으로 같은 모양으로 감싸지지만, 커스텀 액션(예: cancel/, click/)에서
    바로 원하는 모양을 만들고 싶을 때 사용한다.
    """
    return Response({"success": True, "data": data, "message": message}, status=status)


def error_response(message, code="error", status=400, details=None):
    """에러 응답 공통 포맷. 대부분의 에러는 custom_exception_handler가 자동 처리하므로,
    view 안에서 예외 없이 바로 에러를 반환하고 싶은 특수한 경우에만 직접 사용한다."""
    return Response(
        {"success": False, "error": {"code": code, "message": message, "details": details}},
        status=status,
    )
