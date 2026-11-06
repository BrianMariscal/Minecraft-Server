"""Respaldos reales en disco: la base del bot de pagos entra y sale sana.

Lo delicado es SQLite en modo WAL: lo último escrito puede vivir en el
archivo -wal. Copiar a lo bruto con el bot escribiendo, o restaurar dejando
un -wal viejo junto a la base, deja una base que no abre.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path

import pytest

from mc_admin.cli import respaldos as cli
from mc_admin.contexto import Contexto
from mc_admin.infra import rcon, sqlite


def _base_en_wal(ruta: Path, filas: int = 3) -> sqlite3.Connection:
    """Una base en WAL con datos que todavía NO pasaron al archivo principal."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(ruta, isolation_level=None)
    cx.execute("PRAGMA journal_mode = WAL")
    # Que no haga checkpoint solo: queremos los datos en el -wal.
    cx.execute("PRAGMA wal_autocheckpoint = 0")
    cx.execute("CREATE TABLE pagos (quien TEXT)")
    for i in range(filas):
        cx.execute("INSERT INTO pagos VALUES (?)", (f"persona{i}",))
    return cx


def _cuantas_filas(ruta: Path) -> int:
    with closing(sqlite3.connect(ruta)) as cx:
        return int(cx.execute("SELECT count(*) FROM pagos").fetchone()[0])


class TestSqlite:
    def test_la_copia_trae_lo_que_estaba_en_el_wal(self, tmp_path: Path) -> None:
        origen = tmp_path / "pagos.sqlite"
        cx = _base_en_wal(origen)
        try:
            assert Path(f"{origen}-wal").stat().st_size > 0
            copia = tmp_path / "copia.sqlite"
            sqlite.copia_consistente(origen, copia)
        finally:
            cx.close()
        assert _cuantas_filas(copia) == 3
        assert sqlite.esta_sana(copia)

    def test_basura_no_esta_sana(self, tmp_path: Path) -> None:
        basura = tmp_path / "pagos.sqlite"
        basura.write_bytes(b"esto no es una base de datos" * 100)
        assert not sqlite.esta_sana(basura)
        assert not sqlite.esta_sana(tmp_path / "no-existe.sqlite")

    def test_borrar_con_wal(self, tmp_path: Path) -> None:
        base = tmp_path / "pagos.sqlite"
        for nombre in ("pagos.sqlite", "pagos.sqlite-wal", "pagos.sqlite-shm", "otro.txt"):
            (tmp_path / nombre).write_text("x")
        sqlite.borrar_con_wal(base)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["otro.txt"]


@pytest.fixture
def ctx(env_lleno: Path, monkeypatch: pytest.MonkeyPatch) -> Contexto:
    # Servidor apagado: no hay RCON con quién hablar.
    monkeypatch.setattr(rcon, "esta_vivo", lambda _c: False)
    (env_lleno / "data" / "world").mkdir(parents=True)
    (env_lleno / "data" / "world" / "level.dat").write_text("mundo")
    (env_lleno / "data" / "pagos-datos").mkdir()  # el punto de montaje vacío
    return Contexto.cargar(env_lleno)


class TestCrearRespaldo:
    def test_la_base_del_bot_entra_consistente(self, ctx: Contexto) -> None:
        cx = _base_en_wal(ctx.raiz / "pagos-datos" / "pagos.sqlite")
        try:
            destino = cli.crear_respaldo(ctx)
        finally:
            cx.close()

        with tarfile.open(destino) as tar:
            nombres = tar.getnames()
            assert "pagos-datos/pagos.sqlite" in nombres
            # Ni -wal ni -shm: la copia es un solo archivo completo.
            assert not [n for n in nombres if n.endswith(("-wal", "-shm"))]
            assert "world/level.dat" in nombres
            assert "settings.yml" in nombres
            datos = tar.extractfile("pagos-datos/pagos.sqlite")
            assert datos is not None
            extraida = ctx.raiz / "extraida.sqlite"
            extraida.write_bytes(datos.read())
        assert _cuantas_filas(extraida) == 3

    def test_el_punto_de_montaje_no_entra(self, ctx: Contexto) -> None:
        """data/pagos-datos es solo donde se monta la base en el contenedor."""
        destino = cli.crear_respaldo(ctx)
        with tarfile.open(destino) as tar:
            # Sin base de pagos en este test: no debe haber nada de pagos-datos.
            assert not [n for n in tar.getnames() if n.startswith("pagos-datos")]


def _tar_de_itzg(ruta: Path, archivos: dict[str, bytes]) -> None:
    """Un tar como los de itzg/mc-backup: todo con "./" adelante."""
    with tarfile.open(ruta, "w:gz") as tar:
        for nombre, contenido in archivos.items():
            info = tarfile.TarInfo(f"./{nombre}")
            info.size = len(contenido)
            tar.addfile(info, io.BytesIO(contenido))


def _bytes_de_una_base(tmp_path: Path, filas: int) -> bytes:
    ruta = tmp_path / f"base-{filas}.sqlite"
    cx = _base_en_wal(ruta, filas)
    cx.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cx.close()
    return ruta.read_bytes()


class TestRestaurarBaseDePagos:
    def test_respaldo_de_itzg_con_punto_diagonal(self, ctx: Contexto, tmp_path: Path) -> None:
        """Antes, el "./" hacía que la base acabara en data/pagos-datos."""
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(tar_ruta, {"pagos-datos/pagos.sqlite": _bytes_de_una_base(tmp_path, 5)})

        with tarfile.open(tar_ruta) as tar:
            cli._restaurar_base_de_pagos(ctx, tar)

        assert _cuantas_filas(ctx.raiz / "pagos-datos" / "pagos.sqlite") == 5

    def test_un_wal_viejo_no_se_le_aplica_encima(self, ctx: Contexto, tmp_path: Path) -> None:
        # Lo del WAL: una base con su -wal lleno.
        actual = ctx.raiz / "pagos-datos" / "pagos.sqlite"
        viejo = _base_en_wal(actual, filas=9)
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(tar_ruta, {"pagos-datos/pagos.sqlite": _bytes_de_una_base(tmp_path, 2)})
        try:
            with tarfile.open(tar_ruta) as tar:
                cli._restaurar_base_de_pagos(ctx, tar)
        finally:
            viejo.close()
        assert _cuantas_filas(actual) == 2
        assert sqlite.esta_sana(actual)

    def test_si_la_base_viene_danada_usa_la_foto(self, ctx: Contexto, tmp_path: Path) -> None:
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "pagos-datos/pagos.sqlite": b"basura" * 1000,
                "pagos-datos/pagos.copia.sqlite": _bytes_de_una_base(tmp_path, 4),
            },
        )
        with tarfile.open(tar_ruta) as tar:
            cli._restaurar_base_de_pagos(ctx, tar)
        assert _cuantas_filas(ctx.raiz / "pagos-datos" / "pagos.sqlite") == 4

    def test_sin_base_en_el_respaldo_no_toca_nada(self, ctx: Contexto, tmp_path: Path) -> None:
        actual = ctx.raiz / "pagos-datos" / "pagos.sqlite"
        _base_en_wal(actual, filas=1).close()
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(tar_ruta, {"world/level.dat": b"x"})
        with tarfile.open(tar_ruta) as tar:
            cli._restaurar_base_de_pagos(ctx, tar)
        assert _cuantas_filas(actual) == 1


def _bytes_de_una_base_con_wal(ruta: Path, filas: int) -> tuple[bytes, bytes]:
    """Bytes de la base y de su -wal, capturados antes de cerrar la conexión."""
    cx = _base_en_wal(ruta, filas)
    try:
        base = ruta.read_bytes()
        wal = Path(f"{ruta}-wal").read_bytes()
    finally:
        cx.close()
    return base, wal


class TestSnapshots:
    def test_una_base_viva_entra_fotografiada(self, ctx: Contexto) -> None:
        base = ctx.raiz / "data" / "plugins" / "CoreProtect" / "database.db"
        cx = _base_en_wal(base, filas=4)
        try:
            destino = cli.crear_respaldo(ctx)
        finally:
            cx.close()

        with tarfile.open(destino) as tar:
            nombres = tar.getnames()
            assert "plugins/CoreProtect/database.db" in nombres
            assert not [n for n in nombres if n.endswith(("-wal", "-shm"))]
            datos = tar.extractfile("plugins/CoreProtect/database.db")
            assert datos is not None
            extraida = ctx.raiz / "coreprotect.db"
            extraida.write_bytes(datos.read())
        assert _cuantas_filas(extraida) == 4
        assert sqlite.esta_sana(extraida)

    def test_guarda_info_y_checksums(self, ctx: Contexto) -> None:
        destino = cli.crear_respaldo(ctx)
        with tarfile.open(destino) as tar:
            datos = tar.extractfile("BACKUP_INFO.json")
            assert datos is not None
            info = json.loads(datos.read())
        assert info["formato"] == 1
        assert info["etiqueta"] == "world"
        assert info["archivos"] >= 1
        assert "settings.yml" not in info["bases_sqlite"]

        sha = destino.with_name(destino.name + ".sha256")
        metadatos = destino.with_name(destino.name + ".json")
        assert sha.is_file()
        assert metadatos.is_file()
        assert cli._sha256(destino) == sha.read_text(encoding="utf-8").split()[0]
        assert cli._problemas_de(destino) == []

    def test_verify_detecta_un_archivo_roto(self, ctx: Contexto, tmp_path: Path) -> None:
        cli.crear_respaldo(ctx)
        roto = tmp_path / "roto.tgz"
        roto.write_bytes(b"esto no es un tar")
        assert cli._problemas_de(roto)

    def test_un_respaldo_viejo_sin_ficha_no_se_reporta_danado(
        self, ctx: Contexto, tmp_path: Path
    ) -> None:
        viejo = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(viejo, {"world/level.dat": b"x"})
        assert cli._problemas_de(viejo) == []

    def test_un_log_de_h2_con_sufijo_db_no_se_confunde_con_sqlite(
        self, ctx: Contexto, tmp_path: Path
    ) -> None:
        """GravesX deja graves.data.trace.db, que es texto y no una base."""
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "world/level.dat": b"x",
                "plugins/GravesX/data/graves.data.trace.db": (
                    b"2026-10-31 01:16:30 database: could not close the database\n"
                ),
            },
        )
        assert cli._problemas_de(tar_ruta) == []

    def test_verify_sigue_detectando_una_base_sqlite_rota(
        self, ctx: Contexto, tmp_path: Path
    ) -> None:
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "world/level.dat": b"x",
                "plugins/CoreProtect/database.db": b"SQLite format 3\x00" + b"basura" * 100,
            },
        )
        problemas = cli._problemas_de(tar_ruta)
        assert any("database.db" in p and "integrity_check" in p for p in problemas)

    def test_consolidar_wal_viejo_de_coreprotect(self, ctx: Contexto, tmp_path: Path) -> None:
        base_bytes, wal_bytes = _bytes_de_una_base_con_wal(tmp_path / "origen.db", filas=5)
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "plugins/CoreProtect/database.db": base_bytes,
                "plugins/CoreProtect/database.db-wal": wal_bytes,
            },
        )

        with tarfile.open(tar_ruta) as tar:
            miembros = [m for m in tar.getmembers() if "CoreProtect" in m.name]
            tar.extractall(ctx.carpeta_datos, members=miembros, filter="data")
            cli._consolidar_bases_extraidas(ctx, tar)

        base = ctx.carpeta_datos / "plugins" / "CoreProtect" / "database.db"
        assert _cuantas_filas(base) == 5
        assert not Path(f"{base}-wal").exists()
        assert not Path(f"{base}-shm").exists()
        assert sqlite.esta_sana(base)

    def test_restaurar_pagos_con_wal_viejo(self, ctx: Contexto, tmp_path: Path) -> None:
        base_bytes, wal_bytes = _bytes_de_una_base_con_wal(tmp_path / "origen.db", filas=6)
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "pagos-datos/pagos.sqlite": base_bytes,
                "pagos-datos/pagos.sqlite-wal": wal_bytes,
            },
        )

        with tarfile.open(tar_ruta) as tar:
            cli._restaurar_base_de_pagos(ctx, tar)

        base = ctx.raiz / "pagos-datos" / "pagos.sqlite"
        assert _cuantas_filas(base) == 6
        assert not Path(f"{base}-wal").exists()
        assert sqlite.esta_sana(base)


class TestSimulacro:
    def test_extrae_el_mundo_y_valida_las_bases(self, tmp_path: Path) -> None:
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "world/level.dat": b"mundo",
                "pagos-datos/pagos.sqlite": _bytes_de_una_base(tmp_path, 3),
            },
        )
        destino = tmp_path / "extraido"
        assert cli._simulacro_de_restauracion(tar_ruta, destino) == []
        assert (destino / "world" / "level.dat").read_bytes() == b"mundo"

    def test_un_mundo_sin_level_dat_no_sirve(self, tmp_path: Path) -> None:
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(tar_ruta, {"world/region/r.0.0.mca": b"x"})
        problemas = cli._simulacro_de_restauracion(tar_ruta, tmp_path / "extraido")
        assert any("level.dat" in p for p in problemas)

    def test_una_base_rota_se_detecta_al_extraer(self, tmp_path: Path) -> None:
        tar_ruta = tmp_path / "world-20261001-120000.tgz"
        _tar_de_itzg(
            tar_ruta,
            {
                "world/level.dat": b"mundo",
                "plugins/CoreProtect/database.db": b"SQLite format 3\x00" + b"basura" * 100,
            },
        )
        problemas = cli._simulacro_de_restauracion(tar_ruta, tmp_path / "extraido")
        assert any("integrity_check" in p for p in problemas)
