# Django Portfolio Engine

Proyecto Django para modelar portafolios de inversión y responder:
- $C_{i,0}$ : cantidades iniciales por activo
- $V_t$ : valor del portafolio en el tiempo
- $w_{i,t}$ : weights por activo en el tiempo

Incluye:
- ETL desde **datos.xlsx** (sheets `weights` y `Precios`)
- **Bonus 1**: vista con gráficos (Chart.js)
- **Bonus 2**: trades (compra/venta) aplicados al historial
- Switch **con/sin trades** (flag y página separada)

Setup (antes del runserver):
```powershell
# instalar requirements.txt
pip install -r requirements.txt

# migrar
python manage.py migrate

# cargar excel
python manage.py import_xlsx .\datos.xlsx --initial-date 15-02-2022 --weights-sheet weights --prices-sheet Precios



