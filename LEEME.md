# Laboratorio de inversión — Interfaz sencilla V9

Esta versión conserva los datos y el motor de máximo Sharpe. Solo se rediseñó la **interfaz**.

## Abrir en Windows

Abre la carpeta del proyecto en el Explorador, escribe `cmd` en su barra de dirección y ejecuta:

```bat
python -m pip install -r requirements.txt
python -m streamlit run app_usuario.py
```

Para examinar estadísticas y decisiones del algoritmo:

```bat
python -m streamlit run app_desarrollador.py
```

## ¿Qué cambia en el recorrido público?

- **Fondo claro** (marfil, azul petróleo, cobre), alineado con el PDF.
- **Cuatro etapas visibles**: elige y crea, mira cómo te fue, conócete, compara opciones. Las seis pantallas internas siguen disponibles.
- **Elige el mercado desde dos botones**. No se muestran listas técnicas.
- **Cartera libre:** barras y campos numéricos sincronizados. No se redistribuye nada automáticamente; deben sumar 100%.
- **Cuestionario:** se conservan diez preguntas en lenguaje cotidiano.
- **Resultados:** gráficas claras, cifras destacadas y comentarios breves. No hay fórmulas en la interfaz pública.
- **Frontera eficiente:** sigue existiendo en el proyecto y en el PDF, pero en la pantalla pública se muestra solo si la persona activa «Explorar la relación entre riesgo y rendimiento». En desarrollador se abre por defecto.
- **Navegación:** al cambiar de pantalla se solicita volver al inicio del contenido. Se conserva un enlace «Volver arriba» al final como respaldo, por si el navegador limita el desplazamiento automático desde el componente.
- **Informe PDF:** no cambia su contenido ni su estilo editorial. Incluye los datos personales elegidos, la recomendación, sus gráficas, las explicaciones y las noticias relevantes.

## ¿Qué no cambia?

Los activos de cada mercado, los históricos de 2016–2025, la comparación de enero a septiembre de 2026, la modalidad retrospectiva fija en la versión de usuario, la optimización de máximo Sharpe y sus restricciones **solo sobre las carteras recomendadas**, la selección sin límites de la cartera libre, el QR para una URL pública y el correo opcional.

**Transparencia:** la versión de usuario está configurada como demostración retrospectiva; utiliza información de 2026 para favorecer la selección de empresas, de modo que la comparación de 2026 no es una predicción hecha antes de conocer el año.

## Instalación parcial

Si ya tienes el proyecto, es suficiente reemplazar `app.py` y añadir el archivo `.streamlit/config.toml` incluido en el parche. No necesitas modificar `reporte_pdf.py` ni volver a descargar la carpeta `datos`.

## Validación

El código compila y se ejecutaron 20 pruebas automáticas sobre el motor, las restricciones, las gráficas, el PDF y la estructura de navegación. No fue posible iniciar la aplicación Streamlit visualmente en el entorno de pruebas, así que el desplazamiento automático debe confirmarse en tu navegador. Si un navegador bloquea el componente de desplazamiento, utiliza el enlace discreto «Volver arriba» al final de las pantallas.
