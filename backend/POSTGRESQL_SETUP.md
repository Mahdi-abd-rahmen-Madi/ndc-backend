# PostgreSQL Database Setup Guide

## Overview
Successfully configured Django to use PostgreSQL instead of SQLite for the NDC backend application.

## Database Configuration

### Database Details
- **Database Name**: `ndc_db`
- **User**: `ndc_user`
- **Password**: `ndc_password`
- **Host**: `localhost`
- **Port**: `5432`
- **PostgreSQL Version**: 18.1

### Environment Variables
The `.env` file contains the following database configuration:

```bash
# Database Settings (PostgreSQL)
DATABASE_URL=postgresql://ndc_user:ndc_password@localhost:5432/ndc_db

# Database Credentials (for manual connection if needed)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=ndc_db
DB_USER=ndc_user
DB_PASSWORD=ndc_password
DB_HOST=localhost
DB_PORT=5432
```

## Setup Steps Completed

### 1. Package Installation
```bash
pip install dj-database-url psycopg2-binary
```

### 2. Database Creation
```sql
-- Create user
CREATE USER ndc_user WITH PASSWORD 'ndc_password';

-- Create database
CREATE DATABASE ndc_db OWNER ndc_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ndc_db TO ndc_user;
```

### 3. Django Configuration
- Updated `settings.py` to use `dj-database-url`
- Configured environment variables using `python-decouple`
- Set up proper database connection parsing

### 4. Migration and Data Import
- Ran Django migrations to create all tables
- Successfully imported antenna equipment data (33 records)
- Created Django superuser for admin access

## Database Tables Created

### Core Django Tables
- `auth_user` - User accounts
- `auth_group` - User groups
- `django_migrations` - Migration tracking
- `django_session` - Session data
- `django_admin_log` - Admin activity logs

### Application Tables
- `api_*` tables - Building management system (9 tables)
- `geodata_*` tables - Antenna equipment system (3 tables)

### Antenna Equipment Tables
- `geodata_antennaequipment` - Main equipment records
- `geodata_antennaspecification` - 4G/5G specifications
- `geodata_terrainloadcalculation` - Terrain calculations

## Connection Methods

### Django ORM Connection
```python
from django.db import connection
# Uses DATABASE_URL environment variable
```

### Manual Connection
```python
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="ndc_db",
    user="ndc_user",
    password="ndc_password",
    port=5432
)
```

### Command Line Connection
```bash
sudo -u postgres psql -d ndc_db
```

## Verification Tests

### Django Check
```bash
python manage.py check --database default
# Result: System check identified no issues
```

### Database Engine Verification
```python
from django.db import connection
print(connection.vendor)  # Output: postgresql
```

### Data Count Verification
```python
from geodata.models import AntennaEquipment
print(AntennaEquipment.objects.count())  # Output: 33
```

## Admin Access

### Superuser Credentials
- **Username**: `admin`
- **Email**: `admin@example.com`
- **Password**: `admin123`

### Admin Interface
- URL: `http://localhost:8000/admin/`
- Full access to all models and data
- Can manage users, permissions, and content

## Security Considerations

### Current Setup (Development)
- Password is simple (`ndc_password`)
- Debug mode enabled
- All hosts allowed for development

### Production Recommendations
1. **Change Password**: Use a strong, randomly generated password
2. **Environment Variables**: Keep `.env` file out of version control
3. **Database Security**: Limit database user permissions
4. **SSL Connection**: Enable SSL for database connections
5. **Backup Strategy**: Implement regular database backups

### Environment Security
```bash
# Add to .gitignore
.env
*.sqlite3
db.sqlite3
```

## Performance Benefits

### PostgreSQL vs SQLite
- **Concurrent Access**: Multiple users can access simultaneously
- **Advanced Features**: Full-text search, JSON operations, advanced indexing
- **Scalability**: Handles larger datasets more efficiently
- **Data Integrity**: ACID compliance and robust transaction support
- **Backup Tools**: Professional backup and recovery tools

### Query Optimization
- Automatic query planning and optimization
- Advanced indexing options (B-tree, Hash, GiST, GIN)
- Connection pooling support
- Query caching mechanisms

## Migration Notes

### From SQLite to PostgreSQL
- All data successfully migrated
- Schema automatically adapted
- Foreign key constraints preserved
- Index relationships maintained

### Future Migrations
- Django migrations work seamlessly
- Can switch between databases using environment variables
- Migration files are database-agnostic

## Troubleshooting

### Common Issues
1. **Connection Refused**: Check PostgreSQL service status
2. **Authentication Failed**: Verify user credentials
3. **Permission Denied**: Ensure database user has proper privileges
4. **Port Issues**: Confirm PostgreSQL is running on port 5432

### Debug Commands
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test database connection
sudo -u postgres psql -d ndc_db -c "SELECT version();"

# Check Django database connection
python manage.py check --database default
```

## Status: COMPLETE

PostgreSQL is now fully configured and operational with:
- Database and user created with proper permissions
- Django application successfully connected
- All migrations applied and data imported
- Admin interface accessible
- Environment variables properly configured

The system is ready for development and can be easily configured for production deployment.
