# Multi-Modal Location Recommendation Engine

A cross-city location recommendation system spanning four European cities (**Kaunas, Madrid, Paris, and Rome**) that matches points of interest using deep visual embeddings and dominant color palettes.

## Pipeline & Architecture
- **Database Ingestion (`data_load/load_to_db.py`):** Loads geospatial POI metadata (originally harvested via Wikidata SPARQL queries and the OpenStreetMap Overpass API) into a normalized PostgreSQL database using cached Django ORM operations.
- **Distributed Feature Extraction (`data_processing/run_processing_mpi.py`):** Uses an MPI (`mpi4py`) parallel worker pipeline to extract 4,096-dimensional VGG16 feature embeddings and 5-rank K-Means color swatches, then computes and batch-inserts cross-city similarity mappings.
- **Web Application (`p160b013site/`):** Django interface for browsing cities, viewing place profiles, and exploring visually similar locations across cities.

## Tech Stack
Python · Django · PostgreSQL · TensorFlow/Keras (VGG16) · Scikit-learn (K-Means) · MPI (`mpi4py`)

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment variables: `DJANGO_SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`.
3. Apply migrations and run the app from `p160b013site/`:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

> **Note:** Raw scraped imagery and merged CSV datasets (`data_collection/collected_data/`) are excluded from version control.
