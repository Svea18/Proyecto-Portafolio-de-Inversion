"""Generador editorial de reportes personales de inversión (PDF dinámico).

Referencias de diseño: portadas con degradados verde-azulados, titulares grandes,
secciones separadas por líneas finas, tablas financieras claras y gráficas limpias.

Solo dibuja información recibida del motor; NO descarga datos, calcula nuevas
carteras ni sustituye métricas con cifras inventadas. Compatible con reportlab
habitual de Windows: utiliza exclusivamente fuentes PDF estándar.
"""
from __future__ import annotations

from io import BytesIO
from datetime import date
from math import isfinite, ceil
from html import escape

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import Paragraph

PW, PH = A4
LEFT = 37
RIGHT = PW - 37
WIDTH = PW - 74
WHITE = colors.HexColor('#FFFFFF')
TEAL = colors.HexColor('#006E72')
DEEP = colors.HexColor('#034F57')
AQUA = colors.HexColor('#39A8A7')
MINT = colors.HexColor('#B7E5D5')
MINT_SOFT = colors.HexColor('#EAF7F1')
SKY = colors.HexColor('#D8F0EE')
NAVY = colors.HexColor('#1B3441')
INK = colors.HexColor('#1F3D46')
MUTED = colors.HexColor('#667D83')
CREAM = colors.HexColor('#F9FAF2')
BORDER = colors.HexColor('#DBE9E5')
GOLD = colors.HexColor('#D9A853')



# Base editorial congelada al 30-sep-2026: enlaces a publicaciones fechadas
# durante el periodo del backtesting. No requiere internet al generar el PDF.
# Se muestran EXCLUSIVAMENTE las acciones de la cartera libre con peso positivo.
# Cada resumen es contexto informativo, no una prueba causal de movimientos de precio.
NOTICIAS_2026 = {
    'MX': {
        'FEMSAUBD.MX': ('28 jul 2026', 'OXXO mantuvo su crecimiento: FEMSA informó ingresos consolidados 9.3% mayores en el segundo trimestre y un aumento de 11.8% en OXXO México. La evolución del consumo minorista fue un factor relevante para las expectativas de la empresa.', 'FEMSA · resultados 2T26', 'https://www.femsa.com/es/sala-de-prensa/comunicado/femsa-2t-2026-resultados/'),
        'GFNORTEO.MX': ('21 jul 2026', 'Banorte reportó un crecimiento anual de 8% en su cartera de crédito vigente. Destacaron los préstamos para automóviles, nómina y tarjetas, mientras el mercado también siguió de cerca los riesgos de morosidad.', 'Banorte · resultados 2T26', 'https://www.banorte.com/GFB/Boletines-de-prensa/Grupo-Financiero-Banorte-reporta-un-crecimiento-solido-en-sus-carteras-de-credito'),
        'AMXB.MX': ('21 jul 2026', 'América Móvil presentó sus resultados del segundo trimestre y anunció un acuerdo para adquirir WOW Perú. El crecimiento de sus servicios de conectividad y sus inversiones en redes fueron asuntos importantes para evaluar sus perspectivas.', 'América Móvil · resultados 2T26', 'https://www.sec.gov/Archives/edgar/data/1129137/000114036126029404/ef20078440_6k.htm'),
        'WALMEX.MX': ('22 jul 2026', 'Walmart de México publicó resultados del segundo trimestre en un entorno de consumo más débil. Los inversionistas prestaron atención a la evolución de las ventas, las transacciones y los márgenes de su operación.', 'Walmex · comunicados a la BMV', 'https://www.walmex.mx/comunicados-y-eventos/comunicados-a-bmv.html'),
        'GMEXICOB.MX': ('21 jul 2026', 'El alza del precio del cobre favoreció los ingresos y ganancias del negocio minero de Grupo México durante el segundo trimestre. La cotización de metales sigue siendo una fuente importante de oportunidades y volatilidad.', 'Reuters · resultados Grupo México', 'https://www.investing.com/news/stock-market-news/higher-copper-prices-push-grupo-mexico-quarterly-profit-up-79-4804397'),
        'CEMEXCPO.MX': ('23 jul 2026', 'Cemex reportó un crecimiento de 24% en flujo de operación trimestral y elevó su previsión anual. Aun con cifras favorables, la acción puede fluctuar si el mercado esperaba mejores resultados o anticipa menor demanda.', 'Cemex · resultados 2T26', 'https://www.cemex.es/w/resultados-segundo-trimestre-2026'),
        'BIMBOA.MX': ('23 jul 2026', 'Grupo Bimbo informó crecimiento de ventas en México y expansión global excluyendo tipo de cambio. Sin embargo, la apreciación del peso redujo el valor de sus ventas internacionales al convertirlas a moneda mexicana.', 'El Economista · Bimbo 2T26', 'https://www.eleconomista.com.mx/mercados/mundial-futbol-impulso-resultados-bimbo-ii-trim-20260723-824791.html'),
        'ASURB.MX': ('23 jul 2026', 'ASUR reportó una reducción anual de 5% en pasajeros de sus aeropuertos mexicanos en el segundo trimestre, principalmente por menor tráfico internacional. Esta debilidad turística fue un riesgo para las expectativas de crecimiento.', 'ASUR · resultados 2T26', 'https://www.sec.gov/Archives/edgar/data/1123452/000110465926086284/tm2621230d1_ex99-1.htm'),
        'GAPB.MX': ('14 jul 2026', 'GAP afrontó una caída de 5.6% en tráfico de pasajeros durante el segundo trimestre, aunque aumentaron algunos ingresos aeroportuarios. El turismo y los costos de operación fueron factores relevantes para sus perspectivas.', 'GAP · resultados 2T26', 'https://www.globenewswire.com/news-release/2026/07/14/3326564/0/en/grupo-aeroportuario-del-pacifico-announces-results-for-the-second-quarter-of-2026.html'),
        'AC.MX': ('23 jul 2026', 'Arca Continental informó ventas netas y EBITDA prácticamente estables frente al segundo trimestre de 2025. La moderación del crecimiento, junto con su rentabilidad, ayuda a contextualizar un comportamiento bursátil contenido.', 'Arca Continental · resultados 2T26', 'https://www.arcacontal.com/es/noticia/financiera/arca-continental-reporta-resultados-del-2t26-con-resiliencia-en-rentabilidad'),
    },
    'US': {
        'AAPL': ('30 jul 2026', 'Apple informó ingresos trimestrales 16% mayores. iPhone, Mac y servicios marcaron máximos para un trimestre de junio; sus avances en inteligencia artificial también influyeron en las expectativas del mercado.', 'Apple Newsroom · resultados', 'https://www.apple.com/newsroom/2026/07/apple-reports-third-quarter-results/'),
        'MSFT': ('29 jul 2026', 'Microsoft reportó crecimiento de 18% en ingresos, apoyado por la nube. La expansión de inteligencia artificial ofreció oportunidades, pero los elevados gastos de infraestructura siguieron siendo una preocupación para inversionistas.', 'Microsoft · resultados FY26 Q4', 'https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast'),
        'NVDA': ('26 ago 2026', 'NVIDIA informó ingresos 106% superiores a un año antes, con fuerte demanda de chips para centros de datos. Las restricciones de venta a China seguían siendo un riesgo para una acción muy sensible a las expectativas de IA.', 'NVIDIA · resultados fiscal 2T27', 'https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/'),
        'AMZN': ('30 jul 2026', 'Amazon reportó un crecimiento de 20% en ventas y de 37% en ingresos de AWS. La expansión del negocio de nube fue favorable, mientras que las inversiones tecnológicas afectaron las expectativas de gasto.', 'Amazon · resultados 2T26', 'https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Second-Quarter-Results/default.aspx'),
        'JPM': ('14 jul 2026', 'JPMorgan Chase reportó utilidad neta trimestral de 21,200 millones de dólares, aunque parte provino de ganancias extraordinarias. Conviene distinguir esos ingresos de la rentabilidad recurrente del banco.', 'JPMorgan Chase · resultados 2T26', 'https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/quarterly-earnings/2026/2nd-quarter/6cded9fd-a164-4e6c-8cff-377357cf105c.pdf'),
        'JNJ': ('15 jul 2026', 'Johnson & Johnson incrementó sus ventas trimestrales 6.6% y elevó su previsión anual. Los nuevos tratamientos y los productos de tecnología médica respaldaron expectativas de crecimiento, con los riesgos propios del sector salud.', 'Johnson & Johnson · resultados 2T26', 'https://www.jnj.com/media-center/press-releases/johnson-johnson-reports-q2-2026-results-raises-2026-outlook'),
        'KO': ('21 jul 2026', 'Coca-Cola reportó 7% más ingresos y 5% más volumen global en el segundo trimestre. Su crecimiento y la solidez de sus marcas son relevantes, aunque costos y cambios en hábitos de consumo también influyen.', 'Coca-Cola · resultados 2T26', 'https://investors.coca-colacompany.com/news-events/press-releases/detail/1168/coca-cola-reports-second-quarter-2026-results-and-raises-full-year-guidance'),
        'XOM': ('31 jul 2026', 'ExxonMobil registró mayores ganancias trimestrales, apoyadas por precios energéticos y producción en campos clave. El petróleo puede generar rendimientos elevados, pero su precio también responde a factores geopolíticos.', 'ExxonMobil · resultados 2T26', 'https://investor.exxonmobil.com/company-information/press-releases/detail/1208/exxonmobil-announces-second-quarter-2026-results'),
        'WMT': ('20 ago 2026', 'Walmart reportó ingresos 5.9% mayores y ventas digitales 23% superiores. Los resultados destacaron su transformación comercial, aunque las expectativas de consumo y márgenes también condicionaron a la acción.', 'Walmart · resultados FY27 Q2', 'https://corporate.walmart.com/news/2026/08/20/walmart-releases-q2-fy27-earnings'),
        'CAT': ('4 ago 2026', 'Caterpillar presentó un crecimiento de 24% en ingresos trimestrales hasta 20,500 millones de dólares. La demanda de maquinaria e infraestructura fue favorable, junto con riesgos por costos de materiales y comercio.', 'Caterpillar · resultados 2T26', 'https://www.caterpillar.com/en/news/corporate-press-releases/h/2q26-results-caterpillar-inc.html'),
    }
}


def noticias_seleccionadas(market, own, umbral=0.00005):
    """Devuelve las noticias SOLO de acciones activas de la cartera creada.

    Los bonos no son acciones: CETES/TBIL se excluyen de este apartado.
    Al guardar localmente los resúmenes, los PDF se generan sin conexión.
    """
    catalogo = NOTICIAS_2026.get(market, {})
    return [(ticker, float(peso), catalogo[ticker])
            for ticker, peso in own.items()
            if ticker in catalogo and float(peso) > umbral]


# ─────────────────────────────────────────────────────────────────────────────
# V8 · SISTEMA EDITORIAL PARA REPORTES DE INVERSIÓN
# Referencias de estilo: composición de reportes institucionales y editorial.
# Solo diseño; métricas, ponderaciones y noticias son las que entrega la app.
# Las fuentes se buscan en el equipo. NO se distribuyen archivos de tipografía.
# ─────────────────────────────────────────────────────────────────────────────
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAPER = colors.HexColor('#FFFFFF')
MIDNIGHT = colors.HexColor('#142936')
PETROL = colors.HexColor('#145668')
RUST = colors.HexColor('#B7804D')
GOLD2 = colors.HexColor('#D4B289')
SOFT = colors.HexColor('#F7F8F6')
LINE = colors.HexColor('#DBE2E1')
TEXT = colors.HexColor('#243A44')
SUB = colors.HexColor('#64777A')
PALE = colors.HexColor('#EFF4F3')
GREEN = colors.HexColor('#2D776E')
RED = colors.HexColor('#B05E54')
WHITE2 = colors.white
MARGIN=46
R=PW-MARGIN
SPACE=PW-2*MARGIN


def setup_fonts():
    def pick(name, possible):
        for path in possible:
            if Path(path).is_file():
                try:
                    pdfmetrics.registerFont(TTFont(name,str(path)))
                    return name
                except Exception:
                    pass
        return None
    regular=pick('ReportSans', [r'C:\Windows\Fonts\segoeui.ttf',r'C:\Windows\Fonts\arial.ttf','/usr/share/fonts/truetype/lato/Lato-Regular.ttf']) or 'Helvetica'
    strong=pick('ReportSansBold', [r'C:\Windows\Fonts\segoeuib.ttf',r'C:\Windows\Fonts\arialbd.ttf','/usr/share/fonts/truetype/lato/Lato-Bold.ttf']) or 'Helvetica-Bold'
    display=pick('ReportDisplay', [r'C:\Windows\Fonts\georgia.ttf',r'C:\Windows\Fonts\times.ttf','/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf']) or 'Times-Roman'
    displaystrong=pick('ReportDisplayBold', [r'C:\Windows\Fonts\georgiab.ttf',r'C:\Windows\Fonts\timesbd.ttf','/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf']) or 'Times-Bold'
    return regular,strong,display,displaystrong

BODY,BOLD,DISPLAY,DISPLAYB=setup_fonts()

def label(c,x,y,text,size=8,color=SUB,spacing=.95):
    c.setFont(BOLD,size);c.setFillColor(color)
    obj=c.beginText(x,y)
    obj.setCharSpace(spacing)
    obj.textOut(str(text).upper());obj.setCharSpace(0);c.drawText(obj)


def line(c,x1,y1,x2,y2,color=LINE,lw=.6):
    c.setStrokeColor(color);c.setLineWidth(lw);c.line(x1,y1,x2,y2)


def t(c,x,y,string,sz=10,color=TEXT,bold=False,serif=False):
    c.setFont(DISPLAYB if serif and bold else DISPLAY if serif else BOLD if bold else BODY,sz)
    c.setFillColor(color);c.drawString(x,y,str(string))


def rt(c,x,y,string,sz=10,color=TEXT,bold=False):
    c.setFont(BOLD if bold else BODY,sz);c.setFillColor(color)
    c.drawRightString(x,y,str(string))


def p(c,string,x,top,width=SPACE,size=9.6,leading=14.6,color=TEXT,bold=False):
    style=ParagraphStyle('editorial',fontName=BOLD if bold else BODY,fontSize=size,leading=leading,textColor=color,spaceBefore=0,spaceAfter=0,allowWidows=0,allowOrphans=0)
    par=Paragraph(escape(str(string)),style)
    _,h=par.wrap(width,1000);par.drawOn(c,x,top-h)
    return top-h


def header(c,num,eyebrow,title):
    c.setFillColor(PAPER);c.rect(0,0,PW,PH,fill=1,stroke=0)
    c.setFillColor(MIDNIGHT);c.rect(0,PH-14,PW,14,fill=1,stroke=0)
    label(c,MARGIN,796,'LABORATORIO / CARTERAS',7.8,PETROL)
    rt(c,R,796,'REPORTE  2026',7.7,SUB)
    line(c,MARGIN,780,R,780)
    label(c,MARGIN,749,eyebrow,8.1,RUST)
    t(c,MARGIN,707,title,29,MIDNIGHT,serif=True)
    line(c,MARGIN,688,R,688)


def foot(c,page,total):
    line(c,MARGIN,46,R,46)
    t(c,MARGIN,30,'EJERCICIO ACADÉMICO  ·  INFORME DE INVERSIÓN',7.3,SUB)
    rt(c,R,30,f'{page:02d} / {total:02d}',8,PETROL,True)
    c.showPage()


def percent(v):
    try:
        n=float(v)
        return f'{n:+.2%}' if isfinite(n) else 'N/D'
    except (TypeError,ValueError):return 'N/D'

def fmt(v,percentage=False):
    try:
        n=float(v)
        if not isfinite(n):return 'N/D'
        return f'{n:.2%}' if percentage else f'{n:.2f}'
    except (TypeError,ValueError):return 'N/D'


def large_stat(c,x,y,value,title,wide):
    label(c,x,y,title,7.9,SUB,spacing=.55)
    val_color=RED if str(value).startswith('-') else MIDNIGHT
    t(c,x,y-35,value,24,val_color,bold=True)
    line(c,x,y-50,x+wide,y-50)


def active_list(weights,names):
    return sorted([(names.get(k,k),float(v)) for k,v in weights.items() if float(v)>0.00005],key=lambda a:-a[1])


def holdings(c,weights,names,x,top,width,limit=12):
    items=active_list(weights,names)
    label(c,x,top,'DISTRIBUCIÓN DE ACTIVOS',8.1,PETROL)
    y=top-20
    line(c,x,y,x+width,y,MIDNIGHT,1.1)
    y-=24
    label(c,x+3,y,'INVERSIÓN',7.1,SUB,.3)
    rt(c,x+width-5,y,'PESO',7.1,SUB,True)
    y-=11
    line(c,x,y,x+width,y)
    # 10 acciones + renta fija deben caber sin invadir la gráfica inferior.
    row_h=min(23.0,168.0/max(min(len(items),limit),1))
    for i,(name,w) in enumerate(items[:limit]):
        y-=row_h
        name=str(name)
        while len(name)>4 and pdfmetrics.stringWidth(name,BODY,9)>width-82:
            name=name[:-2]
        t(c,x+3,y+6,name,9,TEXT)
        rt(c,x+width-5,y+6,f'{w:.2%}',9,MIDNIGHT,True)
        line(c,x,y-1,x+width,y-1)
    y-=24
    t(c,x+3,y,'Total',9,PETROL,True)
    rt(c,x+width-5,y,f'{sum(w for _,w in items):.2%}',9,PETROL,True)
    return y


def figure(c,data,x,y,w,h):
    if not data:
        c.setFillColor(SOFT);c.rect(x,y,w,h,stroke=0,fill=1)
        line(c,x+14,y+h/2,x+w-14,y+h/2)
        t(c,x+14,y+h/2+8,'Gráfica no disponible en esta simulación',8.3,SUB)
        return
    try:
        im=ImageReader(BytesIO(data));iw,ih=im.getSize()
        f=min(w/iw,h/ih)
        dw,dh=iw*f,ih*f
        c.drawImage(im,x+(w-dw)/2,y+(h-dh)/2,width=dw,height=dh,mask='auto')
    except Exception:
        t(c,x,y+h/2,'Gráfica no disponible',8.5,SUB)


def margin_note(c,headline,text_,x,y,width):
    line(c,x,y+66,x+width,y+66,RUST,1.8)
    t(c,x,y+45,headline,12,MIDNIGHT,serif=True)
    p(c,text_,x,y+33,width,9.1,13.7,SUB)


def news_page(c,stories,labels,page,total,idx,total_groups):
    header(c,'', 'CONTEXTO DEL MERCADO', 'Noticias de tus acciones')
    p(c,'Información publicada durante el periodo analizado. Son hechos que ayudan a comprender el contexto, no una explicación única del precio de una acción.',MARGIN,667,SPACE,9.2,14,SUB)
    y=623
    for ticker,w,(when,summary,source,url) in stories:
        t(c,MARGIN,y,labels.get(ticker,ticker),13,MIDNIGHT,serif=True)
        rt(c,R,y,f'{w:.2%} de la cartera',8.4,PETROL,True)
        t(c,MARGIN,y-19,when.upper()+'   ·   '+source,7.5,SUB)
        bottom=p(c,summary,MARGIN,y-31,SPACE,8.8,13.3,TEXT)
        t(c,MARGIN,bottom-16,'CONSULTAR FUENTE ORIGINAL',7.0,PETROL,True)
        c.linkURL(url,(MARGIN,bottom-19,R,bottom-4),relative=0,thickness=0)
        line(c,MARGIN,bottom-29,R,bottom-29)
        y-=111
    foot(c,page,total)


def generar_pdf(*,market,profile,points,own,optimal,names,observed,estimated,rf,images,retrospective=True):
    """Construye un reporte PDF a partir de los datos calculados por la aplicación.

    No actualiza precios, modifica posiciones, ni genera cifras de rendimiento.
    Mantiene la misma firma pública que las versiones anteriores.
    """
    b=BytesIO();c=canvas.Canvas(b,pagesize=A4,pageCompression=1)
    c.setTitle('Análisis personal de inversiones | 2026')
    c.setAuthor('Laboratorio de inversión')
    c.setSubject('Cartera personal, alternativa de máximo Sharpe y contexto 2026')
    fixed='CETES' if market=='MX' else 'TBIL'
    country='México' if market=='MX' else 'Estados Unidos'
    labels={**dict(names),'CETES':'CETES · 28 días','TBIL':'TBIL · Tesoro de EE. UU.'}
    personal=percent(observed.get('Tu cartera',0))
    rec=percent(observed.get('Recomendado',0))
    ref=percent(observed.get(fixed,0))
    os=estimated.get('own',{})
    rs=estimated.get('rec',{})
    news=noticias_seleccionadas(market,own)
    nnews=ceil(len(news)/5)
    total=5+nnews

    # 01 · Portada: una afirmación editorial, tres indicadores y contexto.
    c.setFillColor(PAPER);c.rect(0,0,PW,PH,fill=1,stroke=0)
    c.setFillColor(MIDNIGHT);c.rect(0,PH-15,PW,15,fill=1,stroke=0)
    label(c,MARGIN,792,'LABORATORIO DE INVERSIÓN',8,PETROL)
    rt(c,R,792,'INFORME PERSONAL / 2026',8,SUB)
    line(c,MARGIN,775,R,775)
    label(c,MARGIN,722,'ANÁLISIS DE PORTAFOLIO',9,RUST)
    t(c,MARGIN,655,'Tus decisiones,',39,MIDNIGHT,serif=True)
    t(c,MARGIN,608,'en perspectiva.',39,MIDNIGHT,serif=True)
    p(c,'Una lectura de tu cartera, de una alternativa optimizada y de los riesgos que ambas asumieron durante 2026.',MARGIN,572,410,11.5,17.8,TEXT)
    # Banda única sin tarjetas independientes.
    c.setFillColor(MIDNIGHT);c.rect(0,320,PW,198,fill=1,stroke=0)
    label(c,MARGIN,485,'RESULTADOS OBSERVADOS  ·  ENERO–SEPTIEMBRE 2026',8.2,GOLD2)
    xcol=[MARGIN,MARGIN+178,MARGIN+354]
    vcol=[personal,rec,ref]
    lcol=['TU CARTERA','CARTERA RECOMENDADA',fixed]
    for i in range(3):
        if i:line(c,xcol[i]-15,368,xcol[i]-15,470,colors.HexColor('#627782'),.6)
        label(c,xcol[i],438,lcol[i],7.1,colors.HexColor('#D0DBDD'),.2)
        t(c,xcol[i],392,vcol[i],22,WHITE2,True)
    label(c,MARGIN,274,'MERCADO',7.8,PETROL)
    t(c,MARGIN,252,country,13,MIDNIGHT,True)
    label(c,MARGIN+266,274,'PERFIL DEL CUESTIONARIO',7.8,PETROL)
    t(c,MARGIN+266,252,f'{profile}  ·  {points}/30 puntos',12.2,MIDNIGHT,True)
    line(c,MARGIN,222,R,222)
    t(c,MARGIN,197,'Cómo leer este informe',16,MIDNIGHT,serif=True)
    p(c,'La página siguiente explica los conceptos básicos. Después encontrarás tu cartera, la recomendación de máximo Sharpe, las gráficas y las noticias de las empresas que elegiste.',MARGIN,184,SPACE,9.5,14.6,TEXT)
    p(c,'Estimaciones: 2016–2025. Comparación histórica: 2 de enero–30 de septiembre de 2026. Resultados educativos, sin comisiones ni impuestos.',MARGIN,93,SPACE,8.2,12,SUB)
    foot(c,1,total)

    # 02 · Guía: primero entender, luego interpretar.
    header(c,'', 'GUÍA PARA LEER EL INFORME', 'Entiende tus resultados')
    p(c,'No necesitas conocer de finanzas para comprender tu resultado. Estas cuatro ideas explican casi todo lo que verás a continuación.',MARGIN,667,SPACE,10,15,TEXT)
    concepts=[
        ('01','Rendimiento','Es cuánto subió o bajó el valor de tu inversión durante un periodo.'),
        ('02','Volatilidad','Mide cuánto se mueve el precio. Una cartera puede crecer y aun así tener caídas fuertes.'),
        ('03','Diversificación','Consiste en repartir el dinero entre inversiones que no se comportan exactamente igual.'),
        ('04','Índice de Sharpe','Compara el rendimiento adicional frente a la renta fija con las oscilaciones de la cartera.')]
    y=593
    for no,title,descr in concepts:
        t(c,MARGIN,y,no,10,RUST,True)
        t(c,MARGIN+43,y,title,15,MIDNIGHT,serif=True)
        p(c,descr,MARGIN+43,y-10,SPACE-43,9.2,13.8,TEXT)
        line(c,MARGIN,y-52,R,y-52)
        y-=83
    # Pull quote used sparingly; nondecorative.
    c.setFillColor(RUST);c.rect(MARGIN,153,3,73,fill=1,stroke=0)
    t(c,MARGIN+15,203,'No se trata solo de cuánto ganas,',17,MIDNIGHT,serif=True)
    t(c,MARGIN+15,182,'sino del riesgo que aceptas.',17,MIDNIGHT,serif=True)
    p(c,'Sharpe = (rendimiento esperado − tasa de referencia) ÷ volatilidad. Un valor mayor suele indicar una mejor relación entre ambos, pero no asegura ganancias.',MARGIN,136,SPACE,8.7,13,SUB)
    note='Se seleccionaron empresas con información conocida de 2026: esta es una demostración retrospectiva, no una predicción.' if retrospective else 'La selección se realizó con datos previos al periodo de prueba.'
    p(c,note,MARGIN,83,SPACE,7.8,11,SUB)
    foot(c,2,total)

    # 03 · Carteras: tabla sin cuadros, métricas y un gráfico principal.
    header(c,'','TU PROPUESTA','Tu cartera, tus decisiones')
    p(c,'Estas son las inversiones y los porcentajes que elegiste. No se añadieron activos que hayas dejado en cero.',MARGIN,668,SPACE,9.5,14,SUB)
    a=SPACE/3
    for i,(v,label_) in enumerate([(fmt(os.get('retorno'),True),'Rendimiento esperado'),(fmt(os.get('volatilidad'),True),'Volatilidad anual'),(fmt(os.get('sharpe')),'Índice de Sharpe')]):
        large_stat(c,MARGIN+i*a,619,v,label_,a-15)
    holdings(c,own,labels,MARGIN,560,300)
    margin_note(c,'Resultado de esta cartera',f'Rendimiento observado: {personal}. Una inversión de 100% en {fixed} habría obtenido {ref} en el mismo periodo.',MARGIN+328,429,SPACE-328)
    label(c,MARGIN,303,'EVOLUCIÓN HISTÓRICA',8.1,PETROL)
    figure(c,images.get('cartera_vs_renta_fija.png'),MARGIN,78,SPACE,207)
    p(c,f'Comparación diaria del rendimiento acumulado de tu cartera y {fixed}. Ambas líneas parten de cero.',MARGIN,72,SPACE,7.8,11,SUB)
    foot(c,3,total)

    # 04 · Recomendación.
    header(c,'','RECOMENDACIÓN ESTADÍSTICA','El portafolio para tu perfil')
    p(c,'La distribución propuesta busca equilibrar rendimiento esperado y volatilidad. Una cartera conservadora combina más renta fija; las otras asumen mayor exposición a acciones.',MARGIN,669,SPACE,9.5,14,SUB)
    for i,(v,label_) in enumerate([(fmt(rs.get('retorno'),True),'Rendimiento esperado'),(fmt(rs.get('volatilidad'),True),'Volatilidad anual'),(fmt(rs.get('sharpe')),'Índice de Sharpe')]):
        large_stat(c,MARGIN+i*a,618,v,label_,a-15)
    holdings(c,optimal,labels,MARGIN,559,300)
    alloc_txt={'Conservador':'70% renta fija, 30% acciones','Balanceado':'40% renta fija, 60% acciones','Agresivo':'100% acciones'}.get(profile,'Distribución de acuerdo con el perfil')
    margin_note(c,'La lógica de la recomendación',f'{alloc_txt}. Cada empresa puede recibir como máximo el 40% de la parte destinada a acciones.',MARGIN+328,427,SPACE-328)
    label(c,MARGIN,303,'COMPARACIÓN DE RESULTADOS',8.1,PETROL)
    figure(c,images.get('cartera_vs_recomendacion.png'),MARGIN,79,SPACE,207)
    p(c,f'Tu cartera frente a la recomendación y a {fixed}. El resultado observado de la recomendada fue {rec}.',MARGIN,73,SPACE,7.8,11,SUB)
    foot(c,4,total)

    # 05 · Gráficas, con abundante espacio para leer.
    header(c,'','LECTURA DE MERCADO','Rendimiento frente a riesgo')
    p(c,'La rentabilidad histórica más alta no siempre corresponde a la cartera más conveniente. Las variaciones en el camino también importan.',MARGIN,670,SPACE,9.6,14,TEXT)
    label(c,MARGIN,627,'01   EVOLUCIÓN HISTÓRICA  /  2026',8.3,PETROL)
    figure(c,images.get('comparacion_final.png'),MARGIN,378,SPACE,240)
    line(c,MARGIN,367,R,367)
    label(c,MARGIN,347,'02   Frontera de Markowitz',8.3,PETROL)
    figure(c,images.get('frontera_markowitz.png'),MARGIN,104,SPACE,235)
    p(c,'La Frontera de Markowitz muestra las relaciones posibles entre rendimiento esperado y riesgo. El máximo Sharpe sirve como referencia; tu cartera libre puede seguir reglas diferentes.',MARGIN,96,SPACE,8.0,11.5,SUB)
    foot(c,5,total)

    # Noticias: solo las empresas seleccionadas y referencias clicables.
    for idx in range(nnews):
        news_page(c,news[5*idx:5*(idx+1)],labels,6+idx,total,idx+1,nnews)

    c.save()
    return b.getvalue()
