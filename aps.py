# =====================================================
# =================== IMPORTS =========================
# =====================================================
import os
import requests
import re
from datetime import datetime, timezone, timedelta
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, session, url_for, send_file

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import landscape, letter


# =====================================================
# =================== APP CONFIG ======================
# =====================================================

app = Flask(__name__)
app.secret_key = "fac_login_fijo_2026"
app.config["SERVER_START_TIME"] = datetime.now(timezone.utc).timestamp()


# =====================================================
# =================== FUNCIONES AUX ===================
# =====================================================

def clasificar_probabilidad(valor):
    try:
        v = int(str(valor).replace("%", ""))
    except:
        return "VERY LOW"

    if v <= 20:
        return "VERY LOW"
    elif v <= 40:
        return "LOW"
    elif v <= 60:
        return "MEDIUM"
    elif v <= 80:
        return "HIGH"
    else:
        return "VERY HIGH"


def clase_color_probabilidad(escala):
    return {
        "VERY LOW": "nivel-verde-oscuro",
        "LOW": "nivel-verde",
        "MEDIUM": "nivel-amarillo",
        "HIGH": "nivel-naranja",
        "VERY HIGH": "nivel-rojo"
    }.get(escala, "nivel-verde-oscuro")


def kp_a_g(kp):
    try:
        kp = float(kp)
    except:
        return "G0"

    if kp >= 9: return "G5"
    if kp >= 8: return "G4"
    if kp >= 7: return "G3"
    if kp >= 6: return "G2"
    if kp >= 5: return "G1"
    return "G0"


def clase_color_kp(kp):
    if kp < 5:
        return "nivel-verde-oscuro"
    elif kp < 6:
        return "nivel-amarillo"        # MINOR
    elif kp < 7:
        return "nivel-naranja"         # MODERATE
    elif kp < 8:
        return "nivel-naranja-oscuro"  # STRONG
    elif kp < 9:
        return "nivel-rojo"            # SEVERE
    else:
        return "nivel-vinotinto"       # EXTREME



# =====================================================
# =================== NOAA DATOS ======================
# =====================================================

def obtener_kp_real():
    try:
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        r = requests.get(url, timeout=10)
        data = r.json()

        for fila in reversed(data):
            if fila[1] != "null":
                return float(fila[1])
        return 0
    except:
        return 0


def obtener_kp_3h_3dias():
    try:
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        r = requests.get(url, timeout=10)
        data = r.json()

        bloques = []

        for fila in data[1:]:
            fecha_str = fila[0].split(".")[0]
            kp = fila[1]

            if kp != "null":
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
                fecha = fecha.replace(tzinfo=timezone.utc)

                bloques.append({
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "hora": fecha.strftime("%H:%M"),
                    "kp": float(kp)
                })

        bloques = bloques[-24:]

        for b in bloques:
            b["color"] = clase_color_kp(b["kp"])

        return bloques

    except Exception as e:
        print("Error KP:", e)
        return []


def obtener_probabilidades():
    try:
        r = requests.get("https://services.swpc.noaa.gov/text/3-day-forecast.txt", timeout=5)
        texto = r.text

        r1 = re.search(r"R1-R2\s+(\d+%)", texto)
        r3 = re.search(r"R3\s+or\s+greater\s+(\d+%)", texto)
        s1 = re.search(r"S1\s+or\s+greater\s+(\d+%)", texto)

        return {
            "R12": r1.group(1) if r1 else "0%",
            "R3": r3.group(1) if r3 else "0%",
            "S1": s1.group(1) if s1 else "0%"
        }

    except:
        return {"R12": "0%", "R3": "0%", "S1": "0%"}


# =====================================================
# =================== LOGIN ===========================
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    # 🔹 Si ya hay sesión activa → no mostrar login
    if "usuario" in session:
        return redirect(url_for("index"))

    if request.method == "POST":

        usuario = request.form.get("usuario")
        clave = request.form.get("clave")

        if usuario == "admin" and clave == "fac2026":
            session["usuario"] = "admin"
            session["login_time"] = app.config["SERVER_START_TIME"]
            return redirect(url_for("index"))

        else:
            return render_template("login.html", error="Credenciales incorrectas")

    # 🔹 ESTE RETURN FALTABA (para GET)
    return render_template("login.html")



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# =================== DASHBOARD =======================
# =====================================================
@app.route("/imagen_proxy")
def imagen_proxy():
    url = request.args.get("url")
    try:
        r = requests.get(url, timeout=10)
        return r.content, 200, {'Content-Type': r.headers['Content-Type']}
    except:
        return "", 404
    

@app.route("/")
def index():

    if "usuario" not in session:
        return redirect(url_for("login"))

    # ================= KP FORECAST =================
    try:
        forecast_url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
        r_forecast = requests.get(forecast_url, timeout=5)
        forecast_data = r_forecast.json()

        kp_values = [float(row[1]) for row in forecast_data[1:] if row[1] != "null"]
        kp_maximo = max(kp_values) if kp_values else 0

    except:
        kp_maximo = 0

    # ================= FECHA ACTUAL REAL (ZULU) =================
    ahora_utc = datetime.now(timezone.utc)
    fecha_actual = ahora_utc.strftime("%Y-%m-%d %H:%M UTC")

    # ================= KP REAL =================
    kp_real = obtener_kp_real()

    # ================= BLOQUES 3H =================
    bloques = obtener_kp_3h_3dias()

    # ================= PROBABILIDADES =================
    probs = obtener_probabilidades()

    # ================= FECHA EMISIÓN =================
    try:
        r_texto = requests.get(
            "https://services.swpc.noaa.gov/text/3-day-forecast.txt",
            timeout=5
        )
        texto = r_texto.text
        fecha_match = re.search(r"Issued:\s*(.+?UTC)", texto)
        fecha_emision = fecha_match.group(1) if fecha_match else "N/A"
    except:
        fecha_emision = "N/A"

    # ================= ESCALA GEOMAGNÉTICA =================
    escala_geo = clasificar_probabilidad(str(int(kp_maximo * 10)) + "%")
    clase_geo = clase_color_probabilidad(escala_geo)

    # ================= ALERTA =================
    if kp_maximo >= 7:
        alerta = "🔴 ALERTA SEVERA: Tormenta Geomagnética Fuerte (G3+)"
    elif kp_maximo >= 5:
        alerta = "🟠 ALERTA: Posible Tormenta Geomagnética (G1–G2)"
    else:
        alerta = None

    # ================= CONSTRUIR DICCIONARIO =================
    datos = {
        "kp_3h": bloques,

        "Kp_maximo": round(kp_maximo, 2),
        "Escala_G": kp_a_g(kp_maximo),

        "kp_real": kp_real,
        "kp_real_g": kp_a_g(kp_real),

        "Prob_R1_R2": probs["R12"],
        "Prob_R3": probs["R3"],
        "Prob_S1": probs["S1"],

        "Escala_R12": clasificar_probabilidad(probs["R12"]),
        "Escala_R3": clasificar_probabilidad(probs["R3"]),
        "Escala_S1": clasificar_probabilidad(probs["S1"]),

        "Clase_R12": clase_color_probabilidad(clasificar_probabilidad(probs["R12"])),
        "Clase_R3": clase_color_probabilidad(clasificar_probabilidad(probs["R3"])),
        "Clase_S1": clase_color_probabilidad(clasificar_probabilidad(probs["S1"])),

        "Escala_Geomagnetic": escala_geo,
        "Clase_Geomagnetic": clase_geo,

        "fecha_emision": fecha_emision,
        "fecha_actual": fecha_actual,

        "Alerta_Geomagnetica": alerta
    }

    # ================= IMÁGENES SDO =================
    aurora_url = "https://www.spaceweatherlive.com/images/SDO/SDO_HMIIF_1024.jpg" 
    sdo_url = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_2048_0193.jpg"

    return render_template(
        "index.html",
        datos=datos,
        aurora_url=aurora_url,
        sdo_url=sdo_url
    )


# =====================================================
# =================== REPORTE PDF =====================
# =====================================================

@app.route("/reporte")
def generar_reporte():

    bloques = obtener_kp_3h_3dias()
    kp_real = obtener_kp_real()
    probs = obtener_probabilidades()

    file_path = os.path.join(app.root_path, "reporte_FAC.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(letter),
        rightMargin=25,
        leftMargin=25,
        topMargin=40,
        bottomMargin=30
    )

    elements = []
    styles = getSampleStyleSheet()

    # ================= ENCABEZADO =================

    elements.append(Paragraph("<b>FUERZA AEROESPACIAL COLOMBIANA</b>", styles["Title"]))
    elements.append(Paragraph("Comando de Operaciones Aéreas y Espaciales", styles["Normal"]))
    elements.append(Paragraph("Centro de Operaciones Espaciales", styles["Normal"]))
    elements.append(Spacer(1, 0.4 * inch))

    # ================= RESUMEN =================

    elements.append(Paragraph("<b>SPACE WEATHER REPORT</b>", styles["Heading2"]))
    elements.append(Spacer(1, 0.2 * inch))

    resumen = [
        ["Emission Date", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
        ["Observed Kp", f"{kp_real} ({kp_a_g(kp_real)})"],
        ["Solar Radiation (S1+)", probs["S1"]],
        ["Radio Blackouts (R1-R2)", probs["R12"]],
        ["Radio Blackouts (R3+)", probs["R3"]],
    ]

    resumen_table = Table(resumen, colWidths=[2.5*inch, 3*inch])
    resumen_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f4f4f4")),
    ]))

    elements.append(resumen_table)
    elements.append(Spacer(1, 0.4 * inch))

    # ================= TABLA OPERACIONAL =================

    elements.append(Paragraph("<b>SPACE ENVIRONMENT THREATS (OPERATIONAL VIEW)</b>", styles["Heading2"]))
    elements.append(Spacer(1, 0.3 * inch))

    tabla = []
    header = ["Threat"] + [b["hora"]+"Z" for b in bloques]
    tabla.append(header)

    filas = [
        "Radio Blackouts (R)",
        "Solar Radiation (S)",
        "Geomagnetic Storm (G)",
        "Possible Affectations",
        "Satellite Operations",
        "Power Systems",
        "HF Communications",
        "Navigation"
    ]

    for fila in filas:
        tabla.append([fila] + [""] * len(bloques))

    total_width = landscape(letter)[0] - 60
    first_col = 2.6 * inch
    dynamic = (total_width - first_col) / len(bloques)

    table = Table(tabla, colWidths=[first_col] + [dynamic]*len(bloques), repeatRows=1)

    style = TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
    ])

    # Separador oscuro
    style.add("BACKGROUND", (0,4), (-1,4), colors.HexColor("#1c2833"))
    style.add("TEXTCOLOR", (0,4), (-1,4), colors.white)

    def color_kp(kp):
        if kp < 5:
            return colors.HexColor("#2e7d32")
        elif kp < 6:
            return colors.yellow
        elif kp < 7:
            return colors.orange
        elif kp < 8:
            return colors.HexColor("#e65100")
        elif kp < 9:
            return colors.red
        else:
            return colors.HexColor("#8b0000")

    for col in range(1, len(bloques)+1):
        kp = bloques[col-1]["kp"]
        c = color_kp(kp)
        for row in [1,2,3,5,6,7,8]:
            style.add("BACKGROUND", (col,row), (col,row), c)

    table.setStyle(style)
    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))

    # ================= IMÁGENES SOLARES =================

    from reportlab.platypus import Image

    try:
        img1 = Image("https://www.spaceweatherlive.com/images/SDO/SDO_HMIIF_1024.jpg", width=3*inch, height=3*inch)
        img2 = Image("https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0193.jpg", width=3*inch, height=3*inch)

        images_table = Table([[img1, img2]], colWidths=[4*inch,4*inch])
        elements.append(Paragraph("<b>CURRENT SOLAR ACTIVITY</b>", styles["Heading2"]))
        elements.append(Spacer(1,0.3*inch))
        elements.append(images_table)

    except:
        elements.append(Paragraph("Solar images not available.", styles["Normal"]))

    elements.append(Spacer(1,0.5*inch))
    elements.append(Paragraph("Information provided by NOAA", styles["Normal"]))

    doc.build(elements)

    return send_file(file_path, as_attachment=True)


# =====================================================
# =================== MAIN ============================
# =====================================================

#if __name__ == "__main__":
#    app.run(host="127.0.0.1", port=5050, debug=True)

if __name__ == "__main__":
    app.run()
