import contextvars
import re
import uuid

_request_id = contextvars.ContextVar('request_id', default=None)
_VALID_ID = re.compile(r'^[A-Za-z0-9-]{8,64}$')


def get_request_id():
    return _request_id.get()


class RequestIdMiddleware:
    """Propagates X-Request-ID so API logs can be correlated with proxy logs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get('X-Request-ID', '')
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response['X-Request-ID'] = request_id
        return response
