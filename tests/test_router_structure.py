from backend.app.routers import admin, audit, auth, bank_ai, dashboard, definitions, epos, health, jobs, modules, settings


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


def test_reconciliation_definition_routes_are_registered():
    assert {
        "/api/reconciliation-definitions",
        "/api/reconciliation-definitions/{definition_id}",
        "/api/reconciliation-definitions/{definition_id}/versions",
        "/api/reconciliation-definitions/{definition_id}/versions/{version_id}",
        "/api/reconciliation-definitions/{definition_id}/versions/{version_id}/restore",
    }.issubset(_paths(definitions.router))


def test_background_job_routes_are_registered():
    assert {
        "/api/jobs/{module_id}",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/cancel",
    }.issubset(_paths(jobs.router))


def test_dashboard_route_is_registered():
    assert "/api/dashboard" in _paths(dashboard.router)


def test_bank_ai_summary_route_is_registered():
    assert "/api/modules/bank_rrn/ai/summary" in _paths(bank_ai.router)
