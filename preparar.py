"""Descarga UNA SOLA VEZ; app no depende de conexión a Internet."""
from pathlib import Path
import os
import requests
from io import StringIO
import csv
import re
import json
import pandas as pd
import yfinance as yf
from catalogo import US,MX
DEST=Path(__file__).resolve().parent/'datos';DEST.mkdir(exist_ok=True)
for region,catalog in [('US',US),('MX',MX)]:
    result={}; failures={}
    for ticker in catalog:
        try:
            df=yf.download(ticker,start='2016-01-01',end='2026-10-01',auto_adjust=True,progress=False,threads=False,timeout=20)
            if df.empty:raise ValueError('Sin precios')
            close=df['Close'].squeeze()
            if isinstance(close,pd.DataFrame):close=close.iloc[:,0]
            close.index=pd.to_datetime(close.index).tz_localize(None)
            if close.loc['2016-01-01':'2025-12-31'].dropna().shape[0]<2000 or close.loc['2026-01-02':'2026-09-30'].dropna().shape[0]<140:
                raise ValueError('Se requieren al menos 2000 cierres entre 2016 y 2025 y 140 durante 2026')
            result[ticker]=close.rename(ticker)
            print(region,ticker,'OK')
        except Exception as exc:
            failures[ticker]=str(exc);print(region,ticker,'ERROR',exc)
    if len(result)==len(catalog):
        pd.concat(result.values(),axis=1).sort_index().to_csv(DEST/f'precios_{region}.csv')
        print(f'{region}: datos de acciones guardados, entrenamiento 2016-2025, prueba 2026.')
    else:
        print(f'{region}: {len(result)}/{len(catalog)} válidas: No se genera una base incompleta.')
    (DEST/f'errores_{region}.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')

# La descarga de TBIL comienza en 2016, pero solo devuelve fechas desde su creación en 2022.
# NO se inventan precios anteriores a su fecha de lanzamiento.
# Instrumento de renta fija estadounidense. TBIL es ETF de Treasury Bills,
# no cuenta dentro de las 50 acciones; precios AJUSTADOS incluyen distribuciones.
try:
    tbil=yf.download('TBIL',start='2016-01-01',end='2026-10-01',auto_adjust=True,progress=False,threads=False,timeout=30)
    if tbil.empty: raise ValueError('Sin precios TBIL')
    ser=tbil['Close'].squeeze()
    if isinstance(ser,pd.DataFrame):ser=ser.iloc[:,0]
    ser.index=pd.to_datetime(ser.index).tz_localize(None)
    ser.rename('TBIL').to_csv(DEST/'precios_TBIL.csv',header=True)
    print('TBIL: precios ajustados guardados')
except Exception as exc:print('ERROR TBIL',exc)
# Banxico SIE REST requiere token gratuito: https://www.banxico.org.mx/SieAPIRest/
# Serie SF43936: tasa de rendimiento CETES 28 días (verificar metadata).
def leer_csv_cetes_publico(contenido):
    """Lee exportaciones con notas previas y cabeceras variables, sin inventar tasas."""
    contenido = contenido.decode('utf-8-sig', errors='replace')
    if '<html' in contenido[:1000].lower() or '<!doctype html' in contenido[:1000].lower():
        raise ValueError('El servidor devolvió una página HTML, no datos CSV.')
    lineas = contenido.splitlines()
    for idx, linea in enumerate(lineas[:40]):
        if 'fecha' not in linea.lower() and 'date' not in linea.lower():
            continue
        for separador in (',', ';', '\t'):
            try:
                campos = next(csv.reader([linea], delimiter=separador))
            except csv.Error:
                continue
            campos_normalizados = [re.sub(r'[^a-z0-9]', '', campo.lower()) for campo in campos]
            fechas = [i for i,c in enumerate(campos_normalizados) if 'fecha' in c or c=='date']
            tasas = [i for i,c in enumerate(campos_normalizados) if '28' in c and ('cete' in c or 'dias' in c or c in ('28d','28'))]
            if not tasas:
                tasas = [i for i,c in enumerate(campos_normalizados) if '28' in c]
            if not fechas or not tasas or len(campos)<2:
                continue
            try:
                raw = pd.read_csv(StringIO('\n'.join(lineas[idx:])), sep=separador, on_bad_lines='skip', dtype=str)
                fecha_col = raw.iloc[:, fechas[0]].str.strip()
                tasa_col = raw.iloc[:, tasas[0]].str.strip().str.replace('%', '', regex=False)
                fechas_parsed = pd.to_datetime(fecha_col, errors='coerce', format='mixed', dayfirst=False)
                tasas_parsed = pd.to_numeric(tasa_col, errors='coerce')
                dat = pd.DataFrame({'Fecha': fechas_parsed, 'TasaAnualPct': tasas_parsed}).dropna()
                dat = dat.drop_duplicates('Fecha').sort_values('Fecha')
                if len(dat)<100:
                    continue
                if (dat.TasaAnualPct.lt(0) | dat.TasaAnualPct.gt(100)).any():
                    continue
                if dat.Fecha.min()>pd.Timestamp('2016-02-01') or dat.Fecha.max()<pd.Timestamp('2026-09-01'):
                    continue
                return dat
            except Exception:
                continue
    raise ValueError('No se detectó una tabla con columnas de fecha y CETES 28 días, o faltan fechas de 2016-2026. Importa un CSV oficial.')

def preparar_cetes():
    token=os.environ.get('BANXICO_TOKEN','').strip()
    if not token:
        # Copia CSV republicada con atribución a Banxico, no requiere token.
        try:
            url='https://calcu.mx/calculadoras/cetes/tasas.csv'
            response=requests.get(url,timeout=30)
            response.raise_for_status()
            dat=leer_csv_cetes_publico(response.content)
            dat.to_csv(DEST/'tasas_cetes_28d.csv',index=False)
            print('CETES: historial guardado desde CSV de Calcu.mx (fuente indicada: Banxico SIE SF43936).')
            return
        except Exception as exc:
            print('CETES: copia pública no disponible:',exc)
            print('Alternativa: BANXICO_TOKEN o importar CSV Fecha,TasaAnualPct desde la aplicación.')
            return
    url='https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43936/datos/2016-01-01/2026-09-30'
    try:
        response=requests.get(url,headers={'Bmx-Token':token,'Accept':'application/json'},timeout=35)
        response.raise_for_status()
        series=response.json()['bmx']['series'][0]
        # Evitar series confundidas: obligar al usuario a revisar denominación.
        title=str(series.get('titulo',''))
        if '28' not in title or 'cete' not in title.lower():
            raise ValueError(f'La serie no parece CETES 28 días: {title}')
        rows=[]
        for item in series['datos']:
            v=item.get('dato','').replace(',','').strip()
            if not v or v=='N/E':continue
            dt=pd.to_datetime(item['fecha'],dayfirst=True,errors='coerce')
            if pd.notna(dt):rows.append((dt,float(v)))
        df=pd.DataFrame(rows,columns=['Fecha','TasaAnualPct']).drop_duplicates('Fecha').sort_values('Fecha')
        if df.empty or df.Fecha.min()>pd.Timestamp('2016-02-01') or df.Fecha.max()<pd.Timestamp('2026-09-01'):
            raise ValueError('Historia insuficiente: comprobar ID serie y permisos.')
        df.to_csv(DEST/'tasas_cetes_28d.csv',index=False)
        print('CETES: datos Banxico guardados',len(df),'registros')
    except Exception as exc:
        print('CETES: no se pudo importar automáticamente:',exc)
        print('Descarga los datos oficiales de Banxico e impórtalos como datos/tasas_cetes_28d.csv')

preparar_cetes()
