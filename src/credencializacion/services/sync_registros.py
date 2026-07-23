"""
Depuración compartida de registros locales tras una sincronización externa.

Usada por cualquier flujo de sincronización (API miescuela.net, Google
Sheets, …) que descargue el padrón completo de un cliente y necesite
garantizar fidelidad: todo registro local que ya no aparezca en la fuente
se considera borrado en origen y se elimina localmente.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def purge_stale_records(
    session, cliente_id: int, raw_records: list[dict]
) -> tuple[int, list[str]]:
    """Elimina los registros locales que ya no existen en la fuente externa.

    Compara los ``enrollment_code`` de los registros descargados contra los
    registros locales del cliente y borra los huérfanos. Los ítems de colas
    de impresión que los referencien se eliminan en cascada (FK
    ``ON DELETE CASCADE``); las colas afectadas ajustan su
    ``total_registros`` y se devuelven para notificar al usuario.

    Si ``raw_records`` no aporta ninguna matrícula utilizable (por ejemplo,
    una respuesta vacía o transitoriamente incompleta), no se depura nada:
    es preferible no borrar ante la duda que vaciar la base local por un
    fallo pasajero de la fuente.

    Returns:
        (número de registros depurados, nombres de colas afectadas)
    """
    from credencializacion.db.models import ColaImpresion, ItemCola, Registro

    api_enrollments = {
        rec.get("enrollment_code") or rec.get("matricula", "")
        for rec in raw_records
        if isinstance(rec, dict)
    }
    api_enrollments.discard("")
    if not api_enrollments:
        return 0, []

    stale = (
        session.query(Registro)
        .filter(
            Registro.cliente_id == cliente_id,
            Registro.enrollment_code.isnot(None),
            Registro.enrollment_code.notin_(api_enrollments),
        )
        .all()
    )
    if not stale:
        return 0, []

    stale_ids = [r.id for r in stale]

    # Colas que referencian registros a depurar (antes de borrarlos)
    colas_tocadas = (
        session.query(ColaImpresion)
        .join(ItemCola, ItemCola.cola_id == ColaImpresion.id)
        .filter(ItemCola.registro_id.in_(stale_ids))
        .distinct()
        .all()
    )

    for reg in stale:
        session.delete(reg)
    session.flush()

    # Ajustar el conteo de las colas tras la cascada de sus ítems
    nombres_colas: list[str] = []
    for cola in colas_tocadas:
        cola.total_registros = (
            session.query(ItemCola).filter_by(cola_id=cola.id).count()
        )
        nombres_colas.append(cola.nombre)

    return len(stale_ids), nombres_colas
