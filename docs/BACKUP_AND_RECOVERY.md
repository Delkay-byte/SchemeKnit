# TeachFlow Backup and Recovery

## What to Back Up

1. **Database** (`teachflow.db` or PostgreSQL dump)
2. **Uploaded files** (`uploads/` directory)
3. **Environment configuration** (`.env` file)
4. **Exported files** (`exports/` directory, if needed)

## Backup Schedule

| Component | Frequency | Retention |
|-----------|-----------|-----------|
| Database | Daily | 30 days |
| Uploads | Weekly | 90 days |
| Full system | Monthly | 1 year |

## Backup Commands

### Automated (Linux/Mac)

```bash
#!/bin/bash
BACKUP_DIR="/backups/teachflow"
DATE=$(date +%Y%m%d_%H%M%S)

# Database
cp teachflow.db "$BACKUP_DIR/db/teachflow_$DATE.db"

# Uploads
tar -czf "$BACKUP_DIR/uploads/uploads_$DATE.tar.gz" uploads/

# Clean old backups (30 days)
find "$BACKUP_DIR" -mtime +30 -delete
```

### Windows

```powershell
$date = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item "teachflow.db" "C:\Backups\TeachFlow\db\teachflow_$date.db"
Compress-Archive -Path "uploads" -DestinationPath "C:\Backups\TeachFlow\uploads\uploads_$date.zip"
```

## Recovery

### Restore Database

```bash
# SQLite
cp backup.db teachflow.db

# PostgreSQL
psql teachflow < backup.sql
```

### Restore Uploads

```bash
tar -xzf uploads_backup.tar.gz
```

## Disaster Recovery Steps

1. Install Python and Node.js on new machine
2. Clone the repository
3. Restore `.env` configuration
4. Restore database backup
5. Restore uploads directory
6. Install dependencies: `pip install -r requirements.txt && cd frontend && npm install`
7. Start services

## Testing Backups

Verify backups monthly by:
1. Copying backup to a test location
2. Starting the application with the backup data
3. Verifying schemes and lesson plans are accessible
