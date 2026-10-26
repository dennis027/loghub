import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ProviderUnavailable(APIException):
    """An integrated backend (Elasticsearch, Graylog, ...) could not serve the request."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = 'provider_unavailable'
    default_detail = 'The log backend is temporarily unavailable.'


class InvalidQuery(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'invalid_query'
    default_detail = 'The search query is invalid.'


def api_exception_handler(exc, context):
    """Consistent envelope: {"error": {"code", "message", "details"}}."""
    response = exception_handler(exc, context)
    if response is None:
        logger.exception('Unhandled API error', extra={'view': context['view'].__class__.__name__})
        return Response(
            {'error': {'code': 'server_error', 'message': 'Internal server error.', 'details': None}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    code = getattr(exc, 'default_code', 'error')
    if hasattr(exc, 'get_codes'):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes
    if isinstance(data, dict) and set(data) == {'detail'}:
        message, details = str(data['detail']), None
    else:
        message, details = 'Validation failed.' if response.status_code == 400 else str(exc), data
        if response.status_code == 400:
            code = 'validation_error'
    response.data = {'error': {'code': code, 'message': message, 'details': details}}
    return response
