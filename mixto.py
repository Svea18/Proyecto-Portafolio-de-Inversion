"""Carteras mixtas: proporción de renta fija preestablecida, renta variable optimizable."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from motor import DATA, TRAIN_START, TRAIN_END, TEST_START, TEST_END, DAYS

ASIGNACION={'Conservador':(.70,.30),'Balanceado':(.40,.60),'Agresivo':(.00,1.00)}
# El máximo de 40% se aplica SOLO al minifondo de acciones.
MAX_PESO_ACCION_VARIABLE = 0.40
def tope_accion(perfil):
    return ASIGNACION[perfil][1] * MAX_PESO_ACCION_VARIABLE



def renta_fija(market, fechas):
    """Retornos diarios de TBIL (cierre ajustado) o CETES 28d (tasa anual histórica)."""
    fechas=pd.DatetimeIndex(fechas)
    if market=='US':
        ruta=DATA/'precios_TBIL.csv'
        if not ruta.exists():
            raise FileNotFoundError('Falta datos/precios_TBIL.csv. Ejecuta python preparar.py')
        b=pd.read_csv(ruta,index_col=0,parse_dates=True).iloc[:,0].astype(float).sort_index()
        b=b.reindex(fechas).ffill(limit=3)
        if b.isna().sum() or (b<=0).any():
            raise ValueError('Histórico de TBIL incompleto.')
        r=b.pct_change(fill_method=None).fillna(0)
        return r.rename('TBIL (Treasury 3M)')
    ruta=DATA/'tasas_cetes_28d.csv'
    if not ruta.exists():
        raise FileNotFoundError('Falta datos/tasas_cetes_28d.csv. Consulta LEEME.md para importar tasas históricas de Banxico; no se simularán.')
    df=pd.read_csv(ruta)
    if not {'Fecha','TasaAnualPct'}.issubset(df.columns):
        raise ValueError('CETES requiere las columnas Fecha,TasaAnualPct y fechas reales históricas.')
    df['Fecha']=pd.to_datetime(df.Fecha,errors='coerce')
    df['TasaAnualPct']=pd.to_numeric(df.TasaAnualPct,errors='coerce')
    ser=df.dropna().drop_duplicates('Fecha',keep='last').set_index('Fecha')['TasaAnualPct'].sort_index()
    if ser.empty or (ser<0).any() or (ser>100).any():
        raise ValueError('Tasas CETES vacías o fuera de rango.')
    # 40 días calendario aprox. para observaciones mensuales; no extrapolar años desconocidos.
    union=ser.index.union(fechas).sort_values()
    diaria=ser.reindex(union).ffill().reindex(fechas)
    last=ser.index.searchsorted(fechas,side='right')-1
    age=np.array([(t-ser.index[i]).days if i>=0 else 99999 for t,i in zip(fechas,last)])
    if diaria.isna().any() or (age>40).any():
        raise ValueError('CETES: fechas sin tasa histórica próxima válida (máximo 40 días); completa el CSV.')
    return pd.Series((1+diaria.to_numpy()/100)**(1/DAYS)-1,index=fechas,name='CETES 28 días')


def rendimientos_conjuntos(market,prices,names):
    px=prices[names].dropna()
    r=px.pct_change(fill_method=None).iloc[1:]
    bond=renta_fija(market,px.index).iloc[1:]
    return r.join(bond)


def parametros(market,prices,names,table):
    # Las acciones usan 2016-2025 en la tabla de promedios, pero para la
    # covarianza con TBIL se usan exclusivamente las fechas en las que TBIL existe.
    # Esto evita crear rendimientos sintéticos del ETF anteriores a 2022.
    periodo=prices.loc[TRAIN_START:TRAIN_END]
    if market=='US':
        ruta=DATA/'precios_TBIL.csv'
        if not ruta.exists(): raise FileNotFoundError('Falta precios_TBIL.csv')
        inicio_tbil=pd.read_csv(ruta,index_col=0,parse_dates=True).dropna().index.min()
        periodo=periodo.loc[inicio_tbil:]
    r=rendimientos_conjuntos(market,periodo,names)
    if len(r)<250: raise ValueError('Pocos datos coincidentes entre acciones y renta fija.')
    cov=r.cov().to_numpy()*DAYS
    # Estimación lineal anualizada de renta fija con rentabilidad compuesta en US y tasas sucesivas en MX.
    bond_mu=float((1+r.iloc[:,-1]).prod()**(DAYS/len(r))-1)
    mu=np.r_[table.loc[names,'retorno_historico_anual'].to_numpy(),bond_mu]
    return mu,cov


def evaluar(market,prices,names,table,perfil,pesos_acciones,rf=0.):
    b,e=ASIGNACION[perfil]
    w=np.r_[np.asarray(pesos_acciones,float),b]
    if abs(sum(w)-1)>1e-5 or min(w)<-1e-7 or max(w[:-1],default=0)>tope_accion(perfil)+1e-6:
        raise ValueError('Pesos inválidos: deben sumar 100% y ninguna acción superar el 40% de la parte variable.')
    mu,cov=parametros(market,prices,names,table)
    ret=float(w@mu); vol=float(np.sqrt(max(w@cov@w,0)))
    return {'retorno':ret,'volatilidad':vol,'sharpe':(ret-rf)/vol if vol>0 else np.nan,
            'bonos':b,'acciones':e,'retorno_bonos':float(mu[-1])}


def optimizar(market,prices,names,table,perfil,criterio='sharpe',rf=0.,target=None):
    b,e=ASIGNACION[perfil]
    if e<=0:return np.zeros(len(names))
    mu,cov=parametros(market,prices,names,table)
    n=len(names); x0=np.full(n,e/n)
    bounds=[(0,tope_accion(perfil))]*n
    cs=[{'type':'eq','fun':lambda x:sum(x)-e}]
    if target is not None:cs.append({'type':'eq','fun':lambda x:float(np.r_[x,b]@mu)-target})
    def obj(x):
        w=np.r_[x,b];variance=max(w@cov@w,1e-14)
        if criterio=='minvar' or target is not None:return variance
        if criterio=='return':return -float(w@mu)
        if criterio=='minreturn':return float(w@mu)
        return -(float(w@mu)-rf)/np.sqrt(variance)
    ans=minimize(obj,x0,bounds=bounds,constraints=cs,method='SLSQP',options={'ftol':1e-11,'maxiter':2000})
    if not ans.success or abs(sum(ans.x)-e)>1e-5 or max(ans.x)>tope_accion(perfil)+1e-6:
        raise ValueError('No pudo converger con estas restricciones: '+ans.message)
    return np.clip(ans.x,0,tope_accion(perfil))


def frontera(market,prices,names,table,perfil,rf=0.,pasos=25):
    mini=optimizar(market,prices,names,table,perfil,'minvar',rf)
    maxi=optimizar(market,prices,names,table,perfil,'return',rf)
    lo=evaluar(market,prices,names,table,perfil,mini,rf)['retorno']
    hi=evaluar(market,prices,names,table,perfil,maxi,rf)['retorno']
    puntos=[]
    for v in np.linspace(lo,hi,pasos):
        try:
            w=optimizar(market,prices,names,table,perfil,'minvar',rf,float(v))
            m=evaluar(market,prices,names,table,perfil,w,rf)
            puntos.append({'riesgo':m['volatilidad'],'rendimiento':m['retorno']})
        except ValueError:pass
    return pd.DataFrame(puntos)


def curva_markowitz_completa(market,prices,names,table,perfil,rf=0.,pasos=75):
    """Ambas ramas de mínima varianza condicionada al retorno: C factible.
    La rama inferior es ineficiente en media-varianza.
    """
    lo=optimizar(market,prices,names,table,perfil,'minreturn',rf)
    hi=optimizar(market,prices,names,table,perfil,'return',rf)
    mv=optimizar(market,prices,names,table,perfil,'minvar',rf)
    def er(w):return evaluar(market,prices,names,table,perfil,w,rf)['retorno']
    minimum,maximum,vertex=er(lo),er(hi),er(mv)
    samples=[]
    for target in np.linspace(minimum,maximum,pasos):
        try:
            w=optimizar(market,prices,names,table,perfil,'minvar',rf,target=float(target))
            m=evaluar(market,prices,names,table,perfil,w,rf)
            samples.append({'riesgo':m['volatilidad'],'rendimiento':m['retorno'],
                            'rama':'Eficiente' if target>=vertex-1e-8 else 'Ineficiente'})
        except ValueError:pass
    # La cartera de tangencia se optimiza directamente y no se aproxima a la malla.
    try:
        tang=optimizar(market,prices,names,table,perfil,'sharpe',rf)
        tang_metrics=evaluar(market,prices,names,table,perfil,tang,rf)
    except ValueError:
        top=[row for row in samples if row['rama']=='Eficiente' and row['riesgo']>1e-10]
        if not top:raise ValueError('No existen puntos eficientes para calcular tangencia')
        tang_metrics=max(top,key=lambda m:(m['rendimiento']-rf)/m['riesgo'])
    return pd.DataFrame(samples),tang_metrics


def backtest_mixto(market,prices,names,perfil,pesos_acciones):
    b,_=ASIGNACION[perfil]
    p=prices.loc[TEST_START:TEST_END,names].dropna()
    if len(p)<140:raise ValueError('Backtest con pocas observaciones')
    equity_values=(p/p.iloc[0]).to_numpy()@np.asarray(pesos_acciones,float)
    # Las contribuciones del bono se reinvierten diariamente; las acciones son buy-and-hold.
    rb=renta_fija(market,p.index)
    bond_values=b*(1+rb).cumprod().to_numpy()/(1+rb.iloc[0])
    wealth=pd.Series(equity_values+bond_values,index=p.index,name='Portafolio mixto')
    dr=wealth.pct_change(fill_method=None).dropna()
    result={'inicio_real':str(p.index[0].date()),'fin_real':str(p.index[-1].date()),
            'rendimiento_periodo':float(wealth.iloc[-1]-1),
            'volatilidad_anualizada':float(dr.std()*np.sqrt(DAYS)),
            'caida_maxima':float((wealth/wealth.cummax()-1).min())}
    return wealth,result


def carteras_factibles(market,prices,names,table,perfil,cantidad=1500,semilla=2026):
    """Muestra reproducible de carteras admisibles, no pretende enumerar un continuo infinito."""
    b,e=ASIGNACION[perfil]
    mu,cov=parametros(market,prices,names,table)
    rng=np.random.default_rng(semilla)
    n=len(names)
    if e<=0:return pd.DataFrame(columns=['riesgo','rendimiento'])
    out=[]
    # Dirichlet condicionada a que ningún peso exceda 40% del subportafolio de renta variable.
    trials=0
    while len(out)<cantidad and trials<max(15000,cantidad*35):
        trials+=1
        v=rng.dirichlet(np.full(n,1.4))*e
        if np.max(v)>tope_accion(perfil)+1e-10:continue
        w=np.r_[v,b]
        out.append((float(np.sqrt(max(w@cov@w,0))),float(w@mu)))
    return pd.DataFrame(out,columns=['riesgo','rendimiento'])


def curva_libre_completa(market, prices, table, rf=0., pasos=39, peso_fijo=0.):
    """Frontera C libre de 10 acciones, con renta fija del visitante CONSTANTE.

    Primero el usuario elige libremente el porcentaje de CETES/TBIL; aquí no
    se cambia. Se optimiza cómo repartir el RESTO entre las diez acciones, sin
    tope 40% y sin posiciones negativas, sobre el universo completo. Así el
    punto de su cartera es factible en ESTA misma frontera.

    Excepción: cuando alguien eligió 100% CETES/TBIL no existe frontera para
    su decisión (es un único punto). Para visualizar la C se usa como referencia
    un universo 100% de renta variable, identificado en la interfaz.
    """
    from catalogo import US,MX
    if not 0<=peso_fijo<=1:raise ValueError('Peso de renta fija fuera de [0,1].')
    stock_tickers=list((US if market=='US' else MX).keys())
    mu,cov=parametros(market,prices,stock_tickers,table)
    n=len(stock_tickers)
    b=float(peso_fijo) if peso_fijo<1-1e-9 else 0.
    e=1.-b
    stockmu=mu[:-1]
    bounds=[(0.,1.)]*n
    con_sum={'type':'eq','fun':lambda w:float(np.sum(w)-1.)}
    equal=np.full(n,1./n)
    def complete(x):return np.r_[x*e,b]
    def variance(x):
        w=complete(x)
        return float(w@cov@w)
    def expected(x):return float(complete(x)@mu)
    def solve(fun,start,cs):
        res=minimize(fun,start,bounds=bounds,constraints=cs,method='SLSQP',
                     options={'ftol':1e-10,'maxiter':650})
        if not res.success or abs(np.sum(res.x)-1)>1e-5:
            raise ValueError('Frontera libre: optimización no convergió: '+str(res.message))
        return np.clip(res.x,0,1.)
    low=np.eye(n)[int(np.argmin(stockmu))]
    high=np.eye(n)[int(np.argmax(stockmu))]
    retmin=expected(low);retmax=expected(high)
    mv=solve(variance,equal,[con_sum])
    ret_vertex=expected(mv)
    rows=[]
    for val in np.linspace(retmin,retmax,pasos):
        if abs(val-retmin)<1e-9:x=low
        elif abs(val-retmax)<1e-9:x=high
        else:
            frac=(val-retmin)/(retmax-retmin)
            initial=(1-frac)*low+frac*high
            target_con={'type':'eq','fun':lambda x,v=val:float(expected(x)-v)}
            try:x=solve(variance,initial,[con_sum,target_con])
            except ValueError:continue
        rows.append({'riesgo':float(np.sqrt(max(variance(x),0.))),
                     'rendimiento':expected(x),
                     'rama':'Eficiente' if val>=ret_vertex-1e-8 else 'Ineficiente'})
    def neg_sharpe(x):
        return -(expected(x)-rf)/np.sqrt(max(variance(x),1e-14))
    candidate=[]
    for initial in (equal,mv,high):
        try:candidate.append(solve(neg_sharpe,initial,[con_sum]))
        except ValueError:pass
    if not candidate:raise ValueError('No fue posible optimizar Sharpe de la cartera libre.')
    tangent=max(candidate,key=lambda x:-neg_sharpe(x))
    report={'retorno':expected(tangent),
            'volatilidad':float(np.sqrt(max(variance(tangent),0.))),
            'sharpe':float(-neg_sharpe(tangent))}
    return pd.DataFrame(rows),report
