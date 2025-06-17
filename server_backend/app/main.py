import datetime
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import yaml
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from minio.error import S3Error
from starlette.background import BackgroundTask

from config import settings
from db import (
    DatabaseConnectionError,
    get_file_minio_details,
    search_files_in_db,
    store_file_metadata_in_db,
)
from minio_client import get_minio_client
from utils import get_file_extension, sanitize_filename, sanitize_project_id

# Configure logging for this module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Read MinIO Configuration from settings instance
MINIO_ENDPOINT = settings.MINIO_ENDPOINT
MINIO_ACCESS_KEY = settings.MINIO_ACCESS_KEY
MINIO_SECRET_KEY = settings.MINIO_SECRET_KEY
MINIO_DEFAULT_BUCKET = settings.MINIO_DEFAULT_BUCKET
MINIO_USE_HTTPS = settings.MINIO_USE_HTTPS

# Initialize FastAPI app
app = FastAPI(title="API Data Service")

# Initialize MinIO client
minio_client = get_minio_client(
    endpoint=MINIO_ENDPOINT,
    username=MINIO_ACCESS_KEY,
    password=MINIO_SECRET_KEY,
    default_bucket=MINIO_DEFAULT_BUCKET,
    secure=MINIO_USE_HTTPS,
)


async def process_and_store_file(
    file_data,
    original_filename: str,
    content_type: str,
    file_size: int,
    user_metadata: dict,
    minio_folder_prefix: str = "",  # Add a prefix for folder uploads
) -> dict:
    """
    Helper function to process a single file, upload it to MinIO, and store its metadata.
    This logic is shared between single file and folder uploads.
    """
    # Fetch metadata from dictionary
    research_project_id = user_metadata.get("research_project_id", "")
    author = user_metadata.get("author")
    experiment_type = user_metadata.get("experiment_type")
    date_conducted_str = user_metadata.get("date_conducted")
    custom_tags = user_metadata.get("custom_tags")

    # Sanitize filename and project ID for safe storage
    preferred_filename = sanitize_filename(original_filename)
    project_id_prefix = sanitize_project_id(research_project_id)

    # Combine the project prefix and the new folder prefix
    full_prefix = os.path.join(project_id_prefix, minio_folder_prefix)

    # Compose initial object name for MinIO
    desired_object_name = os.path.join(full_prefix, preferred_filename)
    final_object_name = desired_object_name

    # Handle duplicate object names by appending a counter
    counter = 0
    base_name_for_counter, extension_for_counter = os.path.splitext(preferred_filename)
    while True:
        try:
            minio_client.stat_object(MINIO_DEFAULT_BUCKET, final_object_name)
            counter += 1
            current_try_filename_with_counter = (
                f"{base_name_for_counter}({counter}){extension_for_counter}"
            )
            final_object_name = os.path.join(
                full_prefix, current_try_filename_with_counter
            )
        except S3Error as stat_exc:
            if stat_exc.code == "NoSuchKey":
                break  # Name is available
            else:
                raise stat_exc  # Re-raise other S3 errors

    # Upload result to MinIO
    minio_client.put_object(
        MINIO_DEFAULT_BUCKET,
        final_object_name,
        file_data,
        length=file_size,
        part_size=10 * 1024 * 1024,
        content_type=content_type or "application/octet-stream",
    )

    file_type_extension = get_file_extension(original_filename)
    date_conducted = None
    if date_conducted_str:
        try:
            date_conducted = datetime.datetime.strptime(
                str(date_conducted_str), "%Y-%m-%d"
            ).date()
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid date format: '{date_conducted_str}'. Storing as null."
            )

    ingestion_time = datetime.datetime.now(datetime.timezone.utc)
    new_file_id = uuid.uuid4()

    metadata_storage_result = await store_file_metadata_in_db(
        file_id=new_file_id,
        original_file_name=original_filename,
        minio_bucket_name=MINIO_DEFAULT_BUCKET,
        minio_object_path=final_object_name,
        file_type_extension=file_type_extension,
        content_type=content_type or "application/octet-stream",
        upload_timestamp=ingestion_time,
        experiment_type=experiment_type,
        date_conducted=date_conducted,
        author=author,
        research_project_id=research_project_id,
        custom_tags=custom_tags,
        size_bytes=file_size,
    )

    return {
        "status": metadata_storage_result.get("status"),
        "original_filename": original_filename,
        "final_object_name": final_object_name,
        "file_id": str(new_file_id),
        "message": metadata_storage_result.get("message"),
    }


@app.get("/status")
async def read_root():
    """Root endpoint for health check or welcome message."""
    logger.info("Root endpoint accessed.")
    return {"message": "API SERVICE RUNNING"}


@app.post("/uploadfile/")
async def create_upload_file(
    data_file: UploadFile = File(...),
    metadata_file: UploadFile = File(...),
):
    """Handles a single file upload along with its YAML metadata."""
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO service not available.")

    try:
        yaml_content = await metadata_file.read()
        user_metadata = yaml.safe_load(yaml_content)
        if not isinstance(user_metadata, dict):
            raise ValueError("YAML content could not be parsed into a dictionary.")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid or malformed metadata YAML file: {e}"
        )
    finally:
        await metadata_file.close()

    try:
        result = await process_and_store_file(
            file_data=data_file.file,
            original_filename=data_file.filename,
            content_type=data_file.content_type,
            file_size=data_file.size,
            user_metadata=user_metadata,
        )
        return JSONResponse(
            status_code=200 if result["status"] == "success" else 500, content=result
        )
    except Exception as e:
        logger.error(
            f"Error processing single file upload {data_file.filename}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        await data_file.close()


@app.post("/upload_folder/")
async def create_upload_folder(
    zip_file: UploadFile = File(...),
    metadata_file: UploadFile = File(...),
):
    """
    Handles folder uploads as a single ZIP file. All files are placed in a uniquely named folder in MinIO.
    """
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO service not available.")

    try:
        yaml_content = await metadata_file.read()
        user_metadata = yaml.safe_load(yaml_content)
        if not isinstance(user_metadata, dict):
            raise ValueError("YAML content could not be parsed into a dictionary.")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid or malformed metadata YAML file: {e}"
        )
    finally:
        await metadata_file.close()

    # Create a unique folder name for this upload batch based on the zip file name
    zip_filename_base, _ = os.path.splitext(zip_file.filename)
    unique_folder_name = (
        f"{sanitize_filename(zip_filename_base)}_{uuid.uuid4().hex[:8]}"
    )

    logger.info(f"Creating MinIO folder prefix: {unique_folder_name}")

    temp_dir = tempfile.mkdtemp()
    results = []

    try:
        zip_file_path = Path(temp_dir) / zip_file.filename
        with open(zip_file_path, "wb") as f:
            shutil.copyfileobj(zip_file.file, f)

        with zipfile.ZipFile(zip_file_path, "r") as zf:
            zf.extractall(temp_dir)

        # Iterate through all extracted files, including those in subdirectories
        for filepath in Path(temp_dir).rglob("*"):
            if (
                filepath.is_file()
                and not filepath.name.startswith("__MACOSX")
                and filepath.suffix != ".zip"
            ):
                with open(filepath, "rb") as f:
                    file_size = filepath.stat().st_size
                    result = await process_and_store_file(
                        file_data=f,
                        original_filename=filepath.name,
                        content_type=None,
                        file_size=file_size,
                        user_metadata=user_metadata,
                        minio_folder_prefix=unique_folder_name,  # Pass the folder prefix
                    )
                    results.append(result)

        return JSONResponse(status_code=200, content={"upload_results": results})

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400, detail="The uploaded file is not a valid ZIP archive."
        )
    except Exception as e:
        logger.error(
            f"Error processing folder upload {zip_file.filename}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        await zip_file.close()
        shutil.rmtree(temp_dir)  # Clean up the temporary directory


@app.get("/search")
async def search_files_endpoint(
    # ... (existing search endpoint code remains the same)
    file_id: uuid.UUID | None = Query(
        None, description="Filter by exact file ID (UUID)."
    ),
    research_project_id: str | None = Query(
        None, description="Filter by exact research project ID."
    ),
    author: str | None = Query(
        None, description="Filter by author name (case-insensitive, partial match)."
    ),
    file_type: str | None = Query(
        None,
        description="Filter by file extension, e.g., 'PDF', 'MAT' (case-insensitive, exact match).",
    ),
    experiment_type: str | None = Query(
        None, description="Filter by experiment type (case-insensitive, partial match)."
    ),
    tags_contain: str | None = Query(
        None, description="Search for a keyword within the custom_tags field."
    ),
    date_after: datetime.date | None = Query(
        None,
        description="Filter for files conducted ON or AFTER this date (YYYY-MM-DD).",
    ),
    date_before: datetime.date | None = Query(
        None,
        description="Filter for files conducted ON or BEFORE this date (YYYY-MM-DD).",
    ),
):
    try:
        results = await search_files_in_db(
            file_id=file_id,
            research_project_id=research_project_id,
            author=author,
            file_type=file_type,
            experiment_type=experiment_type,
            tags_contain=tags_contain,
            date_after=date_after,
            date_before=date_before,
        )
        return results
    except Exception as e:
        logger.error(f"API Error during file search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/download/{file_id}")
async def download_file_by_stream(file_id: uuid.UUID):
    """
    Looks up a file by its metadata file ID, fetches it directly from MinIO,
    and streams it back to the client as a download. This acts as a secure proxy.
    """

    response_stream = None
    if not minio_client:
        logger.error("Download link generation failed: MinIO client not initialized.")
        raise HTTPException(status_code=503, detail="MinIO service not available.")

    # Fetch Object and Path for streaming
    try:
        minio_details = await get_file_minio_details(file_id)

        if not minio_details:
            logger.warning(f"No MinIO details found for file_id: {file_id}")
            raise HTTPException(
                status_code=404, detail=f"File with ID {file_id} not found."
            )

        bucket_name = minio_details.get("bucket")
        object_path = minio_details.get("path")
        original_filename = minio_details.get("filename")
        content_type = minio_details.get("content_type") or "application/octet-stream"

        logger.info(
            f"Proxying download for '{object_path}' from bucket '{bucket_name}'..."
        )

        # Use get_object for streaming
        response_stream = minio_client.get_object(bucket_name, object_path)

        def close_stream():
            logger.info(f"Closing MinIO response stream for {object_path}")
            response_stream.close()
            response_stream.release_conn()

        return StreamingResponse(
            content=response_stream.stream(amt=65536),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{original_filename}"'
            },
            background=BackgroundTask(
                close_stream
            ),  # Use BackgroundTask so stream stays open
        )

    except HTTPException as http_exc:
        raise http_exc
    except S3Error as e:
        if e.code == "NoSuchKey":
            logger.error(
                f"File with ID {file_id} found in DB but not in MinIO at path {minio_details.get('path') if 'minio_details' in locals() else 'unknown'}"
            )
            raise HTTPException(
                status_code=404,
                detail="File record found, but data does not exist in storage.",
            )
        else:
            logger.error(
                f"MinIO S3 error during download for file ID {file_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500, detail="Error retrieving file from storage."
            )
    except DatabaseConnectionError as e:
        logger.error(
            f"Download failed due to DB connection error for file_id {file_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=503, detail="Could not connect to metadata database."
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while downloading file for ID {file_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
