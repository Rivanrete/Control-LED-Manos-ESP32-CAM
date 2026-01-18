from flask import Flask, render_template_string, Response, jsonify
import cv2
import mediapipe as mp
import requests
import numpy as np

app = Flask(__name__)

# --- MediaPipe ---
mp_hands = mp.solutions.hands
mp_dibujo = mp.solutions.drawing_utils

manos = mp_hands.Hands(
    static_image_mode=False,      
    max_num_hands=1,              
    min_detection_confidence=0.7, 
    min_tracking_confidence=0.7   
)

# --- URL del ESP32CAM ---
url_cam = "http://192.168.4.1/cam.jpg"

# --- Último valor enviado ---
ultimo_valor = -1

# --- Variables globales para mostrar en HTML ---
datos_mano = {"dedos": 0, "mano_tipo": "Ninguna", "potencia": 0}

def generar_frames():
    global ultimo_valor, datos_mano
    while True:
        try:
            # Pedir imagen del ESP32CAM
            respuesta = requests.get(url_cam, timeout=1)
            img_array = np.array(bytearray(respuesta.content), dtype=np.uint8)
            frame = cv2.imdecode(img_array, -1)
            if frame is None:
                continue

            frame = cv2.flip(frame, 0)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resultado = manos.process(frame_rgb)

            dedos = 0
            mano_tipo = "Ninguna"

            if resultado.multi_hand_landmarks:
                for idx, mano_puntos in enumerate(resultado.multi_hand_landmarks):
                    # --- Dibujar los palitos y puntos ---
                    mp_dibujo.draw_landmarks(frame, mano_puntos, mp_hands.HAND_CONNECTIONS)

                    puntos = mano_puntos.landmark
                    # Índice, medio, anular, meñique
                    if puntos[8].y < puntos[6].y:
                        dedos += 1
                    if puntos[12].y < puntos[10].y:
                        dedos += 1
                    if puntos[16].y < puntos[14].y:
                        dedos += 1
                    if puntos[20].y < puntos[18].y:
                        dedos += 1

                    mano_tipo = resultado.multi_handedness[idx].classification[0].label
                    # Pulgar
                    if mano_tipo == "Right":
                        if puntos[4].x < puntos[3].x:
                            dedos += 1
                    else:
                        if puntos[4].x > puntos[3].x:
                            dedos += 1

            # --- Mapear dedos a potencia ---
            potencia = int(dedos * 255 / 5)
            # --- Enviar al ESP32 solo si cambia ---
            if potencia != ultimo_valor:
                try:
                    requests.get(f"http://192.168.4.1/control?potencia={potencia}", timeout=0.5)
                    ultimo_valor = potencia
                except:
                    pass

            # --- Actualizar variables para HTML ---
            datos_mano["dedos"] = dedos
            datos_mano["mano_tipo"] = mano_tipo
            datos_mano["potencia"] = potencia

            # --- Convertir a JPEG ---
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        except:
            continue

# --- Página principal ---
@app.route('/')
def index():
    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>ESP32-CAM Monitor - Dashboard Oscuro</title>
        <style>
            body { background-color: #121212; color: #fff; font-family: Arial, sans-serif; display:flex; flex-direction: row; height: 100vh; margin:0; }
            #camara { flex: 2; display:flex; align-items:center; justify-content:center; background-color: #1e1e1e; }
            #datos { flex: 1; padding: 20px; display:flex; flex-direction: column; justify-content:center; background-color: #1a1a1a; }
            h1, h2, p { margin: 10px 0; color: #fff; }
            .dato { font-size: 1.5em; margin-bottom: 15px; }
        </style>
    </head>
    <body>
        <div id="camara">
            <!-- Video fluido -->
            <img src="{{ url_for('video_feed') }}" width="100%">
        </div>
        <div id="datos">
            <h1>Estado de la mano</h1>
            <p class="dato">Mano detectada: <span id="mano_tipo">Ninguna</span></p>
            <p class="dato">Dedos levantados: <span id="dedos">0</span></p>
            <p class="dato">Potencia enviada: <span id="potencia">0</span></p>
        </div>

        <script>
            // --- Actualizar datos cada 200 ms ---
            setInterval(() => {
                fetch('/datos')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('mano_tipo').textContent = data.mano_tipo;
                    document.getElementById('dedos').textContent = data.dedos;
                    document.getElementById('potencia').textContent = data.potencia;
                })
            }, 200);
        </script>
    </body>
    </html>
    '''
    return render_template_string(html)

# --- Endpoint para datos de la mano ---
@app.route('/datos')
def datos():
    return jsonify(datos_mano)

# --- Streaming del video ---
@app.route('/video_feed')
def video_feed():
    return Response(generar_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
