# Module 1 architecture

The browser status page calls the FastAPI health and readiness endpoints. `/health` checks only the API process; `/ready` verifies PostgreSQL connectivity with `SELECT 1`. PostgreSQL runs locally through Docker Compose and persists data in a named volume.

Business models, authentication, background processing, billing calculations, and analytics are deliberately deferred to later modules.

