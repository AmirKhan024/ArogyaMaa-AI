"""
Central auth guard — FastAPI port of app/__init__.py::register_route_protection.

Same contract:
1. Dashboard HTML prefixes -> redirect to login (+ role check) if not authenticated.
2. JSON API prefixes -> 401 unless logged-in session OR valid X-Internal-Token.
Paths ending /health stay public.
"""

from starlette.responses import JSONResponse, RedirectResponse

from app.web_settings import settings

PROTECTED_PREFIXES = [
    '/admin/dashboard',
    '/asha/dashboard',
    '/doctor/dashboard',
    '/dashboard/shared',
]

ROLE_MAP = {
    '/admin/dashboard': 'admin',
    '/asha/dashboard': 'asha',
    '/doctor/dashboard': 'doctor',
}

# JSON API prefixes that must not be world-readable.
API_PROTECTED_PREFIXES = ('/admin', '/asha', '/doctor', '/api', '/ai')

LOGIN_URL = '/'  # Flask url_for('auth.login')


def _api_authorized(request):
    if request.session.get('logged_in'):
        return True
    token = request.headers.get('X-Internal-Token')
    internal = settings.INTERNAL_API_TOKEN
    return bool(token and internal and token == internal)


async def auth_guard(request, call_next):
    path = request.url.path

    # 1. Dashboard HTML routes -> redirect + role check
    for prefix in PROTECTED_PREFIXES:
        if path.startswith(prefix):
            if not request.session.get('logged_in'):
                return RedirectResponse(LOGIN_URL, status_code=302)
            required_role = ROLE_MAP.get(prefix)
            user_role = request.session.get('role')
            if prefix == '/dashboard/shared':
                if user_role not in ['asha', 'doctor']:
                    return RedirectResponse(LOGIN_URL, status_code=302)
            elif required_role and user_role != required_role:
                return RedirectResponse(LOGIN_URL, status_code=302)
            return await call_next(request)  # dashboard auth handled

    # 2. JSON API routes -> 401 unless session or internal token
    if path.startswith(API_PROTECTED_PREFIXES) and not path.endswith('/health'):
        if not _api_authorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    return await call_next(request)
