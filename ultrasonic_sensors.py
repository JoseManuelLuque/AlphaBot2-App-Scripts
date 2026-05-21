#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE SENSORES ULTRASÓNICOS PARA ALPHABOT2
=============================================================================
Gestiona los 2 sensores ultrasónicos HC-SR04 para detección de obstáculos.

PINES GPIO:
- Sensor Izquierdo: TRIG=22, ECHO=27
- Sensor Derecho: TRIG=23, ECHO=24

=============================================================================
NO HA SIDO USADO EN LA APP FINAL, YA QUE TENIA PENSADO USARLO COMO UN SISITEMA
DE SEGURIDAD PARA NO CHOCAR CON PAREDES PERO ME ROMPIA EL BUCLE DE CONTROL POR
COMPLETO Y NO PODIA VOLVER A INICIARLO, LO DEJO YA QUE EN SI EL SCRIPT FUNCONA
ME FALLA YA EN EL ESTADO DE LOS OTROS
=============================================================================
"""

import RPi.GPIO as GPIO
import time
import threading

class UltrasonicSensors:
    """
    Controlador de sensores ultrasónicos para detección de obstáculos
    """

    # ===== CONFIGURACIÓN DE PINES =====
    # Sensor izquierdo
    TRIG_LEFT = 22
    ECHO_LEFT = 27

    # Sensor derecho
    TRIG_RIGHT = 23
    ECHO_RIGHT = 24

    # ===== CONFIGURACIÓN DE SEGURIDAD =====
    DANGER_DISTANCE = 20.0  # cm - Distancia de peligro
    WARNING_DISTANCE = 30.0  # cm - Distancia de advertencia
    MAX_DISTANCE = 400.0     # cm - Rango máximo del sensor
    TIMEOUT = 0.03           # segundos - Timeout para lectura

    # ===== HISTÉRESIS (ANTI-FLAPPING) =====
    # Requiere varias lecturas consecutivas para cambiar de estado
    UNSAFE_CONSECUTIVE = 3   # ~150ms (a 50ms por lectura)
    SAFE_CONSECUTIVE = 5     # ~250ms
    CLEAR_MARGIN = 5.0       # cm adicionales para despejar (DANGER + margin)

    def __init__(self, debug=False):
        """
        Inicializa los sensores ultrasónicos

        Args:
            debug (bool): Si True, imprime información de depuración
        """
        self.debug = debug

        # Distancias actuales
        self.distance_left = self.MAX_DISTANCE
        self.distance_right = self.MAX_DISTANCE

        # Estado de obstáculos (estable con histéresis)
        self.obstacle_detected = False
        self.obstacle_left = False
        self.obstacle_right = False

        # Contadores de histéresis
        self._unsafe_count = 0
        self._safe_count = 0

        # Thread para lectura continua
        self.running = False
        self.sensor_thread = None

        # Lock para thread-safety
        self.lock = threading.Lock()

        # Inicializar GPIO
        self._init_gpio()

        print("🛡️  Sistema de sensores ultrasónicos inicializado")

    def _init_gpio(self):
        """Configura los pines GPIO para los sensores"""
        try:
            # Configurar pines como salida (TRIG) y entrada (ECHO)
            GPIO.setup(self.TRIG_LEFT, GPIO.OUT)
            GPIO.setup(self.ECHO_LEFT, GPIO.IN)
            GPIO.setup(self.TRIG_RIGHT, GPIO.OUT)
            GPIO.setup(self.ECHO_RIGHT, GPIO.IN)

            # Asegurar que TRIG esté en LOW
            GPIO.output(self.TRIG_LEFT, GPIO.LOW)
            GPIO.output(self.TRIG_RIGHT, GPIO.LOW)
            time.sleep(0.1)

            if self.debug:
                print("✅ GPIO de sensores ultrasónicos configurado")

        except Exception as e:
            print(f"❌ Error configurando GPIO de sensores: {e}")

    def _read_sensor(self, trig_pin, echo_pin):
        """
        Lee la distancia de un sensor ultrasónico

        Args:
            trig_pin: Pin GPIO del trigger
            echo_pin: Pin GPIO del echo

        Returns:
            float: Distancia en centímetros, o MAX_DISTANCE si hay error
        """
        try:
            # Enviar pulso de 10µs
            GPIO.output(trig_pin, GPIO.HIGH)
            time.sleep(0.00001)  # 10 microsegundos
            GPIO.output(trig_pin, GPIO.LOW)

            # Esperar respuesta con timeout
            timeout_start = time.time()

            # Esperar a que ECHO pase a HIGH
            while GPIO.input(echo_pin) == GPIO.LOW:
                pulse_start = time.time()
                if pulse_start - timeout_start > self.TIMEOUT:
                    return self.MAX_DISTANCE

            # Esperar a que ECHO pase a LOW
            while GPIO.input(echo_pin) == GPIO.HIGH:
                pulse_end = time.time()
                if pulse_end - timeout_start > self.TIMEOUT:
                    return self.MAX_DISTANCE

            # Calcular distancia
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # Velocidad del sonido / 2
            distance = round(distance, 2)

            # Validar rango
            if distance < 2 or distance > self.MAX_DISTANCE:
                return self.MAX_DISTANCE

            return distance

        except Exception as e:
            if self.debug:
                print(f"⚠️  Error leyendo sensor: {e}")
            return self.MAX_DISTANCE

    def read_sensors(self):
        """
        Lee ambos sensores y actualiza el estado con histéresis

        Returns:
            tuple: (distance_left, distance_right, obstacle_detected)
        """
        with self.lock:
            # Leer sensor izquierdo
            self.distance_left = self._read_sensor(self.TRIG_LEFT, self.ECHO_LEFT)
            time.sleep(0.01)  # Pequeña pausa entre lecturas

            # Leer sensor derecho
            self.distance_right = self._read_sensor(self.TRIG_RIGHT, self.ECHO_RIGHT)

            # Determinar estados instantáneos
            instant_left = self.distance_left < self.DANGER_DISTANCE
            instant_right = self.distance_right < self.DANGER_DISTANCE
            instant_obstacle = instant_left or instant_right

            # Histéresis: actualizar contadores
            if instant_obstacle:
                self._unsafe_count += 1
                self._safe_count = 0
            else:
                # Requerir despeje con margen para considerar SAFE
                if (
                    self.distance_left > (self.DANGER_DISTANCE + self.CLEAR_MARGIN)
                    and self.distance_right > (self.DANGER_DISTANCE + self.CLEAR_MARGIN)
                ):
                    self._safe_count += 1
                    self._unsafe_count = 0
                else:
                    # En zona gris (entre peligro y peligro+margen) no cambiar contadores
                    pass

            # Aplicar umbrales de cambio de estado
            if not self.obstacle_detected and self._unsafe_count >= self.UNSAFE_CONSECUTIVE:
                self.obstacle_detected = True
            elif self.obstacle_detected and self._safe_count >= self.SAFE_CONSECUTIVE:
                self.obstacle_detected = False

            # Flags laterales informativos
            self.obstacle_left = self.distance_left < self.DANGER_DISTANCE
            self.obstacle_right = self.distance_right < self.DANGER_DISTANCE

            # Log limitado
            if self.obstacle_detected and self.debug:
                print(
                    f"⚠️  OBSTÁCULO (estable) - Izq: {self.distance_left:.1f}cm, Der: {self.distance_right:.1f}cm"
                )

            return self.distance_left, self.distance_right, self.obstacle_detected

    def start_monitoring(self):
        """Inicia el monitoreo continuo de sensores en background"""
        if not self.running:
            self.running = True
            self.sensor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.sensor_thread.start()
            print(
                f"🔍 Monitoreo de sensores iniciado (peligro < {self.DANGER_DISTANCE}cm | despeje > {self.DANGER_DISTANCE + self.CLEAR_MARGIN}cm)"
            )

    def _monitor_loop(self):
        """Loop de monitoreo continuo (ejecutado en thread separado)"""
        while self.running:
            self.read_sensors()
            time.sleep(0.05)  # Leer cada 50ms (20 lecturas/segundo)

    def stop_monitoring(self):
        """Detiene el monitoreo de sensores"""
        self.running = False
        if self.sensor_thread:
            self.sensor_thread.join(timeout=1.0)
        print("🛑 Monitoreo de sensores detenido")

    def is_safe_to_move_forward(self):
        """
        Verifica si es seguro moverse hacia adelante (estado estable)

        Returns:
            bool: True si es seguro, False si hay obstáculo
        """
        with self.lock:
            return not self.obstacle_detected

    def get_status(self):
        """
        Obtiene el estado actual de los sensores

        Returns:
            dict: Estado completo de los sensores
        """
        with self.lock:
            return {
                'left_distance': self.distance_left,
                'right_distance': self.distance_right,
                'obstacle_detected': self.obstacle_detected,
                'obstacle_left': self.obstacle_left,
                'obstacle_right': self.obstacle_right,
                'safe_to_move': not self.obstacle_detected
            }

    def cleanup(self):
        """Limpieza al salir"""
        self.stop_monitoring()


# =============================================================================
# CÓDIGO DE PRUEBA
# =============================================================================
if __name__ == '__main__':
    """
    Prueba del sistema de sensores ultrasónicos
    """
    print("=" * 60)
    print("🧪 PRUEBA DE SENSORES ULTRASÓNICOS")
    print("=" * 60)

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        sensors = UltrasonicSensors(debug=True)
        sensors.start_monitoring()

        print("\n📊 Leyendo sensores (Ctrl+C para salir)...")
        print("-" * 60)

        while True:
            status = sensors.get_status()

            # Construir barra visual de distancia
            def distance_bar(distance):
                if distance >= sensors.MAX_DISTANCE:
                    return "████████████ (>400cm)"
                bars = int((distance / 50) * 12)
                return "█" * bars + "░" * (12 - bars) + f" ({distance:.1f}cm)"

            print(f"\r🔍 IZQ: {distance_bar(status['left_distance'])} | "
                  f"DER: {distance_bar(status['right_distance'])} | "
                  f"{'🚫 BLOQUEADO' if status['obstacle_detected'] else '✅ SEGURO'}    ", end='', flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n⛔ Prueba interrumpida")
    finally:
        sensors.cleanup()
        GPIO.cleanup()
        print("👋 Limpieza completada")
