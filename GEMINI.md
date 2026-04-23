# Image Catalog AI (A-Eye)

A self-hosted, AI-powered image intelligence and cataloging system designed to work with large photo libraries stored on NAS/SMB shares. It uses local vision and language models to understand, describe, tag, and search your photos without any cloud dependency.

## Project Overview

This project is a sophisticated photo management system that integrates various AI technologies for deep image analysis.

- **Frontend:** Modern React application built with Vite and Tailwind CSS.
- **Backend:** FastAPI (Python) serving a REST API and managing background processing workers.
- **Database:** MariaDB/MySQL via SQLAlchemy for metadata and relationship storage.
- **Search Engine:** Elasticsearch for natural language and keyword-based photo search.
- **Storage:** Designed to interface with NAS via SMB, mounting shares for scanning and processing.
- **AI Stack:**
    - **Inference:** Ollama or llama.cpp/LM Studio for high-level description and sentiment analysis.
    - **Object Detection:** YOLOv8 (Ultralytics) for recognizing common objects and scenes.
    - **Face Recognition:** FaceNet-PyTorch for face detection, embedding generation, and clustering.
    - **Safety:** NudeNet for NSFW content detection and automated folder tagging.
    - **Metadata:** Pillow and specialized libraries for EXIF, GPS (reverse geocoding), and RAW format support.

## Architecture

The system operates in two main phases when scanning:
1.  **Phase 1 (Local Vision):** Extracts metadata, generates thumbnails, runs object detection (YOLO), detects faces (FaceNet), and checks for NSFW content.
2.  **Phase 2 (LLM Analysis):** Sends image context to a local LLM (Ollama/llama.cpp) to generate natural language descriptions and sentiment analysis.

## Building and Running

### Prerequisites
- Python 3.10+
- Node.js & npm
- MariaDB/MySQL server
- Elasticsearch server
- Local AI provider (Ollama or llama.cpp)

### Backend Setup
1.  Create a virtual environment: `python -m venv venv`
2.  Activate it: `source venv/bin/activate`
3.  Install dependencies: `pip install -r backend/requirements.txt`
4.  Configure environment: Copy `.env.example` (if it exists) or create `.env` with DB, SMB, and AI provider details.

### Frontend Setup
1.  Navigate to `frontend/`
2.  Install dependencies: `npm install`
3.  Build for production: `npm run build` or run dev: `npm run dev`

### Running the Application
The easiest way to start both components in development mode is using the provided script:
```bash
./start.sh
```
- **Frontend:** http://localhost:5173 (Vite dev server)
- **Backend:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs

## Development Conventions

- **Python:** Use type hints and follow FastAPI best practices. Business logic is primarily located in `backend/services/`.
- **Database:** All schema changes should be reflected in `backend/models.py`. Migrations are currently handled via startup checks in `main.py`.
- **Frontend:** React with functional components and hooks. Styling is strictly Tailwind CSS.
- **AI Models:** Large model files (like YOLO `.pt` files) are stored in the `backend/` root or downloaded on demand.
- **NAS Integration:** The `smb_service.py` handles the complexities of remote file access. Ensure SMB credentials in `.env` are correct for your environment.

## Key Files
- `backend/main.py`: Application entry point and startup logic.
- `backend/models.py`: SQLAlchemy database models.
- `backend/config.py`: Configuration management using `pydantic-settings` or `python-dotenv`.
- `backend/services/scanner_service.py`: Orchestrates the multi-phase scanning process.
- `frontend/src/`: React source code.
- `start.sh`: Utility script to launch the full stack.
- `A-EYE/`: Legacy or alternative version of the application (Jinja2/HTMX based).
