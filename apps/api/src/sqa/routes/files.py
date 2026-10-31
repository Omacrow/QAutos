"""Download endpoint for LocalStore (development). S3/R2 serves its own signed URLs."""

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from sqa.storage import LocalStore, content_disposition

router = APIRouter(prefix="/v1/files", tags=["files"], include_in_schema=False)


@router.get("/{token}")
async def download_file(token: str, request: Request) -> FileResponse:
    store = request.app.state.store
    if not isinstance(store, LocalStore):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        path, filename, content_type = store.resolve_token(token)
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link invalid or expired") from None
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return FileResponse(
        path,
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition(filename or path.name),
            "Cache-Control": "private, no-store",
        },
    )
