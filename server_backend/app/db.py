import datetime
import logging
import uuid

import psycopg2  # library for PostgreSQL database connection

from config import settings

logger = logging.getLogger(__name__)

# Load PostgreSQL connection details from environment variables
PG_HOST = settings.PG_HOST
PG_DATABASE = settings.PG_DATABASE
PG_USER = settings.PG_USER
PG_PASSWORD = settings.PG_PASSWORD
PG_PORT = settings.PG_PORT


class DatabaseConnectionError(Exception):
    """Custom exception for database connection errors."""

    pass


def get_pg_connection():
    """
    Establish and return a connection to the PostgreSQL database.
    Raises DatabaseConnectionError if configuration is missing or connection fails.
    """
    # Check if all required environment variables are set
    if not all([PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD]):
        logger.error(
            "PostgreSQL connection details (PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD) are not fully configured in db environment."
        )
        raise DatabaseConnectionError(
            "Configuration details not set for PostgreSQL connection."
        )
    try:
        # Build connection string for psycopg2
        conn_string = f"host='{PG_HOST}' port='{PG_PORT}' dbname='{PG_DATABASE}' user='{PG_USER}' password='{PG_PASSWORD}'"
        conn = psycopg2.connect(conn_string)
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to PostGreSQL: {e}", exc_info=True)
        raise DatabaseConnectionError(f"Failed to connect to database: {e}")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}", exc_info=True)
        raise DatabaseConnectionError(f"Unexpected error connecting to database: {e}")


async def store_file_metadata_in_db(
    file_id: uuid.UUID,
    original_file_name: str,
    file_type_extension: str,
    content_type: str,
    size_bytes: int,
    minio_bucket_name: str,
    minio_object_path: str,
    upload_timestamp: datetime.datetime,
    project_id: str = None,
    experiment_type: str = None,
    author: str = None,
    date_conducted: datetime.date = None,
    custom_tags: str = None,
) -> dict:
    """
    Store file metadata in the PostgreSQL database.

    Args:
        file_id: UUID of the file.
        original_file_name: Name of the file as uploaded.
        file_type_extension: File extension/type.
        content_type: Type of content in file.
        size_bytes: Size of the file in bytes.
        minio_bucket_name: Name of the MinIO bucket where the file is stored.
        minio_object_path: Path to the object in MinIO.
        upload_timestamp: Timestamp when the file was uploaded.
        project_id: (Optional) Associated project ID.
        experiment_type: (Optional) Type of experiment.
        author: (Optional) Author of the experiment.
        date_conducted: (Optional) Date when the experiment was conducted.
        custom_tags: (Optional) Custom tags for the file.

    Returns:
        dict: Status and message about the operation.
    """
    logger.info("Attempting to store file metadata in PostgreSQL database.")

    conn = None

    # Prepare data for insertion into the database
    data_to_insert = {
        "file_id": str(file_id),  # This is already a UUID object
        "project_id": project_id,
        "file_name": original_file_name,
        "file_type": file_type_extension,
        "content_type": content_type,
        "experiment_type": experiment_type,
        "author": author,
        "date_conducted": date_conducted,
        "size_bytes": size_bytes,
        "minio_bucket_name": minio_bucket_name,
        "minio_object_path": minio_object_path,
        "upload_timestamp": upload_timestamp,
        "custom_tags": custom_tags,
    }

    try:
        conn = get_pg_connection()

        with conn.cursor() as cursor:
            # SQL insert statement for file metadata
            insert_query = """
            INSERT INTO file_index.files_metadata_catalog (
                file_id, project_id, file_name, file_type, content_type,
                experiment_type, author, date_conducted, size_bytes,
                minio_bucket_name, minio_object_path, upload_timestamp, custom_tags
            ) VALUES (
                %(file_id)s, %(project_id)s, %(file_name)s, %(file_type)s,
                %(content_type)s, %(experiment_type)s, %(author)s,
                %(date_conducted)s, %(size_bytes)s,
                %(minio_bucket_name)s, %(minio_object_path)s,
                %(upload_timestamp)s, %(custom_tags)s
            )
            """
            cursor.execute(insert_query, data_to_insert)
            conn.commit()
        logger.info("File metadata successfully stored in PostgreSQL database.")
        return {
            "status": "success",
            "file_id": str(file_id),  # Return string representation of UUID
            "inserted_metadata_summary": {  # A summary of what was passed for insertion
                "original_file_name": original_file_name,
                "minio_object_path": minio_object_path,
                "project_id": project_id,
            },
            "message": "Metadata stored successfully.",
        }
    except DatabaseConnectionError as conn_err:
        # Handle database connection errors
        logger.error(
            f"Cannot store metadata due to database connection issue: {conn_err}",
            exc_info=False,
        )  # exc_info=False as conn_err already contains details
        return {
            "status": "error",
            "message": f"Database Connection Error: {str(conn_err)}",
        }
    except (
        psycopg2.Error
    ) as db_op_err:  # Catch errors during DB operations (insert, commit)
        if conn:
            conn.rollback()  # Rollback transaction on error
        logger.error(
            f"PostgreSQL operational error storing metadata for {original_file_name}: {db_op_err}",
            exc_info=True,
        )
        return {
            "status": "error",
            "message": f"Database operational error: {str(db_op_err)}",
        }
    except Exception as e:  # Catch any other unexpected errors
        if conn:
            conn.rollback()
        logger.error(
            f"Unexpected error storing metadata for {original_file_name}: {e}",
            exc_info=True,
        )
        return {"status": "error", "message": f"Failed to store metadata: {str(e)}"}
    finally:
        if conn:
            conn.close()  # Ensure the connection is closed


async def search_files_in_db(
    file_id: uuid.UUID | None = None,
    project_id: str | None = None,
    author: str | None = None,
    file_type: str | None = None,
    experiment_type: str | None = None,
    tags_contain: str | None = None,
    date_before: datetime.date | None = None,
    date_after: datetime.date | None = None,
) -> list[dict]:
    """
    Searches for file metadata in PostgreSQL based on filter criteria.

    Args:
        project_id: Filter by an exact project ID (case-insensitive).
        author: Filter by author name (case-insensitive).
        file_type: Filter by file extension (e.g., 'MATLAB', 'PDF'), case-insensitive.
        experiment_type: Filter by experiment type (case-insensitive).
        tags_contain: Search for a keyword within the comma-separated custom_tags field.
        date_before: Filter files conducted before this date.
        date_after: Filter files conducted after this date.
        file_id: * Not meant as serach criteria, only for proper handling in MATLAB client library

    Returns:
        A list of dictionaries, where each dictionary is a file metadata record.
    """

    logger.info("Searching for files in PostgreSQL database with provided filters.")
    conn = None
    results = []

    try:
        conn = get_pg_connection()
        with conn.cursor() as cursor:
            base_query = """
            SELECT file_id, project_id, file_name, file_type, content_type,
                   experiment_type, author, date_conducted, size_bytes,
                   minio_bucket_name, minio_object_path, upload_timestamp, custom_tags
            FROM file_index.files_metadata_catalog
            """
            where_clauses = []
            query_params = {}

            # Add conditions only for parameters that are actually provided by the client
            if file_id:
                where_clauses.append("file_id = %(file_id)s")
                query_params["file_id"] = str(file_id)

            if project_id:
                # Use ILIKE for case-insensitive matching for text fields
                where_clauses.append("project_id ILIKE %(project_id)s")
                query_params["project_id"] = (
                    f"%{project_id}%"  # Add wildcards for partial match
                )

            if author:
                where_clauses.append("author ILIKE %(author)s")
                query_params["author"] = f"%{author}%"

            if file_type:
                where_clauses.append("file_type ILIKE %(file_type)s")
                query_params["file_type"] = f"%{file_type}%"

            if experiment_type:
                where_clauses.append("experiment_type ILIKE %(experiment_type)s")
                query_params["experiment_type"] = f"%{experiment_type}%"

            if date_after:
                where_clauses.append("date_conducted >= %(date_after)s")
                query_params["date_after"] = date_after

            if date_before:
                where_clauses.append("date_conducted <= %(date_before)s")
                query_params["date_before"] = date_before

            if tags_contain:
                where_clauses.append("custom_tags ILIKE %(tags_contain)s")
                query_params["tags_contain"] = f"%{tags_contain}%"

            if where_clauses:
                final_query = f"{base_query} WHERE {' AND '.join(where_clauses)}"
            else:
                final_query = base_query

            final_query += " ORDER BY upload_timestamp DESC LIMIT 100;"

            logger.info(
                f"Executing search query: {final_query} with params: {query_params}"
            )

            cursor.execute(final_query, query_params)

            column_names = [desc[0] for desc in cursor.description]  # Get column names

            # Fetch all results and convert to list of dictionaries
            for row in cursor.fetchall():
                results.append(dict(zip(column_names, row)))

        return results

    except (DatabaseConnectionError, psycopg2.Error) as e:
        logger.error(f"Database error during metadata search: {e}", exc_info=True)
        # Re-raise the exception to be handled by the API endpoint layer
        raise e
    finally:
        if conn:
            conn.close()


async def get_file_minio_details(file_id: uuid.UUID) -> dict | None:
    """
    Retrieves the MinIO bucket and object path, file name, and object type for a given file_id from PostgreSQL.
    """
    logger.info(f"Retrieving MinIO details for file ID: {file_id}")

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cursor:
            # SQL query to fetch MinIO details for the given file_id
            sql_query = """
            SELECT minio_bucket_name, minio_object_path, file_name, content_type
            FROM file_index.files_metadata_catalog
            WHERE file_id = %s;
            """
            params_to_execute = (str(file_id),)

            cursor.execute(
                sql_query,
                params_to_execute,
            )
            result = cursor.fetchone()
            # If a result is found, unpack it into a dictionary and return it
            if result:
                bucket_name = result[0]
                object_path = result[1]
                filename = result[2]
                content_type = result[3]
                logger.info(
                    f"Found MinIO path for file_id {file_id}: {bucket_name}/{object_path}"
                )
                return {
                    "bucket": bucket_name,
                    "path": object_path,
                    "filename": filename,
                    "content_type": content_type,
                }
            else:
                logger.info(f"No MinIO details found for file ID: {file_id}")
                return None
    except (DatabaseConnectionError, psycopg2.Error) as e:
        logger.error(f"Database error retrieving MinIO details: {e}", exc_info=True)
        raise e
    finally:
        if conn:
            conn.close()
