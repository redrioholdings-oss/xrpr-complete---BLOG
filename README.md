# XRP Complete Blog — Homepage v48

A homepage-only visual rebuild for the existing Flask application.

## Deployment

1. Back up the current Railway deployment and persistent volume.
2. Replace the repository files with the contents of this package.
3. Keep the existing Railway environment variables:
   - `SECRET_KEY`
   - `ADMIN_PASSWORD`
   - `DATA_DIR=/data`
4. Push to GitHub and allow Railway to redeploy.

## Scope

- Rebuilt public homepage presentation.
- Preserved the existing Flask routes, SQLite database, uploads, admin login, portal, and hidden pages.
- No database migration is required.
- Existing posts and uploaded images are read from the same database and upload directory.

## Validation completed

- Python syntax compilation passed.
- ZIP archive integrity passed.
- Full Flask route rendering could not be executed in this workspace because Flask was not available for installation.
