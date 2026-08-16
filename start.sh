#!/usr/bin/env bash

# Stop the script if any command fails
set -e

echo "Setting up the project..."

# 1. Create the virtual environment if it's missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# 2. Activate the virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# 3. Install packages
echo "Checking and installing dependencies..."
pip install --upgrade pip --quiet

if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "requirements.txt not found, installing packages directly..."
  pip install django django-jazzmin django-admincharts django-import-export django-weasyprint python-dateutil Pillow
fi

# 4. Set up the database
echo "Setting up the database..."
python3 manage.py makemigrations
python3 manage.py migrate

# 5. Start the development server
echo ""
echo "Setup finished successfully. Starting server..."
echo "App URL:   http://127.0.0.1:8000/"
echo "Admin URL: http://127.0.0.1:8000/admin/"
echo "Press Ctrl+C to stop the server."
echo ""

python3 manage.py runserver
