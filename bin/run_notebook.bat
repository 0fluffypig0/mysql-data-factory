@echo off
chcp 65001 >nul
echo [REFERENCE ONLY] Notebook is not the main entry in the minimal workflow.
echo The offline runtime no longer packages Jupyter as a required dependency.
echo Use bin\test_connection.bat, bin\export_sample.bat, bin\expand_rows.bat, and bin\insert_csv.bat.
exit /b 1
