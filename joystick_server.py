#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SERVIDOR DE CONTROL PARA ALPHABOT2
=============================================================================
Este servidor maneja el control en tiempo real del robot AlphaBot2,
recibiendo comandos desde una aplicación Android vía socket TCP.

CARACTERÍSTICAS:
- Control de motores DC (movimiento del robot)
- Control de servos de cámara (pan/tilt)
- Sistema de timeout de seguridad (500ms)
- Arquitectura cliente-servidor persistente
- Watchdog automático para detener motores

PUERTOS:
- Puerto 5555: Control de motores y cámara (TCP)
- Puerto 8080: Streaming de video (gestionado por camera_stream.py)

COMANDOS SOPORTADOS:
- "MOVE x y"    : Mover robot (x, y entre -1.0 y 1.0)
- "CAMERA x y"  : Mover cámara (x, y son velocidades entre -1.0 y 1.0)
- "STOP"        : Detener motores y centrar cámara
- "QUIT"        : Desconectar cliente

SEGURIDAD:
- Timeout de 500ms: si no hay comandos, detiene motores automáticamente
- Watchdog en thread separado monitoreando constantemente

=============================================================================
"""

import socket
import RPi.GPIO as GPIO
import sys
import time
import threading

# ===== IMPORTAR CONTROLADOR DE CÁMARA =====
try:
    from camera_control import CameraController
    camera_available = True
except ImportError:
    print("⚠️  Módulo de cámara no disponible")
    camera_available = False

# =============================================================================
# CONFIGURACIÓN DE PINES GPIO DEL ALPHABOT2
# =============================================================================
# El AlphaBot2 tiene dos motores DC controlados mediante puente H (L298N)
# Cada motor necesita:
# - 2 pines de dirección (IN1, IN2)
# - 1 pin PWM para velocidad

# ===== MOTOR IZQUIERDO =====
AIN1 = 12  # GPIO 12 - Dirección adelante
AIN2 = 13  # GPIO 13 - Dirección atrás
PWMA = 6   # GPIO 6  - PWM velocidad (0-100%)

# ===== MOTOR DERECHO =====
BIN1 = 20  # GPIO 20 - Dirección adelante
BIN2 = 21  # GPIO 21 - Dirección atrás
PWMB = 26  # GPIO 26 - PWM velocidad (0-100%)

# =============================================================================
# VARIABLES GLOBALES PARA SISTEMA DE SEGURIDAD
# =============================================================================
last_command_time = time.time()    # Timestamp del último comando recibido
motors_active = False               # Estado de los motores (activos/inactivos)
TIMEOUT_SECONDS = 0.5               # Timeout de seguridad: 500 milisegundos

# Variables globales para PWM (se inicializan en init_gpio)
pwm_a = None
pwm_b = None

# =============================================================================
# INICIALIZACIÓN DE GPIO
# =============================================================================

def init_gpio():
    """
    Inicializa los pines GPIO y objetos PWM.

    Esta función debe llamarse una vez al inicio del servidor.
    Se separó del nivel del módulo para mejor manejo de errores.
    """
    global pwm_a, pwm_b

    print("🔧 Inicializando GPIO...")

    try:
        GPIO.setmode(GPIO.BCM)              # Usar numeración BCM de pines
        GPIO.setwarnings(False)             # Desactivar warnings de GPIO

        # Configurar pines de motores como salidas
        GPIO.setup(AIN1, GPIO.OUT)
        GPIO.setup(AIN2, GPIO.OUT)
        GPIO.setup(BIN1, GPIO.OUT)
        GPIO.setup(BIN2, GPIO.OUT)
        GPIO.setup(PWMA, GPIO.OUT)
        GPIO.setup(PWMB, GPIO.OUT)

        # Crear objetos PWM con frecuencia de 1000 Hz
        # Mayor frecuencia = movimiento más suave y menos ruido audible
        pwm_a = GPIO.PWM(PWMA, 1000)       # PWM motor izquierdo a 1 kHz
        pwm_b = GPIO.PWM(PWMB, 1000)       # PWM motor derecho a 1 kHz
        pwm_a.start(0)                      # Iniciar PWM al 0% (motor detenido)
        pwm_b.start(0)

        print("✅ GPIO inicializado correctamente")
        return True

    except Exception as e:
        print(f"❌ Error inicializando GPIO: {e}")
        return False

# =============================================================================
# FUNCIONES DE CONTROL DE MOTORES
# =============================================================================

def set_motor_left(speed):
    """
    Controla el motor izquierdo del robot.

    El motor se controla mediante un puente H (L298N):
    - IN1=HIGH, IN2=LOW → Motor gira adelante
    - IN1=LOW, IN2=HIGH → Motor gira atrás
    - IN1=LOW, IN2=LOW  → Motor detenido (freno)
    - PWM controla la velocidad (duty cycle 0-100%)

    Args:
        speed (int): Velocidad del motor (-100 a +100)
                     Positivo: adelante
                     Negativo: atrás
                     Cero: detenido
    """
    if speed > 0:
        # ===== ADELANTE =====
        GPIO.output(AIN1, GPIO.HIGH)
        GPIO.output(AIN2, GPIO.LOW)
        pwm_a.ChangeDutyCycle(min(abs(speed), 100))
    elif speed < 0:
        # ===== ATRÁS =====
        GPIO.output(AIN1, GPIO.LOW)
        GPIO.output(AIN2, GPIO.HIGH)
        pwm_a.ChangeDutyCycle(min(abs(speed), 100))
    else:
        # ===== DETENIDO =====
        GPIO.output(AIN1, GPIO.LOW)
        GPIO.output(AIN2, GPIO.LOW)
        pwm_a.ChangeDutyCycle(0)

def set_motor_right(speed):
    """
    Controla el motor derecho del robot.

    Funciona igual que set_motor_left() pero para el motor derecho.

    Args:
        speed (int): Velocidad del motor (-100 a +100)
                     Positivo: adelante
                     Negativo: atrás
                     Cero: detenido
    """
    if speed > 0:
        # ===== ADELANTE =====
        GPIO.output(BIN1, GPIO.HIGH)
        GPIO.output(BIN2, GPIO.LOW)
        pwm_b.ChangeDutyCycle(min(abs(speed), 100))
    elif speed < 0:
        # ===== ATRÁS =====
        GPIO.output(BIN1, GPIO.LOW)
        GPIO.output(BIN2, GPIO.HIGH)
        pwm_b.ChangeDutyCycle(min(abs(speed), 100))
    else:
        # ===== DETENIDO =====
        GPIO.output(BIN1, GPIO.LOW)
        GPIO.output(BIN2, GPIO.LOW)
        pwm_b.ChangeDutyCycle(0)

def joystick_to_motors(x, y):
    """
    Convierte las coordenadas del joystick a velocidades de los motores.

    Usa el algoritmo "tank drive" o "arcade drive" para control intuitivo:
    - Joystick arriba: ambos motores adelante → robot avanza
    - Joystick abajo: ambos motores atrás → robot retrocede
    - Joystick derecha: motor izq. más rápido → robot gira a la derecha
    - Joystick izquierda: motor der. más rápido → robot gira a la izquierda

    Fórmula tank drive:
        motor_izquierdo = adelante + giro
        motor_derecho = adelante - giro

    Args:
        x (float): Coordenada X del joystick (-1.0 a 1.0)
                   -1.0 = completamente a la izquierda
                   +1.0 = completamente a la derecha

        y (float): Coordenada Y del joystick (-1.0 a 1.0)
                   -1.0 = completamente abajo (atrás)
                   +1.0 = completamente arriba (adelante)

    Returns:
        tuple: (velocidad_izquierda, velocidad_derecha)
               Ambos valores entre -100 y 100

    Ejemplo:
        joystick_to_motors(0, 1)    → (100, 100)   # Adelante recto
        joystick_to_motors(0, -1)   → (-100, -100) # Atrás recto
        joystick_to_motors(1, 0)    → (100, -100)  # Girar en su eje a la derecha
        joystick_to_motors(0.5, 1)  → (150, 50)    # Adelante girando a la derecha
                                                     # (limitado a 100, 50)
    """
    # ===== COMPONENTES DEL MOVIMIENTO =====
    forward = y * 100    # Componente adelante/atrás (-100 a +100)
    turn = x * 100       # Componente de giro (-100 a +100)

    # ===== MEZCLA TANK-DRIVE =====
    # Sumar giro al motor izquierdo, restar del derecho
    left = forward + turn
    right = forward - turn

    # ===== LIMITAR A RANGO VÁLIDO (-100 a +100) =====
    left = max(-100, min(100, left))
    right = max(-100, min(100, right))

    # ===== ZONA MUERTA (DEADZONE) =====
    # Si la velocidad es muy baja, ponerla a 0
    # Esto evita vibraciones o movimientos residuales cuando el joystick
    # no está perfectamente centrado
    DEADZONE = 5
    if abs(left) < DEADZONE:
        left = 0
    if abs(right) < DEADZONE:
        right = 0

    return int(left), int(right)

def stop():
    """
    Detiene ambos motores completamente y de forma segura.

    Proceso:
    1. Pone todos los pines de dirección en LOW (freno activo)
    2. Pone el PWM a 0% (sin potencia)
    3. Marca los motores como inactivos

    Nota:
        Poner ambos pines de dirección en LOW activa el freno
        del puente H, deteniendo el motor más rápido que simplemente
        poner PWM a 0.
    """
    global motors_active

    # Freno activo: ambos pines de dirección en LOW
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.LOW)

    # PWM a 0%
    pwm_a.ChangeDutyCycle(0)
    pwm_b.ChangeDutyCycle(0)

    # Actualizar estado
    motors_active = False

def cleanup():
    """
    Limpia recursos GPIO antes de salir del programa.

    Es importante llamar a esta función al terminar para:
    - Detener los motores
    - Detener las señales PWM
    - Liberar los pines GPIO
    - Evitar warnings en futuras ejecuciones
    """
    print("🧹 Limpiando recursos GPIO...")
    stop()                  # Detener motores
    pwm_a.stop()           # Detener PWM motor izquierdo
    pwm_b.stop()           # Detener PWM motor derecho
    GPIO.cleanup()         # Liberar todos los pines GPIO
    print("✅ GPIO limpiado")

# =============================================================================
# SISTEMA DE SEGURIDAD: WATCHDOG
# =============================================================================

def timeout_watchdog():
    """
    Thread de vigilancia que monitorea el timeout de comandos.

    Este thread se ejecuta en segundo plano y verifica constantemente
    si han pasado más de TIMEOUT_SECONDS desde el último comando.
    Si detecta timeout, detiene los motores automáticamente.

    ¿Por qué es necesario?
    - Si la app Android se cierra abruptamente, el robot seguiría moviéndose
    - Si hay pérdida de conexión WiFi, el robot podría chocar
    - Es una medida de seguridad esencial

    Este thread corre como daemon, por lo que se cierra automáticamente
    al salir del programa principal.
    """
    global last_command_time, motors_active

    while True:
        time.sleep(0.1)  # Verificar cada 100 milisegundos

        # Calcular tiempo transcurrido desde el último comando
        elapsed = time.time() - last_command_time

        # Si los motores están activos y ha pasado el timeout
        if motors_active and elapsed > TIMEOUT_SECONDS:
            print(f"⚠️  TIMEOUT DETECTADO ({elapsed:.2f}s) - Deteniendo motores por seguridad")
            stop()

# =============================================================================
# SERVIDOR PRINCIPAL
# =============================================================================

def start_server(port=5555):
    """
    Inicia el servidor socket que escucha comandos de control.

    Este es el corazón del sistema de control. Mantiene un servidor TCP
    esperando conexiones de la app Android y procesando comandos en tiempo real.

    Args:
        port (int): Puerto TCP donde escuchar (por defecto 5555)

    Flujo de operación:
    1. Inicializar controlador de cámara
    2. Iniciar watchdog de seguridad
    3. Crear socket del servidor
    4. Esperar conexiones de clientes
    5. Para cada cliente:
       a. Recibir comandos continuamente
       b. Procesar y ejecutar comandos
       c. Enviar confirmación
       d. Al desconectar, detener motores
    6. Repetir desde el paso 4
    """
    global last_command_time, motors_active

    # ===== INICIALIZAR CONTROLADOR DE CÁMARA =====
    camera = None
    camera_enabled = camera_available  # Usar variable local para evitar problemas de scope

    if camera_enabled:
        try:
            camera = CameraController(debug=False)
            print("📷 Controlador de cámara inicializado")
        except Exception as e:
            print(f"⚠️  No se pudo inicializar la cámara: {e}")
            camera_enabled = False

    # ===== INICIAR WATCHDOG DE SEGURIDAD =====
    print("🛡️  Iniciando watchdog de seguridad...")
    watchdog = threading.Thread(target=timeout_watchdog, daemon=True)
    watchdog.start()
    print(f"✅ Watchdog activo (timeout: {TIMEOUT_SECONDS}s)")

    # ===== CREAR SOCKET DEL SERVIDOR =====
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', port))  # Escuchar en todas las interfaces
    server_socket.listen(1)                # Permitir 1 conexión en cola

    # ===== SERVIDOR LISTO =====
    print("\n" + "=" * 60)
    print("🚀 SERVIDOR DE CONTROL ALPHABOT2 ACTIVO")
    print("=" * 60)
    print(f"📡 Puerto TCP:          {port}")
    print(f"🛡️  Timeout seguridad:   {TIMEOUT_SECONDS}s")
    print(f"📷 Control de cámara:   {'✅ Habilitado' if camera else '❌ Deshabilitado'}")
    print("=" * 60)
    print("\n⏳ Esperando conexión de la app Android...\n")

    try:
        # ===== BUCLE PRINCIPAL: ACEPTAR CLIENTES =====
        while True:
            # Esperar a que un cliente se conecte (bloqueante)
            client_socket, address = server_socket.accept()
            print(f"✅ Cliente conectado desde {address[0]}:{address[1]}")

            try:
                # ===== BUCLE DE COMANDOS DEL CLIENTE =====
                while True:
                    # Recibir comando del cliente
                    data = client_socket.recv(1024).decode('utf-8').strip()

                    # Si no hay datos, el cliente se desconectó
                    if not data:
                        break

                    # ===== ACTUALIZAR TIMESTAMP DE SEGURIDAD =====
                    last_command_time = time.time()

                    # ===== PARSEAR COMANDO =====
                    parts = data.split()

                    # ----- COMANDO: MOVE x y -----
                    # Controla el movimiento del robot
                    if len(parts) == 3 and parts[0].upper() == "MOVE":
                        try:
                            x = float(parts[1])
                            y = float(parts[2])

                            # Limitar valores a rango válido
                            x = max(-1.0, min(1.0, x))
                            y = max(-1.0, min(1.0, y))

                            # Convertir joystick a velocidades de motores
                            left_speed, right_speed = joystick_to_motors(x, y)

                            # Aplicar velocidades
                            set_motor_left(left_speed)
                            set_motor_right(right_speed)

                            # Actualizar estado
                            motors_active = (left_speed != 0 or right_speed != 0)

                            # Confirmación al cliente
                            client_socket.send(b"OK\n")

                        except ValueError:
                            client_socket.send(b"ERROR: Invalid values\n")

                    # ----- COMANDO: CAMERA x y -----
                    # Controla el movimiento de la cámara (tipo FPS incremental)
                    elif len(parts) == 3 and parts[0].upper() == "CAMERA":
                        if camera:
                            try:
                                x = float(parts[1])
                                y = float(parts[2])

                                # Limitar valores a rango válido
                                x = max(-1.0, min(1.0, x))
                                y = max(-1.0, min(1.0, y))

                                # Mover cámara de forma INCREMENTAL
                                # x e y son VELOCIDADES, no posiciones
                                camera.move_incremental(x, y)

                                # Confirmación al cliente
                                client_socket.send(b"OK\n")

                            except ValueError:
                                client_socket.send(b"ERROR: Invalid camera values\n")
                        else:
                            client_socket.send(b"ERROR: Camera not available\n")

                    # ----- COMPATIBILIDAD: Comandos antiguos (2 valores) -----
                    # Formato antiguo sin "MOVE", solo "x y"
                    elif len(parts) == 2:
                        try:
                            x = float(parts[0])
                            y = float(parts[1])

                            x = max(-1.0, min(1.0, x))
                            y = max(-1.0, min(1.0, y))

                            left_speed, right_speed = joystick_to_motors(x, y)
                            set_motor_left(left_speed)
                            set_motor_right(right_speed)
                            motors_active = (left_speed != 0 or right_speed != 0)

                            client_socket.send(b"OK\n")

                        except ValueError:
                            client_socket.send(b"ERROR: Invalid values\n")

                    # ----- COMANDO: STOP -----
                    # Detiene motores y centra cámara
                    elif data.lower() == "stop":
                        stop()
                        if camera:
                            camera.center()
                        client_socket.send(b"STOPPED\n")

                    # ----- COMANDO: QUIT -----
                    # Desconectar cliente ordenadamente
                    elif data.lower() == "quit":
                        stop()
                        if camera:
                            camera.cleanup()
                        client_socket.send(b"BYE\n")
                        break

            except Exception as e:
                print(f"❌ Error con cliente {address[0]}: {e}")

            finally:
                # ===== LIMPIEZA AL DESCONECTAR CLIENTE =====
                client_socket.close()
                stop()  # Detener motores por seguridad
                if camera:
                    camera.center()
                print(f"🔌 Cliente {address[0]} desconectado - motores detenidos")
                print("⏳ Esperando nueva conexión...\n")

    except KeyboardInterrupt:
        print("\n⛔ Servidor detenido por usuario")

    finally:
        # ===== LIMPIEZA FINAL DEL SERVIDOR =====
        server_socket.close()
        if camera:
            camera.cleanup()
        cleanup()
        print("👋 Servidor terminado")

# =============================================================================
# PUNTO DE ENTRADA DEL SCRIPT
# =============================================================================

if __name__ == "__main__":
    """
    Ejecuta el servidor cuando se llama el script directamente.
    """
    try:
        # Inicializar GPIO antes de iniciar el servidor
        if not init_gpio():
            print("❌ Falló la inicialización de GPIO. El servidor no puede arrancar.")
            sys.exit(1)

        start_server()
    except Exception as e:
        print(f"💥 Error fatal: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        sys.exit(1)
