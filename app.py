"""Interfaz Streamlit compartida por la versión pública y la de desarrollador.

FLUJO:
0 mercado -> 1 construir cartera propia -> 2 comprobar desempeño ->
3 cuestionario -> 4 recomendación inalterable -> 5 comparación global y exportación.

Las posiciones propias NUNCA se normalizan automáticamente. La renta fija es una
inversión más al diseñarlas. Solo las carteras OPTIMIZADAS respetan 70/30,
40/60 o 0/100 y 40% máximo dentro del bloque de renta variable.
"""
from __future__ import annotations
import io
import os
import re
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import qrcode
import streamlit.components.v1 as components

from catalogo import US, MX, PREGUNTAS, grade
from logica import generar_distribucion_aleatoria
from reporte_pdf import generar_pdf
from motor import load, stats, candidates, DATA, TEST_START, TEST_END
from mixto import ASIGNACION, optimizar, evaluar, backtest_mixto, renta_fija, curva_markowitz_completa
from logica import (validar_porcentajes, activos_visibles, serie_cartera_libre,
                    serie_solo_bonos, indicadores_cartera_libre,
                    rendimientos_comparados, estadisticas_observadas)

PROFILES=['Conservador','Balanceado','Agresivo']
STAGES=['Mercado','Arma tu cartera','Tu resultado','Cuestionario',
        'Cartera recomendada','Comparación final']
# La misma identidad visual del reporte descargable: marfil, petróleo y cobre.
COLORS={'Tu cartera':'#145668','Recomendado':'#B7804D',
        'Conservador':'#598C80','Balanceado':'#7E99A5','Agresivo':'#976B84',
        'CETES':'#C39B50','TBIL':'#C39B50'}


def config(name,default=''):
    """Lee secretos en el servidor, nunca incrusta contraseñas en el código."""
    try: val=st.secrets.get(name)
    except Exception: val=None
    return str(val or os.environ.get(name,default))


def fixed_name(mkt):return 'TBIL' if mkt=='US' else 'CETES'


def label_market(mkt):return 'Estados Unidos' if mkt=='US' else 'México'


def labels_for(mkt):
    d=US if mkt=='US' else MX
    return {**d,fixed_name(mkt):'TBIL · letras del Tesoro' if mkt=='US' else 'CETES · 28 días'}


def ir_a_pagina(page):
    """Toda navegación pasa aquí: guarda el paso y pide un único salto arriba."""
    st.session_state.page = page
    st.session_state.nav_counter = st.session_state.get('nav_counter', 0) + 1
    if page != 5:
        st.session_state.pop('pdf_report', None)
    st.rerun()


def ensure_defaults():
    st.session_state.setdefault('page', 0)
    st.session_state.setdefault('market', 'MX')
    st.session_state.setdefault('custom_allocations', {})
    st.session_state.setdefault('custom_entry_text', {})
    st.session_state.setdefault('custom_drafts', {})
    st.session_state.setdefault('questionnaire_answers', {})
    st.session_state.setdefault('questionnaire_results', {})
    st.session_state.setdefault('retrospective_dev', True)
    st.session_state.setdefault('nav_counter', 0)
    st.session_state.setdefault('nav_scrolled', 0)


def scroll_to_top_on_navigation():
    """Sube el CONTENEDOR real de Streamlit, solo en cambios de página.

    st.rerun conserva a veces el scroll de la vista. Un pequeño componente
    ejecuta el desplazamiento desde el iframe de Streamlit. Nunca se activa
    por un slider, campo numérico, respuesta o descarga del PDF.
    """
    nonce = st.session_state.get('nav_counter', 0)
    if nonce == st.session_state.get('nav_scrolled', 0):
        return
    st.session_state.nav_scrolled = nonce
    script = """<script>
    (() => {
      const scrollUp = () => {
        try {
          const doc = window.parent.document;
          // Streamlit puede usar distintos contenedores según la versión.
          const anchor = doc.getElementById('top-of-page');
          if (anchor) anchor.scrollIntoView({block:'start',behavior:'instant'});
          const targets = [
            doc.querySelector('section[data-testid="stMain"]'),
            doc.querySelector('[data-testid="stAppViewContainer"]'),
            doc.querySelector('section.main'),
            doc.scrollingElement,
            doc.documentElement,
            doc.body
          ];
          targets.filter(Boolean).forEach(el => {
            try { el.scrollTo({top: 0, left: 0, behavior: 'instant'}); } catch (_) {}
            el.scrollTop = 0;
          });
          window.parent.scrollTo(0, 0);
        } catch (_) {
          // Algunos entornos aislados no permiten acceder a la ventana superior.
          // La navegación sigue funcionando aunque bloqueen el desplazamiento.
        }
      };
      scrollUp();
      requestAnimationFrame(scrollUp);
      setTimeout(scrollUp, 120);
      setTimeout(scrollUp, 320);
    })();
    </script>"""
    # El identificador cambia en cada navegación para forzar remontar el iframe.
    # Streamlit puede reutilizar el HTML anterior si no cambia su contenido/width.
    script = script.replace('(() => {', f'(() => {{ const navigationId = {nonce};')
    components.html(script, width=1 + (nonce % 2), height=1, scrolling=False)


def page_intro(kicker, title, description):
    """Un titular amplio y una sola frase; evita pantallas llenas de instrucciones."""
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="page-title">{title}</h1>', unsafe_allow_html=True)
    if description:
        st.markdown(f'<p class="page-lead">{description}</p>', unsafe_allow_html=True)


def top_navigation():
    """Botones de regreso ARRIBA y navegación a Inicio (además de los inferiores)."""
    stage=st.session_state.page
    if stage==0:return
    col_back,col_start,col_space=st.columns([1.6,1,3.8],vertical_alignment='center')
    with col_back:
        if st.button('← Regresar',key=f'nav_top_back_{stage}',use_container_width=True):
            ir_a_pagina(stage-1)
    with col_start:
        if st.button('⌂ Inicio',key=f'nav_top_home_{stage}',use_container_width=True):
            ir_a_pagina(0)


def back_to_top_fallback():
    """Enlace nativo de respaldo si un navegador bloquea el scroll automático."""
    st.markdown('<div style="text-align:right;margin-top:18px">'
                '<a href="#top-of-page" target="_self" '
                'style="color:#145668;font-size:.85rem;text-decoration:none">'
                '↑ Volver arriba</a></div>', unsafe_allow_html=True)



def sync_slider(market,ticker):
    """Slider → cuadro numérico, sin tocar otras acciones ni normalizar."""
    value=float(st.session_state[f'slider_{market}_{ticker}'])
    st.session_state[f'number_{market}_{ticker}']=value
    st.session_state['custom_drafts'].setdefault(market,{})[ticker]=value


def sync_number(market,ticker):
    """Cuadro numérico → slider; ocurre ANTES de instanciar ambos widgets."""
    value=float(st.session_state[f'number_{market}_{ticker}'])
    st.session_state[f'slider_{market}_{ticker}']=value
    st.session_state['custom_drafts'].setdefault(market,{})[ticker]=value


def randomizar_cartera(market):
    """Genera una asignación aleatoria EXACTA de 100%, sin topes por activo.

    Se ejecuta desde el botón anterior a los widgets para poder actualizar
    el número y el deslizador sin StreamlitWidgetAlreadyInstantiatedError.
    """
    tickers=list((US if market=='US' else MX).keys())+[fixed_name(market)]
    draft=generar_distribucion_aleatoria(tickers)
    st.session_state['custom_drafts'][market]=dict(draft)
    for ticker,value in draft.items():
        st.session_state[f'number_{market}_{ticker}']=value
        st.session_state[f'slider_{market}_{ticker}']=value
    st.session_state.pop('pdf_report',None)


def custom_weight_controls(market):
    """Entrada doble sincronizada, 0–100%, sin límites de perfil ni ajustes automáticos.

    Los borradores se conservan fuera de las keys de Streamlit, que pueden
    desaparecer al dejar de renderizar una pantalla y luego regresar.
    """
    d=st.session_state['custom_drafts'].setdefault(market,{})
    saved=st.session_state.custom_allocations.get(market,{})
    names=labels_for(market)
    tickers=list((US if market=='US' else MX).keys())+[fixed_name(market)]
    st.caption('Arrastra o escribe un porcentaje. Puedes cambiar cualquier valor.')
    labels=st.columns([2.2,1.1,3.5],vertical_alignment='center')
    with labels[0]:st.markdown('**Inversión**')
    with labels[1]:st.markdown('**Porcentaje (%)**')
    with labels[2]:st.markdown('**Ajuste con barra**')
    values={}
    for ticker in tickers:
        current=float(d.get(ticker,round(saved.get(ticker,0)*100,2)))
        sk=f'slider_{market}_{ticker}'
        nk=f'number_{market}_{ticker}'
        if sk not in st.session_state: st.session_state[sk]=current
        if nk not in st.session_state: st.session_state[nk]=current
        col_name,col_num,col_slider=st.columns([2.2,1.1,3.5],vertical_alignment='center')
        with col_name:st.write(names[ticker])
        with col_num:
            st.number_input(f'{names[ticker]} (%)',min_value=0.0,max_value=100.0,
                step=0.01,format='%.2f',label_visibility='collapsed',key=nk,
                on_change=sync_number,args=(market,ticker))
        with col_slider:
            st.slider(f'Barra {names[ticker]}',min_value=0.0,max_value=100.0,
                step=0.01,label_visibility='collapsed',key=sk,
                on_change=sync_slider,args=(market,ticker))
        values[ticker]=float(st.session_state[nk])
        d[ticker]=values[ticker]
    total=round(sum(values.values()),4)
    balance=round(100-total,4)
    st.metric('Llevas asignado',f'{total:.2f}% de 100%')
    if abs(balance)<1e-7:st.success('¡Perfecto! Ya repartiste todo tu dinero.')
    elif balance>0:st.info(f'Te falta repartir {balance:.2f}%.')
    else:st.warning(f'Te pasaste por {-balance:.2f}%. Ajusta tus cantidades.')
    return values


def valid_public_url():
    url=config('APP_PUBLIC_URL').strip()
    p=urlparse(url)
    if p.scheme!='https' or not p.netloc or p.hostname in ('localhost','127.0.0.1'):
        return None
    return url.rstrip('/')


def show_qr():
    url=valid_public_url()
    if url:
        qr=qrcode.QRCode(box_size=7,border=2)
        qr.add_data(url);qr.make(fit=True)
        st.image(qr.make_image(fill_color='black',back_color='white').get_image(),width=172)
        st.caption('Escanea para abrir la aplicación en tu celular.')
        st.code(url,language=None)
    else:
        st.info('QR para celular: primero publica la aplicación y configura APP_PUBLIC_URL con su dirección HTTPS. La dirección localhost solo funciona en esta computadora.')


def heading():
    """Cuatro pasos visibles en vez de una lista técnica de seis pantallas."""
    stage = st.session_state.page
    phase = [1, 1, 2, 3, 4, 4][stage]
    titles = ['Elige y crea', 'Mira cómo te fue', 'Conócete', 'Compara opciones']
    st.progress(phase / 4)
    st.caption(f'PASO {phase} DE 4  ·  {titles[phase-1]}')


@st.cache_data(show_spinner='Analizando diez años y optimizando los perfiles…',max_entries=8)
def preparar_mercado(market,retrospective,file_stamp):
    """Solo se hace una vez por mercado y modo, no en cada botón o input."""
    p=load(market)
    table,cov,corr=stats(p)
    idx=p.loc['2016-01-01':'2025-12-31'].dropna().index
    if market=='US':
        b=pd.read_csv(DATA/'precios_TBIL.csv',index_col=0,parse_dates=True).dropna()
        idx=idx[idx>=b.index.min()]
    rf_ret=renta_fija(market,idx).iloc[1:]
    if rf_ret.empty:raise ValueError('No hay suficientes datos para tasa libre de riesgo.')
    rf=float((1+rf_ret).prod()**(252/len(rf_ret))-1)
    selected=candidates(table,cov,corr,rf,precios=p,retrospectivo=retrospective)
    portfolios={}
    for entry in selected:
        name=entry['perfil'];tickers=entry['tickers']
        weights=optimizar(market,p,tickers,table,name,'sharpe',rf)
        portfolios[name]={'tickers':tickers,'weights':weights}
    return p,table,corr,rf,portfolios


def file_stamp(mkt):
    result=[]
    for filename in (f'precios_{mkt}.csv','precios_TBIL.csv' if mkt=='US' else 'tasas_cetes_28d.csv'):
        path=DATA/filename
        result.append(path.stat().st_mtime_ns if path.exists() else -1)
    return tuple(result)


@st.cache_data(show_spinner=False,max_entries=18)
def backtest_perfil(market,profile,retrospective,stamp):
    p,table,corr,rf,portfolios=preparar_mercado(market,retrospective,stamp)
    x=portfolios[profile]
    return backtest_mixto(market,p,x['tickers'],profile,x['weights'])[0]


@st.cache_data(show_spinner=False,max_entries=12)
def frontier_cached(market,profile,retrospective,stamp):
    p,table,corr,rf,portfolios=preparar_mercado(market,retrospective,stamp)
    return curva_markowitz_completa(market,p,portfolios[profile]['tickers'],table,profile,rf,pasos=37)


@st.cache_data(show_spinner='Calculando la frontera del mercado…',max_entries=5)
def frontier_free_cached(market,stamp,peso_fijo):
    """Frontera SIN topes: representa las opciones libres del visitante.

    Se calcula una sola vez por mercado/archivos históricos y sirve como
    referencia antes de responder el cuestionario.
    """
    from mixto import curva_libre_completa
    p=load(market)
    table,_,_=stats(p)
    idx=p.loc['2016-01-01':'2025-12-31'].dropna().index
    if market=='US':
        b=pd.read_csv(DATA/'precios_TBIL.csv',index_col=0,parse_dates=True).dropna()
        idx=idx[idx>=b.index.min()]
    r=renta_fija(market,idx).iloc[1:]
    rf=float((1+r).prod()**(252/len(r))-1)
    return curva_libre_completa(market,p,table,rf,pasos=39,peso_fijo=peso_fijo)


def plot_markowitz(curve,tangent,own_metrics,rf,title):
    """C completa + DOS puntos: cartera creada y cartera de máximo Sharpe.

    Sin nube de carteras factibles. Incluye recta desde la tasa de referencia.
    """
    fig=go.Figure()
    for branch,color,dash in [('Ineficiente','#A3B5B7','dot'),
                               ('Eficiente','#145668','solid')]:
        pts=curve[curve.rama==branch].sort_values('rendimiento')
        if not pts.empty:
            fig.add_trace(go.Scatter(x=pts.riesgo,y=pts.rendimiento,mode='lines',
                name=f'Rama {branch.lower()}',line=dict(color=color,width=3,dash=dash),
                hovertemplate='Riesgo: %{x:.2%}<br>Rendimiento: %{y:.2%}<extra></extra>'))
    tr=float(tangent['volatilidad']);tm=float(tangent['retorno'])
    if tr>1e-8:
        max_x=max(float(curve.riesgo.max()),tr,float(own_metrics['volatilidad']))*1.07
        end_x=max(tr*1.15,max_x)
        end_y=rf+(tm-rf)*end_x/tr
        fig.add_trace(go.Scatter(x=[0,end_x],y=[rf,end_y],mode='lines',
            name='Recta de tangencia',line=dict(color='#B7804D',width=2,dash='dash')))
    # Los dos puntos pueden coincidir: usamos símbolos distintos para ver ambos.
    fig.add_trace(go.Scatter(x=[float(own_metrics['volatilidad'])],
        y=[float(own_metrics['retorno'])],mode='markers',name='Tu cartera',
        marker=dict(symbol='diamond',size=14,color='#145668',line=dict(width=1.5,color='#ffffff')),
        hovertemplate='Tu cartera<br>Riesgo %{x:.2%}<br>Rendimiento %{y:.2%}<extra></extra>'))
    fig.add_trace(go.Scatter(x=[tr],y=[tm],mode='markers',
        name='Cartera óptima',marker=dict(symbol='star',size=17,
        color='#B7804D',line=dict(width=1.3,color='#ffffff')),
        hovertemplate='Cartera óptima<br>Riesgo %{x:.2%}<br>Rendimiento %{y:.2%}<extra></extra>'))
    fig.update_layout(template='plotly_white',title=title,height=430,
        paper_bgcolor='#FBFBF8',plot_bgcolor='#FFFFFF',font=dict(color='#26414A'),
        xaxis=dict(title='Riesgo (volatilidad anual)',tickformat='.1%',rangemode='tozero'),
        yaxis=dict(title='Rendimiento anual esperado',tickformat='.1%'),
        legend=dict(orientation='h',y=-.33),hovermode='closest',
        margin=dict(l=25,r=20,t=60,b=110))
    return fig


def show_frontier(curve,tangent,own_metrics,rf,title,restricted=False,free_bond=None):
    st.subheader('Riesgo y rendimiento')
    st.plotly_chart(plot_markowitz(curve,tangent,own_metrics,rf,title),use_container_width=True)
    st.caption('El gráfico compara lo que elegiste con una combinación de inversiones que busca equilibrar ganancias y riesgo.')


def optional_frontier(stage, market, developer, build):
    """Mostrar la curva solo si el visitante la quiere ver, con una llamada visual más clara."""
    key=f'ver_frontera_{stage}_{market}'
    if key not in st.session_state:
        st.session_state[key]=bool(developer)
    label='Explorar la relación entre riesgo y rendimiento'
    # Solo este botón: verde salvia claro, acorde con la paleta del reporte.
    # La clase st-key-* la genera Streamlit a partir de la clave del botón.
    st.markdown("""
    <style>
    div[class*="st-key-btn_ver_frontera_"] button {
        background-color: #DDEDE5 !important;
        border: 1px solid #9CBCAF !important;
        border-radius: 12px !important;
        color: #205448 !important;
        font-weight: 650 !important;
        min-height: 3.1rem;
        box-shadow: 0 2px 7px rgba(32, 84, 72, 0.07);
        transition: background-color .15s ease, border-color .15s ease;
    }
    div[class*="st-key-btn_ver_frontera_"] button:hover {
        background-color: #CDE5D9 !important;
        border-color: #598C80 !important;
        color: #183E35 !important;
    }
    div[class*="st-key-btn_ver_frontera_"] button:focus-visible {
        outline: 2px solid #598C80 !important;
        outline-offset: 2px;
    }
    div[class*="st-key-btn_ver_frontera_"] button p {
        color: inherit !important;
        font-weight: inherit !important;
    }
    </style>
    """, unsafe_allow_html=True)
    cols=st.columns([1.2,2.6,1.2])
    with cols[1]:
        if st.button(label, key=f'btn_{key}', use_container_width=True, type='secondary'):
            st.session_state[key]=not st.session_state[key]
    if st.session_state[key]:
        st.markdown(
            '<div style="margin:.35rem 0 1rem 0;padding:.75rem 1rem;border-radius:12px;'
            'background:#F3F0EA;border:1px solid #D7CCC1;color:#39525A;font-size:.98rem">'
            '<b>Sharpe:</b> aquí llamamos <b>cartera óptima</b> a la combinación que logra la '
            'mejor relación entre <b>riesgo</b> y <b>rendimiento esperado</b>. '
            'No es la que más gana en todos los casos, sino la que mejor equilibra ambos.'
            '</div>',
            unsafe_allow_html=True
        )
        with st.spinner('Preparando tu comparación…'):
            build()


def plot_lines(df,title):
    """Rendimientos acumulados diarios, nunca se agregan a meses."""
    fig=go.Figure()
    for name in df.columns:
        key=name
        prominent=name in ('Tu cartera','Recomendado','CETES','TBIL')
        fig.add_trace(go.Scatter(x=df.index,y=df[name]*100,name=name,mode='lines',
            line={'width':3.7 if prominent else 1.8,'color':COLORS.get(key,'#9a9a9a'),
                  'dash':'dash' if name in ('CETES','TBIL') else 'solid'},
            opacity=1 if prominent else .75,
            hovertemplate='%{x|%d %b %Y}<br>%{y:+.2f}%<extra>'+name+'</extra>'))
    fig.update_layout(template='plotly_white',title=title,height=410,
         paper_bgcolor='#FBFBF8',plot_bgcolor='#FFFFFF',font=dict(color='#26414A'),
         xaxis_title='',yaxis_title='Rendimiento acumulado (%)',hovermode='x unified',
         legend={'orientation':'h','y':-0.22},margin={'l':15,'r':10,'t':55,'b':90})
    fig.update_yaxes(ticksuffix='%',gridcolor='#E7ECEB')
    fig.add_hline(y=0,line_color='#98A9AB',line_width=1)
    return fig


def show_comparison(df,title):
    left,right=st.columns([4.4,1.1],gap='small')
    with left:st.plotly_chart(plot_lines(df,title),use_container_width=True)
    with right:
        st.markdown('**Así terminó cada opción**')
        for name in df.columns:
            z=float(df[name].iloc[-1])*100
            color=COLORS.get(name,'#afafaf')
            st.markdown(f'<div style="border-left:4px solid {color};padding:6px 9px;'
                        f'margin:6px 0;background:rgba(140,140,140,.08);border-radius:5px">'
                        f'<div style="font-size:0.8rem">{name}</div>'
                        f'<b style="color:{color};font-size:1.15rem">{z:+.2f}%</b></div>',
                        unsafe_allow_html=True)
    st.caption('Así habría evolucionado cada alternativa entre enero y septiembre de 2026.')


def pie_active(weights,market,title):
    frame=activos_visibles(weights,labels_for(market))
    if frame.empty:
        st.warning('No hay inversiones activas para mostrar.')
        return
    pie_palette=['#145668','#B7804D','#598C80','#7E99A5','#976B84','#C39B50',
                 '#89A6A0','#D0AE7B','#5D7480','#B890A2','#8EAFA7','#D8C7AF']
    unique_assets=frame['Activo'].tolist()
    color_map={}
    next_idx=0
    for asset in unique_assets:
        if asset.startswith('CETES') or asset.startswith('TBIL'):
            color_map[asset]='#C39B50'
        else:
            color_map[asset]=pie_palette[next_idx % len(pie_palette)]
            next_idx+=1
    fig=px.pie(frame,names='Activo',values='Peso',hole=.40,title=title,
               color='Activo',color_discrete_map=color_map)
    fig.update_traces(textinfo='percent',hovertemplate='%{label}: %{percent}<extra></extra>',
                      marker=dict(line=dict(color='#FFFFFF',width=1.5)))
    fig.update_layout(template='plotly_white',height=330,
                      paper_bgcolor='#FBFBF8',font=dict(color='#26414A'),margin=dict(l=4,r=4,t=48,b=4),
                      legend=dict(orientation='h',y=-.1))
    st.plotly_chart(fig,use_container_width=True)


def optimal_alloc(market,profile,portfolios):
    """Convertir pesos sobre total a un diccionario sin falsear bonos en agresivo."""
    bond,equity=ASIGNACION[profile]
    source=portfolios[profile]
    return {**{ticker:float(w) for ticker,w in zip(source['tickers'],source['weights'])},
            fixed_name(market):float(bond)}


def make_report_images(charts,market,allocation,frontier=None):
    """Prepara visuales para el PDF, con una paleta financiera discreta.

    No modifica datos ni métricas: solo cambia el estilo de las imágenes.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    files={}
    palette={'Tu cartera':'#145668','Recomendado':'#B7804D',
             'Conservador':'#598C80','Balanceado':'#7E99A5',
             'Agresivo':'#976B84','CETES':'#C39B50','TBIL':'#C39B50'}

    def clean(ax):
        ax.set_facecolor('white')
        for key in ('top','right'):ax.spines[key].set_visible(False)
        for key in ('left','bottom'):ax.spines[key].set_color('#CBD6D7')
        ax.grid(axis='y',color='#E6EBEB',linewidth=.7)
        ax.tick_params(labelsize=8.5,colors='#50636C',length=0)
        ax.set_axisbelow(True)

    for name,frame in charts.items():
        fig,ax=plt.subplots(figsize=(10.8,4.5),facecolor='white')
        for key in frame.columns:
            ax.plot(frame.index,frame[key]*100,label=key,
                color=palette.get(key,'#9DAAB2'),
                linewidth=2.65 if key in ('Tu cartera','Recomendado',fixed_name(market)) else 1.3,
                alpha=1 if key in ('Tu cartera','Recomendado',fixed_name(market)) else .75,
                linestyle='--' if key==fixed_name(market) else '-')
        clean(ax)
        ax.axhline(0,color='#A8B5B8',linewidth=.8)
        ax.set_ylabel('Rendimiento acumulado (%)',fontsize=9,color='#50636C')
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        ax.legend(loc='upper left',frameon=False,fontsize=8,ncol=3)
        fig.subplots_adjust(left=.10,right=.98,bottom=.15,top=.95)
        bio=io.BytesIO();fig.savefig(bio,format='png',dpi=155,facecolor='white');plt.close(fig)
        files[f'{name}.png']=bio.getvalue()
        files[f'{name}.csv']=frame.to_csv().encode('utf-8-sig')

    active=activos_visibles(allocation,labels_for(market))
    fig,ax=plt.subplots(figsize=(8,5),facecolor='white')
    ax.pie(active.Peso,labels=active.Activo,autopct='%1.1f%%',startangle=85,
           wedgeprops={'linewidth':1.0,'edgecolor':'white'},
           colors=['#145668','#6E9293','#B7804D','#8CAEB1','#A1A1A0','#D0B58D'])
    bio=io.BytesIO();fig.savefig(bio,format='png',dpi=150,bbox_inches='tight',facecolor='white');plt.close(fig)
    files['composicion.png']=bio.getvalue()
    files['ponderaciones.csv']=active.to_csv(index=False).encode('utf-8-sig')
    if frontier is not None:
        curve,tang,own_metrics,rf=frontier
        fig,ax=plt.subplots(figsize=(10,5.5),facecolor='white')
        for branch,style,color in [('Eficiente','-','#145668'),('Ineficiente','--','#92ADB0')]:
            sample=curve[curve.rama==branch].sort_values('rendimiento')
            ax.plot(sample.riesgo*100,sample.rendimiento*100,
                    linestyle=style,color=color,linewidth=2.5 if branch=='Eficiente' else 1.7,label=branch)
        x=float(tang['volatilidad']);y=float(tang['retorno'])
        if x>1e-8:
            high=max(x,float(curve.riesgo.max()),float(own_metrics['volatilidad']))*1.08
            ax.plot([0,high*100],[rf*100,(rf+(y-rf)*high/x)*100],
                    '--',linewidth=1.4,color='#B7804D',label='Tangente')
        ax.scatter(float(own_metrics['volatilidad'])*100,float(own_metrics['retorno'])*100,
                   marker='D',s=70,color='#9B7184',label='Tu cartera',zorder=4)
        ax.scatter(x*100,y*100,marker='o',s=110,color='#B7804D',
                   label='Máximo Sharpe',zorder=5)
        clean(ax)
        ax.set_xlabel('Riesgo anual (%)',fontsize=9,color='#50636C')
        ax.set_ylabel('Rendimiento esperado anual (%)',fontsize=9,color='#50636C')
        ax.legend(frameon=False,fontsize=8,ncol=3,loc='best')
        fig.subplots_adjust(left=.10,right=.98,bottom=.14,top=.96)
        bio=io.BytesIO();fig.savefig(bio,format='png',dpi=155,facecolor='white');plt.close(fig)
        files['frontera_markowitz.png']=bio.getvalue()
    return files


def email_available():
    return all(config(k) for k in ['SMTP_HOST','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'])


def send_email(destination,pdf_bytes,summary):
    """SOLO por acción voluntaria, con credenciales del servidor.

    El correo se manda directamente por SMTP con STARTTLS o SSL; no se almacena.
    """
    from email.utils import parseaddr
    if '\n' in destination or '\r' in destination:
        raise ValueError('Dirección de correo inválida.')
    _,addr=parseaddr(destination)
    if addr!=destination.strip() or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',addr):
        raise ValueError('Introduce una dirección de correo válida.')
    if not email_available():raise RuntimeError('El servidor de correo todavía no está configurado.')
    msg=EmailMessage()
    msg['Subject']='Resultados de tu simulación de inversión'
    msg['From']=config('SMTP_FROM');msg['To']=addr
    msg.set_content(summary+'\n\nSimulación académica; resultados históricos, no asesoría personalizada.')
    msg.add_attachment(pdf_bytes,maintype='application',subtype='pdf',
                       filename='reporte_portafolio.pdf')
    port=int(config('SMTP_PORT','587'))
    if config('SMTP_SSL','false').lower()=='true':
        with smtplib.SMTP_SSL(config('SMTP_HOST'),port,timeout=18) as conn:
            conn.login(config('SMTP_USER'),config('SMTP_PASSWORD'))
            conn.send_message(msg)
    else:
        with smtplib.SMTP(config('SMTP_HOST'),port,timeout=18) as conn:
            conn.starttls();conn.login(config('SMTP_USER'),config('SMTP_PASSWORD'))
            conn.send_message(msg)


def render(developer=False):
    st.set_page_config(page_title='Tu inversión, tus decisiones',page_icon='📈',layout='wide')
    st.markdown("""<style>
    /* Identidad del PDF editorial: fondo cálido, azul petróleo y cobre */
    .stApp, [data-testid="stAppViewContainer"] {background:#FBFBF8;color:#183640}
    [data-testid="stHeader"] {background:#FBFBF8}
    .block-container {max-width:1040px;padding-top:1.3rem;padding-bottom:3.5rem}
    h1,h2,h3 {color:#183640;letter-spacing:-.025em}
    h1.page-title {font-family:Georgia,'Times New Roman',serif;font-size:clamp(2rem,4vw,3.35rem);
        font-weight:500;line-height:1.12;margin:.15rem 0 .4rem}
    .eyebrow {font-size:.73rem;letter-spacing:.18em;font-weight:750;color:#B7804D;margin:.6rem 0}
    .page-lead {font-size:1.06rem;color:#597078;max-width:760px;line-height:1.55;margin:0 0 1.15rem}
    .app-mark {font-size:.8rem;font-weight:750;letter-spacing:.14em;color:#145668;margin-bottom:.7rem}
    .stButton button,.stFormSubmitButton button,[data-testid="stDownloadButton"] button {
      min-height:46px;border-radius:9px;border-color:#C7D2D1;font-weight:650}
    button[kind="primary"],button[data-testid="baseButton-primary"] {
      background:#145668!important;border-color:#145668!important;color:#FFF!important}
    .stButton button:hover,.stFormSubmitButton button:hover {border-color:#145668!important}
    div[data-testid="stTextInput"] input,div[data-testid="stNumberInput"] input {
      background:#FFFFFF;border-radius:8px;font-size:1rem}
    [data-testid="stMetric"] {background:#F1F5F3;border:1px solid #E3EAE7;
      padding:1rem 1.1rem;border-radius:12px}
    [data-testid="stMetricValue"] {font-family:Georgia,serif;letter-spacing:-.035em}
    [data-testid="stProgressBar"] > div > div {background:#145668}
    [data-testid="stAlert"] {border-radius:8px}
    .market-card {min-height:118px;background:#F2F6F3;border:1px solid #DDE6E3;
      border-radius:12px;padding:19px 20px;margin-bottom:10px}
    .market-name {font-family:Georgia,serif;font-size:1.45rem;color:#183640}
    .market-description {font-size:.9rem;color:#5B7379;margin-top:6px}
    .mini-note {border-top:1px solid #D9E2E0;padding-top:16px;color:#5B7379}
    @media(max-width:640px){
       .block-container{padding-left:1rem;padding-right:1rem;padding-top:1rem}
       h1.page-title{font-size:2rem}
       .stButton button{min-height:48px}
    }
    </style>""",unsafe_allow_html=True)
    ensure_defaults()
    st.markdown('<div id="top-of-page"></div>',unsafe_allow_html=True)
    # Solo se dispara en un cambio de pantalla; nunca con controles normales.
    scroll_to_top_on_navigation()
    st.markdown('<div class="app-mark">◈ &nbsp; LABORATORIO DE INVERSIÓN</div>',unsafe_allow_html=True)
    heading()
    top_navigation()
    stage=st.session_state.page
    market=st.session_state.market

    # PASO 1. Elegir exclusivamente UNO de los mercados.
    if stage==0:
        page_intro('BIENVENIDO', 'Tu dinero. Tus decisiones.',
                   'Elige un mercado, crea tu propia combinación y descubre cómo le habría ido.')
        left,right=st.columns(2,gap='large')
        with left:
            st.markdown('<div class="market-card"><div class="market-name">México</div>'
                        '<div class="market-description">Empresas mexicanas y CETES.</div></div>',
                        unsafe_allow_html=True)
            if st.button('Elegir México  →',key='choose_mx',type='primary',use_container_width=True):
                st.session_state.market='MX'
                ir_a_pagina(1)
        with right:
            st.markdown('<div class="market-card"><div class="market-name">Estados Unidos</div>'
                        '<div class="market-description">Empresas estadounidenses y TBIL.</div></div>',
                        unsafe_allow_html=True)
            if st.button('Elegir Estados Unidos  →',key='choose_us',use_container_width=True):
                st.session_state.market='US'
                ir_a_pagina(1)
        if valid_public_url():
            with st.expander('Abrir también desde tu celular'):
                show_qr()
        if developer:
            st.divider()
            st.toggle('Selección retrospectiva (usa información de 2026)',key='retrospective_dev')
            st.caption('En la versión pública este modo permanece activado.')
            with st.expander('Empresas disponibles'):
                st.write('México:',MX)
                st.write('Estados Unidos:',US)
        st.stop()

    retrospective=st.session_state.retrospective_dev if developer else True
    names=labels_for(market)
    key=market

    # PASO 2. Cartera libre: barra y número sincronizados, SIN reajuste automático.
    if stage==1:
        page_intro('TU COMBINACIÓN', 'Arma tu cartera',
                   'Reparte 100% entre las empresas y '+fixed_name(market)+'. Tú eliges cuánto poner en cada una.')
        st.button('✦ Sorpréndeme con una cartera al azar',
                  key=f'random_alloc_{market}',on_click=randomizar_cartera,
                  args=(market,),use_container_width=True,
                  help='Genera porcentajes aleatorios que suman exactamente 100%. Puedes editarlos libremente después.')
        st.caption('¿No sabes por dónde empezar? Prueba una mezcla al azar y luego hazla tuya.')
        entries=custom_weight_controls(market)
        if st.button('Ver cómo me habría ido →',key='save_free_alloc',type='primary',use_container_width=True):
            valid,error,total=validar_porcentajes(entries)
            if error:st.error(error)
            else:
                st.session_state.custom_allocations[market]=valid
                st.session_state.custom_entry_text[market]={k:f'{v:.2f}' for k,v in entries.items()}
                ir_a_pagina(2)
        if st.button('← Cambiar de mercado',key='bottom_back_market'):ir_a_pagina(0)
        back_to_top_fallback()
        st.stop()

    if market not in st.session_state.custom_allocations:
        st.warning('Primero crea una cartera que sume 100%.')
        if st.button('Volver a crear cartera'):ir_a_pagina(1)
        st.stop()
    own=st.session_state.custom_allocations[market]

    # Se necesita el motor a partir del primer resultado, no durante el formulario.
    try:
        stamp=file_stamp(market)
        p,table,corr,rf,portfolios=preparar_mercado(market,retrospective,stamp)
        own_wealth=serie_cartera_libre(market,p,own)
        fixed_wealth=serie_solo_bonos(market,p)
        own_expected=indicadores_cartera_libre(market,p,table,own,rf)
    except Exception as exc:
        st.error(f'No fue posible calcular resultados con los históricos locales: {exc}')
        st.info('Verifica los archivos de la carpeta datos y ejecuta python preparar.py si faltan.')
        if st.button('← Editar cartera'):ir_a_pagina(1)
        st.stop()

    # PASO 3. Comparar SOLO cartera propia con renta fija.
    if stage==2:
        page_intro('TU PRIMER RESULTADO', 'Así habría ido tu inversión',
                   'Compara tu elección con una alternativa de renta fija.')
        example=rendimientos_comparados({'Tu cartera':own_wealth,fixed_name(market):fixed_wealth})
        if abs(own.get(fixed_name(market),0)-1.0)<1e-9:
            st.info('Elegiste solo '+fixed_name(market)+': ambas líneas son iguales y aparecen superpuestas.')
        show_comparison(example,'Tu cartera frente a '+fixed_name(market)+' · 2026')
        real=estadisticas_observadas(own_wealth)
        a,b,c=st.columns(3)
        a.metric('Cambio total',f"{real['rendimiento']:+.2%}")
        b.metric('Cuánto osciló',f"{real['volatilidad']:.2%}")
        c.metric('Mayor bajada',f"{real['caida']:.2%}")
        def plot_free():
            free_curve,free_tangent=frontier_free_cached(market,stamp,float(own.get(fixed_name(market),0)))
            show_frontier(free_curve,free_tangent,own_expected,rf,
                          'Tu cartera y otra combinación posible',
                          free_bond=float(own.get(fixed_name(market),0)))
        optional_frontier(stage,market,developer,plot_free)
        if developer:
            with st.expander('Revisión técnica: datos utilizados y correlaciones'):
                st.write('Estimación con cierres de 2016–2025; comparación con rendimientos diarios de 2026.')
                st.dataframe(table, use_container_width=True)
                st.write('Correlaciones entre acciones del mercado:')
                st.dataframe(corr.round(3), use_container_width=True)
                st.write('Pesos del visitante, sin límites de cartera modelo:', own)
        left,right=st.columns(2)
        with left:
            if st.button('← Cambiar mis porcentajes',use_container_width=True):ir_a_pagina(1)
        with right:
            if st.button('Descubrir mi perfil →',type='primary',use_container_width=True):ir_a_pagina(3)
        back_to_top_fallback()
        st.stop()

    # PASO 4. Cuestionario accesible para personas sin conocimientos de inversiones.
    if stage==3:
        page_intro('AHORA HABLEMOS DE TI','¿Cómo te gusta cuidar tu dinero?',
                   'Diez preguntas sencillas. No hay respuestas correctas o incorrectas.')
        prev=st.session_state.questionnaire_answers.get(market,{})
        with st.form('questionnaire_form'):
            answers={}
            for i,(question,options) in enumerate(PREGUNTAS):
                choices=[x for x,pts in options]
                old=prev.get(i)
                answers[i]=st.radio(f'{i+1}. {question}',choices,
                                    index=choices.index(old) if old in choices else None,
                                    key=f'q_{market}_{i}')
                st.markdown('<div style="height:13px"></div>',unsafe_allow_html=True)
            done=st.form_submit_button('Ver mi cartera sugerida →',type='primary',use_container_width=True)
        if done:
            if any(v is None for v in answers.values()):
                st.error('Responde todas las preguntas para conocer tu perfil.')
            else:
                total=sum(dict(options)[answers[i]] for i,(_,options) in enumerate(PREGUNTAS))
                st.session_state.questionnaire_answers[market]=answers
                st.session_state.questionnaire_results[market]={'puntos':total,'perfil':grade(total)}
                ir_a_pagina(4)
        if st.button('← Mi resultado anterior'):ir_a_pagina(2)
        back_to_top_fallback()
        st.stop()

    result=st.session_state.questionnaire_results.get(market)
    if not result:
        st.warning('Primero responde el cuestionario.')
        if st.button('Ir al cuestionario'):ir_a_pagina(3)
        st.stop()
    profile=result['perfil']
    optimal=optimal_alloc(market,profile,portfolios)
    rec=portfolios[profile]
    rec_wealth=backtest_perfil(market,profile,retrospective,stamp)
    # El recomendado NO es editable por el público.
    if stage==4:
        st.markdown('<div style="text-align:center;font-size:.9rem;letter-spacing:.18em;color:#B7804D">ENCONTRAMOS TU ESTILO</div>',unsafe_allow_html=True)
        st.markdown(f'<div style="text-align:center;font-family:Georgia,serif;color:#145668;font-size:clamp(2.8rem,7vw,5rem);font-weight:500">{profile}</div>',unsafe_allow_html=True)
        st.markdown(f'<div style="text-align:center;margin-bottom:1.4rem">{result["puntos"]} de 30 puntos · {label_market(market)}</div>',unsafe_allow_html=True)
        st.write('Esta combinación busca un equilibrio entre posibles ganancias y cambios de valor, según tus respuestas.')
        c1,c2=st.columns([1,1.3])
        with c1:
            pie_active(optimal,market,'Composición recomendada')
        with c2:
            frame=activos_visibles(optimal,names)
            st.markdown('**Así se reparte la cartera sugerida**')
            for _, item in frame.iterrows():
                name_col, number_col = st.columns([3,1])
                with name_col: st.write(str(item['Activo']))
                with number_col: st.markdown(f"**{float(item['Peso']):.1%}**")
                st.progress(min(1.0,max(0.0,float(item['Peso']))))
            m=evaluar(market,p,rec['tickers'],table,profile,rec['weights'],rf)
            a,b=st.columns(2)
            a.metric('Ganancia anual estimada',f"{m['retorno']:.2%}")
            b.metric('Variación estimada',f"{m['volatilidad']:.2%}")
            if developer: st.metric('Índice de Sharpe',f"{m['sharpe']:.2f}")
        three=rendimientos_comparados({'Tu cartera':own_wealth,
                                      'Recomendado':rec_wealth,
                                      fixed_name(market):fixed_wealth})
        show_comparison(three,'Tu cartera · recomendación · '+fixed_name(market))
        def plot_recommended():
            rec_curve,rec_tangent=frontier_cached(market,profile,retrospective,stamp)
            show_frontier(rec_curve,rec_tangent,own_expected,rf,
                          'Tus elecciones frente a la recomendación',restricted=True)
        optional_frontier(stage,market,developer,plot_recommended)
        if developer:
            st.caption('Los indicadores esperados usan 2016–2025; la modalidad retrospectiva usa también 2026 para elegir empresas.')
            with st.expander('Diagnóstico: pesos, restricciones y universo seleccionado'):
                st.write('Perfil:',profile)
                st.write('Pesos optimizados:',dict(zip(rec['tickers'],np.round(rec['weights'],6))))
                st.write('Renta fija obligatoria:',ASIGNACION[profile][0])
                st.write('Máximo por acción, respecto al total:',ASIGNACION[profile][1]*.40)
                st.write('Tasa de referencia anual estimada:',rf)
                st.write('Selección retrospectiva:',retrospective)
        a,b=st.columns(2)
        with a:
            if st.button('← Cambiar respuestas',use_container_width=True):ir_a_pagina(3)
        with b:
            if st.button('Comparar todas las opciones →',type='primary',use_container_width=True):ir_a_pagina(5)
        back_to_top_fallback()
        st.stop()

    # PASO 6. Todas las comparaciones, reflexión final y entrega voluntaria.
    page_intro('COMPARACIÓN FINAL','¿Cuál habría funcionado mejor?',
               'Estas son diferentes maneras de invertir el mismo dinero.')
    portfolio_histories={
        'Tu cartera':own_wealth,
        'Conservador':backtest_perfil(market,'Conservador',retrospective,stamp),
        'Balanceado':backtest_perfil(market,'Balanceado',retrospective,stamp),
        'Agresivo':backtest_perfil(market,'Agresivo',retrospective,stamp),
        fixed_name(market):fixed_wealth
    }
    all_history=rendimientos_comparados(portfolio_histories)
    show_comparison(all_history,'Conservador · Balanceado · Agresivo · Tu cartera · '+fixed_name(market))
    def plot_final_frontier():
        rec_curve,rec_tangent=frontier_cached(market,profile,retrospective,stamp)
        show_frontier(rec_curve,rec_tangent,own_expected,rf,
                      'Tu cartera y el equilibrio entre riesgo y ganancia',restricted=True)
    optional_frontier(stage,market,developer,plot_final_frontier)
    st.subheader('Cada forma de invertir tiene su propio ritmo')
    st.markdown("""
    <div style="display:flex;justify-content:center;gap:0;align-items:stretch;margin:0.4rem 0 0.8rem 0;">
        <div style="flex:1;text-align:center;padding:0 1.1rem;">
            <div style="font-weight:700;font-size:1.25rem;color:#26414A;margin-bottom:.5rem;">Conservador</div>
            <div style="color:#35545F;line-height:1.75;max-width:290px;margin:0 auto;">Prioriza la estabilidad. Mantiene la mayor parte en renta fija.</div>
        </div>
        <div style="width:1px;background:#D6D0C7;align-self:stretch;margin:.15rem 0;"></div>
        <div style="flex:1;text-align:center;padding:0 1.1rem;">
            <div style="font-weight:700;font-size:1.25rem;color:#26414A;margin-bottom:.5rem;">Balanceado</div>
            <div style="color:#35545F;line-height:1.75;max-width:290px;margin:0 auto;">Combina estabilidad y oportunidades de crecimiento.</div>
        </div>
        <div style="width:1px;background:#D6D0C7;align-self:stretch;margin:.15rem 0;"></div>
        <div style="flex:1;text-align:center;padding:0 1.1rem;">
            <div style="font-weight:700;font-size:1.25rem;color:#26414A;margin-bottom:.5rem;">Agresivo</div>
            <div style="color:#35545F;line-height:1.75;max-width:290px;margin:0 auto;">Busca más crecimiento y acepta cambios de valor mayores.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.caption('Más ganancias en un periodo no significan más seguridad. Este ejercicio recrea resultados históricos; no predice el futuro.')
    st.subheader('Composición de las carteras')
    left,right=st.columns(2)
    with left:pie_active(own,market,'La cartera que creaste')
    with right:pie_active(optimal,market,'La cartera recomendada')
    st.markdown('---')
    st.subheader('Guarda o envía tus resultados')
    st.write('Llévate tu resumen con gráficas, porcentajes y explicaciones fáciles de entender. El correo es opcional.')
    summary=(f'Mercado: {label_market(market)}\nPerfil sugerido: {profile} ({result["puntos"]}/30 puntos)\n'
             f'Rendimiento acumulado 2026 de tu cartera: {all_history["Tu cartera"].iloc[-1]:+.2%}\n'
             f'Rendimiento acumulado 2026 del perfil recomendado: {all_history[profile].iloc[-1]:+.2%}\n'
             f'Rendimiento acumulado 2026 de {fixed_name(market)}: {all_history[fixed_name(market)].iloc[-1]:+.2%}\n'
             'Metodología: estudio académico; selección retrospectiva de emisoras, si aplica.\n'
             'Datos: estimaciones 2016–2025 y comparación histórica 02-ene a 30-sep-2026.\n')
    # El PDF sólo se crea cuando el visitante lo solicita.
    # No se vuelven a ejecutar optimizaciones al descargar o enviar.
    if st.button('Crear mi informe personal (PDF)',type='primary',use_container_width=True):
        with st.spinner('Preparando tu informe…'):
            # El PDF sí incorpora la frontera, aun si el usuario no abrió la vista avanzada.
            rec_curve,rec_tangent=frontier_cached(market,profile,retrospective,stamp)
            files=make_report_images({
                'cartera_vs_renta_fija':rendimientos_comparados({'Tu cartera':own_wealth,fixed_name(market):fixed_wealth}),
                'cartera_vs_recomendacion':rendimientos_comparados({'Tu cartera':own_wealth,'Recomendado':rec_wealth,fixed_name(market):fixed_wealth}),
                'comparacion_final':all_history
            },market,optimal,frontier=(rec_curve,rec_tangent,own_expected,rf))
            rec_est=evaluar(market,p,rec['tickers'],table,profile,rec['weights'],rf)
            observed={name:float(all_history[name].iloc[-1]) for name in all_history.columns}
            observed['Recomendado']=float(all_history[profile].iloc[-1])
            st.session_state['pdf_report']=generar_pdf(
                market=market,profile=profile,points=result['puntos'],
                own=own,optimal=optimal,names=names,observed=observed,
                estimated={'own':own_expected,'rec':rec_est},rf=rf,
                images=files,retrospective=retrospective)
    if st.session_state.get('pdf_report'):
        pdf_bytes=st.session_state['pdf_report']
        st.download_button('Descargar mi informe en PDF',data=pdf_bytes,
                           file_name='reporte_personal_de_inversion.pdf',
                           mime='application/pdf',use_container_width=True)
        if email_available():
            with st.form('send_email_form',clear_on_submit=True):
                recipient=st.text_input('Correo al que quieres enviar tu reporte',placeholder='ejemplo@correo.com')
                consent=st.checkbox('Autorizo enviar el PDF a este correo.')
                send=st.form_submit_button('Enviar reporte PDF por correo')
            if send:
                if not consent:st.warning('Marca la casilla de autorización antes de enviar.')
                else:
                    try:
                        send_email(recipient.strip(),pdf_bytes,summary)
                        st.success('El servidor de correo aceptó el mensaje.')
                    except Exception as e:
                        st.error('No se pudo enviar el reporte. Revisa la configuración SMTP. '+str(e))
        else:
            st.caption('El correo directo requiere SMTP configurado. Puedes descargar el PDF y enviarlo desde tu correo.')
    # El cambio de pantalla desencadena una sola orden de regresar arriba.
    a,b=st.columns(2)
    with a:
        if st.button('← Ver mi cartera recomendada',use_container_width=True):ir_a_pagina(4)
    with b:
        if st.button('Crear otra cartera',use_container_width=True):
            # Se limpia solo el recorrido del mercado, no los archivos de datos.
            for k in ('custom_allocations','custom_entry_text','questionnaire_answers','questionnaire_results'):
                st.session_state[k]={}
            st.session_state['export_ready']=False
            ir_a_pagina(0)
    back_to_top_fallback()


if __name__=='__main__':
    # También permite ejecutar directamente: streamlit run app.py
    render(developer=False)
