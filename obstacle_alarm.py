#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SISTEMA DE DETECCIÓN DE OBSTÁCULOS CON ALARMA - ALPHABOT2
=============================================================================
Sistema integrado que monitorea obstáculos con sensores ultrasónicos HC-SR04
y activa el buzzer en patrón intermitente cuando detecta peligro.

PATRÓN DE ALARMA:
- Obstáculo detectado: BEEP 0.5s → SILENCIO 1s → repetir
- Sin obstáculo: Silencio total

SENSORES:
- HC-SR04 izquierdo (TRIG=22, ECHO=27)
- HC-SR04 derecho (TRIG=23, ECHO=24)
- Buzzer (GPIO 4)

USO:
    python3 obstacle_alarm.py

    Ctrl+C para detener

=============================================================================
"""

import RPi.GPIO as GPIO
import time
import threading
import signal
import sys

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Pines de sensores ultrasónicos
TRIG_LEFT = 22
ECHO_LEFT = 27
TRIG_RIGHT = 23
ECHO_RIGHT = 24

# Pin del buzzer
BUZZER_PIN = 4

# Distancias de detección
DANGER_DISTANCE = 10.0  # cm - Distancia de alarma
MAX_DISTANCE = 400.0    # cm - Rango máximo

# Patrón de alarma
BEEP_DURATION = 0.5     # segundos de pitido
SILENCE_DURATION = 1.0  # segundos de silencio

# Configuración de lectura
READ_INTERVAL = 0.05    # segundos entre lecturas (20 Hz)
TIMEOUT = 0.03          # timeout para sensor

# Histéresis (anti-rebotes)
UNSAFE_CONSECUTIVE = 3  # Lecturas para activar alarma
SAFE_CONSECUTIVE = 5    # Lecturas para desactivar alarma
CLEAR_MARGIN = 5.0      # cm adicionales para despejar

# =============================================================================
# CLASE: ObstacleAlarmSystem
# =============================================================================

class ObstacleAlarmSystem:
    """Sistema integrado de detección de obstáculos con alarma"""

    def __init__(self, debug=False):
        """
        Inicializa el sistema de alarma

        Args:
            debug (bool): Activa mensajes de depuración
        """
        self.debug = debug
        self.running = False

        # Estado de sensores
        self.distance_left = MAX_DISTANCE
        self.distance_right = MAX_DISTANCE
        self.obstacle_detected = False

        # Contadores de histéresis
        self._unsafe_count = 0
        self._safe_count = 0

        # PWM del buzzer
        self.buzzer_pwm = None

        # Threads
        self.sensor_thread = None
        self.alarm_thread = None

        # Locks
        self.lock = threading.Lock()

        # Inicializar GPIO
        self._init_gpio()

        print("=" * 60)
        print("🚨 SISTEMA DE DETECCIÓN DE OBSTÁCULOS CON ALARMA")
        print("=" * 60)
        print(f"📏 Distancia de alarma: {DANGER_DISTANCE} cm")
        print(f"🔊 Patrón: {BEEP_DURATION}s ON / {SILENCE_DURATION}s OFF")
        print("=" * 60)

    def _init_gpio(self):
        """Configura los pines GPIO"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Configurar sensores ultrasónicos
            GPIO.setup(TRIG_LEFT, GPIO.OUT)
            GPIO.setup(ECHO_LEFT, GPIO.IN)
            GPIO.setup(TRIG_RIGHT, GPIO.OUT)
            GPIO.setup(ECHO_RIGHT, GPIO.IN)

            # Asegurar triggers en LOW
            GPIO.output(TRIG_LEFT, GPIO.LOW)
            GPIO.output(TRIG_RIGHT, GPIO.LOW)

            # Configurar buzzer
            GPIO.setup(BUZZER_PIN, GPIO.OUT)
            self.buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)  # 1000 Hz

            time.sleep(0.1)

            if self.debug:
                print("✅ GPIO configurado correctamente")

        except Exception as e:
            print(f"❌ Error configurando GPIO: {e}")
            sys.exit(1)

    def _read_sensor(self, trig_pin, echo_pin):
        """
        Lee distancia de un sensor ultrasónico

        Args:
            trig_pin: Pin GPIO del trigger
            echo_pin: Pin GPIO del echo

        Returns:
            float: Distancia en cm o MAX_DISTANCE si error
        """
        try:
            # Enviar pulso de 10µs
            GPIO.output(trig_pin, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(trig_pin, GPIO.LOW)

            # Esperar respuesta con timeout
            timeout_start = time.time()

            # Esperar ECHO HIGH
            while GPIO.input(echo_pin) == GPIO.LOW:
                pulse_start = time.time()
                if pulse_start - timeout_start > TIMEOUT:
                    return MAX_DISTANCE

            # Esperar ECHO LOW
            while GPIO.input(echo_pin) == GPIO.HIGH:
                pulse_end = time.time()
                if pulse_end - timeout_start > TIMEOUT:
                    return MAX_DISTANCE

            # Calcular distancia
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # Velocidad sonido / 2
            distance = round(distance, 2)

            # Validar rango
            if distance < 2 or distance > MAX_DISTANCE:
                return MAX_DISTANCE

            return distance

        except Exception as e:
            if self.debug:
                print(f"⚠️  Error leyendo sensor: {e}")
            return MAX_DISTANCE

    def _sensor_loop(self):
        """Loop de lectura de sensores (thread separado)"""
        while self.running:
            with self.lock:
                # Leer ambos sensores
                self.distance_left = self._read_sensor(TRIG_LEFT, ECHO_LEFT)
                time.sleep(0.01)
                self.distance_right = self._read_sensor(TRIG_RIGHT, ECHO_RIGHT)

                # Determinar estado instantáneo
                instant_obstacle = (
                    self.distance_left < DANGER_DISTANCE or
                    self.distance_right < DANGER_DISTANCE
                )

                # Aplicar histéresis
                if instant_obstacle:
                    self._unsafe_count += 1
                    self._safe_count = 0
                else:
                    # Requiere margen extra para despejar
                    if (self.distance_left > (DANGER_DISTANCE + CLEAR_MARGIN) and
                        self.distance_right > (DANGER_DISTANCE + CLEAR_MARGIN)):
                        self._safe_count += 1
                        self._unsafe_count = 0

                # Cambiar estado con umbrales
                if not self.obstacle_detected and self._unsafe_count >= UNSAFE_CONSECUTIVE:
                    self.obstacle_detected = True
                    if self.debug:
                        print(f"\n⚠️  OBSTÁCULO DETECTADO!")
                        print(f"   Izquierda: {self.distance_left:.1f}cm")
                        print(f"   Derecha: {self.distance_right:.1f}cm\n")

                elif self.obstacle_detected and self._safe_count >= SAFE_CONSECUTIVE:
                    self.obstacle_detected = False
                    if self.debug:
                        print(f"\n✅ OBSTÁCULO DESPEJADO")
                        print(f"   Izquierda: {self.distance_left:.1f}cm")
                        print(f"   Derecha: {self.distance_right:.1f}cm\n")

            time.sleep(READ_INTERVAL)

    def _alarm_loop(self):
        """Loop de alarma del buzzer (thread separado)"""
        while self.running:
            with self.lock:
                should_beep = self.obstacle_detected

            if should_beep:
                # BEEP por BEEP_DURATION segundos
                if self.debug:
                    print("🔊 BEEP!")

                self.buzzer_pwm.start(50)  # 50% duty cycle
                time.sleep(BEEP_DURATION)
                self.buzzer_pwm.stop()

                # SILENCIO por SILENCE_DURATION segundos
                # (chequeando cada 0.1s por si cambia el estado)
                for _ in range(int(SILENCE_DURATION / 0.1)):
                    time.sleep(0.1)
                    with self.lock:
                        if not self.obstacle_detected:
                            break  # Salir del silencio si se despeja
            else:
                # Sin obstáculo, esperar sin hacer ruido
                time.sleep(0.1)

    def start(self):
        """Inicia el sistema de alarma"""
        if self.running:
            print("⚠️  El sistema ya está en ejecución")
            return

        self.running = True

        # Iniciar thread de sensores
        self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self.sensor_thread.start()

        # Iniciar thread de alarma
        self.alarm_thread = threading.Thread(target=self._alarm_loop, daemon=True)
        self.alarm_thread.start()

        print("\n✅ Sistema iniciado correctamente")
        print("🔍 Monitoreando obstáculos...")
        print("🔊 Alarma lista para activarse")
        print("\n💡 Presiona Ctrl+C para detener\n")

    def stop(self):
        """Detiene el sistema de alarma"""
        print("\n\n🛑 Deteniendo sistema...")

        self.running = False

        # Esperar threads
        if self.sensor_thread:
            self.sensor_thread.join(timeout=1.0)
        if self.alarm_thread:
            self.alarm_thread.join(timeout=1.0)

        # Apagar buzzer
        if self.buzzer_pwm:
            self.buzzer_pwm.stop()

        print("✅ Sistema detenido correctamente")

    def cleanup(self):
        """Limpia recursos GPIO"""
        self.stop()
        GPIO.cleanup()
        print("🧹 GPIO limpiado")


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def signal_handler(sig, frame):
    """Manejador de señal para Ctrl+C"""
    print("\n\n⚠️  Interrupción detectada...")
    if 'system' in globals():
        system.cleanup()
    sys.exit(0)


def main():
    global system

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Crear e iniciar sistema
    system = ObstacleAlarmSystem(debug=True)
    system.start()

    # Mantener vivo
    try:
        while True:
            time.sleep(1)

            # Mostrar estado cada 5 segundos
            # (opcional, puedes comentar esto)
            # with system.lock:
            #     print(f"📊 L: {system.distance_left:.1f}cm | R: {system.distance_right:.1f}cm | Alarma: {'🔴 ON' if system.obstacle_detected else '🟢 OFF'}")

    except KeyboardInterrupt:
        pass

    finally:
        system.cleanup()


if __name__ == '__main__':
    main()

