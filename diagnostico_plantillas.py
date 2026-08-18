#!/usr/bin/env python3
"""Diagnóstico (SOLO LECTURA) de las imágenes base de plantilla por escuela.

Detecta las escuelas afectadas por el bug de sobrescritura: aquellas cuya imagen
base (`Plantilla.recursos['fondo_frente'/'fondo_vuelta']`) NO vive dentro de su
carpeta aislada `plantilla_base/cliente_<id>/`, o que comparten el mismo nombre
de archivo con otra escuela. Esas son las que hay que REASIGNAR una vez en el
editor tras instalar el build corregido.

NO modifica la base de datos ni ningún archivo.

Uso:
    python diagnostico_plantillas.py [ruta_a_credencializacion.db]

Si no se indica la ruta, se prueban ubicaciones comunes (incluida la carpeta de
datos del usuario en la app compilada).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict


def _find_db(arg: str | None) -> str | None:
    """Localiza el archivo de base de datos a inspeccionar."""
    if arg:
        return arg if os.path.exists(arg) else None
    candidatos = [
        os.path.join("data", "credencializacion.db"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                     "credencializacion.db"),
    ]
    # App compilada (Windows / macOS): carpeta de datos del usuario.
    home = os.path.expanduser("~")
    candidatos += [
        os.path.join(home, "AppData", "Roaming", "Credencializacion", "data",
                     "credencializacion.db"),
        os.path.join(home, "AppData", "Local", "Credencializacion", "data",
                     "credencializacion.db"),
        os.path.join(home, "Library", "Application Support",
                     "Credencializacion", "data", "credencializacion.db"),
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return None


def _split_path(pathstr: str) -> tuple[str, str]:
    """Devuelve (nombre_carpeta_padre, nombre_archivo) tolerando \\ y /.

    Los paths guardados pueden venir de Windows (con ``\\``) aunque se analicen
    en otro SO, así que se normalizan ambos separadores.
    """
    norm = pathstr.replace("\\", "/")
    partes = [p for p in norm.split("/") if p]
    if not partes:
        return "", ""
    base = partes[-1]
    padre = partes[-2] if len(partes) >= 2 else ""
    return padre, base


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    db = _find_db(arg)
    if not db:
        print("No se encontró la base de datos. Indica la ruta:")
        print("    python diagnostico_plantillas.py C:\\ruta\\a\\credencializacion.db")
        return 2

    print(f"Base de datos: {db}\n")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    clientes = {r["id"]: (r["nombre"] or f"Cliente #{r['id']}")
                for r in con.execute("SELECT id, nombre FROM clientes")}

    # Recolecta cada fondo con su contexto.
    entradas: list[dict] = []
    # Dueños por RUTA COMPLETA (mismo archivo físico): dos carpetas distintas
    # con el mismo nombre de archivo NO colisionan; solo el mismo path sí.
    path_owners: dict[str, set[int]] = defaultdict(set)

    for r in con.execute("SELECT id, cliente_id, nombre, recursos FROM plantillas"):
        recursos = json.loads(r["recursos"] or "{}")
        for key in ("fondo_frente", "fondo_vuelta"):
            path = recursos.get(key)
            if not path:
                continue
            padre, base = _split_path(path)
            aislada = padre.lower() == f"cliente_{r['cliente_id']}"
            norm = path.replace("\\", "/").lower()
            path_owners[norm].add(r["cliente_id"])
            entradas.append({
                "cliente_id": r["cliente_id"],
                "escuela": clientes.get(r["cliente_id"], f"Cliente #{r['cliente_id']}"),
                "plantilla": r["nombre"],
                "lado": "frente" if key == "fondo_frente" else "vuelta",
                "path": path,
                "norm": norm,
                "aislada": aislada,
                "existe": os.path.exists(path),
                "basename": base,
            })
    con.close()

    if not entradas:
        print("No hay plantillas con imagen base configurada.")
        return 0

    # Marca colisiones REALES: el MISMO archivo físico referido por >1 escuela.
    for e in entradas:
        e["compartida"] = len(path_owners[e["norm"]]) > 1
        e["otras_escuelas"] = sorted(path_owners[e["norm"]] - {e["cliente_id"]})

    afectadas = [e for e in entradas if (not e["aislada"]) or e["compartida"]]
    ok = [e for e in entradas if e not in afectadas]

    print("=" * 72)
    print(f"RESUMEN: {len(entradas)} imágenes base | "
          f"{len(ok)} correctas | {len(afectadas)} a revisar")
    print("=" * 72)

    if afectadas:
        print("\n⚠  ESCUELAS A REASIGNAR (reabre el editor, vuelve a asignar la "
              "imagen base y guarda):\n")
        # Agrupa por escuela.
        por_escuela: dict[str, list[dict]] = defaultdict(list)
        for e in afectadas:
            por_escuela[e["escuela"]].append(e)
        for escuela in sorted(por_escuela):
            print(f"  • {escuela}")
            for e in por_escuela[escuela]:
                motivos = []
                if not e["aislada"]:
                    motivos.append("fuera de su carpeta cliente_%d" % e["cliente_id"])
                if e["compartida"]:
                    motivos.append("MISMO archivo compartido con cliente(s) %s"
                                   % e["otras_escuelas"])
                if not e["existe"]:
                    motivos.append("archivo no existe en disco")
                print(f"      - {e['lado']:6s} [{e['plantilla']}]: {'; '.join(motivos)}")
                print(f"               ruta actual: {e['path']}")
        print()

    if ok:
        print(f"\n✓  Correctas (aisladas por escuela, sin colisión): {len(ok)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
