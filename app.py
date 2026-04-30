from flask import Flask, render_template, request, redirect
import psycopg2
from datetime import datetime, timedelta

app = Flask(__name__)

DB_URL = "postgresql://postgres.sqbgizedptxsuznfewhi:MinsaMCC100@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

def get_conn():
    return psycopg2.connect(DB_URL)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/patients")
def patients():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, hc, community, dni, last_name, mother_last_name,
               first_name, birth_date, sex, phone
        FROM patients
        ORDER BY 
            LOWER(TRIM(last_name)),
            LOWER(TRIM(mother_last_name)),
            LOWER(TRIM(first_name))
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("patients.html", patients=rows)

@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM patients WHERE id=%s", (id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(request.referrer or "/patients")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":

        cur.execute("""
            UPDATE patients
            SET hc=%s,
                community=%s,
                dni=%s,
                last_name=%s,
                mother_last_name=%s,
                first_name=%s,
                birth_date=%s,
                sex=%s,
                phone=%s
            WHERE id=%s
        """, (
            request.form["hc"],
            request.form["community"],
            request.form["dni"],
            request.form["last_name"],
            request.form["mother_last_name"],
            request.form["first_name"],
            request.form["birth_date"] or None,
            request.form["sex"],
            request.form["phone"],
            id
        ))

        conn.commit()
        cur.close()
        conn.close()

        next_page = request.args.get("next")
        return redirect(next_page or "/patients")

    # GET
    cur.execute("""
        SELECT id, hc, community, dni, last_name, mother_last_name,
               first_name, birth_date, sex, phone
        FROM patients WHERE id=%s
    """, (id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    # convertir a dict para usar p.hc en HTML
    p = {
        "id": row[0],
        "hc": row[1],
        "community": row[2],
        "dni": row[3],
        "last_name": row[4],
        "mother_last_name": row[5],
        "first_name": row[6],
        "birth_date": row[7],
        "sex": row[8],
        "phone": row[9]
    }

    return render_template("edit.html", p=p)


@app.route("/register", methods=["GET", "POST"])
def register():

    mensaje = ""

    if request.method == "POST":

        hc = request.form["hc"]
        community = request.form["community"]
        dni = request.form["dni"] or None
        last_name = request.form["last_name"]
        mother_last_name = request.form["mother_last_name"]
        first_name = request.form["first_name"]
        birth_date = request.form["birth_date"] or None
        sex = request.form["sex"]
        phone = request.form["phone"] or None

        try:
            conn = get_conn()
            cur = conn.cursor()

            if dni:
                cur.execute("SELECT id FROM patients WHERE dni=%s", (dni,))
                if cur.fetchone():
                    mensaje = "❌ Ya existe un paciente con ese DNI"
                    cur.close()
                    conn.close()
                    return render_template("register.html", mensaje=mensaje)


            cur.execute("""
                INSERT INTO patients
                (hc, community, dni, last_name, mother_last_name,
                 first_name, birth_date, sex, phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                hc, community, dni, last_name,
                mother_last_name, first_name,
                birth_date, sex, phone
            ))

            conn.commit()
            cur.close()
            conn.close()

            mensaje = "✅ Paciente registrado correctamente"

        except Exception as e:
            mensaje = f"❌ Error: {str(e)}"

    return render_template("register.html", mensaje=mensaje)


@app.route("/search", methods=["GET", "POST"])
def search():

    pacientes = []

    if request.method == "POST":

        tipo = request.form["tipo"]
        valor = request.form["valor"]

        conn = get_conn()
        cur = conn.cursor()

        query = """
            SELECT id, hc, community, dni, last_name, mother_last_name,
                   first_name, birth_date, sex, phone
            FROM patients
        """

        params = []

        if tipo == "apellido":
            query += " WHERE last_name ILIKE %s OR mother_last_name ILIKE %s"
            params = [f"%{valor}%", f"%{valor}%"]

        elif tipo == "dni":
            query += " WHERE dni ILIKE %s"
            params = [f"%{valor}%"]

        elif tipo == "hc":
            query += " WHERE hc ILIKE %s"
            params = [f"%{valor}%"]

        elif tipo == "anio" and valor.isdigit():
            query += " WHERE EXTRACT(YEAR FROM birth_date) = %s"
            params = [int(valor)]

        # 🔥 ORDEN CORRECTO (paterno + materno + nombre)
        query += """
        ORDER BY 
            LOWER(TRIM(last_name)),
            LOWER(TRIM(mother_last_name)),
            LOWER(TRIM(first_name))
        """

        cur.execute(query, params)
        pacientes = cur.fetchall()

        cur.close()
        conn.close()

    return render_template("search.html", pacientes=pacientes)

@app.route("/controls/<grupo>", methods=["GET", "POST"])
def controls(grupo):

    conn = get_conn()
    cur = conn.cursor()

    year = datetime.now().year

    grupos = {
        "adolescentes": (12, 17, 3),
        "jovenes": (18, 29, 3),
        "adultos": (30, 59, 1),
        "adultos_mayores": (60, 120, 6)
    }

    nombres_adulto_mayor = [
        "Visita", "Vacuna", "Salud Mental",
        "Nutrición", "Salud Ocular", "VACAM"
    ]

    if grupo not in grupos:
        return "Grupo inválido"

    edad_min, edad_max, n_controles = grupos[grupo]

    # 🔥 CLAVE: FILTRAR CONTROL_TYPE SEGÚN GRUPO
    if grupo == "adultos_mayores":
        filtro_controles = "AND (c.control_type BETWEEN 1 AND 6 OR c.control_type IS NULL)"
    else:
        filtro_controles = ""

    query = f"""
        SELECT 
            p.id, p.hc, p.dni, p.last_name, p.mother_last_name,
            p.first_name,
            EXTRACT(YEAR FROM AGE(p.birth_date)) as edad,
            c.control_type, c.done, c.date
        FROM patients p
        LEFT JOIN controls c
            ON p.id = c.patient_id 
            AND c.year = %s
            {filtro_controles}
        WHERE EXTRACT(YEAR FROM AGE(p.birth_date)) BETWEEN %s AND %s
    """

    params = [year, edad_min, edad_max]

    # 🔍 filtros búsqueda
    if request.method == "POST":
        tipo = request.form.get("tipo")
        valor = request.form.get("valor", "")

        if tipo == "apellido":
            query += " AND (p.last_name ILIKE %s OR p.mother_last_name ILIKE %s)"
            params += [f"%{valor}%", f"%{valor}%"]

        elif tipo == "dni":
            query += " AND p.dni ILIKE %s"
            params.append(f"%{valor}%")

    # 🔥 ORDEN DOBLE (paterno + materno)
    query += " ORDER BY LOWER(p.last_name), LOWER(p.mother_last_name)"

    cur.execute(query, params)
    rows = cur.fetchall()

    pacientes = {}

    for r in rows:
        pid = r[0]

        if pid not in pacientes:
            pacientes[pid] = {
                "id": pid,
                "hc": r[1],
                "dni": r[2],
                "nombre": f"{r[3]} {r[4]} {r[5]}",
                "edad": int(r[6]),
                "controles": [
                    {"done": False, "fecha": "", "bloqueado": False}
                    for _ in range(n_controles)
                ]
            }

        if r[7] is not None:
            idx = r[7] - 1
            if 0 <= idx < n_controles:
                pacientes[pid]["controles"][idx]["done"] = r[8]
                pacientes[pid]["controles"][idx]["fecha"] = r[9] or ""

    # 🔒 solo secuencial para otros grupos
    if grupo != "adultos_mayores":
        for p in pacientes.values():
            for i in range(len(p["controles"])):
                if i > 0 and not p["controles"][i-1]["done"]:
                    p["controles"][i]["bloqueado"] = True

    pacientes = list(pacientes.values())

    total = len(pacientes)
    completos = sum(
        1 for p in pacientes
        if all(c["done"] for c in p["controles"])
    )

    if grupo == "adultos_mayores":
        headers = nombres_adulto_mayor
    else:
        headers = [f"{i+1}°" for i in range(n_controles)]

    cur.close()
    conn.close()

    imagenes = {
        "adolescentes": "Adolescente.jpeg",
        "jovenes": "Jovenes.jpeg",
        "adultos": "Adultos.jpeg",
        "adultos_mayores": "Adulto mayor.jpeg",
        "ninos": "logo.jpeg"
    }

    return render_template(
        "controls.html",
        grupo=grupo,
        pacientes=pacientes,
        headers=headers,
        total=total,
        completos=completos,
        imagen=imagenes.get(grupo, "logo.jpeg")
    )

@app.route("/controls/ninos", methods=["GET", "POST"])
def controls_ninos():

    conn = get_conn()
    cur = conn.cursor()

    year = datetime.now().year

    rango = request.form.get("rango")
    tipo = request.form.get("tipo")
    valor = request.form.get("valor", "")

    controles = {
        "menor1": ["7d","14d","21d","1m","2m","3m","4m","6m","7m","9m"],
        "1anio": ["1a","1a3m","1a6m","1a9m"],
        "2a4": ["Cumple", "Medio año"],
        "5a11": ["Control anual"]
    }

    if not rango:
        return render_template(
            "controls_ninos.html",
            pacientes=pacientes if rango else [],
            headers=controles[rango] if rango else [],
            rango=rango,
            total=total if rango else 0,
            completos=completos if rango else 0
        )

    # ======================
    # CONDICIÓN EDAD
    # ======================
    if rango == "menor1":
        condicion = "AGE(birth_date) < INTERVAL '1 year'"
    elif rango == "1anio":
        condicion = "AGE(birth_date) >= INTERVAL '1 year' AND AGE(birth_date) < INTERVAL '2 years'"
    elif rango == "2a4":
        condicion = "AGE(birth_date) >= INTERVAL '2 years' AND AGE(birth_date) < INTERVAL '5 years'"
    elif rango == "5a11":
        condicion = "AGE(birth_date) >= INTERVAL '5 years' AND AGE(birth_date) < INTERVAL '12 years'"

    query = f"""
        SELECT 
            p.id, p.hc, p.dni,
            p.last_name, p.mother_last_name, p.first_name,
            p.birth_date,
            EXTRACT(YEAR FROM AGE(p.birth_date)) as edad,
            c.control_type, c.done, c.date
        FROM patients p
        LEFT JOIN controls c
            ON p.id = c.patient_id AND c.year = %s
        WHERE {condicion}
    """

    params = [year]

    if tipo == "apellido":
        query += " AND (p.last_name ILIKE %s OR p.mother_last_name ILIKE %s)"
        params += [f"%{valor}%", f"%{valor}%"]

    elif tipo == "dni":
        query += " AND p.dni ILIKE %s"
        params.append(f"%{valor}%")

    cur.execute(query, params)
    rows = cur.fetchall()

    pacientes = {}
    n = len(controles[rango])

    # ======================
    # FUNCIÓN FECHA OBJETIVO
    # ======================
    def calcular_fecha_objetivo(birth_date, tipo_control):
        if rango == "menor1":
            dias = [7,14,21,30,60,90,120,180,210,270]
            return birth_date + timedelta(days=dias[tipo_control])

        elif rango == "1anio":
            meses = [12,15,18,21]
            return birth_date + timedelta(days=meses[tipo_control]*30)

        elif rango == "2a4":
            if tipo_control == 0:
                return birth_date + timedelta(days=365*edad_actual)
            else:
                return birth_date + timedelta(days=365*edad_actual + 180)

        elif rango == "5a11":
            return birth_date + timedelta(days=365*edad_actual)

        return None

    # AGRUPAR
    for r in rows:
        pid = r[0]
        birth = r[6]
        edad_actual = int(r[7])

        if pid not in pacientes:
            pacientes[pid] = {
                "id": pid,
                "hc": r[1],
                "dni": r[2],
                "nombre": f"{r[3]} {r[4]} {r[5]}",
                "edad": edad_actual,
                "controles": [
                    {"done": False, "fecha": "", "esperada": ""}
                    for _ in range(n)
                ]
            }

            # calcular fechas objetivo
            for i in range(n):
                fecha_obj = calcular_fecha_objetivo(birth, i)
                if fecha_obj:
                    pacientes[pid]["controles"][i]["esperada"] = fecha_obj.strftime("%Y-%m-%d")

        # cargar datos reales
        if r[8] is not None:
            if rango == "5a11":
                if r[8] == 1:
                    pacientes[pid]["controles"][0]["done"] = r[9]
                    pacientes[pid]["controles"][0]["fecha"] = r[10] or ""
            else:
                idx = r[8] - 1
                if 0 <= idx < n:
                    pacientes[pid]["controles"][idx]["done"] = r[9]
                    pacientes[pid]["controles"][idx]["fecha"] = r[10] or ""

    pacientes = list(pacientes.values())

    total = len(pacientes)
    completos = sum(
        1 for p in pacientes
        if all(c["done"] for c in p["controles"])
    )

    cur.close()
    conn.close()

    return render_template(
        "controls_ninos.html",
        pacientes=pacientes,
        headers=controles[rango],
        rango=rango,
        total=total,
        completos=completos
    )

@app.route("/controls/cancer", methods=["GET", "POST"])
def controls_cancer():

    conn = get_conn()
    cur = conn.cursor()

    year = datetime.now().year

    tipo = request.form.get("tipo")
    valor = request.form.get("valor", "")
    modo = request.form.get("modo")  # 👈 nuevo selector

    cancer_rules = {
        "mama": ("MAMA", "F", 40, 69),
        "prostata": ("PROSTATA", "M", 50, 75),
        "colon": ("COLON", "ALL", 50, 70),
        "piel": ("PIEL", "ALL", 18, 70)
    }

    # SI NO SE HA ELEGIDO MODO
    if not modo:
        return render_template("controls_cancer.html", modo=None)

    nombre, sexo_req, min_e, max_e = cancer_rules[modo]

    query = """
        SELECT 
            p.id, p.hc, p.dni,
            p.last_name, p.mother_last_name, p.first_name,
            p.sex,
            EXTRACT(YEAR FROM AGE(p.birth_date)) as edad,
            c.control_type, c.done, c.date
        FROM patients p
        LEFT JOIN controls c
            ON p.id = c.patient_id AND c.year = %s
        WHERE EXTRACT(YEAR FROM AGE(p.birth_date))
        BETWEEN %s AND %s
    """

    params = [year, min_e, max_e]

    if sexo_req != "ALL":
        query += " AND p.sex = %s"
        params.append(sexo_req)

    if tipo == "apellido":
        query += " AND (p.last_name ILIKE %s OR p.mother_last_name ILIKE %s)"
        params += [f"%{valor}%", f"%{valor}%"]

    elif tipo == "dni":
        query += " AND p.dni ILIKE %s"
        params.append(f"%{valor}%")

    cur.execute(query, params)
    rows = cur.fetchall()

    pacientes = {}

    for r in rows:
        pid = r[0]

        if pid not in pacientes:
            pacientes[pid] = {
                "id": pid,
                "hc": r[1],
                "dni": r[2],
                "nombre": f"{r[3]} {r[4]} {r[5]}",
                "edad": r[7],
                "controles": {
                    nombre: {
                        "tipo": 1,
                        "done": False,
                        "fecha": ""
                    }
                }
            }

        if r[8] == 1:
            pacientes[pid]["controles"][nombre]["done"] = r[9]
            pacientes[pid]["controles"][nombre]["fecha"] = r[10] or ""

    pacientes = list(pacientes.values())

    total = len(pacientes)
    completos = sum(1 for p in pacientes if p["controles"][nombre]["done"])

    cur.close()
    conn.close()

    return render_template(
        "controls_cancer.html",
        modo=modo,
        pacientes=pacientes,
        nombre=nombre,
        total=total,
        completos=completos
    )

@app.route("/toggle/<int:patient_id>/<int:control_type>")
def toggle(patient_id, control_type):

    conn = get_conn()
    cur = conn.cursor()

    year = datetime.now().year
    today = datetime.now().date()

    cur.execute("""
        SELECT id, done FROM controls
        WHERE patient_id=%s AND year=%s AND control_type=%s
    """, (patient_id, year, control_type))

    row = cur.fetchone()

    if row:
        nuevo = not row[1]

        if nuevo:
            cur.execute("""
                UPDATE controls
                SET done=%s, date=%s
                WHERE id=%s
            """, (True, today, row[0]))
        else:
            cur.execute("""
                UPDATE controls
                SET done=%s, date=NULL
                WHERE id=%s
            """, (False, row[0]))
    else:
        cur.execute("""
            INSERT INTO controls (patient_id, year, control_type, done, date)
            VALUES (%s,%s,%s,TRUE,%s)
        """, (patient_id, year, control_type, today))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(request.referrer)

if __name__ == "__main__":
    app.run(debug=True)