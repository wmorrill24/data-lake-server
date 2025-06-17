import datetime
import os


def get_file_extension(filename):
    # Split the filename to get the extension
    _, extension = os.path.splitext(filename)
    if extension:
        # Remove the leading dot and convert to uppercase
        return extension.lstrip(".").upper()
    return "UNKNOWN"  # Return UNKNOWN if no extension is found


def sanitize_filename(filename):
    # Split the filename into base name and extension
    base_name, extension_original = os.path.splitext(filename)
    # Replace any non-alphanumeric or non-allowed characters with underscore
    sane_base_name = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in base_name
    )
    if not sane_base_name:
        # If base name is empty, generate a name using current UTC timestamp
        # NOTE: Unsure if 'datetime.datetime.utc()' is correct; should be 'datetime.datetime.utcnow()'
        sane_base_name = f"upload_{datetime.datetime.utc().strftime('%Y%m%d%H%M%S%f')}"

    sanitized_extension = ""
    if extension_original:
        # Sanitize the extension: keep only alphanumeric characters if extension starts with '.'
        sanitized_extension = "." + "".join(
            c
            for c in extension_original.lstrip(".")
            if c.isalnum() and extension_original.startswith(".")
        )
        if sanitized_extension == ".":
            # If nothing left after sanitization, remove the dot
            sanitized_extension = ""
    # Return the sanitized filename
    return f"{sane_base_name}{sanitized_extension}"


def sanitize_project_id(project_id):
    sane_prefix = ""
    if project_id:
        # Replace any non-alphanumeric or non-allowed characters with underscore
        sane_project_id = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in project_id.strip()
        ).strip("_")
        if sane_project_id:
            # Add a trailing slash if the project_id is not empty after sanitization
            sane_prefix = f"{sane_project_id}/"
    return sane_prefix
