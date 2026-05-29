import serial
import requests
import json
import time

# Configura tu puerto COM (Windows) o /dev/ttyUSB0 (Linux/Mac)
PUERTO = 'COM4'  # Cambia según tu sistema (ver en Administrador de dispositivos)
BAUDIOS = 115200
URL_RENDER = 'https://estacion-meteorologica-gehe.onrender.com/api/sensor-data'

try:
    ser = serial.Serial(PUERTO, BAUDIOS, timeout=5)
    print(f"Conectado a {PUERTO}")
    
    while True:
        linea = ser.readline().decode('utf-8').strip()
        if linea and linea.startswith('{'):
            try:
                datos = json.loads(linea)
                print("Recibido:", datos)
                
                # Enviar a Render
                respuesta = requests.post(URL_RENDER, json=datos, timeout=10)
                print("Enviado a Render:", respuesta.status_code, respuesta.json())
                
            except json.JSONDecodeError:
                print("JSON inválido:", linea)
            except requests.exceptions.RequestException as e:
                print("Error al enviar:", e)
                
        time.sleep(0.5)

except serial.SerialException as e:
    print(f"Error de conexión serial: {e}")
    print("Verifica el puerto COM en Administrador de dispositivos")