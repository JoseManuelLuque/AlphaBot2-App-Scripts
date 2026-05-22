# AlphaBot2 - Scripts de Hardware (Raspberry Pi)

Este repositorio contiene los scripts en Python que se ejecutan directamente en la Raspberry Pi del robot AlphaBot2. Su función es levantar servidores de escucha y procesar las peticiones de red para accionar los motores, servos, LEDs y sensores físicos mediante los pines GPIO.

**Repositorio principal (App Android de Control):** [Repositorio Principal](https://github.com/JoseManuelLuque/AlphaBot2_App)

## Arquitectura de Comunicación

La comunicación entre la aplicación móvil y el robot se realiza a través de sockets TCP y conexiones SSH. Los scripts de este repositorio se dividen según el hardware que controlan y los puertos asignados:

* **Movimiento y Cámara (Puerto TCP 5555):** Recibe coordenadas cartesianas (`MOVE x y`, `CAMERA x y`) para calcular el PWM de los motores DC (L298N) y la posición de los servomotores.
* **Iluminación LED (Puerto TCP 5556):** Controla las tiras LED RGB direccionables. Recibe comandos de color y efectos (`EFFECT Respiración`, `QUIT`).
* **Módulo Siguelíneas (Puerto TCP 5003):** Gestiona la calibración y lectura de los sensores infrarrojos inferiores. *(Nota: Módulo actualmente en desarrollo/inactivo en el sistema principal).*
* **Zumbador (Puerto SSH 22):** Scripts de audio independientes que se ejecutan remotamente bajo demanda para generar frecuencias piezoeléctricas.

## Dependencias

Para que los scripts funcionen correctamente en el entorno de la Raspberry Pi, se requieren las siguientes librerías:

```bash
sudo apt-get update
sudo apt-get install python3-pip
pip3 install RPi.GPIO
pip3 install rpi_ws281x
