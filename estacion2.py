from flask import Flask, render_template_string, jsonify, request
import time
from threading import Thread, Lock
import sqlite3
import os

app = Flask(__name__)
from flask_cors import CORS
CORS(app)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtr01.db")

# ============================================================
# CONFIGURACIÓN PARA ESP32
# ============================================================
# Si quieres una protección básica, descomenta y configura:
# ESP32_API_KEY = "mtr01-secret-2024"   # <-- cámbialo por tu clave

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            temperatura REAL,
            humedad REAL,
            presion REAL,
            uv REAL,
            lluvia REAL,
            viento REAL
        )
    """)
    conn.commit()
    conn.close()

def save_reading(data):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO sensor_readings (timestamp, temperatura, humedad, presion, uv, lluvia, viento)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (time.time(), data["temperatura"], data["humedad"], data["presion"], data["uv"], data["lluvia"], data["viento"]))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[DB ERROR]", e)

def get_last_reading():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT temperatura, humedad, presion, uv, lluvia, viento FROM sensor_readings ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "temperatura": row[0], "humedad": row[1], "presion": row[2],
                "uv": row[3], "lluvia": row[4], "viento": row[5]
            }
    except Exception as e:
        print("[DB READ ERROR]", e)
    return None

def get_historial_db(metrica, limit=100):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"SELECT {metrica} FROM sensor_readings ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [r[0] for r in reversed(rows)]
    except Exception as e:
        print("[DB HIST ERROR]", e)
    return []

# ============================================================
# ESTADO GLOBAL (thread-safe)
# ============================================================
sensor_data = {
    "temperatura": 18.44,
    "humedad": 62.00,
    "presion": 1013.25,
    "uv": 5.20,
    "lluvia": 0.00,
    "viento": 15.0
}

historial = {k: [] for k in sensor_data.keys()}
data_lock = Lock()
last_external_update = time.time()

# Inicializar base de datos y restaurar última lectura
init_db()
last = get_last_reading()
if last:
    sensor_data.update(last)

# ============================================================
# ENDPOINTS API
# ============================================================

@app.route('/api/status', methods=['GET'])
def api_status():
    """Para que el ESP32 verifique conectividad."""
    return jsonify({
        "status": "online",
        "server_time": time.time(),
        "last_update": last_external_update,
        "sensors": list(sensor_data.keys())
    }), 200

@app.route('/api/sensor-data', methods=['GET'])
def get_data():
    with data_lock:
        return jsonify(sensor_data)

@app.route('/api/historial/<metrica>', methods=['GET'])
def get_historial(metrica):
    with data_lock:
        if metrica in historial and len(historial[metrica]) > 0:
            return jsonify(historial[metrica])
    db_hist = get_historial_db(metrica)
    if db_hist:
        return jsonify(db_hist)
    return jsonify([]), 404

@app.route('/api/sensor-data', methods=['POST'])
def post_data():
    global sensor_data, last_external_update
    data = request.get_json(silent=True)

    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "JSON inválido o vacío"}), 400

    # Validación de campos requeridos
    required = ["temperatura", "humedad", "presion", "uv", "lluvia", "viento"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"status": "error", "message": f"Faltan campos: {missing}"}), 400

    # Validación opcional de API key (descomenta si la usas)
    # key = request.headers.get("X-API-Key")
    # if key != ESP32_API_KEY:
    #     return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        # Convertir a float y sanitizar
        payload = {
            "temperatura": float(data["temperatura"]),
            "humedad":     float(data["humedad"]),
            "presion":     float(data["presion"]),
            "uv":          float(data["uv"]),
            "lluvia":      float(data["lluvia"]),
            "viento":      float(data["viento"]),
        }
    except (ValueError, TypeError) as e:
        return jsonify({"status": "error", "message": f"Tipo de dato inválido: {e}"}), 400

    with data_lock:
        sensor_data.update(payload)
        last_external_update = time.time()
        for k in sensor_data:
            historial[k].append(sensor_data[k])
            if len(historial[k]) > 100:
                historial[k].pop(0)

    save_reading(sensor_data)
    print(f"[ESP32] Datos recibidos: {payload}")
    return jsonify({"status": "success", "data": sensor_data}), 200

# ============================================================
# HTML TEMPLATE (sin cambios visuales)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESTACIÓN MTR-01</title>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #04020e;
            --bg-mid: #07041a;
            --bg-card: rgba(120,60,255,0.05);
            --border: rgba(139,92,246,0.18);
            --border-bright: rgba(139,92,246,0.35);
            --text: #f0eeff;
            --text-dim: #9d8fc9;
            --temp: #ef4444; --hum: #06b6d4; --pres: #10b981; --uv: #f59e0b; --lluvia: #a855f7; --viento: #3b82f6;
            --violet: #8b5cf6; --cyan: #06b6d4;
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Syne',sans-serif; background:var(--bg); color:var(--text); overflow-x:hidden; min-height:100vh; }
        ::-webkit-scrollbar{width:6px} ::-webkit-scrollbar-track{background:var(--bg)} ::-webkit-scrollbar-thumb{background:rgba(139,92,246,0.4);border-radius:3px}

        #portal-screen {
            position:fixed; inset:0; z-index:1000;
            display:flex; flex-direction:column; align-items:center;
            justify-content:flex-start; overflow-y:auto; overflow-x:hidden;
            transition:opacity 1s ease, transform 1s ease;
        }
        #portal-screen.hidden { opacity:0; pointer-events:none; transform:scale(1.04); }

        #starCanvas { position:fixed; inset:0; z-index:0; pointer-events:none; }

        .portal-bg {
            position:fixed; inset:0; z-index:0;
            background:
                radial-gradient(ellipse 140% 80% at 50% 100%, rgba(100,30,220,0.5) 0%, rgba(40,10,100,0.25) 35%, transparent 60%),
                radial-gradient(ellipse 120% 60% at 50% 100%, rgba(60,15,160,0.35) 0%, transparent 50%),
                linear-gradient(180deg, #020108 0%, #050210 40%, #080318 100%);
        }

        .hero-text-block {
            position:relative; z-index:5;
            display:flex; flex-direction:column; align-items:center;
            text-align:center;
            padding-top:clamp(20px,3vh,40px);
            padding-bottom:clamp(10px,1.5vh,20px);
            gap:0;
        }

        .hero-badge {
            font-family:'JetBrains Mono',monospace;
            font-size:11px; letter-spacing:5px; text-transform:uppercase;
            color:rgba(220,200,255,0.98);
            border:1px solid rgba(139,92,246,0.55);
            padding:8px 24px; border-radius:22px;
            background:rgba(139,92,246,0.18);
            backdrop-filter:blur(10px);
            margin-bottom:clamp(16px,2.8vh,28px);
            box-shadow:0 0 25px rgba(139,92,246,0.25), 0 0 50px rgba(6,182,212,0.1);
            text-shadow:0 0 12px rgba(139,92,246,0.5);
        }

        .hero-title {
            font-size:clamp(2.2rem,5vw,4rem);
            font-weight:800; line-height:1.1; letter-spacing:-1px;
            background:linear-gradient(135deg, #ffffff 0%, #f0e8ff 30%, #d4c5ff 55%, #a080ff 80%, #06b6d4 100%);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
            margin-bottom:clamp(10px,1.8vh,18px);
            filter:drop-shadow(0 0 18px rgba(20,5,60,0.95))
                   drop-shadow(0 0 35px rgba(20,5,60,0.80))
                   drop-shadow(0 2px 6px rgba(0,0,0,0.7));
        }

        .hero-subtitle {
            font-size:clamp(0.9rem,1.5vw,1.15rem);
            color:rgba(230,210,255,1.0);
            font-weight:600; letter-spacing:0.5px;
            margin-bottom:0;
            text-shadow:
                0 0 12px rgba(10,3,40,0.99),
                0 0 28px rgba(10,3,40,0.85),
                0 1px 4px rgba(0,0,0,0.8),
                0 0 50px rgba(6,182,212,0.25);
        }

        .bh-wrapper {
            position:relative; z-index:3;
            display:flex; align-items:flex-start; justify-content:center;
            width:100%;
            flex-shrink:0;
            height:clamp(300px, 50vh, 520px);
            margin-top:clamp(-40px,-4vh,-15px);
            overflow:visible;
        }

        .bh-container {
            position:relative;
            width:clamp(300px,48vh,520px);
            height:clamp(300px,48vh,520px);
            flex-shrink:0;
        }

        .bh-outer-nebula {
            position:absolute;
            top:-60%; left:-55%; right:-55%; bottom:-35%;
            border-radius:50%;
            background:
                radial-gradient(ellipse 80% 55% at 50% 52%,
                    rgba(255,255,255,0.08)   0%,
                    rgba(200,80,255,0.30)     8%,
                    rgba(147,51,234,0.55)    18%,
                    rgba(109,20,220,0.40)    30%,
                    rgba(70,8,180,0.22)      45%,
                    rgba(30,4,120,0.10)      60%,
                    transparent              78%);
            filter:blur(38px);
            z-index:1; pointer-events:none;
            animation:halouPulse 6s ease-in-out infinite;
        }

        .bh-corona-top {
            position:absolute;
            top:-55%; left:-30%; right:-30%;
            height:80%;
            border-radius:50%;
            background:
                radial-gradient(ellipse 70% 60% at 50% 78%,
                    rgba(255,255,255,0.55)   0%,
                    rgba(255,240,255,0.45)   4%,
                    rgba(220,140,255,0.70)   10%,
                    rgba(168,85,247,0.80)    20%,
                    rgba(126,34,206,0.60)    34%,
                    rgba(88,14,175,0.35)     50%,
                    rgba(40,5,120,0.12)      68%,
                    transparent              84%);
            filter:blur(22px);
            z-index:2; pointer-events:none;
            animation:halouPulse 6s ease-in-out infinite 0.8s;
        }

        .bh-photon-ring {
            position:absolute; inset:5%; border-radius:50%;
            background:transparent;
            box-shadow:
                0 0  8px  3px rgba(255,245,255,0.90),
                0 0 20px  8px rgba(240,180,255,0.70),
                0 0 45px 18px rgba(200,90,255,0.50),
                0 0 90px 40px rgba(160,50,255,0.28),
                0 0 160px 80px rgba(120,20,240,0.14),
                0 -12px 60px 30px rgba(200,100,255,0.22),
                inset 0 0 30px 10px rgba(220,150,255,0.18);
            z-index:9; pointer-events:none;
            animation:photonPulse 4s ease-in-out infinite;
        }

        .bh-bottom-glow {
            position:absolute; bottom:-30%; left:-40%; right:-40%;
            height:90%;
            background:radial-gradient(ellipse 60% 40% at 50% 0%,
                rgba(147,51,234,0.40)  0%,
                rgba(109,20,220,0.22) 20%,
                rgba(70,8,180,0.10)   38%,
                transparent           60%);
            filter:blur(55px);
            z-index:0; pointer-events:none;
        }

        .bh-disc {
            position:absolute; inset:10%; border-radius:50%;
            background:#000000;
            border:none;
            box-shadow:
                inset 0 0 40px 15px rgba(60,10,140,0.18),
                inset 0 0 80px 35px rgba(0,0,0,0.6);
            z-index:10; pointer-events:none;
        }

        .bh-disc-ring {
            position:absolute;
            top:50%; left:50%;
            width:105%; height:34%;
            transform:translate(-50%, -20%) rotateX(0deg);
            z-index:11; pointer-events:none;
        }

        .bh-disc-ring::before {
            content:'';
            position:absolute;
            top:0; left:0; right:0;
            height:100%;
            border-radius:50%;
            border:3px solid transparent;
            border-top:3px solid rgba(180,100,255,0.0);
            background:
                radial-gradient(ellipse 100% 38% at 50% 0%,
                    rgba(255,255,255,0.28)   0%,
                    rgba(210,140,255,0.55)    5%,
                    rgba(168,85,247,0.45)    15%,
                    rgba(130,50,240,0.20)    28%,
                    transparent              48%);
            filter:blur(5px);
            opacity:0.85;
            animation:accPulse 5s ease-in-out infinite;
        }

        .bh-disc-ring::after {
            content:'';
            position:absolute;
            bottom:-18%; left:-4%; right:-4%;
            height:68%;
            border-radius:50%;
            background:
                radial-gradient(ellipse 60% 45% at 50% 14%,
                    rgba(255,255,255,1.00)   0%,
                    rgba(255,255,255,0.97)   2%,
                    rgba(255,248,255,0.88)   5%,
                    rgba(240,200,255,0.72)   11%,
                    rgba(210,130,255,0.52)   20%,
                    rgba(168,85,247,0.32)    31%,
                    rgba(120,40,240,0.15)    44%,
                    rgba(80,15,200,0.05)     58%,
                    transparent              72%),
                linear-gradient(90deg,
                    transparent              0%,
                    rgba(147,51,234,0.12)   12%,
                    transparent             25%,
                    transparent             75%,
                    rgba(147,51,234,0.12)   88%,
                    transparent            100%);
            filter:blur(3.5px);
            animation:accPulse 5s ease-in-out infinite 0.4s;
        }

        .bh-enter-btn {
            position:absolute; top:50%; left:50%;
            transform:translate(-50%, -50%);
            z-index:50;
            font-family:'JetBrains Mono',monospace;
            font-size:10px; letter-spacing:6px; text-transform:uppercase;
            color:rgba(220,200,255,0.75);
            background:rgba(0,0,0,0.55); cursor:pointer;
            transition:all 0.5s ease; padding:7px 18px;
            border-radius:40px;
            border:1px solid rgba(180,100,255,0.32);
            backdrop-filter:blur(4px);
        }
        .bh-enter-btn:hover {
            color:rgba(255,240,255,1.0);
            border-color:rgba(210,110,255,0.90);
            letter-spacing:9px;
            text-shadow:0 0 22px rgba(225,100,255,1.0), 0 0 44px rgba(185,80,255,0.80);
            box-shadow:0 0 30px rgba(205,80,255,0.45);
        }

        .orbit-arc {
            position:absolute; border-radius:50%;
            border:1.5px solid transparent; pointer-events:none;
        }
        .orbit-arc.a1 {
            inset:-65px;
            border-top-color:rgba(178,98,255,0.55);
            border-right-color:rgba(6,215,255,0.38);
            animation:arcSpin 11s linear infinite;
            filter:drop-shadow(0 0 8px rgba(178,98,255,0.45)); z-index:1;
        }
        .orbit-arc.a2 {
            inset:-100px;
            border-bottom-color:rgba(6,215,255,0.48);
            border-left-color:rgba(178,98,255,0.30);
            animation:arcSpin 17s linear infinite reverse;
            filter:drop-shadow(0 0 6px rgba(6,215,255,0.32)); z-index:1;
        }

        .bh-particle {
            position:absolute; border-radius:50%;
            background:white; z-index:3; pointer-events:none;
        }
        .bh-particle.p1 { width:3px;height:3px; box-shadow:0 0 10px 2px rgba(255,255,255,0.90); animation:orbPart 7s linear infinite; }
        .bh-particle.p2 { width:2px;height:2px; background:#e040fb; box-shadow:0 0 10px 2px #e040fb; animation:orbPart 9.5s linear infinite -3s; }
        .bh-particle.p3 { width:2px;height:2px; background:#00e5ff; box-shadow:0 0 10px 2px #00e5ff; animation:orbPart 12s linear infinite -6s; }
        .bh-particle.p4 { width:3px;height:3px; background:#ce93d8; box-shadow:0 0 12px 3px #ce93d8; animation:orbPart 8s linear infinite -1.5s; }

        @keyframes arcSpin    { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes accPulse   { 0%,100%{opacity:0.80} 50%{opacity:1.0} }
        @keyframes halouPulse { 0%,100%{opacity:0.60} 50%{opacity:1.0} }
        @keyframes photonPulse {
            0%,100% {
                opacity:0.60;
                box-shadow:
                    0 0  8px  3px rgba(255,245,255,0.65),
                    0 0 22px  8px rgba(220,140,255,0.45),
                    0 0 55px 22px rgba(180,70,255,0.22),
                    0 0 110px 55px rgba(130,30,240,0.10),
                    0 -12px 60px 30px rgba(200,100,255,0.14),
                    inset 0 0 30px 10px rgba(220,150,255,0.12);
            }
            50% {
                opacity:1.0;
                box-shadow:
                    0 0 12px  5px rgba(255,255,255,0.95),
                    0 0 30px 12px rgba(240,190,255,0.75),
                    0 0 75px 30px rgba(200,90,255,0.48),
                    0 0 150px 75px rgba(160,50,255,0.22),
                    0 -18px 80px 40px rgba(210,110,255,0.28),
                    inset 0 0 40px 14px rgba(230,170,255,0.28);
            }
        }
        @keyframes coronaPulse { 0%,100%{opacity:0.50} 50%{opacity:0.90} }
        @keyframes orbPart {
            from{transform:rotate(0deg) translateX(calc(50% + 60px)) rotate(0deg)}
            to{transform:rotate(360deg) translateX(calc(50% + 60px)) rotate(-360deg)}
        }

        .hero-preview {
            position:relative; z-index:4;
            width:100%; display:flex; justify-content:center;
            margin-top:-clamp(30px,5vh,60px);
            padding-bottom:0;
            pointer-events:auto;
        }

        .preview-panel {
            background:rgba(8,5,28,0.82);
            backdrop-filter:blur(24px);
            border:1px solid rgba(139,92,246,0.22);
            border-bottom:none;
            border-radius:20px 20px 0 0;
            padding:22px 28px 28px;
            width:clamp(300px,50vw,560px);
            box-shadow:0 -20px 60px rgba(139,92,246,0.12), 0 0 0 1px rgba(139,92,246,0.08);
        }

        .preview-panel-header {
            display:flex; justify-content:space-between; align-items:center;
            margin-bottom:16px; padding-bottom:14px;
            border-bottom:1px solid rgba(139,92,246,0.12);
        }

        .preview-date {
            font-family:'JetBrains Mono',monospace;
            font-size:12px; letter-spacing:1px;
            color:rgba(180,150,255,0.9);
            border-left:2px solid var(--violet);
            padding-left:10px;
        }

        .preview-live {
            display:flex; align-items:center; gap:7px;
            font-family:'JetBrains Mono',monospace;
            font-size:10px; letter-spacing:2px; color:#10b981;
        }
        .preview-live-dot {
            width:6px;height:6px;border-radius:50%;background:#10b981;
            box-shadow:0 0 8px #10b981; animation:liveDot 1.5s ease-in-out infinite;
        }
        @keyframes liveDot{0%,100%{opacity:1}50%{opacity:0.3}}

        .mini-cal { display:flex; gap:20px; align-items:flex-start; }

        .mini-cal-section { flex:1; }

        .mini-cal-title {
            font-family:'JetBrains Mono',monospace;
            font-size:11px; letter-spacing:3px; color:rgba(139,92,246,0.8);
            text-transform:uppercase; margin-bottom:12px;
        }

        .mini-cal-grid {
            display:grid; grid-template-columns:repeat(7,1fr);
            gap:3px; text-align:center;
        }

        .mc-dname {
            font-family:'JetBrains Mono',monospace;
            font-size:8px; color:rgba(139,92,246,0.55);
            letter-spacing:0.5px; padding-bottom:5px;
        }

        .mc-day {
            font-size:10px; color:var(--text-dim);
            padding:4px 2px; border-radius:5px;
        }
        .mc-day.today {
            background:rgba(139,92,246,0.9); color:#fff;
            font-weight:700; border-radius:7px;
            box-shadow:0 0 10px rgba(139,92,246,0.6);
        }
        .mc-day.dim { opacity:0.2; }

        .sensor-preview { flex:0 0 auto; min-width:160px; }
        .sp-row {
            display:flex; justify-content:space-between; align-items:center;
            padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.07);
            font-size:11px;
        }
        .sp-label { color:var(--text-dim); font-family:'JetBrains Mono',monospace; letter-spacing:0.5px; }
        .sp-val { font-family:'JetBrains Mono',monospace; font-weight:700; font-size:12px; }

        .top-nav {
            position:fixed; top:0;left:0;right:0; height:68px;
            display:flex; align-items:center; justify-content:space-between;
            padding:0 40px;
            background:rgba(4,2,14,0.85); backdrop-filter:blur(24px);
            border-bottom:1px solid var(--border); z-index:100;
            opacity:0; transform:translateY(-20px); transition:all 0.6s ease 0.3s;
        }
        .top-nav.visible{opacity:1;transform:translateY(0)}
        .nav-logo{font-family:'JetBrains Mono',monospace;font-size:14px;letter-spacing:4px;color:var(--text-dim);display:flex;align-items:center;gap:12px}
        .nav-logo-dot{width:8px;height:8px;border-radius:50%;background:var(--violet);box-shadow:0 0 10px var(--violet);animation:dotPulse 2s ease-in-out infinite}
        @keyframes dotPulse{0%,100%{box-shadow:0 0 6px var(--violet)}50%{box-shadow:0 0 16px var(--violet),0 0 30px rgba(139,92,246,0.4)}}
        .nav-pills{display:flex;gap:6px}
        .nav-pill{font-family:'Syne',sans-serif;font-size:12px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-dim);background:transparent;border:none;padding:9px 18px;border-radius:20px;cursor:pointer;transition:all 0.3s ease;position:relative}
        .nav-pill:hover{color:var(--text);background:rgba(139,92,246,0.08)}
        .nav-pill.active{color:var(--text);background:rgba(139,92,246,0.12)}
        .nav-pill.active::after{content:'';position:absolute;bottom:5px;left:20%;right:20%;height:2px;border-radius:1px;background:var(--violet);box-shadow:0 0 8px var(--violet)}

        #dashboard {
            min-height:100vh; padding-top:90px;
            display:flex; flex-direction:column; align-items:center;
            opacity:0; transition:opacity 0.7s ease;
            background:radial-gradient(ellipse 80% 50% at 10% 10%,rgba(80,20,160,0.12) 0%,transparent 55%),radial-gradient(ellipse 60% 60% at 90% 30%,rgba(50,10,130,0.1) 0%,transparent 55%),radial-gradient(ellipse 100% 40% at 50% 90%,rgba(90,20,180,0.08) 0%,transparent 50%),var(--bg-mid);
        }
        #dashboard.visible{opacity:1}

        .dashboard-header{text-align:center;padding:48px 20px 20px}
        .section-title-sm{font-size:11px;letter-spacing:6px;text-transform:uppercase;color:rgba(139,92,246,0.6);font-family:'JetBrains Mono',monospace;margin-bottom:10px}
        .dashboard-title{font-size:clamp(1.4rem,3vw,2.2rem);font-weight:700;letter-spacing:4px;text-transform:uppercase;background:linear-gradient(90deg,#d4c5ff,#8b5cf6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
        .dashboard-sub{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-dim);letter-spacing:3px;margin-top:8px}
        .live-indicator{display:inline-flex;align-items:center;gap:8px;margin-top:14px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.25);padding:6px 18px;border-radius:20px}
        .live-dot{width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;animation:liveDot 1.5s ease-in-out infinite}
        .live-text{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:3px;color:#10b981}

        .gauges-container{display:flex;flex-wrap:wrap;justify-content:center;gap:50px;max-width:1200px;padding:48px 40px 60px}
        .gauge-item{display:flex;flex-direction:column;align-items:center;cursor:pointer;transition:transform 0.4s cubic-bezier(0.16,1,0.3,1);position:relative}
        .gauge-item:hover{transform:translateY(-10px)}
        .gauge-ring-wrapper{position:relative;width:185px;height:185px}
        .gauge-svg{width:100%;height:100%;transform:rotate(-90deg)}
        .gauge-track{fill:none;stroke:rgba(139,92,246,0.08);stroke-width:3}
        .gauge-fill{fill:none;stroke-width:3;stroke-linecap:round;stroke-dasharray:502;stroke-dashoffset:502;transition:stroke-dashoffset 1.5s cubic-bezier(0.16,1,0.3,1)}
        .gauge-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
        .gauge-value{font-family:'JetBrains Mono',monospace;font-size:34px;font-weight:300;color:var(--text);line-height:1}
        .gauge-unit{font-size:13px;color:var(--text-dim);margin-top:4px}
        .gauge-label{margin-top:18px;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--text-dim);font-weight:600;transition:color 0.3s}
        .gauge-item:hover .gauge-label{color:var(--violet)}
        .gauge-glow{position:absolute;inset:-12px;border-radius:50%;opacity:0;transition:opacity 0.4s;pointer-events:none;filter:blur(20px)}
        .gauge-item:hover .gauge-glow{opacity:0.2}

        #preview-modal{position:fixed;inset:0;background:rgba(2,0,15,0.75);backdrop-filter:blur(16px);z-index:500;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity 0.3s ease}
        #preview-modal.active{opacity:1;pointer-events:auto}
        .modal-card{background:rgba(8,4,28,0.9);backdrop-filter:blur(30px);border:1px solid var(--border-bright);border-radius:28px;padding:44px;width:90%;max-width:720px;display:grid;grid-template-columns:1fr 1fr;gap:44px;transform:scale(0.88) translateY(10px);transition:transform 0.35s cubic-bezier(0.16,1,0.3,1);position:relative;box-shadow:0 0 60px rgba(139,92,246,0.15),0 40px 80px rgba(0,0,0,0.5)}
        .modal-card::before{content:'';position:absolute;top:0;left:40px;right:40px;height:1px;background:linear-gradient(90deg,transparent,rgba(139,92,246,0.6),transparent)}
        #preview-modal.active .modal-card{transform:scale(1) translateY(0)}
        .modal-left{display:flex;flex-direction:column;align-items:center;justify-content:center}
        .modal-big-ring{width:220px;height:220px;position:relative}
        .modal-big-ring .gauge-value{font-size:52px}
        .modal-status{font-size:18px;font-weight:700;margin-top:18px;text-align:center;letter-spacing:1px}
        .modal-right{display:flex;flex-direction:column;justify-content:center}
        .modal-section-title{font-size:10px;letter-spacing:4px;text-transform:uppercase;color:rgba(139,92,246,0.7);margin-bottom:14px;font-family:'JetBrains Mono',monospace}
        .recs-list{list-style:none;margin-bottom:28px}
        .recs-list li{font-size:13px;color:var(--text-dim);margin-bottom:9px;display:flex;align-items:center;gap:10px}
        .recs-list li::before{content:'›';font-family:'JetBrains Mono',monospace;color:var(--violet);font-size:18px}
        .sparkline-box{width:100%;height:80px;background:rgba(139,92,246,0.04);border-radius:12px;padding:8px}
        .modal-close{position:absolute;top:18px;right:22px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.2);color:var(--text-dim);font-size:18px;cursor:pointer;transition:all 0.3s;width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:50%}
        .modal-close:hover{color:var(--text);background:rgba(139,92,246,0.2);border-color:var(--violet)}

        #analytics-page{position:fixed;inset:0;background:radial-gradient(ellipse 80% 50% at 10% 10%,rgba(80,20,160,0.15) 0%,transparent 55%),radial-gradient(ellipse 60% 60% at 90% 30%,rgba(50,10,130,0.12) 0%,transparent 55%),var(--bg-mid);z-index:200;overflow-y:auto;opacity:0;pointer-events:none;transition:opacity 0.4s ease}
        #analytics-page.active{opacity:1;pointer-events:auto}
        .analytics-container{max-width:1100px;margin:0 auto;padding:100px 30px 40px}
        .analytics-header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:30px}
        .back-link{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-dim);background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.2);cursor:pointer;display:flex;align-items:center;gap:8px;transition:all 0.3s;margin-bottom:12px;padding:8px 18px;border-radius:12px;letter-spacing:1px}
        .back-link:hover{color:var(--text);border-color:var(--violet);background:rgba(139,92,246,0.15)}
        .analytics-title{font-size:30px;font-weight:700;letter-spacing:5px;text-transform:uppercase}
        .analytics-current{font-family:'JetBrains Mono',monospace;font-size:46px;font-weight:300}
        .analytics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
        .analytics-main-chart{grid-column:span 3;height:320px;background:rgba(139,92,246,0.04);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:20px;padding:20px}
        .analytics-card{background:rgba(139,92,246,0.04);backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:20px;padding:24px;min-height:140px;max-height:185px;display:flex;flex-direction:column}
        .card-label{font-size:10px;letter-spacing:3px;text-transform:uppercase;color:rgba(139,92,246,0.7);margin-bottom:12px;font-family:'JetBrains Mono',monospace}
        .card-value{font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:400;color:var(--text)}
        .card-sub{font-size:12px;color:var(--text-dim);margin-top:8px}
        .prediction-bar{width:100%;height:5px;background:rgba(139,92,246,0.12);border-radius:3px;margin-top:12px;overflow:hidden}
        .prediction-fill{height:100%;border-radius:3px;transition:width 0.6s ease}

        #info-section{width:100%;padding:80px 0 0;background:radial-gradient(ellipse 100% 60% at 50% 0%,rgba(90,20,180,0.12) 0%,transparent 55%),linear-gradient(180deg,var(--bg-mid) 0%,#030112 100%);border-top:1px solid var(--border);opacity:0;transition:opacity 0.7s ease}
        #info-section.visible{opacity:1}
        .info-container{max-width:1100px;margin:0 auto;padding:0 40px 80px}
        .section-title{font-size:11px;letter-spacing:6px;text-transform:uppercase;color:rgba(139,92,246,0.6);font-family:'JetBrains Mono',monospace;margin-bottom:10px}
        .section-heading{font-size:clamp(1.5rem,3vw,2.2rem);font-weight:700;background:linear-gradient(90deg,#e0d8ff,#8b5cf6 60%,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:28px}
        .about-card{background:rgba(139,92,246,0.05);border:1px solid var(--border);border-radius:24px;padding:40px;margin-bottom:48px;position:relative;overflow:hidden}
        .about-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,rgba(139,92,246,0.7),rgba(6,182,212,0.5),transparent)}
        .about-icon{font-size:2.5rem;margin-bottom:16px}
        .about-text{font-size:1rem;color:var(--text-dim);line-height:1.85;max-width:800px}
        .about-text strong{color:var(--text);font-weight:600}
        .sensors-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;margin-bottom:56px}
        .sensor-card{background:rgba(139,92,246,0.05);border:1px solid var(--border);border-radius:20px;padding:28px 24px;transition:all 0.3s ease;position:relative;overflow:hidden}
        .sensor-card::after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(139,92,246,0.05),transparent);opacity:0;transition:opacity 0.3s}
        .sensor-card:hover{border-color:var(--border-bright);transform:translateY(-4px);box-shadow:0 10px 40px rgba(139,92,246,0.12)}
        .sensor-card:hover::after{opacity:1}
        .sensor-icon{font-size:2rem;margin-bottom:12px}
        .sensor-name{font-size:14px;font-weight:700;color:var(--text);margin-bottom:4px;letter-spacing:1px}
        .sensor-model{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--violet);margin-bottom:10px;letter-spacing:1px}
        .sensor-desc{font-size:12px;color:var(--text-dim);line-height:1.6;margin-bottom:14px}
        .sensor-price{display:inline-block;background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.25);color:var(--violet);font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;padding:5px 14px;border-radius:10px}
        .divider{height:1px;background:linear-gradient(90deg,transparent,rgba(139,92,246,0.3),transparent);margin:48px 0}
        .team-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:48px}
        .team-card{background:rgba(139,92,246,0.04);border:1px solid var(--border);border-radius:18px;padding:22px 20px;text-align:center;transition:all 0.3s ease}
        .team-card:hover{border-color:var(--border-bright);background:rgba(139,92,246,0.08)}
        .team-avatar{width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,rgba(139,92,246,0.4),rgba(6,182,212,0.3));border:2px solid rgba(139,92,246,0.3);margin:0 auto 14px;display:flex;align-items:center;justify-content:center;font-size:20px}
        .team-name{font-size:13px;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1.4}
        .team-role{font-family:'JetBrains Mono',monospace;font-size:10px;color:rgba(139,92,246,0.7);letter-spacing:1px}
        .institute-card{background:rgba(139,92,246,0.05);border:1px solid var(--border);border-radius:24px;padding:36px 40px;display:flex;gap:40px;flex-wrap:wrap;align-items:center}
        .institute-info-block{flex:1;min-width:200px}
        .info-label{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:3px;color:rgba(139,92,246,0.6);text-transform:uppercase;margin-bottom:6px}
        .info-value{font-size:15px;font-weight:600;color:var(--text);line-height:1.4}
        .footer{background:rgba(4,2,14,0.95);border-top:1px solid var(--border);padding:28px 40px;text-align:center}
        .footer-text{font-family:'JetBrains Mono',monospace;font-size:11px;color:rgba(139,92,246,0.4);letter-spacing:2px}

        @media(max-width:768px){
            .bh-container{width:320px;height:320px}
            .hero-preview{margin-top:-40px}
            .preview-panel{width:95vw}
            .mini-cal{flex-direction:column;gap:14px}
            .gauges-container{gap:30px;padding:32px 20px}
            .gauge-ring-wrapper{width:145px;height:145px}
            .gauge-value{font-size:26px}
            .nav-pills{display:none}
            .modal-card{grid-template-columns:1fr}
            .analytics-grid{grid-template-columns:1fr}
            .analytics-main-chart{grid-column:span 1;height:250px}
            .analytics-header{flex-direction:column;align-items:flex-start;gap:12px}
            .institute-card{flex-direction:column;gap:20px}
            .top-nav{padding:0 20px}
            .info-container{padding:0 20px 60px}
        }
    </style>
</head>
<body>

<div id="portal-screen">
    <div class="portal-bg"></div>
    <canvas id="starCanvas"></canvas>

    <div class="hero-text-block">
        <div class="hero-badge">&#9889; Monitoreo en Tiempo Real</div>
        <h1 class="hero-title">Estaci&#243;n Meteorol&#243;gica<br>MTR-01</h1>
        <p class="hero-subtitle">I.E.S.T.P. Honorio Delgado Espinoza &middot; Arequipa, Per&#250;</p>
    </div>

    <div class="bh-wrapper">
        <div class="bh-container">
            <div class="bh-bottom-glow"></div>
            <div class="bh-outer-nebula"></div>
            <div class="bh-corona-top"></div>

            <div class="orbit-arc a1"></div>
            <div class="orbit-arc a2"></div>

            <div class="bh-photon-ring"></div>

            <div class="bh-disc"></div>

            <div class="bh-disc-ring"></div>

            <button class="bh-enter-btn" onclick="enterDashboard()">ENTRAR</button>

            <div class="bh-particle p1"></div>
            <div class="bh-particle p2"></div>
            <div class="bh-particle p3"></div>
            <div class="bh-particle p4"></div>
        </div>
    </div>

    <div class="hero-preview" style="margin-top:clamp(-50px,-6vh,-20px);">
        <div class="preview-panel">
            <div class="preview-panel-header">
                <div class="preview-date" id="previewDateStr">Cargando...</div>
                <div class="preview-live"><div class="preview-live-dot"></div>EN VIVO</div>
            </div>
            <div class="mini-cal">
                <div class="mini-cal-section">
                    <div class="mini-cal-title" id="previewMonthName">---</div>
                    <div class="mini-cal-grid" id="miniCalGrid"></div>
                </div>
                <div class="sensor-preview">
                    <div class="mini-cal-title">Sensores</div>
                    <div class="sp-row"><span class="sp-label">TEMP</span><span class="sp-val" style="color:#ef4444">18.4&#176;C</span></div>
                    <div class="sp-row"><span class="sp-label">HUM</span><span class="sp-val" style="color:#06b6d4">62.0%</span></div>
                    <div class="sp-row"><span class="sp-label">PRES</span><span class="sp-val" style="color:#10b981">1013hPa</span></div>
                    <div class="sp-row"><span class="sp-label">UV</span><span class="sp-val" style="color:#f59e0b">5.2</span></div>
                    <div class="sp-row"><span class="sp-label">LLUVIA</span><span class="sp-val" style="color:#a855f7">0.0%</span></div>
                    <div class="sp-row" style="border:none"><span class="sp-label">VIENTO</span><span class="sp-val" style="color:#3b82f6">15.0km/h</span></div>
                </div>
            </div>
        </div>
    </div>
</div>

<nav class="top-nav" id="topNav">
    <div class="nav-logo"><div class="nav-logo-dot"></div>MTR-01</div>
    <div class="nav-pills">
        <button class="nav-pill" data-metric="temperatura" onclick="navToAnalytics('temperatura')">Temperatura</button>
        <button class="nav-pill" data-metric="humedad" onclick="navToAnalytics('humedad')">Humedad</button>
        <button class="nav-pill" data-metric="presion" onclick="navToAnalytics('presion')">Presi&#243;n</button>
        <button class="nav-pill" data-metric="uv" onclick="navToAnalytics('uv')">Rayos UV</button>
        <button class="nav-pill" data-metric="lluvia" onclick="navToAnalytics('lluvia')">Lluvia</button>
        <button class="nav-pill" data-metric="viento" onclick="navToAnalytics('viento')">Viento</button>
    </div>
</nav>

<div id="dashboard">
    <div class="dashboard-header">
        <div class="section-title-sm">Panel de Control</div>
        <div class="dashboard-title">Mediciones en Vivo</div>
        <div class="dashboard-sub">Actualizaci&#243;n cada 0.5 segundos</div>
        <div class="live-indicator"><div class="live-dot"></div><span class="live-text">EN VIVO</span></div>
    </div>
    <div class="gauges-container" id="gaugesContainer"></div>

    <div id="info-section">
        <div class="info-container">
            <div style="margin-bottom:60px">
                <div class="section-title">Sobre el Proyecto</div>
                <div class="section-heading">&#191;Qu&#233; es la Estaci&#243;n Meteorol&#243;gica MTR-01?</div>
                <div class="about-card">
                    <div class="about-icon">&#127750;&#65039;</div>
                    <p class="about-text">La <strong>Estaci&#243;n Meteorol&#243;gica MTR-01</strong> es un sistema de adquisici&#243;n y monitoreo de datos ambientales desarrollado como proyecto acad&#233;mico para el curso de <strong>Adquisici&#243;n de Datos</strong> de la carrera de <strong>Electr&#243;nica Industrial</strong>. Este sistema integra m&#250;ltiples sensores electr&#243;nicos para medir en tiempo real variables clim&#225;ticas como temperatura, humedad relativa, presi&#243;n atmosf&#233;rica, &#237;ndice de radiaci&#243;n ultravioleta y precipitaciones pluviales.</p>
                    <p class="about-text" style="margin-top:16px">Los datos recolectados se procesan mediante un microcontrolador y se transmiten a un servidor web local desarrollado en <strong>Python (Flask)</strong>, donde se visualizan en un dashboard interactivo con gr&#225;ficas, historial de tendencias y recomendaciones basadas en los valores actuales. El sistema permite la supervisi&#243;n remota de las condiciones clim&#225;ticas en el entorno del instituto, siendo &#250;til para proyectos de investigaci&#243;n, monitoreo ambiental y toma de decisiones en tiempo real.</p>
                </div>
            </div>
            <div style="margin-bottom:60px">
                <div class="section-title">Hardware Utilizado</div>
                <div class="section-heading">Sensores de la Estaci&#243;n</div>
                <div class="sensors-grid">
                    <div class="sensor-card"><div class="sensor-icon">&#127777;&#65039;</div><div class="sensor-name">Temperatura &amp; Humedad</div><div class="sensor-model">DHT22 / AM2302</div><div class="sensor-desc">Sensor digital de alta precisi&#243;n para temperatura (&#8722;40&#176;C a 80&#176;C) y humedad relativa (0&#8211;100% RH). Salida de se&#241;al calibrada de un solo hilo.</div><div class="sensor-price">~ S/. 15 &#8211; S/. 45</div></div>
                    <div class="sensor-card"><div class="sensor-icon">&#128309;</div><div class="sensor-name">Presi&#243;n Atmosf&#233;rica</div><div class="sensor-model">BMP280</div><div class="sensor-desc">Sensor barom&#233;trico de alta precisi&#243;n con resoluci&#243;n de 0.01 hPa. Comunicaci&#243;n I&#178;C/SPI. Rango: 300&#8211;1100 hPa. Ideal para altimetr&#237;a y meteorolog&#237;a.</div><div class="sensor-price">~ S/. 8 &#8211; S/. 25</div></div>
                    <div class="sensor-card"><div class="sensor-icon">&#9728;&#65039;</div><div class="sensor-name">&#205;ndice de Radiaci&#243;n UV</div><div class="sensor-model">GUVA-S12SD / ML8511</div><div class="sensor-desc">Fotodiodo ultravioleta con salida anal&#243;gica proporcional a la intensidad UV. Detecta longitudes de onda entre 280&#8211;390 nm para &#237;ndice UV 0&#8211;15.</div><div class="sensor-price">~ S/. 10 &#8211; S/. 30</div></div>
                    <div class="sensor-card"><div class="sensor-icon">&#127783;&#65039;</div><div class="sensor-name">Precipitaci&#243;n / Lluvia</div><div class="sensor-model">FC-37 Rain Sensor</div><div class="sensor-desc">M&#243;dulo detector de lluvia con placa sensora resistiva y comparador LM393. Salida anal&#243;gica y digital. Detecta presencia e intensidad de lluvia.</div><div class="sensor-price">~ S/. 5 &#8211; S/. 18</div></div>
                    <div class="sensor-card"><div class="sensor-icon">&#127788;&#65039;</div><div class="sensor-name">Velocidad del Viento</div><div class="sensor-model">Anemómetro YL-83 / Pulsos</div><div class="sensor-desc">Sensor anemométrico con salida de pulsos por revolución. Cada pulso representa una velocidad de viento calibrada. Rango típico: 0&#8211;70 km/h. Compatible con interrupciones del ESP32 para conteo preciso.</div><div class="sensor-price">~ S/. 25 &#8211; S/. 60</div></div>
                    <div class="sensor-card"><div class="sensor-icon">&#128187;</div><div class="sensor-name">Microcontrolador</div><div class="sensor-model">ESP32 / Arduino Uno</div><div class="sensor-desc">Unidad de procesamiento central que lee los sensores, procesa los datos y los transmite via serial o WiFi al servidor Flask en Python.</div><div class="sensor-price">~ S/. 20 &#8211; S/. 60</div></div>
                </div>
            </div>
            <div class="divider"></div>
            <div style="margin-bottom:48px">
                <div class="section-title">Grupo de Desarrollo Web</div>
                <div class="section-heading">Integrantes del Equipo</div>
                <div class="team-grid">
                    <div class="team-card"><div class="team-avatar">&#128104;&#8205;&#128187;</div><div class="team-name">Vera Lima<br>Juan Junior</div><div class="team-role">Desarrollador Web</div></div>
                    <div class="team-card"><div class="team-avatar">&#128104;&#8205;&#128187;</div><div class="team-name">Mamani Ccapa<br>Abel Olger</div><div class="team-role">Desarrollador Web</div></div>
                    <div class="team-card"><div class="team-avatar">&#128105;&#8205;&#128187;</div><div class="team-name">Jara Lipa<br>Melany Traisy</div><div class="team-role">Desarrolladora Web</div></div>
                    <div class="team-card"><div class="team-avatar">&#128104;&#8205;&#128187;</div><div class="team-name">Barriga Huaman<br>Moises Anthony</div><div class="team-role">Desarrollador Web</div></div>
                </div>
            </div>
            <div class="institute-card">
                <div class="institute-info-block"><div class="info-label">Instituto</div><div class="info-value">I.E.S.T.P. Honorio Delgado Espinoza</div></div>
                <div class="institute-info-block"><div class="info-label">Carrera</div><div class="info-value">Electr&#243;nica Industrial</div></div>
                <div class="institute-info-block"><div class="info-label">Curso</div><div class="info-value">Adquisici&#243;n de Datos</div></div>
                <div class="institute-info-block"><div class="info-label">Docente</div><div class="info-value">Ing. Mario A. Cusi Huarancca</div></div>
            </div>
        </div>
        <div class="footer"><div class="footer-text">MTR-01 &middot; ESTACI&#211;N METEOROL&#211;GICA &middot; I.E.S.T.P. HONORIO DELGADO ESPINOZA &middot; AREQUIPA, PER&#218;</div></div>
    </div>
</div>

<div id="preview-modal" onclick="closeModal(event)">
    <div class="modal-card" onclick="event.stopPropagation()">
        <button class="modal-close" onclick="closeModal()">&#10005;</button>
        <div class="modal-left">
            <div class="modal-big-ring" id="modalRing"></div>
            <div class="modal-status" id="modalStatus">--</div>
        </div>
        <div class="modal-right">
            <div class="modal-section-title">Recomendaciones</div>
            <ul class="recs-list" id="modalRecs"></ul>
            <div class="modal-section-title">Tendencia Reciente</div>
            <div class="sparkline-box"><canvas id="sparklineChart"></canvas></div>
        </div>
    </div>
</div>

<div id="analytics-page">
    <div class="analytics-container">
        <button class="back-link" onclick="closeAnalytics()"><span>&#8592;</span> VOLVER AL INICIO</button>
        <div class="analytics-header">
            <div><div class="analytics-title" id="anTitle">TEMPERATURA</div></div>
            <div class="analytics-current" id="anCurrent">0.00</div>
        </div>
        <div class="analytics-grid">
            <div class="analytics-main-chart"><canvas id="mainChart"></canvas></div>
            <div class="analytics-card"><div class="card-label">Promedio Semanal</div><div class="card-value" id="anAvg">--</div><div class="card-sub" id="anAvgTrend">--</div></div>
            <div class="analytics-card"><div class="card-label">Predicci&#243;n Ma&#241;ana</div><div class="card-value" id="anPred">--</div><div class="prediction-bar"><div class="prediction-fill" id="anPredBar" style="width:0%"></div></div><div class="card-sub" id="anPredConf">Confianza: --%</div></div>
            <div class="analytics-card"><div class="card-label">R&#233;cords</div><div style="margin-top:8px"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="color:var(--text-dim);font-size:13px">M&#225;x</span><span style="font-family:'JetBrains Mono';font-size:14px" id="anMax">--</span></div><div style="display:flex;justify-content:space-between"><span style="color:var(--text-dim);font-size:13px">M&#237;n</span><span style="font-family:'JetBrains Mono';font-size:14px" id="anMin">--</span></div></div></div>
        </div>
    </div>
</div>

<script>
    (function(){
        const c = document.getElementById('starCanvas');
        const ctx = c.getContext('2d');
        function resize(){ c.width=window.innerWidth; c.height=window.innerHeight; }
        resize(); window.addEventListener('resize',resize);
        const stars = Array.from({length:180},()=>({
            x:Math.random()*window.innerWidth, y:Math.random()*window.innerHeight*0.7,
            r:Math.random()*1.2+0.2, a:Math.random(),
            speed:Math.random()*0.008+0.003
        }));
        function drawStars(){
            c.width=c.width;
            stars.forEach(s=>{
                s.a += s.speed; if(s.a>1) s.a=0;
                const alpha = Math.sin(s.a*Math.PI);
                ctx.beginPath();
                ctx.arc(s.x,s.y,s.r,0,Math.PI*2);
                ctx.fillStyle=`rgba(200,190,255,${alpha*0.85})`;
                ctx.fill();
            });
            requestAnimationFrame(drawStars);
        }
        drawStars();
    })();

    (function buildCal(){
        const now = new Date();
        const year=now.getFullYear(), month=now.getMonth(), today=now.getDate();
        const monthNames=['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE'];
        const dayAbbr=['Lu','Ma','Mi','Ju','Vi','Sa','Do'];
        const longDay=['Lunes','Martes','Mi\xe9rcoles','Jueves','Viernes','S\xe1bado','Domingo'];
        const dow = now.getDay(); const dayName = longDay[dow===0?6:dow-1];

        document.getElementById('previewMonthName').textContent = monthNames[month];
        document.getElementById('previewDateStr').textContent = dayName+', '+today+' de '+monthNames[month]+' '+year;

        const grid = document.getElementById('miniCalGrid');
        dayAbbr.forEach(d=>{ const el=document.createElement('div'); el.className='mc-dname'; el.textContent=d; grid.appendChild(el); });

        const firstDay=new Date(year,month,1).getDay();
        const startOffset=(firstDay===0)?6:firstDay-1;
        const daysInMonth=new Date(year,month+1,0).getDate();
        const prevDays=new Date(year,month,0).getDate();

        for(let i=startOffset-1;i>=0;i--){ const el=document.createElement('div'); el.className='mc-day dim'; el.textContent=prevDays-i; grid.appendChild(el); }
        for(let d=1;d<=daysInMonth;d++){ const el=document.createElement('div'); el.className='mc-day'+(d===today?' today':''); el.textContent=d; grid.appendChild(el); }
    })();

    const metrics = {
        temperatura:{color:'var(--temp)',hex:'#ef4444',unit:'\u00b0C',label:'Temperatura',min:-10,max:50},
        humedad:{color:'var(--hum)',hex:'#06b6d4',unit:'%',label:'Humedad',min:0,max:100},
        presion:{color:'var(--pres)',hex:'#10b981',unit:'hPa',label:'Presi\u00f3n',min:980,max:1040},
        uv:{color:'var(--uv)',hex:'#f59e0b',unit:'',label:'\u00cdndice UV',min:0,max:15},
        lluvia:{color:'var(--lluvia)',hex:'#a855f7',unit:'%',label:'Precipitaci\u00f3n',min:0,max:100},
        viento:{color:'var(--viento)',hex:'#3b82f6',unit:'km/h',label:'Viento',min:0,max:100}
    };

    const getLogic=(key,v)=>{
        const maps={
            temperatura:[{t:35,s:'\ud83e\udd75 Calor Extremo',r:['Ropa muy ligera','Hidrataci\u00f3n constante','Evitar sol directo','Usar ventilador/AC','No ejercicio intenso']},{t:25,s:'\u2600\ufe0f C\u00e1lido',r:['Ropa ligera','Beber agua frecuente','Protector solar','Gafas de sol']},{t:15,s:'\ud83d\ude0a Agradable',r:['Condiciones ideales','Aprovechar exteriores','Ropa c\u00f3moda','D\u00eda perfecto para pasear']},{t:5,s:'\ud83e\udde5 Fresco',r:['Chaqueta ligera','Bebidas calientes','Cuidar garganta']},{t:-50,s:'\ud83e\udd76 Fr\u00edo Intenso',r:['Abrigarse en capas','Guantes y bufanda','Bebidas calientes','Evitar corrientes','Calefacci\u00f3n adecuada']}],
            humedad:[{t:70,s:'\ud83d\udca7 Muy H\u00famedo',r:['Usar deshumidificador','Ventilar hogar','Ropa transpirable','Cuidar moho','Aire acondicionado']},{t:40,s:'\u2705 Confortable',r:['Nivel \u00f3ptimo para salud','Sin acciones necesarias','Ideal para dormir']},{t:0,s:'\ud83c\udfdc\ufe0f Seco',r:['Usar humidificador','Hidrataci\u00f3n constante','Cremas hidratantes','Cuidar mucosas']}],
            presion:[{t:1020,s:'\ud83c\udf24\ufe0f Alta / Estable',r:['Buen clima','Ideal para deportes','Viajes seguros','Paseos al aire libre']},{t:1010,s:'\u26c5 Normal',r:['Condiciones estables','Sin preocupaciones']},{t:1000,s:'\ud83c\udf27\ufe0f Baja',r:['Posibilidad de lluvia','Asegurar ventanas','Paraguas preparado','Cerrar claraboyas']},{t:0,s:'\u26c8\ufe0f Muy Baja',r:['Tormenta probable','Evitar actividades al aire libre','Chequear drenajes','Preparar emergencia']}],
            uv:[{t:11,s:'\u2620\ufe0f Extremo',r:['EVITAR salir','FPS 50+ obligatorio','Ropa protectora total','Gafas UV400','Sombra absoluta']},{t:8,s:'\ud83d\udd34 Muy Alto',r:['Evitar exposici\u00f3n','FPS 30-50','Sombra 10am-4pm','Ropa manga larga']},{t:6,s:'\ud83d\udfe1 Alto',r:['FPS 15-30','Gafas de sol','Sombrero','Limitar exposici\u00f3n']},{t:3,s:'\ud83d\udfe2 Moderado',r:['FPS opcional','Gafas recomendadas','Sombra parcial']},{t:0,s:'\u2705 Bajo',r:['Exposici\u00f3n segura','Sin protecci\u00f3n necesaria']}],
            lluvia:[{t:80,s:'\ud83c\udf27\ufe0f Tormenta',r:['NO salir','Refugio seguro','Evitar zonas bajas','Paraguas reforzado','Chequear alertas']},{t:50,s:'\ud83c\udf27\ufe0f Lluvia Intensa',r:['Evitar salir','Paraguas obligatorio','Precauci\u00f3n al conducir','Calzado impermeable']},{t:20,s:'\ud83c\udf26\ufe0f Moderada',r:['Impermeable ligero','Paraguas recomendado','Cuidado en carretera']},{t:1,s:'\ud83d\udca7 Llovizna',r:['Paraguas opcional','Chaqueta cortaviento']},{t:0,s:'\u2600\ufe0f Despejado',r:['Sin precipitaciones','D\u00eda ideal','Aprovechar exteriores']}],
            viento:[{t:80,s:'\ud83c\udf2a\ufe0f Viento Extremo',r:['NO salir a exteriores','Asegurar objetos sueltos','Evitar zonas con \u00e1rboles','Cerrar ventanas','Prepararse para corte de energ\u00eda']},{t:50,s:'\ud83d\udca8 Viento Fuerte',r:['Cuidado al conducir','Sujetar sombreros/gafas','Evitar andar cerca de postes','Chaqueta cortaviento']},{t:30,s:'\ud83c\udf43 Viento Moderado',r:['Ropa ajustada recomendada','Cuidado con puertas','Apto para deportes con precauci\u00f3n']},{t:10,s:'\ud83c\udf3d\ufe0f Brisa',r:['Condiciones agradables','Ideal para exteriores','Aprovechar para actividades']},{t:0,s:'\u2705 Calma',r:['Viento nulo','D\u00eda perfecto','Sin precauciones necesarias']}]
        };
        const arr=maps[key]; for(let item of arr){if(v>=item.t)return{s:item.s,r:item.r};} return arr[arr.length-1];
    };

    let currentData={}, sparkData={temperatura:[],humedad:[],presion:[],uv:[],lluvia:[],viento:[]};
    let activeModalKey=null, sparkChartInst=null, mainChartInst=null, modalOpen=false;

    function enterDashboard(){
        document.getElementById('portal-screen').classList.add('hidden');
        document.getElementById('topNav').classList.add('visible');
        document.getElementById('dashboard').classList.add('visible');
        setTimeout(()=>{
            document.getElementById('portal-screen').style.display='none';
            document.getElementById('info-section').classList.add('visible');
            initGauges(); fetchData();
        },900);
    }

    function initGauges(){
        const container=document.getElementById('gaugesContainer'); container.innerHTML='';
        Object.keys(metrics).forEach(key=>{
            const m=metrics[key], circ=2*Math.PI*85;
            container.innerHTML+=`<div class="gauge-item" onclick="openModal('${key}')" id="gauge-${key}"><div class="gauge-ring-wrapper"><div class="gauge-glow" style="background:${m.hex}"></div><svg class="gauge-svg" viewBox="0 0 200 200"><circle class="gauge-track" cx="100" cy="100" r="85"></circle><circle class="gauge-fill" id="fill-${key}" cx="100" cy="100" r="85" stroke="${m.hex}" stroke-dasharray="${circ}" stroke-dashoffset="${circ}" style="filter:drop-shadow(0 0 8px ${m.hex})"></circle></svg><div class="gauge-center"><div class="gauge-value"><span id="val-${key}">0.0</span></div><div class="gauge-unit">${m.unit}</div></div></div><div class="gauge-label">${m.label}</div></div>`;
        });
    }

    async function fetchData(){
        try{
            const res=await fetch('/api/sensor-data'); const data=await res.json(); currentData=data;
            Object.keys(data).forEach(key=>{
                const val=data[key], m=metrics[key];
                sparkData[key].push(val); if(sparkData[key].length>20)sparkData[key].shift();
                const circ=2*Math.PI*85; let pct=Math.max(0,Math.min(1,(val-m.min)/(m.max-m.min)));
                const offset=circ-(pct*circ);
                const fill=document.getElementById(`fill-${key}`); const valEl=document.getElementById(`val-${key}`);
                if(fill)fill.style.strokeDashoffset=offset;
                if(valEl)animateNumber(valEl,parseFloat(valEl.innerText)||0,val,800,1);
            });
            if(activeModalKey){
                updateModal();
                if(sparkChartInst){
                    sparkChartInst.data.datasets[0].data = sparkData[activeModalKey];
                    sparkChartInst.data.labels = sparkData[activeModalKey].map((_,i)=>i);
                    sparkChartInst.update('none');
                }
            }
            if(document.getElementById('analytics-page').classList.contains('active'))updateAnalytics();
        }catch(e){console.error(e);}
    }

    function animateNumber(el,start,end,duration,decimals){
        const t0=performance.now();
        function step(now){
            const p=Math.min((now-t0)/duration,1); el.innerText=(start+(end-start)*p).toFixed(decimals);
            if(p<1)requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    function openModal(key){
        if(modalOpen)return; modalOpen=true; activeModalKey=key;
        const m=metrics[key], val=currentData[key]||0, circ=2*Math.PI*85;
        let pct=Math.max(0,Math.min(1,(val-m.min)/(m.max-m.min)));
        const offset=circ-(pct*circ);
        document.getElementById('modalRing').innerHTML=`<svg class="gauge-svg" viewBox="0 0 200 200" style="width:100%;height:100%;transform:rotate(-90deg)"><circle class="gauge-track" cx="100" cy="100" r="85"></circle><circle class="gauge-fill" id="modal-fill-circle" cx="100" cy="100" r="85" stroke="${m.hex}" stroke-dasharray="${circ}" stroke-dashoffset="${circ}" style="filter:drop-shadow(0 0 10px ${m.hex})"></circle></svg><div class="gauge-center"><div class="gauge-value" id="modal-gauge-value" style="font-size:52px">${val.toFixed(1)}</div><div class="gauge-unit">${m.unit}</div></div>`;
        requestAnimationFrame(()=>{
            requestAnimationFrame(()=>{
                const circle=document.getElementById('modal-fill-circle');
                if(circle) circle.style.strokeDashoffset=offset;
            });
        });
        updateModal(); drawSparkline(key); document.getElementById('preview-modal').classList.add('active');
    }

    function updateModal(){
        if(!activeModalKey)return;
        const key=activeModalKey, val=currentData[key], logic=getLogic(key,val), m=metrics[key];

        const valEl = document.getElementById('modal-gauge-value');
        if(valEl) animateNumber(valEl, parseFloat(valEl.innerText)||0, val, 800, 1);

        const circ=2*Math.PI*85;
        let pct=Math.max(0,Math.min(1,(val-m.min)/(m.max-m.min)));
        const offset=circ-(pct*circ);
        const circle=document.getElementById('modal-fill-circle');
        if(circle) circle.style.strokeDashoffset=offset;

        document.getElementById('modalStatus').innerText=logic.s;
        document.getElementById('modalStatus').style.color=m.hex;
        const ul=document.getElementById('modalRecs');
        ul.innerHTML='';
        logic.r.forEach(r=>{ul.innerHTML+=`<li>${r}</li>`;});
    }

    function closeModal(e){
        if(e&&e.target!==e.currentTarget&&!e.target.closest('.modal-close'))return;
        document.getElementById('preview-modal').classList.remove('active');
        activeModalKey=null; modalOpen=false;
        if(sparkChartInst){sparkChartInst.destroy();sparkChartInst=null;}
    }

    function drawSparkline(key){
        const ctx=document.getElementById('sparklineChart').getContext('2d');
        if(sparkChartInst)sparkChartInst.destroy();
        sparkChartInst=new Chart(ctx,{type:'line',data:{labels:sparkData[key].map((_,i)=>i),datasets:[{data:sparkData[key],borderColor:metrics[key].hex,borderWidth:2,tension:0.4,pointRadius:0,fill:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{enabled:false}},scales:{x:{display:false},y:{display:false}},animation:{duration:0}}});
    }

    function navToAnalytics(key){
        document.querySelectorAll('.nav-pill').forEach(p=>p.classList.remove('active'));
        document.querySelector(`[data-metric="${key}"]`).classList.add('active');
        document.getElementById('analytics-page').classList.add('active');
        const m=metrics[key];
        document.getElementById('anTitle').innerText=m.label.toUpperCase(); document.getElementById('anTitle').style.color=m.hex; document.getElementById('anCurrent').style.color=m.hex;
        drawMainChart(key); updateAnalytics();
    }

    function closeAnalytics(){
        document.getElementById('analytics-page').classList.remove('active');
        document.querySelectorAll('.nav-pill').forEach(p=>p.classList.remove('active'));
        if(mainChartInst){mainChartInst.destroy();mainChartInst=null;}
    }

    function updateAnalytics(){
        const key=document.querySelector('.nav-pill.active')?.dataset.metric; if(!key)return;
        const val=currentData[key], m=metrics[key];
        document.getElementById('anCurrent').innerText=val.toFixed(1)+m.unit;
        const hist=sparkData[key]; const avg=hist.length>0?hist.reduce((a,b)=>a+b,0)/hist.length:val;
        document.getElementById('anAvg').innerText=avg.toFixed(1)+m.unit;
        document.getElementById('anAvgTrend').innerText=(val>avg?'\u2191':'\u2193')+' vs promedio';
        const pred=hist.length>=2?val+(val-hist[hist.length-2]):val;
        document.getElementById('anPred').innerText=pred.toFixed(1)+m.unit;
        const conf=Math.min(95,50+hist.length*2);
        document.getElementById('anPredConf').innerText=`Confianza: ${conf}%`;
        document.getElementById('anPredBar').style.width=conf+'%'; document.getElementById('anPredBar').style.background=m.hex;
        document.getElementById('anMax').innerText=Math.max(...hist,val).toFixed(1)+m.unit;
        document.getElementById('anMin').innerText=Math.min(...hist,val).toFixed(1)+m.unit;
        if(mainChartInst){const d=mainChartInst.data.datasets[0].data; d[d.length-1]=val; mainChartInst.update('none');}
    }

    function drawMainChart(key){
        const ctx=document.getElementById('mainChart').getContext('2d'); if(mainChartInst)mainChartInst.destroy();
        const m=metrics[key], base=currentData[key]||20;
        const data7=Array.from({length:7},()=>base+(Math.random()-0.5)*(m.max-m.min)*0.1); data7[6]=base;
        const grad=ctx.createLinearGradient(0,0,0,300); grad.addColorStop(0,m.hex+'55'); grad.addColorStop(1,m.hex+'00');
        mainChartInst=new Chart(ctx,{type:'line',data:{labels:['Lun','Mar','Mi\u00e9','Jue','Vie','S\u00e1b','Hoy'],datasets:[{label:m.label,data:data7,borderColor:m.hex,backgroundColor:grad,borderWidth:2.5,tension:0.4,fill:true,pointBackgroundColor:'#04020e',pointBorderColor:m.hex,pointBorderWidth:2,pointRadius:5,pointHoverRadius:8}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{backgroundColor:'rgba(4,2,20,0.95)',titleColor:'#fff',bodyColor:'#fff',borderColor:m.hex,borderWidth:1,padding:12,displayColors:false}},scales:{x:{grid:{color:'rgba(139,92,246,0.06)'},ticks:{color:'#9d8fc9',font:{family:'JetBrains Mono'}}},y:{grid:{color:'rgba(139,92,246,0.06)'},ticks:{color:'#9d8fc9',font:{family:'JetBrains Mono'}}}},interaction:{intersect:false,mode:'index'}}});
    }

    setInterval(fetchData,500);
</script>
</body>
</html>
"""

def fix_surrogates(text):
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        code = ord(c)
        if 0xD800 <= code <= 0xDBFF and i + 1 < len(text):
            low = ord(text[i + 1])
            if 0xDC00 <= low <= 0xDFFF:
                codepoint = 0x10000 + (code - 0xD800) * 0x400 + (low - 0xDC00)
                result.append(chr(codepoint))
                i += 2
                continue
        result.append(c)
        i += 1
    return ''.join(result)

@app.route('/')
def index():
    html = render_template_string(HTML_TEMPLATE)
    return fix_surrogates(html)

if __name__ == '__main__':
    print("=" * 50)
    print("  MTR-01 Servidor Meteorológico")
    print("  Escuchando en: http://0.0.0.0: 5000")
    print("  Endpoint ESP32: POST /api/sensor-data")
    print("  Verificar:     GET  /api/status")
    print("=" * 50)
    app.run(debug=False, port=5000, host='0.0.0.0')