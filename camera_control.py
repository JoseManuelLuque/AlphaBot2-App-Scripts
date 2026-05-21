#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
CONTROLADOR DE SERVOS DE CÁMARA PARA ALPHABOT2
=============================================================================
Este módulo controla los servos que mueven la cámara del robot mediante
el chip PCA9685 (controlador PWM de 16 canales vía I2C).

CARACTERÍSTICAS:
- Control tipo FPS (First Person Shooter) incremental
- 2 servos: horizontal (pan) y vertical (tilt)
- Sin límites de movimiento
- Sin centrado automático
- Comunicación I2C con PCA9685
- Desactivación automática de PWM para evitar ruido

SERVOS:
- Canal 0: Movimiento horizontal (izquierda-derecha)
- Canal 1: Movimiento vertical (arriba-abajo)

CONTROL:
El control es tipo FPS: el joystick indica VELOCIDAD de rotación,
no posición absoluta. Mantener el stick = seguir girando.

=============================================================================
"""

import time
import math
import smbus

# =============================================================================
# CLASE: PCA9685 (Driver del chip controlador PWM)
# =============================================================================
class PCA9685:
    """Driver para el chip PCA9685 de 16 canales PWM vía I2C."""

    # Registros del PCA9685
    __SUBADR1            = 0x02
    __SUBADR2            = 0x03
    __SUBADR3            = 0x04
    __MODE1              = 0x00
    __PRESCALE           = 0xFE
    __LED0_ON_L          = 0x06
    __LED0_ON_H          = 0x07
    __LED0_OFF_L         = 0x08
    __LED0_OFF_H         = 0x09
    __ALLLED_ON_L        = 0xFA
    __ALLLED_ON_H        = 0xFB
    __ALLLED_OFF_L       = 0xFC
    __ALLLED_OFF_H       = 0xFD

    def __init__(self, address=0x40, debug=False):
        self.bus = smbus.SMBus(1)
        self.address = address
        self.debug = debug

        if self.debug:
            print(f"🔧 Inicializando PCA9685 en dirección I2C 0x{address:02X}")

        self.write(self.__MODE1, 0x00)

    def write(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)
        if self.debug:
            print(f"I2C Write: 0x{value:02X} → registro 0x{reg:02X}")

    def read(self, reg):
        result = self.bus.read_byte_data(self.address, reg)
        if self.debug:
            print(f"I2C Read: 0x{result:02X} ← registro 0x{reg:02X}")
        return result

    def setPWMFreq(self, freq):
        prescaleval = 25000000.0
        prescaleval /= 4096.0
        prescaleval /= float(freq)
        prescaleval -= 1.0

        if self.debug:
            print(f"⚙️  Configurando frecuencia PWM a {freq} Hz")
            print(f"   Prescaler calculado: {prescaleval}")

        prescale = math.floor(prescaleval + 0.5)

        if self.debug:
            print(f"   Prescaler final: {prescale}")

        oldmode = self.read(self.__MODE1)
        newmode = (oldmode & 0x7F) | 0x10
        self.write(self.__MODE1, newmode)
        self.write(self.__PRESCALE, int(math.floor(prescale)))
        self.write(self.__MODE1, oldmode)
        time.sleep(0.005)
        self.write(self.__MODE1, oldmode | 0x80)

    def setPWM(self, channel, on, off):
        self.write(self.__LED0_ON_L + 4*channel, on & 0xFF)
        self.write(self.__LED0_ON_H + 4*channel, on >> 8)
        self.write(self.__LED0_OFF_L + 4*channel, off & 0xFF)
        self.write(self.__LED0_OFF_H + 4*channel, off >> 8)

        if self.debug:
            print(f"Canal {channel}: ON={on}, OFF={off}")

    def setServoPulse(self, channel, pulse):
        pulse = int(pulse * 4096 / 20000)
        self.setPWM(channel, 0, pulse)


# =============================================================================
# CLASE: CameraController (Controlador de cámara)
# =============================================================================
class CameraController:
    """
    Controlador para los servos de la cámara con control tipo FPS incremental.

    SIN LÍMITES DE MOVIMIENTO ni CENTRADO AUTOMÁTICO.
    """

    # Canales PWM
    SERVO_HORIZONTAL = 0
    SERVO_VERTICAL = 1

    # Posición inicial (puedes ajustar estos valores según tu instalación)
    INITIAL_HORIZONTAL = 900
    INITIAL_VERTICAL = 1100

    def __init__(self, debug=False):
        # Inicializar chip PCA9685
        self.pwm = PCA9685(0x40, debug=debug)
        self.pwm.setPWMFreq(50)

        # Posiciones actuales
        self.horizontal_pos = self.INITIAL_HORIZONTAL
        self.vertical_pos = self.INITIAL_VERTICAL

        # Estado de movimiento
        self.is_moving = False

        print("📷 Inicializando controlador de cámara...")
        # NO centrar automáticamente
        print("✅ Cámara lista (sin centrado automático)")

    def stop_pwm(self):
        """Desactiva la señal PWM de ambos servos."""
        self.pwm.setPWM(self.SERVO_HORIZONTAL, 0, 0)
        self.pwm.setPWM(self.SERVO_VERTICAL, 0, 0)
        self.is_moving = False

    def move_incremental(self, velocity_x, velocity_y):
        """
        Mueve la cámara de forma incremental basado en velocidad (CONTROL TIPO FPS).
        SIN LÍMITES DE MOVIMIENTO.
        """

        # Zona muerta
        if abs(velocity_x) < 0.05 and abs(velocity_y) < 0.05:
            if self.is_moving:
                time.sleep(0.05)
                self.stop_pwm()
            return

        # Activar modo movimiento
        self.is_moving = True

        # Factor de velocidad optimizado
        BASE_SPEED = 22

        def apply_curve(value):
            sign = 1 if value > 0 else -1
            return sign * (abs(value) ** 1.2) * BASE_SPEED

        # Calcular incrementos
        delta_x = apply_curve(velocity_x)
        delta_y = apply_curve(-velocity_y)

        # Aplicar incrementos SIN LÍMITES
        new_horizontal = self.horizontal_pos + delta_x
        new_vertical = self.vertical_pos + delta_y

        # Interpolación suave
        SMOOTH_FACTOR = 0.75

        self.horizontal_pos = self.horizontal_pos * (1 - SMOOTH_FACTOR) + new_horizontal * SMOOTH_FACTOR
        self.vertical_pos = self.vertical_pos * (1 - SMOOTH_FACTOR) + new_vertical * SMOOTH_FACTOR

        # Aplicar nueva posición
        MIN_MOVEMENT = 2

        new_h = int(self.horizontal_pos)
        new_v = int(self.vertical_pos)

        if not hasattr(self, '_last_h_sent'):
            self._last_h_sent = new_h
            self._last_v_sent = new_v

        if abs(new_h - self._last_h_sent) >= MIN_MOVEMENT:
            self.pwm.setServoPulse(self.SERVO_HORIZONTAL, new_h)
            self._last_h_sent = new_h

        if abs(new_v - self._last_v_sent) >= MIN_MOVEMENT:
            self.pwm.setServoPulse(self.SERVO_VERTICAL, new_v)
            self._last_v_sent = new_v

    def cleanup(self):
        """Limpieza al salir: NO centrar, solo apagar PWM."""
        print("🧹 Limpiando controlador de cámara...")
        self.stop_pwm()


# =============================================================================
# CÓDIGO DE PRUEBA
# =============================================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🧪 MODO DE PRUEBA - CONTROLADOR DE CÁMARA")
    print("=" * 60)

    camera = CameraController(debug=True)

    try:
        print("\n➡️  Test: Movimiento horizontal")
        for i in range(-10, 11, 2):
            velocity_x = i / 10.0
            print(f"   Velocidad X: {velocity_x:+.1f}")
            for _ in range(5):
                camera.move_incremental(velocity_x, 0)
                time.sleep(0.1)

        print("\n⬆️  Test: Movimiento vertical")
        time.sleep(1)
        for i in range(-10, 11, 2):
            velocity_y = i / 10.0
            print(f"   Velocidad Y: {velocity_y:+.1f}")
            for _ in range(5):
                camera.move_incremental(0, velocity_y)
                time.sleep(0.1)

        print("\n✅ Pruebas completadas")

    except KeyboardInterrupt:
        print("\n⛔ Prueba interrumpida por usuario")
    finally:
        camera.cleanup()
        print("👋 Limpieza completada")
