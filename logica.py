"""Funciones puras y testeables: validación, comparaciones y datos de la gráfica circular."""
from decimal import Decimal, InvalidOperation
import numpy as np
import pandas as pd
from motor import TEST_START, TEST_END, DAYS
from mixto import renta_fija, parametros


def validar_porcentajes(valores):
    """Acepta números escritos a mano; NO redistribuye ni limita a 40%.

    Solo acepta porcentajes entre 0 y 100; la suma decimal debe ser 100 exacto.
    Devuelve (pesos en fracciones, mensaje de error, suma ingresada).
    """
    result={}
    for name, raw in valores.items():
        txt=str(raw).strip().replace(',', '.')
        try: x=Decimal(txt)
        except InvalidOperation: return None, f'En {name} debes escribir un número válido.', None
        if not x.is_finite() or x<0 or x>100:
            return None, f'{name} debe estar entre 0 y 100%.', None
        result[name]=x
    total=sum(result.values(), Decimal('0'))
    if total!=Decimal('100'):
        return None, f'La suma es {total:.2f}%. Debe ser exactamente 100% para continuar.', float(total)
    return {k:float(v/100) for k,v in result.items()}, None, 100.0


def activos_visibles(pesos, etiquetas, epsilon=0.00005):
    """Excluye posiciones no activas; p.ej. CETES=0 en agresivo.

    epsilon=0.005% del total; se omiten residuos numéricos del optimizador.
    """
    return pd.DataFrame([
        {'Activo':etiquetas.get(k,k), 'Peso':float(w)}
        for k,w in pesos.items() if float(w)>epsilon
    ])


def serie_cartera_libre(market,prices,pesos):
    """Backtesting compra y conserva: acciones por sus precios y bonos compuestos.

    Se permite desde 100% de acciones hasta 100% renta fija, sin topes por acción.
    """
    fx='TBIL' if market=='US' else 'CETES'
    names=[k for k,v in pesos.items() if k!=fx and v>0]
    bond=float(pesos.get(fx,0))
    # CASO LÍMITE: 100% renta fija debe reutilizar EXACTAMENTE la serie
    # del benchmark, no recalcularla sobre un calendario distinto.
    # Si cambia el calendario por un dato faltante, recalcular la tasa por día
    # puede crear diferencias artificiales en la gráfica de CETES.
    if not names and abs(bond-1.0)<1e-9:
        return serie_solo_bonos(market,prices).rename('Portafolio creado')
    # Comparación de idénticas sesiones: todas las series parten del mismo día
    # y utilizan los mismos días bursátiles para renta fija y renta variable.
    ref=prices.loc[TEST_START:TEST_END].dropna()
    if names: ref=ref[names]
    else: ref=ref.iloc[:,0].to_frame()
    if len(ref)<140: raise ValueError('El periodo de 2026 no tiene suficientes datos en común.')
    value=np.zeros(len(ref))
    if names:
        value+=(ref[names]/ref[names].iloc[0]).to_numpy()@np.array([pesos[t] for t in names])
    if bond:
        r=renta_fija(market, ref.index)
        # El primer día representa la compra inicial, rendimiento inicial cero.
        value+=bond*((1+r).cumprod()/(1+r.iloc[0])).to_numpy()
    wealth=pd.Series(value,index=ref.index,name='Portafolio creado')
    return wealth


def serie_solo_bonos(market, prices):
    idx=prices.loc[TEST_START:TEST_END].dropna().index
    r=renta_fija(market,idx)
    return pd.Series(((1+r).cumprod()/(1+r.iloc[0])).to_numpy(),index=idx)


def indicadores_cartera_libre(market,prices,table,pesos,rf):
    """A diferencia de perfiles estándar, calcula los indicadores sin topes por activo."""
    bond='TBIL' if market=='US' else 'CETES'
    names=[k for k,v in pesos.items() if k!=bond and v>0]
    if names:
        mu,cov=parametros(market,prices,names,table)
        w=np.array([pesos[k] for k in names]+[pesos.get(bond,0)],dtype=float)
        ret=float(w@mu)
        vol=float(np.sqrt(max(w@cov@w,0)))
    else:
        # El rendimiento de renta fija procede de su serie histórica, no de datos futuros.
        idx=prices.loc['2016-01-01':'2025-12-31'].dropna().index
        if market=='US':
            b=pd.read_csv(__import__('motor').DATA/'precios_TBIL.csv',index_col=0,parse_dates=True).dropna()
            idx=idx[idx>=b.index.min()]
        r=renta_fija(market,idx)
        ret=float((1+r.iloc[1:]).prod()**(DAYS/max(len(r)-1,1))-1)
        vol=float(r.iloc[1:].std()*np.sqrt(DAYS))
    return {'retorno':ret,'volatilidad':vol,'sharpe':(ret-rf)/vol if vol>1e-10 else float('nan')}


def rendimientos_comparados(series):
    """Iguala las fechas y normaliza todas las curvas a 0% en el primer día."""
    common=pd.concat(series,axis=1,join='inner').dropna()
    if len(common)<140: raise ValueError('No hay suficientes días comunes para las curvas.')
    return common.div(common.iloc[0]).sub(1)


def estadisticas_observadas(wealth):
    v=wealth/wealth.iloc[0]
    r=v.pct_change(fill_method=None).dropna()
    return {'rendimiento':float(v.iloc[-1]-1),
            'volatilidad':float(r.std()*np.sqrt(DAYS)),
            'caida':float((v/v.cummax()-1).min())}


def generar_distribucion_aleatoria(activos, rng=None):
    """Elige aleatoriamente entre 2 y 7 activos y reparte 100% exacto.

    Cada peso se representa en centésimas porcentuales (10,000 unidades).
    No hay topes ni se modifica la cartera que el visitante ya había creado.
    """
    items=list(dict.fromkeys(activos))
    if not items:raise ValueError('Se necesita al menos un activo.')
    if rng is None:rng=np.random.default_rng()
    count=int(rng.integers(2,min(7,len(items))+1)) if len(items)>=2 else 1
    indices=rng.choice(len(items),size=count,replace=False)
    proportions=rng.dirichlet(np.ones(count)*1.5)
    # Multinomial produce enteros que suman exactamente 10,000.
    units=rng.multinomial(10000,proportions)
    result=dict.fromkeys(items,0.0)
    for i,unit in zip(indices,units):result[items[int(i)]]=round(int(unit)/100,2)
    assert round(sum(result.values()),2)==100.0
    return result
