from typing import List, Dict, Any
from google.cloud import storage
from .config import settings
import uuid


def upload_attachments(attachments: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Upload provided attachment file paths to GCS and return normalized metadata.

    Expected input shape example:
    { "files": ["/local/path/to/image.jpg"] }
    """
    if not attachments or not attachments.get("files"):
        return attachments or {}

    bucket_name = settings.gcs_bucket_name
    if not bucket_name:
        # If no bucket configured, return as-is (caller may store metadata only)
        return attachments

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    uploaded: List[str] = []
    for path in attachments.get("files", []):
        blob_name = f"attachments/{user_id}/{uuid.uuid4()}-{path.split('/')[-1]}"
        blob = bucket.blob(blob_name)
        try:
            blob.upload_from_filename(path)
            blob.make_private()
            uploaded.append(f"gs://{bucket_name}/{blob_name}")
        except Exception:
            # Skip failed uploads silently; production should log this
            continue

    return {"files": uploaded}


