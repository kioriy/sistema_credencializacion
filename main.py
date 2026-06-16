"""Punto de entrada raíz del proyecto.
Redirige al main real del paquete credencializacion.
"""
import sys
import os

# Asegurar que src/ está en el path cuando se ejecuta desde la raíz
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from credencializacion.main import main

if __name__ == "__main__":
    main()
