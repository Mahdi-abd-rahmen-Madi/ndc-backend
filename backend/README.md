# NDC Backend

Django backend for the NDC project with geographic data support.

## Setup

1. Create virtual environment:
```bash
python3 -m venv env
source env/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy environment file:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Run migrations:
```bash
cd ndc
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Start development server:
```bash
python manage.py runserver
```

## Apps

- **api**: REST API endpoints with JWT authentication
- **geodata**: Geographic data handling and tile serving
- **ndc**: Main Django project

## Features

- Django REST Framework with JWT authentication
- PostgreSQL with PostGIS support
- Geographic data processing with GeoPandas
- Vector tile serving
- CORS support for frontend integration
- WhiteNoise for static file serving
