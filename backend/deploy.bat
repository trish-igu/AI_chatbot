@echo off
REM GCP Deployment Script for I Get Happy Chatbot (Windows)
REM This script deploys the chatbot to Google Cloud Run

set PROJECT_ID=igethappy-dev
set SERVICE_NAME=igethappy-chatbot
set REGION=us-central1
set IMAGE_NAME=us-central1-docker.pkg.dev/%PROJECT_ID%/%SERVICE_NAME%/%SERVICE_NAME%

echo 🚀 Starting deployment of I Get Happy Chatbot to GCP...

REM Check if gcloud is installed
where gcloud >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ❌ gcloud CLI is not installed. Please install it first.
    exit /b 1
)

REM Check if user is authenticated
gcloud auth list --filter=status:ACTIVE --format="value(account)" | findstr . >nul
if %ERRORLEVEL% neq 0 (
    echo ❌ Not authenticated with gcloud. Please run 'gcloud auth login' first.
    exit /b 1
)

REM Set the project
echo 📋 Setting project to %PROJECT_ID%...
gcloud config set project %PROJECT_ID%

REM Enable required APIs
echo 🔧 Enabling required APIs...
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com

REM Build and push the Docker image
echo 🐳 Building and pushing Docker image...
gcloud builds submit --tag %IMAGE_NAME% .

REM Deploy to Cloud Run
echo 🚀 Deploying to Cloud Run...
gcloud run deploy %SERVICE_NAME% ^
    --image %IMAGE_NAME% ^
    --region %REGION% ^
    --platform managed ^
    --port 8080 ^
    --memory 2Gi ^
    --cpu 2 ^
    --min-instances 0 ^
    --max-instances 10 ^
    --set-env-vars "DATABASE_URL=postgresql+asyncpg://postgres:aktmar@/mental_health_app?host=/cloudsql/igethappy-dev:us-central1:igethappy-main-db" ^
    --set-secrets INTERNAL_API_KEY=internal-api-key:latest ^
    --add-cloudsql-instances "igethappy-dev:us-central1:igethappy-main-db"

REM Get the service URL
for /f "tokens=*" %%i in ('gcloud run services describe %SERVICE_NAME% --region=%REGION% --format="value(status.url)"') do set SERVICE_URL=%%i

echo ✅ Deployment completed successfully!
echo 🌐 Service URL: %SERVICE_URL%
echo.
echo 📝 Next steps:
echo 1. Update your frontend primary API to your Node service, fallback to Node Cloud Run.
echo.
REM Try to get Node service URL (iguh-backend); ignore if not found
set NODE_SERVICE=iguh-backend
for /f "tokens=*" %%i in ('gcloud run services describe %NODE_SERVICE% --region=%REGION% --format="value(status.url)" 2^>nul') do set NODE_URL=%%i
if defined NODE_URL (
  echo 🔁 Frontend fallback example (Flutter):
  echo flutter run -d chrome ^
    --dart-define=PRIMARY_API_BASE=http://localhost:3000 ^
    --dart-define=BACKUP_API_BASE=%NODE_URL%
) else (
  echo ℹ️ Could not find Node service "%NODE_SERVICE%" in region %REGION%. Set BACKUP_API_BASE to your Node Cloud Run URL manually.
)
echo 2. Test the authentication endpoints
echo 3. Set up a custom domain if needed
echo.
echo 🔗 API Endpoints:
echo - Health: %SERVICE_URL%/health
echo - Register: %SERVICE_URL%/api/auth/register
echo - Login: %SERVICE_URL%/api/auth/login
echo - Chat: %SERVICE_URL%/api/ai/chat

pause
