from backend.app.routers import admin, audit, auth, epos, health, modules, settings


def _paths(router):
    return {route.path for route in router.routes}


def test_backend_routes_keep_public_api_paths_after_split():
    assert "/api/health" in _paths(health.router)

    assert {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
    }.issubset(_paths(auth.router))

    assert {
        "/api/modules",
        "/api/modules/{module_id}/run",
        "/api/modules/{module_id}/archive",
        "/api/modules/{module_id}/archive/{record_id}",
        "/api/modules/{module_id}/analytics",
    }.issubset(_paths(modules.router))

    assert {
        "/api/epos",
        "/api/epos/{terminal_id}",
        "/api/banks",
    }.issubset(_paths(epos.router))

    assert "/api/settings" in _paths(settings.router)
    assert "/api/admin/users" in _paths(admin.router)
    assert "/api/admin/permissions" in _paths(admin.router)
    assert "/api/audit" in _paths(audit.router)
    assert "/api/audit/filters" in _paths(audit.router)
