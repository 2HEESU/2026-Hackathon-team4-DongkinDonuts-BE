from rest_framework.exceptions import APIException

class Conflict(APIException):
    status_code = 409
    default_detail = "현재 상태에서는 요청을 처리할 수 없습니다."
    default_code = "conflict"