import threading

_thread_locals = threading.local()


def get_current_ip():
    return getattr(_thread_locals, 'ip_address', None)


class AuditMiddleware:
    """Middleware to stash the client IP address in thread local storage.

    Signals can then call :func:`get_current_ip` to include the IP in the
    audit record even though they don't receive the request object.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # store remote address; fall back to X-Forwarded-For if behind proxy
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        _thread_locals.ip_address = ip
        response = self.get_response(request)
        return response
