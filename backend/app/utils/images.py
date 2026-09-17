from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from ..config import Settings


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}


@dataclass(frozen=True)
class SavedImage:
    name: str
    path: Path
    width: int
    height: int
    format: str


async def validate_and_save_image(upload: UploadFile, settings: Settings) -> SavedImage:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "只支持 JPEG、PNG 和 WebP 图片")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(1024 * 1024, settings.max_upload_bytes + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(413, "图片大小超过上传限制")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if not payload:
        raise HTTPException(400, "图片内容为空")

    try:
        with Image.open(BytesIO(payload)) as candidate:
            detected_format = (candidate.format or "").upper()
            candidate.verify()
        with Image.open(BytesIO(payload)) as decoded:
            width, height = decoded.size
            decoded.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "图片内容无效或已损坏") from exc

    expected_format, extension = ALLOWED_IMAGE_TYPES[upload.content_type]
    if detected_format not in {item[0] for item in ALLOWED_IMAGE_TYPES.values()}:
        raise HTTPException(400, "图片实际格式不受支持")
    if detected_format != expected_format:
        raise HTTPException(400, "图片声明类型与实际格式不一致")
    if width <= 0 or height <= 0:
        raise HTTPException(400, "图片尺寸无效")
    if width * height > settings.max_image_pixels:
        raise HTTPException(400, "图片像素尺寸超过限制")

    settings.upload_path.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{extension}"
    path = settings.upload_path / name
    try:
        path.write_bytes(payload)
    except OSError as exc:
        raise HTTPException(500, "图片保存失败") from exc
    return SavedImage(name, path, width, height, detected_format)
