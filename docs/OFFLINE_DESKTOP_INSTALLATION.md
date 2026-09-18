# TeachFlow Desktop - Offline Installation Guide

## System Requirements

- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **RAM**: 4 GB minimum, 8 GB recommended
- **Disk Space**: 500 MB for installation, plus space for your data
- **No internet connection required** after installation

## Installation

1. **Download** the installer file `TeachFlow-Setup-1.0.0-x64.exe`
2. **Double-click** the installer to begin installation
3. Follow the on-screen instructions
4. Choose an installation folder (default is recommended)
5. Optionally create a Desktop shortcut
6. Click **Install**, then **Finish** when complete

## First Launch

1. Open TeachFlow from the Start Menu or Desktop shortcut
2. The application will start automatically (no login required)
3. You'll see the TeachFlow home screen
4. Click **Dashboard** to get started

## Where Your Data Is Stored

Your data is stored securely on your computer:

- **Lesson Plans**: Saved in your TeachFlow data folder
- **Uploaded Documents**: Stored locally on your PC
- **Settings**: Your preferences are saved automatically

## Backup Instructions

### To Create a Backup

1. Open TeachFlow
2. Click **Settings** in the navigation
3. Find the **Backup & Restore** section
4. Click **Export Backup**
5. Choose where to save the backup file (e.g., USB drive)
6. The backup will include all your schemes, lesson plans, and settings

### To Restore a Backup

1. Open TeachFlow
2. Click **Settings** in the navigation
3. Find the **Backup & Restore** section
4. Click **Restore Backup**
5. Select your backup file
6. Confirm the restore operation

**Note**: Restoring a backup will replace your current data with the backup data.

## Update Behavior

When you install a newer version of TeachFlow:

- Your **data is preserved** (lesson plans, schemes, settings)
- The application is updated to the new version
- You may need to restart TeachFlow after updating

## Uninstall Behavior

When you uninstall TeachFlow:

- The application files are removed
- **Your data is preserved** unless you explicitly choose to remove it
- You can reinstall later and your data will still be there

To completely remove all data:
1. Uninstall TeachFlow from Windows Settings
2. Manually delete the TeachFlow data folder if desired

## Troubleshooting

### Application Won't Start

1. Check that no other TeachFlow instance is running (check the system tray)
2. Try restarting your computer
3. Reinstall TeachFlow if the problem persists

### Upload Doesn't Work

1. Ensure the file is a `.docx` or `.pdf` file
2. Check the file size (maximum 50 MB)
3. Try a different document to test

### Export Fails

1. Ensure you have enough disk space
2. Close any other applications that might be using the same file
3. Try exporting to a different location

### Need More Help?

Visit: https://github.com/bloomcore/teachflow/issues

## Data Location

Your TeachFlow data is stored at:
```
%LOCALAPPDATA%\TeachFlow\data\
```

To access this folder:
1. Press `Win + R` on your keyboard
2. Type: `%LOCALAPPDATA%\TeachFlow\data`
3. Press Enter

## Version Information

- **Version**: 1.0.0
- **Publisher**: BloomCore Technologies
- **License**: Proprietary

---

*This application works completely offline. No internet connection, no account, no subscription required for core functionality.*
