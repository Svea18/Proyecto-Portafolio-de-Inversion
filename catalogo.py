"""Universo de inversión y preguntas. Cambia aquí las preguntas sin tocar la optimización."""
US={'AAPL':'Apple','MSFT':'Microsoft','NVDA':'NVIDIA','AMZN':'Amazon',
    'JPM':'JPMorgan Chase','JNJ':'Johnson & Johnson','KO':'Coca-Cola',
    'XOM':'Exxon Mobil','WMT':'Walmart','CAT':'Caterpillar'}
MX={'FEMSAUBD.MX':'FEMSA','GFNORTEO.MX':'Banorte','AMXB.MX':'América Móvil',
    'WALMEX.MX':'Walmart de México','GMEXICOB.MX':'Grupo México',
    'CEMEXCPO.MX':'Cemex','BIMBOA.MX':'Grupo Bimbo',
    'ASURB.MX':'ASUR','GAPB.MX':'GAP','AC.MX':'Arca Continental'}

# Cada respuesta tiene exactamente 1, 2 o 3 puntos. 10 preguntas = 10 a 30 puntos.
# Se evita jerga financiera y se mezclan capacidad y disposición a asumir pérdidas.
PREGUNTAS = [
 ('¿Cuándo crees que necesitarás usar el dinero que inviertas?',
  [('En menos de un año',1),('Entre uno y cinco años',2),('Después de cinco años',3)]),
 ('Si surgiera un gasto inesperado importante, ¿cómo lo pagarías?',
  [('Tendría que pedir prestado o vender mis inversiones',1),('Usaría parte de mis ahorros',2),('Tengo dinero reservado para emergencias',3)]),
 ('¿Qué tan seguros son tus ingresos actualmente?',
  [('No tengo ingresos seguros',1),('Cambian de un mes a otro',2),('Son bastante estables',3)]),
 ('Si invirtieras 1,000 pesos y su valor bajara a 900 pesos, ¿qué harías?',
  [('Retiraría el dinero cuanto antes',1),('Esperaría un poco antes de decidir',2),('Podría dejarlo invertido a largo plazo',3)]),
 ('¿Qué es más importante para ti cuando inviertes?',
  [('Evitar que mi dinero baje de valor',1),('Tener un equilibrio entre seguridad y crecimiento',2),('Buscar más crecimiento aunque pueda perder',3)]),
 ('¿Qué tan cómodo te sentirías si tu inversión subiera y bajara con frecuencia?',
  [('Muy incómodo',1),('Algo incómodo, pero lo aceptaría',2),('Lo aceptaría si busco resultados a largo plazo',3)]),
 ('¿Qué parte de este dinero podrías necesitar para gastos cotidianos?',
  [('La mayor parte',1),('Una parte',2),('Prácticamente nada',3)]),
 ('Si la inversión tardara varios años en recuperarse de una caída, ¿qué pasaría?',
  [('Me afectaría mucho económicamente',1),('Tendría que ajustar algunos planes',2),('Podría esperar sin afectar mis gastos importantes',3)]),
 ('¿Cuál de estas opciones se parece más a lo que buscas?',
  [('Ganar poco, con menores cambios de valor',1),('Buscar ganancias moderadas con cambios intermedios',2),('Buscar ganancias mayores aceptando pérdidas posibles',3)]),
 ('¿Qué tan preparado estás para mantener una inversión durante una época difícil?',
  [('Preferiría retirarla pronto',1),('Intentaría esperar y revisarla',2),('Podría mantenerla si mis necesidades no cambian',3)]),
]

def grade(total):
    """Tres intervalos para puntuaciones entre 10 y 30."""
    if total <= 16: return 'Conservador'
    if total <= 23: return 'Balanceado'
    return 'Agresivo'
