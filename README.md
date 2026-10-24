# Alpha Investigation System

Alpha Investigation System is a bilingual (Arabic and English) application for organizing investigation cases and reviewing AI-assisted reports. Users can record case details, manage supporting files, chat about case information, and view incident locations on a map.

The application connects to compatible language models through an n8n workflow. Image and video analysis is available when a vision model is configured. Case data is stored in SQLite, while PostgreSQL stores n8n data.

## Key Features

- Create, update, and organize investigation cases.
- Add supporting documents, images, videos, and audio files.
- Generate and review AI-assisted case reports.
- Chat about case information and attached evidence.
- View case locations on an interactive map.
- Use the interface in Arabic or English.

## Getting Started

1. Install Docker Desktop.
2. Copy `.env.example` to `.env` and configure the required settings.
3. Start the application:

   ```bash
   docker compose up -d --build --wait
