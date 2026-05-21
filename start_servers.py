#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SCRIPT DE INICIO PARA SERVIDORES ALPHABOT2
=============================================================================
Este script coordina el inicio de todos los servidores necesarios para
el funcionamiento del robot AlphaBot2:
1. Servidor de streaming de cámara (puerto 8080)
2. Servidor de control de motores/cámara (puerto 5555)

Automatiza el proceso de:
- Verificar disponibilidad de hardware (cámara)
- Detener servidores previos
- Iniciar servidores en el orden correcto
- Mostrar información de conexión

USO:
    python3 start_servers.py

LOGS:
    /tmp/camera_stream.log  - Log del servidor de streaming
    /tmp/joystick_server.log - Log del servidor de control

=============================================================================
"""

import subprocess
import time
import sys
import os

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def kill_existing_servers():
    """
    Detiene cualquier instancia previa de los servidores.

    Busca procesos Python que estén ejecutando los scripts de servidor
    y los termina. Esto evita conflictos de puertos y procesos zombies.

    Procesos que se detienen:
    - joystick_server.py (puerto 5555)
    - camera_stream.py (puerto 8080)

    Usa SIGTERM (señal 15) para permitir limpieza ordenada.
    """
    print("=" * 60)
    print("🔄 DETENIENDO SERVIDORES ANTERIORES")
    print("=" * 60)

    # Matar servidores usando pkill (busca por nombre de proceso)
    # -f: Buscar en toda la línea de comandos, no solo el nombre del proceso
    # stderr=DEVNULL: Silenciar error si no hay procesos para matar
    # NOTA: NO matamos start_servers.py porque ese es el proceso actual
    # Usar sudo porque los procesos fueron iniciados con sudo
    subprocess.run(["sudo", "pkill", "-f", "joystick_server.py"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-f", "camera_stream.py"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-f", "ultrasonic_sensors.py"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-f", "line_follow_server.py"], stderr=subprocess.DEVNULL)

    # Esperar a que los procesos terminen limpiamente
    time.sleep(1)
    print("✅ Servidores anteriores detenidos\n")

def check_camera():
    """
    Verifica que la Raspberry Pi Camera esté conectada y habilitada.

    Usa el comando 'vcgencmd get_camera' que devuelve información sobre
    el estado de la cámara en la Raspberry Pi.

    Returns:
        bool: True si la cámara está detectada y funcional, False si no

    Salida típica de vcgencmd:
        "supported=1 detected=1" → Cámara OK
        "supported=1 detected=0" → Cámara no conectada o deshabilitada
    """
    print("=" * 60)
    print("📷 VERIFICANDO HARDWARE DE CÁMARA")
    print("=" * 60)

    try:
        # Ejecutar comando vcgencmd para verificar cámara
        result = subprocess.run(
            ["vcgencmd", "get_camera"],
            capture_output=True,    # Capturar stdout y stderr
            text=True,              # Decodificar output como texto
            timeout=5               # Timeout de 5 segundos
        )

        output = result.stdout.strip()
        print(f"🔍 Respuesta del sistema: {output}")

        # Verificar que la cámara esté detectada
        if "detected=1" in output:
            print("✅ Cámara detectada y lista")
            return True
        else:
            print("❌ Cámara no detectada")
            print("\n💡 SOLUCIÓN:")
            print("   1. Verifica que el cable esté conectado al puerto CSI")
            print("   2. Habilita la cámara en raspi-config:")
            print("      sudo raspi-config")
            print("      → Interface Options → Camera → Enable")
            print("   3. Reinicia la Raspberry Pi")
            return False

    except subprocess.TimeoutExpired:
        print("⚠️  Timeout al verificar la cámara")
        return False
    except FileNotFoundError:
        print("⚠️  Comando vcgencmd no encontrado (¿no es una Raspberry Pi?)")
        return False
    except Exception as e:
        print(f"⚠️  Error al verificar cámara: {e}")
        return False
    finally:
        print()

def start_camera_stream():
    """
    Inicia el servidor de streaming de cámara en segundo plano.

    El servidor se ejecuta en un proceso separado y su salida se redirige
    a un archivo de log para no contaminar la consola principal.

    Returns:
        bool: True si el servidor se inició correctamente, False si hubo error

    Archivo de log: /tmp/camera_stream.log
    """
    print("=" * 60)
    print("🎥 INICIANDO SERVIDOR DE STREAMING")
    print("=" * 60)

    # Obtener ruta absoluta del script de cámara
    script_dir = os.path.dirname(os.path.abspath(__file__))
    camera_script = os.path.join(script_dir, "camera_stream.py")

    print(f"📂 Script: {camera_script}")
    print(f"📝 Log: /tmp/camera_stream.log")

    try:
        # Iniciar proceso en segundo plano
        # Popen: Inicia proceso sin esperar a que termine
        # stdout/stderr redirigidos a archivo de log
        process = subprocess.Popen(
            ["python3", camera_script],
            stdout=open("/tmp/camera_stream.log", "w"),
            stderr=subprocess.STDOUT  # Redirigir stderr a stdout
        )

        # Esperar un momento para ver si el proceso arranca correctamente
        time.sleep(3)

        # Verificar que el proceso sigue corriendo
        # poll() devuelve None si el proceso está vivo
        if process.poll() is None:
            print(f"✅ Servidor de streaming iniciado (PID: {process.pid})")
            print("🌐 Puerto: 8080")
            return True
        else:
            print("❌ El servidor de streaming se cerró inesperadamente")
            print("💡 Ver detalles en: /tmp/camera_stream.log")
            return False

    except Exception as e:
        print(f"❌ Error al iniciar servidor de streaming: {e}")
        return False
    finally:
        print()

def start_control_server():
    """
    Inicia el servidor de control de motores y cámara en segundo plano.

    Este es el servidor principal que recibe comandos de la app Android
    para controlar el movimiento del robot y la orientación de la cámara.

    Returns:
        bool: True si el servidor se inició correctamente, False si hubo error

    Archivo de log: /tmp/joystick_server.log
    """
    print("=" * 60)
    print("🎮 INICIANDO SERVIDOR DE CONTROL")
    print("=" * 60)

    # Obtener ruta absoluta del script de control
    script_dir = os.path.dirname(os.path.abspath(__file__))
    control_script = os.path.join(script_dir, "joystick_server.py")

    print(f"📂 Script: {control_script}")
    print(f"📝 Log: /tmp/joystick_server.log")

    try:
        # Iniciar proceso en segundo plano con sudo (necesario para GPIO)
        process = subprocess.Popen(
            ["sudo", "python3", control_script],
            stdout=open("/tmp/joystick_server.log", "w"),
            stderr=subprocess.STDOUT
        )

        # Esperar un momento para verificar inicio
        time.sleep(2)

        # Verificar que el proceso sigue corriendo
        if process.poll() is None:
            print(f"✅ Servidor de control iniciado (PID: {process.pid})")
            print("🌐 Puerto: 5555")
            return True
        else:
            print("❌ El servidor de control se cerró inesperadamente")
            print("💡 Ver detalles en: /tmp/joystick_server.log")
            return False

    except Exception as e:
        print(f"❌ Error al iniciar servidor de control: {e}")
        return False
    finally:
        print()

def start_line_follow_server():
    """
    Inicia el servidor de seguimiento de línea en segundo plano.

    Este servidor maneja el algoritmo PID para seguir líneas negras
    usando los sensores infrarrojos del robot.

    Returns:
        bool: True si el servidor se inició correctamente, False si hubo error

    Archivo de log: /tmp/line_follow_server.log
    """
    print("=" * 60)
    print("📏 INICIANDO SERVIDOR DE SEGUIMIENTO DE LÍNEA")
    print("=" * 60)

    # Obtener ruta absoluta del script de seguimiento de línea
    script_dir = os.path.dirname(os.path.abspath(__file__))
    line_follow_script = os.path.join(script_dir, "line_follow_server.py")

    print(f"📂 Script: {line_follow_script}")
    print(f"📝 Log: /tmp/line_follow_server.log")

    try:
        # Iniciar proceso en segundo plano con sudo (necesario para GPIO)
        process = subprocess.Popen(
            ["sudo", "python3", line_follow_script],
            stdout=open("/tmp/line_follow_server.log", "w"),
            stderr=subprocess.STDOUT
        )

        # Esperar un momento para verificar inicio
        time.sleep(2)

        # Verificar que el proceso sigue corriendo
        if process.poll() is None:
            print(f"✅ Servidor de seguimiento iniciado (PID: {process.pid})")
            print("🌐 Puerto: 5003")
            return True
        else:
            print("❌ El servidor de seguimiento se cerró inesperadamente")
            print("💡 Ver detalles en: /tmp/line_follow_server.log")
            return False

    except Exception as e:
        print(f"❌ Error al iniciar servidor de seguimiento: {e}")
        return False
    finally:
        print()

def get_ip_address():
    """
    Obtiene la dirección IP de la Raspberry Pi en la red local.

    Usa el comando 'hostname -I' que lista todas las IPs asignadas.
    Normalmente la primera IP es la de la interfaz WiFi/Ethernet principal.

    Returns:
        str: Dirección IP principal, o "<IP>" si no se pudo determinar
    """
    try:
        # hostname -I: Lista todas las IPs asignadas
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2
        )

        # Tomar la primera IP de la lista
        ip_addresses = result.stdout.strip().split()
        if ip_addresses:
            return ip_addresses[0]
        else:
            return "<IP>"

    except Exception:
        return "<IP>"

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """
    Función principal que coordina el inicio de todos los servidores.

    Flujo de ejecución:
    1. Mostrar banner
    2. Detener servidores anteriores
    3. Verificar hardware de cámara
    4. Iniciar servidor de streaming (si hay cámara)
    5. Iniciar servidor de control
    6. Mostrar resumen y URLs de acceso
    7. Salir (los servidores quedan corriendo en segundo plano)
    """
    print("\n" + "=" * 60)
    print(" " * 15 + "ALPHABOT2 - INICIO DE SISTEMA")
    print("=" * 60)
    print("🤖 Robot: AlphaBot2")
    print("📱 App: Android Control")
    print("👤 Autor: José Manuel Luque González")
    print("=" * 60 + "\n")

    # ===== PASO 1: DETENER SERVIDORES ANTERIORES =====
    kill_existing_servers()

    # ===== PASO 2: VERIFICAR HARDWARE DE CÁMARA =====
    camera_ok = check_camera()

    # ===== PASO 3: INICIAR SERVIDOR DE STREAMING =====
    # INTENTAR SIEMPRE iniciar el servidor, aunque la detección falle
    # A veces vcgencmd da falsos negativos pero la cámara funciona
    streaming_ok = False
    if camera_ok:
        print("✅ Cámara detectada, iniciando servidor...\n")
        streaming_ok = start_camera_stream()
    else:
        print("⚠️  Cámara no detectada por vcgencmd, pero intentando de todos modos...")
        print("    (A veces funciona aunque no se detecte correctamente)\n")
        streaming_ok = start_camera_stream()

    # ===== PASO 4: INICIAR SERVIDOR DE CONTROL =====
    control_ok = start_control_server()

    # ===== PASO 5: INICIAR SERVIDOR DE SEGUIMIENTO DE LÍNEA =====
    line_follow_ok = start_line_follow_server()

    # ===== PASO 6: OBTENER IP DE LA RASPBERRY PI =====
    ip_address = get_ip_address()

    # ===== PASO 7: MOSTRAR RESUMEN =====
    print("=" * 60)
    print(" " * 20 + "RESUMEN DE INICIO")
    print("=" * 60)

    # Estado de cada servidor
    print("\n📊 ESTADO DE SERVICIOS:")
    print(f"   Streaming de cámara:  {'✅ ACTIVO' if streaming_ok else '❌ INACTIVO'}")
    print(f"   Servidor de control:  {'✅ ACTIVO' if control_ok else '❌ INACTIVO'}")
    print(f"   Seguimiento de línea: {'✅ ACTIVO' if line_follow_ok else '❌ INACTIVO'}")

    # URLs de acceso
    print("\n🌐 INFORMACIÓN DE CONEXIÓN:")
    print(f"   IP de la Raspberry Pi: {ip_address}")

    if streaming_ok:
        print(f"\n   📹 URL del stream de video:")
        print(f"      http://{ip_address}:8080/stream.mjpg")

    if control_ok:
        print(f"\n   🎮 Servidor de control:")
        print(f"      Host: {ip_address}")
        print(f"      Puerto: 5555")

    if line_follow_ok:
        print(f"\n   📏 Servidor de seguimiento:")
        print(f"      Host: {ip_address}")
        print(f"      Puerto: 5003")

    # Logs
    print("\n📝 ARCHIVOS DE LOG:")
    print("   Streaming:  /tmp/camera_stream.log")
    print("   Control:    /tmp/joystick_server.log")
    print("   Línea:      /tmp/line_follow_server.log")

    # Comandos útiles
    print("\n🔧 COMANDOS ÚTILES:")
    print("   Ver log streaming:  tail -f /tmp/camera_stream.log")
    print("   Ver log control:    tail -f /tmp/joystick_server.log")
    print("   Ver log línea:      tail -f /tmp/line_follow_server.log")
    print("   Detener servidores: pkill -f 'joystick_server\\|camera_stream\\|line_follow_server'")

    print("\n" + "=" * 60)

    # ===== PASO 8: VERIFICAR ERRORES CRÍTICOS =====
    if not control_ok:
        print("\n❌ ERROR CRÍTICO: El servidor de control no se inició")
        print("💡 El robot no podrá ser controlado")
        print("🔍 Revisa el log en: /tmp/joystick_server.log")
        print("=" * 60)
        sys.exit(1)

    print("\n✅ SISTEMA LISTO - Los servidores están corriendo en segundo plano")
    print("🚀 Abre la app Android para controlar el robot")
    print("=" * 60 + "\n")

# ===========================
# PUNTO DE ENTRADA DEL SCRIPT
# ===========================

if __name__ == "__main__":
    """
    Ejecuta el script de inicio cuando se llama directamente.
    
    Maneja interrupciones y errores para salir limpiamente.
    """
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⛔ INICIO CANCELADO POR USUARIO")
        print("🔄 Deteniendo servidores iniciados...")
        subprocess.run(["pkill", "-f", "joystick_server.py"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "camera_stream.py"], stderr=subprocess.DEVNULL)
        print("✅ Limpieza completada")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n💥 ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
