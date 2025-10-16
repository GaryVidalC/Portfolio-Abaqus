import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from investments.models import Asset, Portfolio, Price, InitialWeight


def _to_decimal(value, *, field_name='valor', allow_empty=False, treat_percent_as_fraction=True):
    """
    Convierte celdas de Excel a Decimal robustamente:
    - Acepta '5%', '5', '0,25', 0.25, etc.
    - Si treat_percent_as_fraction=True: 5% -> 0.05
    - allow_empty: si True, None/NaN -> Decimal('0'); si False, lanza CommandError
    """
    if pd.isna(value):
        if allow_empty:
            return Decimal('0')
        raise CommandError(f"Celda vacía/NaN encontrada en {field_name}")

    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        if allow_empty:
            return Decimal('0')
        raise CommandError(f"Celda vacía/NaN encontrada en {field_name}")

    had_percent = False
    if s.endswith('%'):
        had_percent = True
        s = s[:-1].strip()

    # normaliza coma decimal -> punto
    s = s.replace(',', '.')

    try:
        d = Decimal(s)
    except InvalidOperation:
        raise CommandError(f"No puedo convertir '{value}' a número válido en {field_name}")

    # si venía con %, o si el número parece un porcentaje (5 -> 5%), conviértelo a fracción
    if treat_percent_as_fraction and (had_percent or (d > 1 and d <= 100)):
        d = d / Decimal('100')

    return d


class Command(BaseCommand):
    help = "Importa Weights y Precios desde datos.xlsx (layout específico y robusto)."

    def add_arguments(self, parser):
        parser.add_argument('xlsx_path', type=str)
        # OJO: dd-mm-aaaa
        parser.add_argument('--initial-date', required=True, help='dd-mm-aaaa (ej: 15-02-2022)')
        parser.add_argument('--v0', default='1000000000')
        parser.add_argument('--weights-sheet', default=None, help='Nombre exacto de hoja de pesos (ej: weights)')
        parser.add_argument('--prices-sheet', default=None, help='Nombre exacto de hoja de precios (ej: precios)')

    def handle(self, *args, **opts):
        xlsx_path = opts['xlsx_path']

        # 1) t0 en dd-mm-aaaa
        try:
            t0 = datetime.strptime(opts['initial_date'], '%d-%m-%Y').date()
        except Exception:
            raise CommandError("Formato de --initial-date debe ser dd-mm-aaaa (ej: 15-02-2022)")

        V0 = _to_decimal(opts['v0'], field_name='--v0', treat_percent_as_fraction=False)

        # 2) Abrir Excel
        try:
            xls = pd.ExcelFile(xlsx_path)
        except Exception as e:
            raise CommandError(f"No pude abrir {xlsx_path}: {e}")

        # 3) Resolver nombres de hoja (tolerante a may/min)
        sheet_map = {s.lower(): s for s in xls.sheet_names}
        weights_name_wanted = (opts.get('weights_sheet') or 'weights')
        prices_name_wanted  = (opts.get('prices_sheet')  or 'precios')

        if weights_name_wanted.lower() not in sheet_map:
            raise CommandError(f"La hoja '{weights_name_wanted}' no existe. Disponibles: {xls.sheet_names}")
        if prices_name_wanted.lower() not in sheet_map:
            raise CommandError(f"La hoja '{prices_name_wanted}' no existe. Disponibles: {xls.sheet_names}")

        weights_name = sheet_map[weights_name_wanted.lower()]
        prices_name  = sheet_map[prices_name_wanted.lower()]

        # 4) Leer hojas
        try:
            df_w = pd.read_excel(xls, weights_name)
        except Exception as e:
            raise CommandError(f"No pude leer hoja '{weights_name}': {e}")

        try:
            df_p = pd.read_excel(xls, prices_name)
        except Exception as e:
            raise CommandError(f"No pude leer hoja '{prices_name}': {e}")

        # 5) Portafolios
        p1, _ = Portfolio.objects.get_or_create(
            name='Portafolio 1', defaults={'initial_value': V0, 'initial_date': t0}
        )
        p2, _ = Portfolio.objects.get_or_create(
            name='Portafolio 2', defaults={'initial_value': V0, 'initial_date': t0}
        )
        for p in (p1, p2):
            p.initial_value = V0
            p.initial_date = t0
            p.save()

        # =========================
        # 6) WEIGHTS (tu layout)
        #     Fecha | activos | portafolio 1 | portafolio 2
        # =========================
        dfw = df_w.copy()
        col_map = {str(c).strip().lower(): c for c in dfw.columns}

        date_col = col_map.get('fecha')
        asset_col = col_map.get('activos') or col_map.get('activo') or col_map.get('asset') or col_map.get('assets')
        p1_col = (col_map.get('portafolio 1') or col_map.get('portfolio 1') or col_map.get('p1') or col_map.get('1'))
        p2_col = (col_map.get('portafolio 2') or col_map.get('portfolio 2') or col_map.get('p2') or col_map.get('2'))

        missing = [name for name, col in [
            ('Fecha', date_col),
            ('activos', asset_col),
            ('portafolio 1', p1_col),
            ('portafolio 2', p2_col),
        ] if col is None]
        if missing:
            raise CommandError(f"En la hoja '{weights_name}' faltan columnas: {missing}. Encabezados: {list(dfw.columns)}")

        # Fecha en dd-mm-aaaa
        try:
            dfw[date_col] = pd.to_datetime(dfw[date_col], dayfirst=True).dt.date
        except Exception as e:
            raise CommandError(f"No pude convertir la columna '{date_col}' a fecha (dd-mm-aaaa). Error: {e}")

        # Solo filas con Fecha == t0
        dfw_t0 = dfw[dfw[date_col] == t0].copy()
        if dfw_t0.empty:
            fechas_disponibles = sorted(dfw[date_col].dropna().unique().tolist())
            raise CommandError(
                f"No encontré filas en weights con Fecha == {t0}. "
                f"Fechas disponibles: {fechas_disponibles[:10]}{'...' if len(fechas_disponibles)>10 else ''}"
            )

        count_weights = 0
        for _, row in dfw_t0.iterrows():
            asset_name = str(row[asset_col]).strip()
            if not asset_name or asset_name.lower() in ('nan', 'none'):
                continue
            a, _ = Asset.objects.get_or_create(name=asset_name)

            w1 = _to_decimal(row[p1_col], field_name=f"Weights[{asset_name}]-P1", allow_empty=False)
            w2 = _to_decimal(row[p2_col], field_name=f"Weights[{asset_name}]-P2", allow_empty=False)

            InitialWeight.objects.update_or_create(portfolio=p1, asset=a, defaults={'weight': w1})
            InitialWeight.objects.update_or_create(portfolio=p2, asset=a, defaults={'weight': w2})
            count_weights += 1

        # Guarda el set de activos válidos (los que existen en weights para t0)
        assets_t0 = list(InitialWeight.objects.filter(portfolio__in=[p1, p2])
                        .values_list('asset__name', flat=True).distinct())
        assets_t0 = [str(a).strip() for a in assets_t0]

        self.stdout.write(self.style.SUCCESS(f"Weights importados para t0={t0} (filas: {count_weights})."))

        # =========================
        # 7) PRECIOS (Dates | activo 1 | ... | activo n)
        #   - Dates en dd-mm-yyyy
        #   - Columnas de activos deben ser las mismas que en weights (t0)
        #   - Import rápido con bulk_create por lotes
        # =========================
        from django.db import transaction

        dfp = df_p.copy()

        # Normaliza cabeceras (quedará 'date' + nombres de activos)
        date_col_p = dfp.columns[0]
        dfp.rename(columns={date_col_p: 'date'}, inplace=True)

        # Parsear fechas dayfirst (dd-mm-yyyy)
        try:
            dfp['date'] = pd.to_datetime(dfp['date'], dayfirst=True, errors='coerce').dt.date
        except Exception:
            raise CommandError(f"No pude convertir la columna fecha '{date_col_p}' a datetime en '{prices_name}'")

        if dfp['date'].isna().any():
            bad = dfp[dfp['date'].isna()].head(5)
            raise CommandError(f"Hay fechas no parseables en '{prices_name}'. Ejemplos:\n{bad}")

        # Normaliza nombres de columnas de activos (strip espacios)
        col_renames = {}
        for c in dfp.columns[1:]:
            new_c = str(c).strip()
            if new_c != c:
                col_renames[c] = new_c
        if col_renames:
            dfp.rename(columns=col_renames, inplace=True)

        # Verifica que todos los activos de weights estén presentes como columnas en precios
        price_asset_cols = [str(c).strip() for c in dfp.columns[1:]]
        missing_in_prices = [a for a in assets_t0 if a not in price_asset_cols]
        extra_in_prices   = [c for c in price_asset_cols if c not in assets_t0]

        if missing_in_prices:
            raise CommandError(
                "Faltan columnas de precios para algunos activos definidos en weights (t0): "
                f"{missing_in_prices}. Columnas encontradas en precios: {price_asset_cols}"
            )

        # Opcional: si hay columnas extra en precios que no están en weights, las ignoramos
        use_cols = ['date'] + assets_t0
        dfp = dfp[use_cols]

        print(f"[Precios] shape={dfp.shape} (filas x columnas). Importando {len(assets_t0)} activos en lotes...")

        # Pre-cargar Asset objects
        asset_map = {a.name: a for a in Asset.objects.filter(name__in=assets_t0)}
        # Por si faltara alguno (no debería si ya vinieron de weights)
        missing_assets = [n for n in assets_t0 if n not in asset_map]
        if missing_assets:
            Asset.objects.bulk_create([Asset(name=n) for n in missing_assets], ignore_conflicts=True)
            asset_map.update({a.name: a for a in Asset.objects.filter(name__in=missing_assets)})

        # Bulk insert de Price
        BATCH_SIZE = 5000
        batch = []
        created_total = 0

        def flush_batch():
            nonlocal batch, created_total
            if not batch:
                return
            Price.objects.bulk_create(batch, batch_size=2000, ignore_conflicts=True)
            created_total += len(batch)
            batch = []

        with transaction.atomic():
            for r_idx, row in dfp.iterrows():
                d = row['date']
                for asset_name in assets_t0:
                    a = asset_map[asset_name]
                    raw = row[asset_name]
                    # Convierte a Decimal (sin % en precios)
                    price = _to_decimal(raw, field_name=f"Precio[{asset_name}] {d}",
                                        allow_empty=False, treat_percent_as_fraction=False)
                    batch.append(Price(asset=a, date=d, price=price))
                    if len(batch) >= BATCH_SIZE:
                        flush_batch()
                # progreso
                # if (r_idx + 1) % 50 == 0:
                #     print(f"[Precios] filas procesadas: {r_idx + 1}/{dfp.shape[0]}")

            flush_batch()
        
        # print(df_w.head(10))
        # print(df_w.dtypes)

        # print(df_p.head(5))
        # print(df_p.dtypes)
        
        #print(f"[Precios] celdas importadas: ~{created_total}.")
        self.stdout.write(self.style.SUCCESS(
            f'Import OK (weights="{weights_name}", prices="{prices_name}") '
            f'-> activos={len(assets_t0)}, filas_precio={dfp.shape[0]}'
        ))

