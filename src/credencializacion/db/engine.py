"""
Configuración del motor SQLAlchemy y gestión de sesiones.
Base de datos SQLite local con soporte para JSON columns.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from credencializacion.utils.paths import get_db_path


# Engine SQLite con WAL mode para mejor concurrencia
_engine = None
_SessionLocal = None


def get_engine():
    """Obtiene o crea el engine de SQLAlchemy (singleton)."""
    global _engine
    if _engine is None:
        db_path = get_db_path()
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        # Habilitar WAL mode y foreign keys en SQLite
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Obtiene el factory de sesiones (singleton)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


def get_session() -> Session:
    """Crea una nueva sesión de base de datos."""
    factory = get_session_factory()
    return factory()


class DatabaseSession:
    """Context manager para transacciones seguras.
    
    Uso:
        with DatabaseSession() as session:
            session.add(registro)
            # commit automático al salir
    """

    def __init__(self):
        self.session: Session | None = None

    def __enter__(self) -> Session:
        self.session = get_session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session is None:
            return
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
