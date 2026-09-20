from fastapi import APIRouter

from modules.registry import module_registry

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "platform": "ReconcileHub Modular Monolith",
        "active_modules_count": len(module_registry.list_manifests()),
        "version": "2.2.0",
    }
