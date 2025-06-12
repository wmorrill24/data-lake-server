# Data-lake-server - Backend Services

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

This repository contains the Docker Compose setup for the backend services of the Data Lake project. It includes the data ingestion API, MinIO object storage, and a PostgreSQL metadata store.

## Architecture Overview

This system uses a service-oriented architecture, managed by Docker Compose:
-   **`server-backend`**: A FastAPI application that serves as the main API for all interactions. It handles file uploads, metadata processing, and provides endpoints for searching and downloading data.
-   **`minio-server`**: An S3-compatible object storage service that acts as the primary data lake for all raw and processed files.
-   **`postgres-metadata-db`**: A PostgreSQL database that stores all extracted metadata about the files in MinIO, making them searchable.

## Prerequisites

-   Docker Engine
-   Docker Compose

## Setup and Configuration

Follow these steps to set up and run the backend services on a development machine or a new server.

### 1. Clone the Repository

```bash
git clone [https://github.com/wmorrill24/data-lake-server.git](https://github.com/wmorrill24/data-lake-server.git)
cd data-lake-server
```

### 2. Create the Configuration File

Copy the .env.example file to local .env file

```bash
cp .env.example .env
```

Open the .env file and fill in credentials / settings

### 3. Create Persistent Data Directories

Create directories to store persistent data on the machine and edit docker-compose to mount the directories.


