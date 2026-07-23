"""阿里云 OSS 上传（工单附件）。"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from customer_service.config.settings import get_settings

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_ATTACHMENTS_PER_TICKET = 3


def _normalize_endpoint(endpoint: str) -> str:
    ep = (endpoint or "").strip()
    if not ep:
        raise ValueError("OSS endpoint is empty")
    if ep.startswith("http://") or ep.startswith("https://"):
        return ep
    return f"https://{ep}"


def _ext_for(filename: str | None, content_type: str) -> str:
    mapped = ALLOWED_IMAGE_CONTENT_TYPES.get(content_type.lower())
    if mapped:
        return mapped
    if filename:
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            return ".jpg" if suffix == ".jpeg" else suffix
    raise ValueError("仅支持 jpg/png/webp/gif 图片")


def upload_ticket_image(
    *,
    data: bytes,
    filename: str | None,
    content_type: str,
) -> str:
    """上传图片到 OSS，返回可访问 URL。"""
    if not data:
        raise ValueError("空文件")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"单张图片不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB")

    ct = (content_type or "").split(";")[0].strip().lower() or "application/octet-stream"
    if ct not in ALLOWED_IMAGE_CONTENT_TYPES and not (
        filename and PurePosixPath(filename).suffix.lower()
        in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ):
        raise ValueError("仅支持 jpg/png/webp/gif 图片")

    settings = get_settings()
    if not settings.oss_configured:
        raise RuntimeError("OSS 未配置或未启用，无法上传附件")

    ext = _ext_for(filename, ct if ct in ALLOWED_IMAGE_CONTENT_TYPES else "image/jpeg")
    prefix = settings.oss_path_prefix
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    object_key = f"{prefix}tickets/{uuid.uuid4().hex}{ext}"

    try:
        import oss2
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 oss2 依赖，请 pip install oss2") from exc

    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(
        auth,
        _normalize_endpoint(settings.oss_endpoint),
        settings.oss_bucket,
    )
    headers = {"Content-Type": ct if ct in ALLOWED_IMAGE_CONTENT_TYPES else f"image/{ext[1:]}"}
    result = bucket.put_object(object_key, data, headers=headers)
    if getattr(result, "status", 200) >= 300:
        raise RuntimeError(f"OSS 上传失败: status={getattr(result, 'status', '?')}")

    domain = settings.oss_domain
    if not domain:
        domain = f"https://{settings.oss_bucket}.{settings.oss_endpoint.lstrip('https://').lstrip('http://')}"
    return f"{domain.rstrip('/')}/{object_key}"
