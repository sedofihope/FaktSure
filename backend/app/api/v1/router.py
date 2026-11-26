from fastapi import APIRouter

from app.api.v1.endpoints import audit, auth, batches, clients, documents, invoices, products, references, settings, users

router = APIRouter(prefix="/api")
router.include_router(auth.router)
router.include_router(batches.router)
router.include_router(clients.router)
router.include_router(products.router)
router.include_router(references.router)
router.include_router(documents.router)
router.include_router(invoices.router)
router.include_router(audit.router)
router.include_router(users.router)
router.include_router(settings.router)
