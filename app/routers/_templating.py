"""
Jinja templating with Flask-compatible helpers.

The templates were written for Flask and use:
- url_for('blueprint.endpoint', **kwargs)  -> path, extra kwargs as query string
- url_for('static', filename=...)          -> /static/<filename>
- request.endpoint                          -> active-nav highlighting

FastAPI routes are registered with name= set to the original Flask endpoint
name (dots are legal in Starlette route names), so both helpers resolve to
byte-identical URLs and no template needs editing.
"""

import os
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

templates = Jinja2Templates(directory=_TEMPLATE_DIR)

_app = None  # set by init_templating()


def init_templating(app):
    global _app
    _app = app
    templates.env.globals["url_for"] = flask_url_for


def _route_by_name(endpoint):
    for route in _app.routes:
        if getattr(route, "name", None) == endpoint:
            return route
    raise KeyError("url_for: no route named %r" % endpoint)


def flask_url_for(endpoint, **values):
    """Flask-compatible url_for: path params fill the path, the rest become
    the query string. Returns a path-only URL, like Flask's default."""
    if endpoint == "static":
        return "/static/" + values["filename"]
    route = _route_by_name(endpoint)
    param_names = getattr(route, "param_convertors", {}).keys()
    path_params = {k: values.pop(k) for k in list(values) if k in param_names}
    path = _app.url_path_for(endpoint, **path_params)
    if values:
        path = path + "?" + urlencode(values)
    return str(path)


def render(request, template_name, status_code=200, **context):
    """render_template() equivalent; also exposes request.endpoint to Jinja."""
    route = request.scope.get("route")
    request.endpoint = getattr(route, "name", None)
    return templates.TemplateResponse(
        request, template_name, context, status_code=status_code
    )
