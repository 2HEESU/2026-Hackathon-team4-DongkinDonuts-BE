from rest_framework.response import Response


class EnvelopeMixin:
    """
    모든 CBV가 상속받는 공통 믹스인. 성공 응답(2xx/3xx)을
    {"success": true, "data": ..., "message": null} 형태로 자동으로 감싼다.
    에러 응답은 common.exceptions.custom_exception_handler가 전역으로 처리하므로
    여기서는 신경 쓰지 않는다.

    사용법: view 정의할 때 DRF generic view보다 먼저 상속하면 된다.
        class DailyContextListView(EnvelopeMixin, generics.ListCreateAPIView):
            ...

    이미 success_response()로 직접 감싼 응답(커스텀 액션 등)은 중복으로 안 감싼다.
    """

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        # 204는 HTTP 스펙상 몸통이 없어야 하는 응답이라 감싸지 않는다. runserver(wsgiref)는
        # 몸통을 자동으로 안 지워주는 걸 확인했기 때문에, 여기서 직접 비워서 확실히 보장한다.
        if response.status_code == 204:
            response.data = None
            return response
        if isinstance(response, Response) and response.status_code < 400:
            data = response.data
            already_wrapped = isinstance(data, dict) and "success" in data
            if not already_wrapped:
                response.data = {"success": True, "data": data, "message": None}
        return response
