@echo off
echo === INICIO ETL LUFT %date% %time% ===

cd /d C:\Users\keyrus\etl_luft

echo --- ETL PROTHEUS ---
python etl_protheus.py

echo --- ETL SILT ---
python etl_silt.py

echo === FIM ETL LUFT %date% %time% ===
