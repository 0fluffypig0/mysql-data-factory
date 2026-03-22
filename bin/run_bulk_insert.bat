@echo off
chcp 65001 >nul
echo [DEPRECATED] bin\run_bulk_insert.bat is no longer the main entry.
echo Use bin\insert_csv.bat --dry-run first, then bin\insert_csv.bat for the actual insert.
exit /b 1
