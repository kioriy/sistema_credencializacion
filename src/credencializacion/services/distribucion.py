"""
Distribución de varios elementos del diseño entre sí.

Se trabaja sobre la caja que cada elemento ocupa **ya girado** —la que se ve—,
igual que el tope contra el borde de la tarjeta: de otro modo, un texto puesto
de pie se repartiría como si siguiera acostado.

Dos maneras de repartir, las dos dejan quietos a los extremos y mueven solo lo
de en medio (quien distribuye ya colocó el primero y el último donde los
quería):

- **Centros equidistantes**: deja los elementos en fila (o en columna), con
  la misma distancia entre centros y alineados entre sí por el centro del
  conjunto. Es la que ordena una escalera. Si al repartirlos se encimarían
  —porque arrancaban muy juntos— la fila se abre lo justo para que no se
  toquen, sin pasarse del borde de la tarjeta: una fila encimada no es lo
  que nadie busca al pulsar «distribuir».
- **Espaciado igual**: el mismo hueco entre una caja y la siguiente, sin
  tocar el otro eje. Sirve para emparejar el aire entre elementos que ya
  están donde deben.

Bastan **dos** elementos: con dos, los centros equidistantes los dejan en
fila (o en columna) uno junto al otro, que es justo lo que se busca al
emparejar dos textos. El espaciado igual sí necesita tres, porque con dos no
hay nada en medio que mover: el hueco entre ellos es el que es.

Todo aquí es puro (sin Qt ni base de datos): recibe cajas y devuelve
posiciones.
"""
from __future__ import annotations

from typing import Iterable, Sequence

# Modos admitidos por `distribuir`.
HORIZONTAL_CENTROS = "horizontal_centros"
VERTICAL_CENTROS = "vertical_centros"
HORIZONTAL_ESPACIO = "horizontal_espacio"
VERTICAL_ESPACIO = "vertical_espacio"

MODOS: tuple[str, ...] = (
    HORIZONTAL_CENTROS, VERTICAL_CENTROS,
    HORIZONTAL_ESPACIO, VERTICAL_ESPACIO,
)

# Con uno solo no hay nada que repartir: hacen falta al menos dos.
MINIMO_ELEMENTOS = 2

# Caja: (x, y, ancho, alto).
Caja = tuple[float, float, float, float]


def distribuir(
    cajas: Sequence[Caja],
    modo: str,
    limite: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    """Reparte las cajas y devuelve la posición nueva de cada una.

    Args:
        cajas: Cajas visuales ``(x, y, ancho, alto)``.
        modo: Uno de :data:`MODOS`.
        limite: ``(ancho, alto)`` de la tarjeta. Solo se usa en los modos de
            centros, para que la fila no se abra más allá del borde.

    Returns:
        Lista de ``(x, y)`` **en el mismo orden que entraron**, para poder
        devolver cada posición a su elemento. Si hay menos de dos cajas o el
        modo no existe, devuelve las posiciones tal cual; con dos cajas el
        espaciado igual tampoco las mueve (no hay hueco intermedio que
        repartir).
    """
    if modo not in MODOS or len(cajas) < MINIMO_ELEMENTOS:
        return [(c[0], c[1]) for c in cajas]

    horizontal = modo in (HORIZONTAL_CENTROS, HORIZONTAL_ESPACIO)
    # Índice del eje sobre el que se reparte: 0 = x/ancho, 1 = y/alto.
    pos_i, tam_i = (0, 2) if horizontal else (1, 3)

    # Se ordena por el centro actual: el orden visual es el que importa, no
    # el orden en que se fueron seleccionando.
    orden = sorted(
        range(len(cajas)),
        key=lambda i: cajas[i][pos_i] + cajas[i][tam_i] / 2.0,
    )

    nuevas = [[c[0], c[1]] for c in cajas]
    if modo in (HORIZONTAL_CENTROS, VERTICAL_CENTROS):
        tope = None
        if limite is not None:
            tope = limite[0] if horizontal else limite[1]
        posiciones = _centros_equidistantes(cajas, orden, pos_i, tam_i, tope)
        # Además se alinean en el otro eje, por el centro del conjunto: es lo
        # que convierte una escalera en una fila (o una columna) ordenada.
        otro_pos, otro_tam = (1, 3) if pos_i == 0 else (0, 2)
        centro_comun = _centro_del_conjunto(cajas, otro_pos, otro_tam)
        for idx, caja in enumerate(cajas):
            nuevas[idx][otro_pos] = centro_comun - caja[otro_tam] / 2.0
    else:
        posiciones = _espaciado_igual(cajas, orden, pos_i, tam_i)

    for idx, valor in posiciones.items():
        nuevas[idx][pos_i] = valor

    return [(x, y) for x, y in nuevas]


def _centro_del_conjunto(
    cajas: Sequence[Caja], pos_i: int, tam_i: int,
) -> float:
    """Centro del bloque que forman todas las cajas en un eje.

    Se usa el bloque completo —del borde más alto al más bajo— y no el
    promedio de los centros: así el conjunto no se recorre hacia donde haya
    más elementos juntos.
    """
    inicio = min(c[pos_i] for c in cajas)
    fin = max(c[pos_i] + c[tam_i] for c in cajas)
    return (inicio + fin) / 2.0


def _centros_equidistantes(
    cajas: Sequence[Caja],
    orden: Iterable[int],
    pos_i: int,
    tam_i: int,
    tope: float | None = None,
) -> dict[int, float]:
    """Posiciones con los centros a la misma distancia.

    El paso sale de dónde estaban los extremos, pero se abre si con él los
    elementos se encimarían, y se cierra si la fila no cabría en la tarjeta.
    Al cambiar el paso el conjunto se mantiene centrado donde estaba.
    """
    orden = list(orden)
    n = len(orden)
    primero, ultimo = cajas[orden[0]], cajas[orden[-1]]
    centro_ini = primero[pos_i] + primero[tam_i] / 2.0
    centro_fin = ultimo[pos_i] + ultimo[tam_i] / 2.0
    paso = (centro_fin - centro_ini) / (n - 1)

    # Lo mínimo para que dos vecinos no se toquen: la mitad de cada uno.
    paso_sin_encimar = max(
        (cajas[orden[i]][tam_i] + cajas[orden[i + 1]][tam_i]) / 2.0
        for i in range(n - 1)
    )
    paso = max(paso, paso_sin_encimar)

    if tope is not None:
        # Lo más que puede abrirse sin que los extremos salgan de la tarjeta.
        margen = (primero[tam_i] + ultimo[tam_i]) / 2.0
        paso_maximo = (tope - margen) / (n - 1)
        if paso_maximo > 0:
            paso = min(paso, paso_maximo)

    # El bloque se queda donde estaba: se reparte alrededor de su centro.
    centro_medio = (centro_ini + centro_fin) / 2.0
    centros = [centro_medio + (i - (n - 1) / 2.0) * paso for i in range(n)]

    if tope is not None:
        inicio = centros[0] - primero[tam_i] / 2.0
        fin = centros[-1] + ultimo[tam_i] / 2.0
        if inicio < 0:
            centros = [c - inicio for c in centros]
        elif fin > tope:
            centros = [c - (fin - tope) for c in centros]

    return {
        idx: centros[i] - cajas[idx][tam_i] / 2.0
        for i, idx in enumerate(orden)
    }


def _espaciado_igual(
    cajas: Sequence[Caja], orden: Iterable[int], pos_i: int, tam_i: int,
) -> dict[int, float]:
    """Posiciones con el mismo hueco entre una caja y la siguiente.

    El hueco puede salir negativo si los elementos no caben entre los
    extremos: ahí se encima lo mismo entre todos, que es más fácil de
    entender (y de corregir) que amontonarlos al principio.
    """
    orden = list(orden)
    primero, ultimo = cajas[orden[0]], cajas[orden[-1]]
    inicio = primero[pos_i]
    fin = ultimo[pos_i] + ultimo[tam_i]
    ocupado = sum(cajas[i][tam_i] for i in orden)
    hueco = (fin - inicio - ocupado) / (len(orden) - 1)

    posiciones: dict[int, float] = {}
    cursor = inicio
    for idx in orden:
        posiciones[idx] = cursor
        cursor += cajas[idx][tam_i] + hueco
    return posiciones
