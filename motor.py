"""Motor sin red: optimización previa, diversificación y backtest sin look-ahead."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from catalogo import US, MX

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'datos'
TRAIN_START='2016-01-01'
TRAIN_END='2025-12-31'
TEST_START='2026-01-02'
TEST_END='2026-09-30'
CAP=.40
N=6
DAYS=252

def load(market):
    file=DATA/f'precios_{market}.csv'
    if not file.exists():
        raise FileNotFoundError(f'No se encontró {file.name}. Ejecuta: python preparar.py')
    p=pd.read_csv(file,index_col=0,parse_dates=True).sort_index()
    tick=list((US if market=='US' else MX).keys())
    missing=[t for t in tick if t not in p.columns]
    if missing: raise ValueError('Faltan '+str(len(missing))+' acciones: '+', '.join(missing[:12]))
    p=p[tick].apply(pd.to_numeric,errors='coerce')
    # Reject data with less than 18 months before backtest, or no backtest observations
    a=p.loc[TRAIN_START:TRAIN_END]; b=p.loc[TEST_START:TEST_END]
    if len(a)<2000 or len(b)<140: raise ValueError('Se necesitan diez años (2016-2025; mínimo 2000 sesiones) y suficientes datos para 2026. Ejecuta python preparar.py.')
    if a.notna().sum().min()<2000 or b.notna().sum().min()<140:
        raise ValueError('Alguna acción tiene menos de 2000 observaciones entre 2016 y 2025 o menos de 140 en 2026. Revisa CSV.')
    return p

def stats(p):
    # Restrict estimation to training data, exclude look-ahead
    train=p.loc[TRAIN_START:TRAIN_END]
    r=train.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
    # Drop price gaps only for correlations, avoid forward-filling returns
    r=r.dropna(axis=0,how='any')
    if len(r)<1900: raise ValueError('Faltan al menos 1900 días comunes válidos entre 2016 y 2025.')
    # Media ARITMÉTICA anualizada de rendimientos diarios (2016–2025).
    # Antes se utilizaba CAGR geométrico: (1+r).prod()**(DAYS/len(r))-1
    # Este cambio no excluye ni neutraliza la pandemia: todas las observaciones permanecen.
    mu=r.mean()*DAYS
    cov=r.cov()*DAYS
    vol=pd.Series(np.sqrt(np.diag(cov)),index=cov.index)
    corr=r.corr()
    # percentile ranks: low/medium/high within market
    risk=pd.Series(np.minimum(3,1+np.floor(vol.rank(method='first',pct=True)*3-1e-9).astype(int)),index=cov.index)
    reward=pd.Series(np.minimum(3,1+np.floor(mu.rank(method='first',pct=True)*3-1e-9).astype(int)),index=cov.index)
    table=pd.DataFrame({'retorno_historico_anual':mu,'volatilidad_anual':vol,'riesgo_puntos':risk,'rendimiento_puntos':reward})
    return table,cov,corr

def metrics(tickers,weights,table,cov,rf=0):
    w=np.array(weights,dtype=float)
    mu=table.loc[tickers,'retorno_historico_anual'].to_numpy()
    s=cov.loc[tickers,tickers].to_numpy()
    ret=float(w@mu)
    vol=float(np.sqrt(max(w@s@w,0)))
    return dict(retorno=ret,volatilidad=vol,sharpe=(ret-rf)/vol if vol>0 else np.nan)

def optimize(names,table,cov,kind='sharpe',rf=0,target=None,fixed=None):
    n=len(names); mu=table.loc[names,'retorno_historico_anual'].to_numpy(); s=cov.loc[names,names].to_numpy()
    if n*CAP < 1-1e-9: raise ValueError('No hay suficientes acciones para cumplir máximo 40%.')
    fixed=fixed or {}
    fixed={names.index(k):float(v) for k,v in fixed.items() if k in names}
    if sum(fixed.values())>1+1e-8: raise ValueError('Los pesos fijados superan 100%.')
    bounds=[(v,v) if i in fixed else (0,CAP) for i,v in enumerate([fixed.get(i,0.) for i in range(n)])]
    if 1-sum(fixed.values())>(n-len(fixed))*CAP+1e-8:
        raise ValueError('Restricciones imposibles: capacidad restante insuficiente.')
    cons=[{'type':'eq','fun':lambda w:np.sum(w)-1}]
    if target is not None: cons.append({'type':'eq','fun':lambda w:float(w@mu)-target})
    def obj(w):
        variance=max(float(w@s@w),1e-12)
        if kind=='minvar' or target is not None:return variance
        if kind=='return':return -float(w@mu)
        return -(float(w@mu)-rf)/np.sqrt(variance)
    x=np.full(n,1/n)
    if fixed:
        free=[i for i in range(n) if i not in fixed]
        x=np.zeros(n); rem=1-sum(fixed.values())
        for i,v in fixed.items():x[i]=v
        for i in free:x[i]=rem/len(free)
    out=minimize(obj,x,method='SLSQP',bounds=bounds,constraints=cons,options={'maxiter':2000,'ftol':1e-11})
    if not out.success or abs(out.x.sum()-1)>1e-5 or np.max(out.x)>CAP+1e-6:
        raise ValueError('Optimización no convergente o restricciones inviables: '+out.message)
    return np.maximum(out.x,0)

def diversify(table,corr,risk_group,k=6,abs_corr=.80,preferencias=None):
    # score suitability while preferring less correlated assets
    risk_target={'Conservador':1,'Balanceado':2,'Agresivo':3}[risk_group]
    return_target={'Conservador':1,'Balanceado':2,'Agresivo':3}[risk_group]
    pref=(4-abs(table.riesgo_puntos-risk_target)*1.4-abs(table.rendimiento_puntos-return_target)*.85)
    # Bonus por empresas destacadas en los diez años y en 2026.
    # Se usa únicamente en el modo retrospectivo explícito; NO en modo backtest.
    if preferencias is not None:
        pref=pref + 2.5*preferencias.reindex(pref.index).fillna(0)
    names=list(table.index)
    chosen=[]
    while len(chosen)<k:
        candidates=[]
        for t in names:
            if t in chosen:continue
            links=np.abs(corr.loc[t,chosen].to_numpy()) if chosen else np.array([])
            avg=float(links.mean()) if len(links) else 0
            mx=float(links.max()) if len(links) else 0
            # hard cap when possible; graceful relaxation only if 50 market stocks highly correlated
            score=float(pref.loc[t])-2.2*avg-1.5*max(0,mx-abs_corr)
            candidates.append((score,-mx,t))
        if not candidates:raise ValueError('No hay acciones suficientes')
        candidates.sort(reverse=True)
        chosen.append(candidates[0][2])
    return chosen

def candidates(table,cov,corr,rf=0,precios=None,retrospectivo=False):
    # En el modo habitual SOLO 2016-2025 determina las inversiones.
    # En modo demostración retrospectiva, reforzamos empresas que rindieron bien
    # tanto en la década pasada como entre enero y septiembre de 2026.
    # Esa elección usa información futura respecto al inicio del backtest.
    bonus=None
    if retrospectivo:
        if precios is None: raise ValueError('Se necesitan precios para selección retrospectiva.')
        test=precios.loc[TEST_START:TEST_END].dropna()
        if len(test)<140: raise ValueError('Datos incompletos de 2026.')
        year_return=test.iloc[-1]/test.iloc[0]-1
        long_return=table['retorno_historico_anual']
        # Ranking combinado de ambos periodos; valores positivos en ambos
        # reciben puntuación. No garantizamos que 2026 siga siendo rentable.
        score=(year_return.rank(pct=True)*0.5+long_return.rank(pct=True)*0.5)
        bonus=score.where((year_return>0)&(long_return>0),0)
    results=[]
    for profile in ['Conservador','Balanceado','Agresivo']:
        names=diversify(table,corr,profile,preferencias=bonus)
        # En esta etapa auxiliar se compara riesgo/retorno de la canasta, sin fijar ponderaciones.
        # La optimización mixta final en app.py/mixto.py maximiza Sharpe.
        kind='sharpe'
        w=optimize(names,table,cov,kind=kind,rf=rf)
        m=metrics(names,w,table,cov,rf)
        vals=np.abs(corr.loc[names,names].to_numpy())
        vals=vals[np.triu_indices(len(names),1)]
        results.append({'perfil':profile,'tickers':names,'pesos':w,'correlacion_media_abs':float(vals.mean()),'correlacion_max_abs':float(vals.max()),**m})
    return results

def frontier(names,table,cov,rf=0,steps=28):
    lo=optimize(names,table,cov,'minvar',rf)
    hi=optimize(names,table,cov,'return',rf)
    minimum=metrics(names,lo,table,cov)['retorno']
    maximum=metrics(names,hi,table,cov)['retorno']
    out=[]
    for goal in np.linspace(minimum,maximum,steps):
        try:
            w=optimize(names,table,cov,'minvar',rf,target=float(goal))
            m=metrics(names,w,table,cov,rf)
            out.append({'rendimiento':m['retorno'],'riesgo':m['volatilidad']})
        except ValueError:continue
    return pd.DataFrame(out)

def backtest(p,names,w):
    prices=p.loc[TEST_START:TEST_END,names].dropna()
    if len(prices)<140:raise ValueError('Backtest sin fechas comunes suficientes')
    # Jan 2 is first US market trading day of 2026; when absent starts first available session
    start=prices.index[0]
    if start>pd.Timestamp('2026-01-09'):raise ValueError('La primera sesión está demasiado lejos del 2 de enero de 2026')
    # constant share holdings / initial weight, rebalance only at inception
    wealth=(prices/prices.iloc[0]).to_numpy() @ np.array(w)
    growth=pd.Series(wealth,index=prices.index,name='Cartera')
    realized=float(growth.iloc[-1]-1)
    drawdown=float((growth/growth.cummax()-1).min())
    daily=growth.pct_change().dropna()
    realized_vol=float(daily.std()*np.sqrt(DAYS))
    return growth,{'inicio_real':str(start.date()),'fin_real':str(prices.index[-1].date()),'rendimiento_periodo':realized,'volatilidad_anualizada':realized_vol,'caida_maxima':drawdown}

def grade(total):
    if total<=13:return 'Conservador'
    if total<=19:return 'Balanceado'
    return 'Agresivo'
