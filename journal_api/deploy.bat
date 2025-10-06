@echo off
set PROJECT_ID=igethappy-dev
set SERVICE_NAME=journal-api
set REGION=us-central1
set IMAGE_NAME=gcr.io/%PROJECT_ID%/%SERVICE_NAME%

echo 🚀 Deploying %SERVICE_NAME% to Cloud Run...

gcloud services enable cloudbuild.googleapis.com run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com

gcloud builds submit --tag %IMAGE_NAME% .

gcloud run deploy %SERVICE_NAME% ^
  --image %IMAGE_NAME% ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8001 ^
  --memory 1Gi ^
  --cpu 1 ^
  --set-env-vars "DATABASE_URL=postgresql+asyncpg://postgres:aktmar@/mental_health_app?host=/cloudsql/igethappy-dev:us-central1:igethappy-main-db" ^
  --add-cloudsql-instances "igethappy-dev:us-central1:igethappy-main-db" ^
  --set-env-vars "JWT_SECRET_KEY=%JWT_SECRET_KEY%"

for /f "tokens=*" %%i in ('gcloud run services describe %SERVICE_NAME% --region=%REGION% --format="value(status.url)"') do set SERVICE_URL=%%i
echo ✅ Deployed. URL: %SERVICE_URL%


