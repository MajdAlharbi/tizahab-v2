"""
core/middleware.py
==================
Lightweight middleware for security and SEO hardening.
"""

# Paths whose responses should never be indexed by search engines.
# These are the authenticated dashboard routes served as TemplateViews.
_NOINDEX_PREFIXES = (
    "/home/",
    "/dashboard/",
    "/daily-plan/",
    "/events/page/",
    "/map/",
    "/profile/",
    "/settings/",
    "/admin-panel/",
    "/onboarding/",
    "/api/",
)


class NoIndexMiddleware:
    """
    Adds ``X-Robots-Tag: noindex, nofollow`` to responses for all
    authenticated dashboard and API paths.

    This reinforces the <meta name="robots"> tag already present in
    dashboard_base.html and covers API endpoints that return JSON
    (which don't have HTML meta tags).

    Note: server-side authentication is handled by JWT in localStorage —
    this middleware does not redirect unauthenticated users (that is done
    by the JS layer) but does prevent search engines from crawling these
    pages regardless of authentication state.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(_NOINDEX_PREFIXES):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
