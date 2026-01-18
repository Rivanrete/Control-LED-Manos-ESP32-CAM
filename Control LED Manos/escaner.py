# ========================================================================================================
#                                                                                   PROYECTO: ESP32-CAM + MediaPipe + Flask (El HTML po)
#
# NOTA IMPORTANTE:
#
# - Este proyecto FUNCIONA correctamente con:
#     * Python 3.10.x
#     * mediapipe 0.10.21
#     *Las demas librerias su version mas actual a la fecha: 18/01/2026

# - Otras versiones de Python (3.11, 3.12) y/o mediapipe
#   DIRECTAMENETE NO LE DABA LA GANA DE FUNCIONAR, las demas librerias no dieron problema con su version al momento de instalarlas
#
# - Y el ejecutar el codigo el servidor es el segundo enlace que se mostrara en consola
# ========================================================================================================




# -------------------- LIBRERIAS--------------------
from flask import Flask, render_template_string, Response, jsonify #Conjunto de 4 Herramientas
        # - Flask: Levanta el servidor web
        # - render_template_string: Muestra código HTML sin usar archivos .html
        # - Response: Permite enviar video en tiempo real (streaming de frames)
        # - jsonify: Manda datos al navegador sin refrescar la página (evita parpadeos)

import cv2                              # para manejar imágenes (decodificar, dibujar, convertir, etc.)
import mediapipe as mp        # IA de Google que detecta manos y dedos
import requests                      # para pedir la imagen al ESP32CAM por HTTP
import numpy as np              # para convertir bytes crudos en imágenes entendibles

# Creamos la app de Flask (el servidor web)
app = Flask(__name__)  #Creo un servidor web en Python y lo guardo en la variable app


# -------------------- MEDIAPIPE --------------------

# Acceso al módulo de manos
mp_hands = mp.solutions.hands
# Herramienta para dibujar los puntos y líneas sobre la mano
mp_dibujo = mp.solutions.drawing_utils

# Configuración del detector de manos
manos = mp_hands.Hands(
    static_image_mode=False,           # False porque estamos trabajando con video
    max_num_hands=1,                     # Solo nos interesa UNA mano
    min_detection_confidence=0.7,   # Qué tan seguro debe estar para decir "esto es una mano"
    min_tracking_confidence=0.7      # Qué tan seguro debe estar para seguirla frame a frame
)

# -------------------- ESP32CAM --------------------

# URL desde donde el ESP32CAM manda la imagen
url_cam = "http://192.168.4.1/cam.jpg"

# Guardamos la última potencia enviada para no mandar lo mismo todo el tiempo
ultimo_valor = -1  # valor imposible a propósito

# Datos que se van a mostrar en el HTML
# Esto se actualiza en tiempo real
datos_mano = {
    "dedos": 0,                            # cuántos dedos detecta
    "mano_tipo": "Ninguna",      # izquierda o derecha
    "potencia": 0                         # valor PWM enviado al ESP32CAM
}

# -------------------- GENERADOR DE VIDEO --------------------

def generar_frames():
    global ultimo_valor, datos_mano

    # Este while corre infinitamente mientras el navegador esté abierto
    while True:
        try:
            # Pedimos una foto al ESP32CAM
            respuesta = requests.get(url_cam, timeout=1)

            # Convertimos los bytes recibidos en un array de números
            img_array = np.array(bytearray(respuesta.content), dtype=np.uint8)

            # Convertimos ese array en una imagen OpenCV
            frame = cv2.imdecode(img_array, -1)

            # Si la imagen llegó mal, saltamos este ciclo
            if frame is None:
                continue

            # Volteamos la imagen porque el ESP32CAM viene al revés
            frame = cv2.flip(frame, 0)

            # OpenCV usa BGR, MediaPipe usa RGB → conversión obligatoria
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Le pasamos la imagen a MediaPipe para que busque manos
            resultado = manos.process(frame_rgb)

            # Inicializamos valores
            dedos = 0
            mano_tipo = "Ninguna"

            # Si detectó alguna mano
            if resultado.multi_hand_landmarks:
                for idx, mano_puntos in enumerate(resultado.multi_hand_landmarks):

                    # Dibujamos los puntitos y líneas sobre la mano
                    mp_dibujo.draw_landmarks(
                        frame,
                        mano_puntos,
                        mp_hands.HAND_CONNECTIONS
                    )

                    # Guardamos todos los puntos de la mano
                    puntos = mano_puntos.landmark

                    # ---- CONTAR DEDOS (excepto pulgar) ----
                    # Si la punta está más arriba que la articulación → dedo levantado
                    if puntos[8].y < puntos[6].y:   # índice
                        dedos += 1
                    if puntos[12].y < puntos[10].y: # medio
                        dedos += 1
                    if puntos[16].y < puntos[14].y: # anular
                        dedos += 1
                    if puntos[20].y < puntos[18].y: # meñique
                        dedos += 1

                    # Identificamos si es mano izquierda o derecha
                    mano_tipo = resultado.multi_handedness[idx].classification[0].label

                    # ---- CONTAR PULGAR ----
                    # El pulgar se mueve horizontalmente, no vertical
                    if mano_tipo == "Right":
                        if puntos[4].x < puntos[3].x:
                            dedos += 1
                    else:  # mano izquierda
                        if puntos[4].x > puntos[3].x:
                            dedos += 1

            # -------------------- PWM --------------------

            # Convertimos dedos (0–5) a potencia (0–255)
            potencia = int(dedos * 255 / 5)

            # Solo mandamos al ESP32CAM si cambió el valor
            if potencia != ultimo_valor:
                try:
                    requests.get(
                        f"http://192.168.4.1/control?potencia={potencia}",
                        timeout=0.5
                    )
                    ultimo_valor = potencia
                except:
                    pass

            # Actualizamos los datos que el HTML va a mostrar
            datos_mano["dedos"] = dedos
            datos_mano["mano_tipo"] = mano_tipo
            datos_mano["potencia"] = potencia

            # Convertimos el frame final a JPG para enviarlo al navegador
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            # Esto es lo que hace que el navegador reciba video continuo
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame_bytes +
                b'\r\n'
            )

        except:
            continue

# -------------------- HTML --------------------

@app.route('/')
def index():
    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>ESP32-CAM Monitor</title>
        <style>
            /* Todo oscuro porque somos gente de bien */
            body {
                background-color: #121212;
                color: #fff;
                font-family: Arial, sans-serif;
                display: flex;
                height: 100vh;
                margin: 0;
            }

            /* Lado izquierdo: cámara */
            #camara {
                flex: 2;
                display: flex;
                align-items: center;
                justify-content: center;
                background-color: #1e1e1e;
            }

            /* Lado derecho: información */
            #datos {
                flex: 1;
                padding: 20px;
                background-color: #1a1a1a;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }

            .dato {
                font-size: 1.5em;
                margin-bottom: 15px;
            }
        </style>
    </head>
    <body>

        <!-- Imagen que recibe el stream de video -->
        <div id="camara">
            <img src="{{ url_for('video_feed') }}" width="100%">
        </div>

        <!-- Datos explicativos -->
        <div id="datos">
            <h1>Estado del sistema</h1>
            <p class="dato">Mano detectada: <span id="mano_tipo">Ninguna</span></p>
            <p class="dato">Dedos levantados: <span id="dedos">0</span></p>
            <p class="dato">Potencia enviada: <span id="potencia">0</span></p>
        </div>

        <script>
            // Cada 200 ms pedimos SOLO los datos (no la página entera)
            setInterval(() => {
                fetch('/datos')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('mano_tipo').textContent = data.mano_tipo;
                    document.getElementById('dedos').textContent = data.dedos;
                    document.getElementById('potencia').textContent = data.potencia;
                });
            }, 200);
        </script>

    </body>
    </html>
    '''
    return render_template_string(html)

# Endpoint que devuelve SOLO los datos en JSON
@app.route('/datos')
def datos():
    return jsonify(datos_mano)

# Endpoint que envía el video como stream continuo
@app.route('/video_feed')
def video_feed():
    return Response(
        generar_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# Arranque del servidor
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
