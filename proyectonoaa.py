# ============================================================
# IMPORTS
# ============================================================

import re
import base64
import requests
import smtplib
import threading
import time
import threading
import time
import requests
import os


from flask import Response
from datetime import datetime, timezone
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, session, send_file

from email.mime.text import MIMEText

from reportlab.platypus import SimpleDocTemplate, Image, PageBreak
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import TableStyle
from reportlab.lib import colors
from reportlab.platypus import TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet



# ============================================================
# CONFIGURACION APP
# ============================================================

app = Flask(__name__)

app.secret_key = "fac_space_weather_2026"


# ============================================================
# CONFIGURACION EMAIL ALERTAS
# ============================================================

EMAIL_ORIGEN = "sebasgalvis04@gmail.com"
EMAIL_PASSWORD = "qzmvjoybzjabfyer"
EMAIL_DESTINO = "isabeldiazbuitrago2003@gmail.com"


# ============================================================
# NOAA SCALES
# conversion KP → G scale
# ============================================================

def kp_a_g(kp):

    kp=float(kp)

    if kp >= 9: return "G5"
    if kp >= 8: return "G4"
    if kp >= 7: return "G3"
    if kp >= 6: return "G2"
    if kp >= 5: return "G1"

    return "G0"


# ============================================================
# COLORES NOAA PARA TABLA
# ============================================================

def nivel_G(kp):

    kp=float(kp)

    if kp <5: return 0
    if kp <6: return 1
    if kp <7: return 2
    if kp <8: return 3
    if kp <9: return 4

    return 5


def clase_G(kp):

    colores=[

        "nivel-verde-oscuro",
        "nivel-amarillo",
        "nivel-naranja",
        "nivel-naranja-oscuro",
        "nivel-rojo",
        "nivel-vinotinto"

    ]

    return colores[nivel_G(kp)]

def nivel_R(probs):

    r12 = int(probs["R12"].replace("%",""))
    r3  = int(probs["R3"].replace("%",""))

    # 🔥 inferencia del nivel máximo posible
    if r3 > 0:
        return "R3"   # mínimo R3 (no sabemos si es R4/R5 aún)

    if r12 > 0:
        return "R1"   # agrupamos R1/R2

    return "R0"

def clase_R_nivel(nivel):

    mapa = {
        "R0": "nivel-verde-oscuro",
        "R1": "nivel-amarillo",
        "R2": "nivel-amarillo",
        "R3": "nivel-naranja",
        "R4": "nivel-rojo",
        "R5": "nivel-vinotinto"
    }

    return mapa.get(nivel, "nivel-verde-oscuro")

def clase_R(prob):

    if isinstance(prob, str):
        p = int(prob.replace("%",""))
    else:
        p = int(prob)

    if p <10: return "nivel-verde-oscuro"
    if p <30: return "nivel-amarillo"
    if p <60: return "nivel-naranja"

    return "nivel-rojo"


def clase_S(prob):

    if isinstance(prob, str):
        p = int(prob.replace("%",""))
    else:
        p = int(prob)

    if p <10: return "nivel-verde-oscuro"
    if p <30: return "nivel-amarillo"
    if p <60: return "nivel-naranja"

    return "nivel-rojo"


# ============================================================
# NOAA DATA
# descarga txt oficial NOAA
# https://services.swpc.noaa.gov/text/3-day-forecast.txt
# ============================================================
time_blocks = [
"00-03",
"03-06",
"06-09",
"09-12",
"12-15",
"15-18",
"18-21",
"21-00"
]

def construir_grid(forecast):

    grid = {}

    probs = obtener_probabilidades()  # 🔥 SOLO UNA VEZ

    # 🔥 AJUSTE FINO DE PROBABILIDAD → NIVEL VISUAL
    def prob_a_nivel(p):
        p = int(p.replace("%",""))

        if p == 0: return 0        # verde
        if p < 20: return 1        # amarillo (bajo)
        if p < 50: return 2        # naranja (moderado)
        return 3                   # rojo (alto)

    # 🔥 separar correctamente
    r12 = prob_a_nivel(probs["R12"])   # R1-R2
    r3  = prob_a_nivel(probs["R3"])    # R3+
    s1  = prob_a_nivel(probs["S1"])

    for i, b in enumerate(forecast):

        bloque = b["hora"].replace("UT","")

        for day in [1,2,3]:

            kp = b[f"d{day}"]

            # G dinámico (correcto)
            if kp >= 9: g = 5
            elif kp >= 8: g = 4
            elif kp >= 7: g = 3
            elif kp >= 6: g = 2
            elif kp >= 5: g = 1
            else: g = 0

            grid[f"G-{day}-{bloque}"] = g

            # 🔥 CORRECCIÓN CLAVE
            # NO mezclar r12 con r3 como máximo directo
            # porque eso infla todo a R3 visual

            # decidir qué evento domina (lógica correcta)
            if r3 >= 2:
                valor_R = probs["R3"]
            else:
                valor_R = probs["R12"]

            # 🔥 guardar porcentaje (no nivel)
            grid[f"R-{day}-{bloque}"] = valor_R

            # 🔥 S igual
            grid[f"S-{day}-{bloque}"] = probs["S1"]

    return grid


def etiqueta_valor(tipo, valor, probs):

    # convertir a número si viene como "10%"
    if isinstance(valor, str):
        p = int(valor.replace("%",""))
    else:
        p = int(valor)

    # 🔥 si es nivel 0 → no mostrar nada
    if p == 0:
        return ""

    if tipo == "G":
        return f"G{p}"

    if tipo == "R":

        r3 = int(probs["R3"].replace("%",""))
        r12 = int(probs["R12"].replace("%",""))

        if r3 > 0 and r12 > 0:
            return "R1-R2 / R3+"

        if r12 > 0:
            return "R1-R2"

        if r3 > 0:
            return "R3+"

        return ""

    if tipo == "S":
        return "S1+" if p > 0 else ""

    return ""



def afectaciones(grid):

    resultado={}

    # 🔥 función interna para convertir a número
    def a_num(x):
        if isinstance(x, str):
            return int(x.replace("%",""))
        return x

    for key in grid:

        partes = key.split("-")

        tipo = partes[0]

        day = partes[1]

        bloque = partes[2] + "-" + partes[3]

        # 🔥 convertir antes de usar
        g = a_num(grid.get(f"G-{day}-{bloque}",0))
        r = a_num(grid.get(f"R-{day}-{bloque}",0))
        s = a_num(grid.get(f"S-{day}-{bloque}",0))

        # reglas de impacto operacional (igual que antes)
        resultado[f"SAT-{day}-{bloque}"]=max(g,s)

        resultado[f"POWER-{day}-{bloque}"]=g

        resultado[f"HF-{day}-{bloque}"]=max(r,s,g if g>=3 else 0)

        resultado[f"NAV-{day}-{bloque}"]=max(r,s,g if g>=3 else 0)


    return resultado


def obtener_forecast():

    url="https://services.swpc.noaa.gov/text/3-day-forecast.txt"

    try:
        txt = requests.get(url, timeout=10).text.splitlines()
    except:
        return [], []
        
    tabla=[]
    fechas=[]

    leyendo=False

    for linea in txt:

        linea=linea.strip()

        # detectar fechas aunque NOAA cambie el orden
        fechas_detectadas = re.findall(
            r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|[A-Za-z]{3}\s+\d{1,2}\s+\d{4}",
            linea
        )

        if len(fechas_detectadas) >= 3:
            fechas = fechas_detectadas[:3]



        # inicio tabla kp
        if "00-03UT" in linea:
            leyendo=True

        # capturar bloques UT incluyendo 21-00UT
        if leyendo and re.match(r"^\d{2}-\d{2}UT", linea):

            rawParts = linea.split()

            partes = []

            for token in rawParts:

                if token.startswith("(") and len(partes) > 0:

                    partes[-1] = partes[-1] + " " + token

                else:

                    partes.append(token)

            if len(partes)>=4:

                try:

                    def limpiar_kp(valor):

                        # detectar si NOAA indica G1 explícitamente
                        if "(G1)" in valor:
                            return 5.0

                        if "(G2)" in valor:
                            return 6.0

                        if "(G3)" in valor:
                            return 7.0

                        if "(G4)" in valor:
                            return 8.0

                        if "(G5)" in valor:
                            return 9.0

                        # eliminar texto restante
                        valor = re.sub(r"\(G\d\)", "", valor)

                        return float(valor)


                    tabla.append({

                        "hora": partes[0],

                        "d1": limpiar_kp(partes[1]),

                        "d2": limpiar_kp(partes[2]),

                        "d3": limpiar_kp(partes[3])

                    })

                except Exception as e:

                    print("ERROR linea forecast:", linea, e)

    return tabla, fechas

def descargar_imagen(url, nombre):

    carpeta = os.path.join("static", "imagenes")
    os.makedirs(carpeta, exist_ok=True)

    ruta_local = os.path.join(carpeta, nombre)

    try:
        r = requests.get(url, timeout=20)

        if r.status_code == 200:
            with open(ruta_local, "wb") as f:
                f.write(r.content)
            print(f"Imagen guardada: {ruta_local}")
        else:
            print(f"Error descargando {url}")

    except Exception as e:
        print("Error:", e)

    return f"imagenes/{nombre}"

# ============================================================
# KP MAX FORECAST
# calcula el mayor kp pronosticado en los 3 días
# ============================================================

def kp_max_forecast(forecast):

    return max(

        max(b["d1"], b["d2"], b["d3"])

        for b in forecast
    )


# ============================================================
# KP OBSERVADO ULTIMAS 24 HORAS
# usa NOAA planetary index
# ============================================================

def kp_24h():

    url="https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

    data=requests.get(url, timeout=10).json()

    valores=[

        float(x["Kp"])

        for x in data

        if x["Kp"]!=None

    ]

    return max(valores[-8:])


# ============================================================
# PROBABILIDADES NOAA
# R1-R2, R3+, S1+
# ============================================================

def obtener_probabilidades():

    url="https://services.swpc.noaa.gov/text/3-day-forecast.txt"

    txt=requests.get(url,timeout=10).text


    r12=re.search(r"R1-R2\s+(\d+%)",txt)

    r3=re.search(r"R3\s+or\s+greater\s+(\d+%)",txt)

    s1=re.search(r"S1\s+or\s+greater\s+(\d+%)",txt)


    return{

        "R12":r12.group(1) if r12 else "0%",

        "R3":r3.group(1) if r3 else "0%",

        "S1":s1.group(1) if s1 else "0%"

    }


# ============================================================
# ALERTAS NOAA OPERACIONALES
# genera texto de impacto operacional
# ============================================================

def generar_alertas(forecast, fechas, probs):

    alertas=[]

    hay_tormenta = False

    for i,b in enumerate(forecast):

        for dia,valor in enumerate([b["d1"],b["d2"],b["d3"]]):

            fecha_texto = fechas[dia] if dia < len(fechas) else f"Día {dia+1}"

            if valor >=5:

                hay_tormenta = True

                alertas.append({

                    "titulo":f"TORMENTA GEOMAGNÉTICA {kp_a_g(valor)}",

                    "descripcion":f"""

                    Fecha:
                    {fecha_texto}

                    Hora (UTC):
                    {b['hora']}

                    Kp pronosticado:
                    {valor}

                    Posibles efectos:

                    Sistemas de potencia:
                    Posibles fluctuaciones débiles 
                    en la red eléctrica.

                    Operaciones satelitales:
                    Posible impacto menor en satélites.

                    Navegación (GPS):
                    Posible degradación en la precisión.

                    Comunicaciones HF:
                    Posible degradación intermitente.
                    """,
                    "clase":clase_G(valor)

                })


    # ===============================
    # CONDICIONES TRANQUILAS (solo si no hay tormenta real)
    # ===============================
    if not hay_tormenta:

        kp_obs=kp_24h()

        alertas.append({

            "titulo":"CONDICIONES GEOMAGNÉTICAS TRANQUILAS",

            "descripcion":f"""
            El mayor índice Kp observado en 
            las últimas 24 horas fue {kp_obs}.

            No se esperan tormentas geomagnéticas (G1+).
            Operación normal.
            """,

            "clase":"alerta-verde"

        })


    # ===============================
    # RADIO (R) → PROBABILIDAD REAL
    # ===============================
    prob_r3 = int(probs["R3"].replace("%",""))

    # ===============================
    # RADIO R1-R2
    # ===============================
    prob_r12 = int(probs["R12"].replace("%",""))

    if prob_r12 > 0:

        if prob_r12 >= 50:
            nivel = "ALTA PROBABILIDAD"
        elif prob_r12 >= 20:
            nivel = "PROBABILIDAD MODERADA"
        else:
            nivel = "BAJA PROBABILIDAD"

        alertas.append({

            "titulo": f"PROBABILIDAD EVENTO RADIO R1-R2 ({nivel})",

            "descripcion": f"""
            Probabilidad:
            {probs['R12']}

            Posibles efectos:
            - Degradación de comunicaciones HF
            - Interferencias en navegación
            - Fallos intermitentes de señal
            """,

            "clase": clase_R(probs["R12"])

        })


    if prob_r3 > 0:

        if prob_r3 >= 50:
            nivel_r = "ALTA"
        elif prob_r3 >= 20:
            nivel_r = "MODERADA"
        else:
            nivel_r = "BAJA"

        alertas.append({

            "titulo":f"PROBABILIDAD EVENTO RADIO R3+ ({nivel_r})",

            "descripcion":f"""
            Probabilidad:
            {probs['R3']}

            Posibles efectos:
            - Apagón HF parcial
            - Degradación de navegación
            - Interrupciones temporales (hasta 1 hora)
            """,

            "clase":clase_R(probs["R3"])

        })


    # ===============================
    # RADIACIÓN SOLAR (S)
    # ===============================
    prob_s1 = int(probs["S1"].replace("%",""))

    if prob_s1 > 0:

        if prob_s1 >= 50:
            nivel_s = "ALTA"
        elif prob_s1 >= 20:
            nivel_s = "MODERADA"
        else:
            nivel_s = "BAJA"

        alertas.append({

            "titulo":f"PROBABILIDAD EVENTO RADIACIÓN S1+ ({nivel_s})",

            "descripcion":f"""
            Probabilidad:
            {probs['S1']}

            Posibles efectos:
            - Anomalías en satélites
            - Degradación HF en zonas polares
            - Incremento de radiación en vuelos
            """,

            "clase":clase_S(probs["S1"])

        })


    return alertas

# ============================================================
# ENVIO EMAIL ALERTAS
# ============================================================

def enviar_alerta_email(alertas):

    try:

        texto="FAC SPACE WEATHER ALERT\n\n"

        for a in alertas:

            texto+=a["titulo"]+"\n"+a["descripcion"]+"\n"


        msg=MIMEText(texto)

        msg["Subject"]="FAC SPACE WEATHER ALERT"

        msg["From"]=EMAIL_ORIGEN
        msg["To"]=EMAIL_DESTINO


        s=smtplib.SMTP("smtp.gmail.com",587)

        s.starttls()

        s.login(EMAIL_ORIGEN,EMAIL_PASSWORD)

        s.send_message(msg)

        s.quit()

    except Exception as e:

        print("EMAIL ERROR:",e)



def tarea_automatica():

    while True:

        try:

            forecast, fechas = obtener_forecast()            

            probs = obtener_probabilidades()

            alertas = generar_alertas(forecast, fechas, probs)

            enviar_alerta_email(alertas)

            print("EMAIL ENVIADO", datetime.now(timezone.utc))

        except Exception as e:

            print("ERROR EMAIL:", e)

        time.sleep(86400)  # 24 horas


threading.Thread(
    target=tarea_automatica,
    daemon=True
).start()


estado_anterior = {
    "G": None,
    "S": None,
    "R": None
}


def obtener_estado_actual():

    forecast, fechas = obtener_forecast()
    probs = obtener_probabilidades()

    kp_max = kp_max_forecast(forecast)

    estado = {

        "G": kp_a_g(kp_max),

        "S": probs["S1"],

        "R": probs["R3"]

    }

    alertas = generar_alertas(forecast, fechas, probs)

    return estado, alertas



def monitoreo_espacial():

    global estado_anterior

    while True:

        try:

            estado_actual, alertas = obtener_estado_actual()

            cambio = False

            for clave in estado_actual:

                if estado_actual[clave] != estado_anterior[clave]:

                    cambio = True


            # enviar si hubo cambio
            if cambio:

                enviar_alerta_email(alertas)

                print("CAMBIO DETECTADO:", estado_actual)

                estado_anterior = estado_actual


            # envío diario 06:00 UTC
            hora = datetime.now(timezone.utc)

            if hora.hour == 6 and hora.minute < 30:

                enviar_alerta_email(alertas)

                print("REPORTE DIARIO 06 UTC")


        except Exception as e:

            print("ERROR MONITOREO:", e)


        time.sleep(1800)  # revisar cada 30 minutos



threading.Thread(

    target=monitoreo_espacial,

    daemon=True

).start()

# ============================================================
# IMAGENES SOLARES NOAA / NASA
# ============================================================

#def obtener_imagenes():

    #return{

    #    "sunspots":"https://soho.nascom.nasa.gov/data/realtime/hmi_igr/1024/latest.jpg",

     #   "coronal":"https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png",
        
      #  "enlil":"https://services.swpc.noaa.gov/images/animations/enlil/latest.jpg",

       # "overview":"https://services.swpc.noaa.gov/images/swx-overview-small.gif"

    #}

def obtener_imagenes():

    return{
        "sunspots": descargar_imagen("https://soho.nascom.nasa.gov/data/realtime/hmi_igr/1024/latest.jpg","sunspots.jpg"),
        "coronal": descargar_imagen("https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png","coronal.jpg"),
        "enlil": descargar_imagen("https://services.swpc.noaa.gov/images/animations/enlil/latest.jpg","enlil.jpg"),
        "overview": descargar_imagen("https://services.swpc.noaa.gov/images/swx-overview-small.gif","overview.gif")
    }


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET","POST"])

def login():

    if request.method=="POST":

        if request.form["usuario"]=="admin" and request.form["clave"]=="fac2026":

            session["user"]=True

            return redirect("/")

    return render_template("login.html")



    
@app.route("/logout")

def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# DASHBOARD PRINCIPAL
# ============================================================

@app.route("/")

def index():

    if "user" not in session:

        return redirect("/login")


    forecast, fechas = obtener_forecast()

    print("FECHAS NOAA:", fechas)

    from datetime import timedelta

    if not fechas:

        hoy = datetime.now(timezone.utc)

        fechas = [

            hoy.strftime("%d %b %Y"),

            (hoy + timedelta(days=1)).strftime("%d %b %Y"),

            (hoy + timedelta(days=2)).strftime("%d %b %Y")

        ]


    probs = obtener_probabilidades()

    imagenes = obtener_imagenes()

    grid = construir_grid(forecast)

    impactos = afectaciones(grid)

    kp_max = kp_max_forecast(forecast)

    kp_obs = kp_24h()


    datos={

        "fecha":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),

        "kp_max":round(kp_max,2),

        "g_max":kp_a_g(kp_max),

        "kp_obs":round(kp_obs,2),

        "g_obs":kp_a_g(kp_obs),

        "Prob_S1":probs["S1"],

        "Prob_R12":probs["R12"],

        "Prob_R3":probs["R3"]

    }


    alertas = generar_alertas(forecast, fechas, probs)


    enviar_alerta_email(alertas)


    return render_template(

        "index.html",

        forecast=forecast,
        fechas=fechas,
        datos=datos,
        probs=probs,
        imagenes=imagenes,
        alertas=alertas,
        grid=grid,
        impactos=impactos,
        time_blocks=time_blocks,
        etiqueta_valor=etiqueta_valor,

        clase_G=clase_G,
        kp_a_g=kp_a_g,
        clase_R=clase_R,
        clase_S=clase_S

    )



# ============================================================
# PDF ESTABLE (optimiza imagen antes de insertar)
# ============================================================

from reportlab.platypus import Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image as PILImage


@app.route("/pdf")


@app.route("/pdf")
def generar_pdf():

    forecast, fechas = obtener_forecast()

    print("FECHAS NOAA:", fechas)

    from datetime import timedelta

    if not fechas:

        hoy = datetime.now(timezone.utc)

        fechas = [

            hoy.strftime("%d %b %Y"),

            (hoy + timedelta(days=1)).strftime("%d %b %Y"),

            (hoy + timedelta(days=2)).strftime("%d %b %Y")

        ]

    probs = obtener_probabilidades()

    imagenes = obtener_imagenes()

    grid = construir_grid(forecast)

    impactos = afectaciones(grid)

    kp_max = kp_max_forecast(forecast)

    kp_obs = kp_24h()

    datos = {

        "fecha": datetime.now(timezone.utc),

        "kp_max": kp_max,

        "g_max": kp_a_g(kp_max),

        "kp_obs": kp_obs,

        "g_obs": kp_a_g(kp_obs),

        "Prob_S1": probs["S1"],

        "Prob_R12": probs["R12"],

        "Prob_R3": probs["R3"]

    }

    alertas = generar_alertas(forecast, fechas, probs)

    html = render_template(

        "index.html",

        forecast=forecast,
        fechas=fechas,
        grid=grid,
        impactos=impactos,
        time_blocks=time_blocks,

        datos=datos,

        alertas=alertas,

        imagenes=imagenes,

        probs=probs

    )

    

    return Response(

        

        mimetype="application/pdf",

        headers={

            "Content-Disposition":

            "attachment; filename=reporte_clima_espacial.pdf"

        }

    )



# ============================================================

if __name__ == "__main__":

    app.run(host="0.0.0.0")

