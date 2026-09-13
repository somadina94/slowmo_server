from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.core.deps import CurrentStaff, CurrentUser, DbDep, get_storage
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.rbac import has_permission
from app.integrations.storage import FileStorage, content_disposition
from app.models.consult import RxFile
from fastapi import Depends

router = APIRouter(tags=["files"])


@router.post("/files/rx")
def upload_rx(
    db: DbDep,
    user: CurrentUser,
    storage: FileStorage = Depends(get_storage),
    file: UploadFile = File(...),
) -> dict:
    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    stored, original = storage.validate(file.filename or "rx.bin", content_type, len(data))
    storage.save(stored, data, content_type=content_type)
    row = RxFile(
        user_id=user.id,
        filename=original,
        stored_name=stored,
        mime=file.content_type or "application/octet-stream",
        size=len(data),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "filename": row.filename, "size": row.size, "status": row.status}


@router.get("/files/rx/{file_id}")
def download_rx(
    file_id: int,
    db: DbDep,
    user: CurrentUser,
    storage: FileStorage = Depends(get_storage),
) -> Response:
    row = db.get(RxFile, file_id)
    if row is None:
        raise NotFoundError("File not found")
    if row.user_id != user.id and not has_permission(user.role, "consults.read"):
        raise ForbiddenError("Not allowed to read this file")
    data = storage.read(row.stored_name)
    return Response(
        content=data,
        media_type=row.mime,
        headers={"Content-Disposition": content_disposition(row.filename)},
    )
