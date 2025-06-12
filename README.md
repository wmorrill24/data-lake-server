Research Data Lake - Backend Services


This repository contains the Dockerized backend services for the Research Data Lake project. It includes the data ingestion API, MinIO object storage, and a PostgreSQL metadata store.

Architecture Overview
This system uses a service-oriented architecture, managed by Docker Compose:

server-backend: A FastAPI application that serves as the main API for all interactions. It handles file uploads, metadata processing, and provides endpoints for searching and downloading data.
minio-server: An S3-compatible object storage service that acts as the primary data lake for all raw and processed files.
postgres-metadata-db: A PostgreSQL database that stores all extracted metadata about the files in MinIO, making them searchable.
Prerequisites
Docker Engine
Docker Compose
Setup and Configuration
Follow these steps to set up and run the backend services on a development machine or a new server.

1. Clone the Repository
Bash

# Replace with your actual repository URL
git clone https://github.com/wmorrill24/data-lake-server.git
cd data-lake-server
2. Create the Configuration File
This project uses a .env file to manage all secrets and environment-specific settings. This file should never be committed to Git.

First, copy the provided template:

Bash

cp .env.example .env
Next, open the new .env file (nano .env or edit it in your IDE) and fill in your desired credentials and settings. The MINIO_PUBLIC_HOST should be localhost:9000 for local development or the server's public IP/domain name for production.

3. Create Persistent Data Directories
This setup uses bind mounts to store persistent data in a predictable location on the host machine. Create the necessary directories:

Bash

mkdir -p ./server_data/minio
mkdir -p ./server_data/postgres
(Note: Ensure Docker has the necessary permissions to write to these directories on your host system.)

Running the Application
For Development (with Live Code Reloading)
This project is configured for a seamless development experience using VS Code's "Remote - Containers" extension.

Open the project folder in VS Code.
If prompted, click "Reopen in Container". This will use the settings in .devcontainer/devcontainer.json to build the server-backend image and attach VS Code to it.
The Docker Compose services will be started automatically. The server-backend API will run with live reloading, meaning changes you make to the code in ./server_backend/app/ will be reflected instantly without restarting the container.
For Production or Manual Startup
From the project root directory, run the following command to build the images and start all services in detached mode:

Bash

docker-compose up -d --build
--build: Builds the server-backend image from its Dockerfile. Required on first run or after code changes.
-d: Runs the containers in the background.
To view the logs for a specific service:

Bash

docker-compose logs -f server-backend
Accessing Services
Once the stack is running, services are available on your host machine at the following ports:

API Backend (FastAPI): http://localhost:8001
Interactive Docs: http://localhost:8001/docs
MinIO Console: http://localhost:9001
PostgreSQL: Connect via port 5432 on localhost
For Development
To contribute to this project, install the dependencies locally in a virtual environment for IDE support (linting, formatting).

Bash

# From the server_backend directory
cd server_backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
The primary development workflow, however, is intended to be inside the VS Code Dev Container.

License
This project is licensed under the MIT License.
