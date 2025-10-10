from __future__ import annotations

import contextlib
from contextlib import closing
import csv
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from io import StringIO
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING
import uuid

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas._libs import lib
from pandas.compat import (
    pa_version_under13p0,
    pa_version_under14p1,
)
from pandas.compat._optional import import_optional_dependency
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    concat,
    date_range,
    isna,
    to_datetime,
    to_timedelta,
)
import pandas._testing as tm
from pandas.util.version import Version

from pandas.io import sql
from pandas.io.sql import (
    SQLAlchemyEngine,
    SQLDatabase,
    SQLiteDatabase,
    get_engine,
    pandasSQL_builder,
    read_sql_query,
    read_sql_table,
)

if TYPE_CHECKING:
    import sqlalchemy


pytestmark = [
    pytest.mark.filterwarnings(
        "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
    ),
    pytest.mark.single_cpu,
]


@pytest.fixture
def sql_strings():
    return {
        "read_parameters": {
            "sqlite": "SELECT * FROM iris WHERE Name=? AND SepalLength=?",
            "mysql": "SELECT * FROM iris WHERE `Name`=%s AND `SepalLength`=%s",
            "postgresql": 'SELECT * FROM iris WHERE "Name"=%s AND "SepalLength"=%s',
        },
        "read_named_parameters": {
            "sqlite": """
                SELECT * FROM iris WHERE Name=:name AND SepalLength=:length
                """,
            "mysql": """
                SELECT * FROM iris WHERE
                `Name`=%(name)s AND `SepalLength`=%(length)s
                """,
            "postgresql": """
                SELECT * FROM iris WHERE
                "Name"=%(name)s AND "SepalLength"=%(length)s
                """,
        },
        "read_no_parameters_with_percent": {
            "sqlite": "SELECT * FROM iris WHERE Name LIKE '%'",
            "mysql": "SELECT * FROM iris WHERE `Name` LIKE '%'",
            "postgresql": "SELECT * FROM iris WHERE \"Name\" LIKE '%'",
        },
    }


def iris_table_metadata():
    import sqlalchemy
    from sqlalchemy import (
        Column,
        Double,
        Float,
        MetaData,
        String,
        Table,
    )

    dtype = Double if Version(sqlalchemy.__version__) >= Version("2.0.0") else Float
    metadata = MetaData()
    iris = Table(
        "iris",
        metadata,
        Column("SepalLength", dtype),
        Column("SepalWidth", dtype),
        Column("PetalLength", dtype),
        Column("PetalWidth", dtype),
        Column("Name", String(200)),
    )
    return iris


def create_and_load_iris_sqlite3(conn, iris_file: Path):
    stmt = """CREATE TABLE iris (
            "SepalLength" REAL,
            "SepalWidth" REAL,
            "PetalLength" REAL,
            "PetalWidth" REAL,
            "Name" TEXT
        )"""

    cur = conn.cursor()
    cur.execute(stmt)
    with iris_file.open(newline=None, encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        next(reader)
        stmt = "INSERT INTO iris VALUES(?, ?, ?, ?, ?)"
        # ADBC requires explicit types - no implicit str -> float conversion
        records = []
        records = [
            (
                float(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                row[4],
            )
            for row in reader
        ]

        cur.executemany(stmt, records)
    cur.close()

    conn.commit()


def create_and_load_iris_postgresql(conn, iris_file: Path):
    stmt = """CREATE TABLE iris (
            "SepalLength" DOUBLE PRECISION,
            "SepalWidth" DOUBLE PRECISION,
            "PetalLength" DOUBLE PRECISION,
            "PetalWidth" DOUBLE PRECISION,
            "Name" TEXT
        )"""
    with conn.cursor() as cur:
        cur.execute(stmt)
        with iris_file.open(newline=None, encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            stmt = "INSERT INTO iris VALUES($1, $2, $3, $4, $5)"
            # ADBC requires explicit types - no implicit str -> float conversion
            records = [
                (
                    float(row[0]),
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    row[4],
                )
                for row in reader
            ]

            cur.executemany(stmt, records)

    conn.commit()


def create_and_load_iris(conn, iris_file: Path):
    from sqlalchemy import insert

    iris = iris_table_metadata()

    with iris_file.open(newline=None, encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        params = [dict(zip(header, row)) for row in reader]
        stmt = insert(iris).values(params)
        with conn.begin() as con:
            iris.drop(con, checkfirst=True)
            iris.create(bind=con)
            con.execute(stmt)


def create_and_load_iris_view(conn):
    stmt = "CREATE VIEW iris_view AS SELECT * FROM iris"
    if isinstance(conn, sqlite3.Connection):
        cur = conn.cursor()
        cur.execute(stmt)
    else:
        adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")
        if adbc and isinstance(conn, adbc.Connection):
            with conn.cursor() as cur:
                cur.execute(stmt)
            conn.commit()
        else:
            from sqlalchemy import text

            stmt = text(stmt)
            with conn.begin() as con:
                con.execute(stmt)


def types_table_metadata(dialect: str):
    from sqlalchemy import (
        TEXT,
        Boolean,
        Column,
        DateTime,
        Float,
        Integer,
        MetaData,
        Table,
    )

    date_type = TEXT if dialect == "sqlite" else DateTime
    bool_type = Integer if dialect == "sqlite" else Boolean
    metadata = MetaData()
    types = Table(
        "types",
        metadata,
        Column("TextCol", TEXT),
        Column("DateCol", date_type),
        Column("IntDateCol", Integer),
        Column("IntDateOnlyCol", Integer),
        Column("FloatCol", Float),
        Column("IntCol", Integer),
        Column("BoolCol", bool_type),
        Column("IntColWithNull", Integer),
        Column("BoolColWithNull", bool_type),
    )
    return types


def create_and_load_types_sqlite3(conn, types_data: list[dict]):
    stmt = """CREATE TABLE types (
                    "TextCol" TEXT,
                    "DateCol" TEXT,
                    "IntDateCol" INTEGER,
                    "IntDateOnlyCol" INTEGER,
                    "FloatCol" REAL,
                    "IntCol" INTEGER,
                    "BoolCol" INTEGER,
                    "IntColWithNull" INTEGER,
                    "BoolColWithNull" INTEGER
                )"""

    ins_stmt = """
                INSERT INTO types
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

    if isinstance(conn, sqlite3.Connection):
        cur = conn.cursor()
        cur.execute(stmt)
        cur.executemany(ins_stmt, types_data)
    else:
        with conn.cursor() as cur:
            cur.execute(stmt)
            cur.executemany(ins_stmt, types_data)

        conn.commit()


def create_and_load_types_postgresql(conn, types_data: list[dict]):
    with conn.cursor() as cur:
        stmt = """CREATE TABLE types (
                        "TextCol" TEXT,
                        "DateCol" TIMESTAMP,
                        "IntDateCol" INTEGER,
                        "IntDateOnlyCol" INTEGER,
                        "FloatCol" DOUBLE PRECISION,
                        "IntCol" INTEGER,
                        "BoolCol" BOOLEAN,
                        "IntColWithNull" INTEGER,
                        "BoolColWithNull" BOOLEAN
                    )"""
        cur.execute(stmt)

        stmt = """
                INSERT INTO types
                VALUES($1, $2::timestamp, $3, $4, $5, $6, $7, $8, $9)
                """

        cur.executemany(stmt, types_data)

    conn.commit()


def create_and_load_types(conn, types_data: list[dict], dialect: str):
    from sqlalchemy import insert
    from sqlalchemy.engine import Engine

    types = types_table_metadata(dialect)

    stmt = insert(types).values(types_data)
    if isinstance(conn, Engine):
        with conn.connect() as conn:
            with conn.begin():
                types.drop(conn, checkfirst=True)
                types.create(bind=conn)
                conn.execute(stmt)
    else:
        with conn.begin():
            types.drop(conn, checkfirst=True)
            types.create(bind=conn)
            conn.execute(stmt)


def create_and_load_postgres_datetz(conn):
    from sqlalchemy import (
        Column,
        DateTime,
        MetaData,
        Table,
        insert,
    )
    from sqlalchemy.engine import Engine

    metadata = MetaData()
    datetz = Table("datetz", metadata, Column("DateColWithTz", DateTime(timezone=True)))
    datetz_data = [
        {
            "DateColWithTz": "2000-01-01 00:00:00-08:00",
        },
        {
            "DateColWithTz": "2000-06-01 00:00:00-07:00",
        },
    ]
    stmt = insert(datetz).values(datetz_data)
    if isinstance(conn, Engine):
        with conn.connect() as conn:
            with conn.begin():
                datetz.drop(conn, checkfirst=True)
                datetz.create(bind=conn)
                conn.execute(stmt)
    else:
        with conn.begin():
            datetz.drop(conn, checkfirst=True)
            datetz.create(bind=conn)
            conn.execute(stmt)

    # "2000-01-01 00:00:00-08:00" should convert to
    # "2000-01-01 08:00:00"
    # "2000-06-01 00:00:00-07:00" should convert to
    # "2000-06-01 07:00:00"
    # GH 6415
    expected_data = [
        Timestamp("2000-01-01 08:00:00", tz="UTC"),
        Timestamp("2000-06-01 07:00:00", tz="UTC"),
    ]
    return Series(expected_data, name="DateColWithTz")


def check_iris_frame(frame: DataFrame):
    pytype = frame.dtypes.iloc[0].type
    row = frame.iloc[0]
    assert issubclass(pytype, np.floating)
    tm.assert_series_equal(
        row, Series([5.1, 3.5, 1.4, 0.2, "Iris-setosa"], index=frame.columns, name=0)
    )
    assert frame.shape in ((150, 5), (8, 5))


def count_rows(conn, table_name: str):
    stmt = f"SELECT count(*) AS count_1 FROM {table_name}"
    adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")
    if isinstance(conn, sqlite3.Connection):
        cur = conn.cursor()
        return cur.execute(stmt).fetchone()[0]
    elif adbc and isinstance(conn, adbc.Connection):
        with conn.cursor() as cur:
            cur.execute(stmt)
            return cur.fetchone()[0]
    else:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import Engine

        if isinstance(conn, str):
            try:
                engine = create_engine(conn)
                with engine.connect() as conn:
                    return conn.exec_driver_sql(stmt).scalar_one()
            finally:
                engine.dispose()
        elif isinstance(conn, Engine):
            with conn.connect() as conn:
                return conn.exec_driver_sql(stmt).scalar_one()
        else:
            return conn.exec_driver_sql(stmt).scalar_one()


@pytest.fixture
def iris_path(datapath):
    iris_path = datapath("io", "data", "csv", "iris.csv")
    return Path(iris_path)


@pytest.fixture
def types_data():
    return [
        {
            "TextCol": "first",
            "DateCol": "2000-01-03 00:00:00",
            "IntDateCol": 535852800,
            "IntDateOnlyCol": 20101010,
            "FloatCol": 10.10,
            "IntCol": 1,
            "BoolCol": False,
            "IntColWithNull": 1,
            "BoolColWithNull": False,
        },
        {
            "TextCol": "first",
            "DateCol": "2000-01-04 00:00:00",
            "IntDateCol": 1356998400,
            "IntDateOnlyCol": 20101212,
            "FloatCol": 10.10,
            "IntCol": 1,
            "BoolCol": False,
            "IntColWithNull": None,
            "BoolColWithNull": None,
        },
    ]


@pytest.fixture
def types_data_frame(types_data):
    dtypes = {
        "TextCol": "str",
        "DateCol": "str",
        "IntDateCol": "int64",
        "IntDateOnlyCol": "int64",
        "FloatCol": "float",
        "IntCol": "int64",
        "BoolCol": "int64",
        "IntColWithNull": "float",
        "BoolColWithNull": "float",
    }
    df = DataFrame(types_data)
    return df[dtypes.keys()].astype(dtypes)


@pytest.fixture
def test_frame1():
    columns = ["index", "A", "B", "C", "D"]
    data = [
        (
            "2000-01-03 00:00:00",
            0.980268513777,
            3.68573087906,
            -0.364216805298,
            -1.15973806169,
        ),
        (
            "2000-01-04 00:00:00",
            1.04791624281,
            -0.0412318367011,
            -0.16181208307,
            0.212549316967,
        ),
        (
            "2000-01-05 00:00:00",
            0.498580885705,
            0.731167677815,
            -0.537677223318,
            1.34627041952,
        ),
        (
            "2000-01-06 00:00:00",
            1.12020151869,
            1.56762092543,
            0.00364077397681,
            0.67525259227,
        ),
    ]
    return DataFrame(data, columns=columns)


@pytest.fixture
def test_frame3():
    columns = ["index", "A", "B"]
    data = [
        ("2000-01-03 00:00:00", 2**31 - 1, -1.987670),
        ("2000-01-04 00:00:00", -29, -0.0412318367011),
        ("2000-01-05 00:00:00", 20000, 0.731167677815),
        ("2000-01-06 00:00:00", -290867, 1.56762092543),
    ]
    return DataFrame(data, columns=columns)


def get_all_views(conn):
    if isinstance(conn, sqlite3.Connection):
        c = conn.execute("SELECT name FROM sqlite_master WHERE type='view'")
        return [view[0] for view in c.fetchall()]
    else:
        adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")
        if adbc and isinstance(conn, adbc.Connection):
            results = []
            info = conn.adbc_get_objects().read_all().to_pylist()
            for catalog in info:
                catalog["catalog_name"]
                for schema in catalog["catalog_db_schemas"]:
                    schema["db_schema_name"]
                    for table in schema["db_schema_tables"]:
                        if table["table_type"] == "view":
                            view_name = table["table_name"]
                            results.append(view_name)

            return results
        else:
            from sqlalchemy import inspect

            return inspect(conn).get_view_names()


def get_all_tables(conn):
    if isinstance(conn, sqlite3.Connection):
        c = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [table[0] for table in c.fetchall()]
    else:
        adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")

        if adbc and isinstance(conn, adbc.Connection):
            results = []
            info = conn.adbc_get_objects().read_all().to_pylist()
            for catalog in info:
                for schema in catalog["catalog_db_schemas"]:
                    for table in schema["db_schema_tables"]:
                        if table["table_type"] == "table":
                            table_name = table["table_name"]
                            results.append(table_name)

            return results
        else:
            from sqlalchemy import inspect

            return inspect(conn).get_table_names()


def drop_table(
    table_name: str,
    conn: sqlite3.Connection | sqlalchemy.engine.Engine | sqlalchemy.engine.Connection,
):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP TABLE IF EXISTS {sql._get_valid_sqlite_name(table_name)}")
        conn.commit()

    else:
        adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")
        if adbc and isinstance(conn, adbc.Connection):
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        else:
            with conn.begin() as con:
                with sql.SQLDatabase(con) as db:
                    db.drop_table(table_name)


def drop_view(
    view_name: str,
    conn: sqlite3.Connection | sqlalchemy.engine.Engine | sqlalchemy.engine.Connection,
):
    import sqlalchemy

    if isinstance(conn, sqlite3.Connection):
        conn.execute(f"DROP VIEW IF EXISTS {sql._get_valid_sqlite_name(view_name)}")
        conn.commit()
    else:
        adbc = import_optional_dependency("adbc_driver_manager.dbapi", errors="ignore")
        if adbc and isinstance(conn, adbc.Connection):
            with conn.cursor() as cur:
                cur.execute(f'DROP VIEW IF EXISTS "{view_name}"')
        else:
            quoted_view = conn.engine.dialect.identifier_preparer.quote_identifier(
                view_name
            )
            stmt = sqlalchemy.text(f"DROP VIEW IF EXISTS {quoted_view}")
            with conn.begin() as con:
                con.execute(stmt)  # type: ignore[union-attr]


@pytest.fixture
def mysql_pymysql_engine():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    pymysql = pytest.importorskip("pymysql")
    engine = sqlalchemy.create_engine(
        "mysql+pymysql://root@localhost:3306/pandas",
        connect_args={"client_flag": pymysql.constants.CLIENT.MULTI_STATEMENTS},
        poolclass=sqlalchemy.pool.NullPool,
    )
    yield engine
    for view in get_all_views(engine):
        drop_view(view, engine)
    for tbl in get_all_tables(engine):
        drop_table(tbl, engine)
    engine.dispose()


@pytest.fixture
def mysql_pymysql_engine_iris(mysql_pymysql_engine, iris_path):
    create_and_load_iris(mysql_pymysql_engine, iris_path)
    create_and_load_iris_view(mysql_pymysql_engine)
    yield mysql_pymysql_engine


@pytest.fixture
def mysql_pymysql_engine_types(mysql_pymysql_engine, types_data):
    create_and_load_types(mysql_pymysql_engine, types_data, "mysql")
    yield mysql_pymysql_engine


@pytest.fixture
def mysql_pymysql_conn(mysql_pymysql_engine):
    with mysql_pymysql_engine.connect() as conn:
        yield conn


@pytest.fixture
def mysql_pymysql_conn_iris(mysql_pymysql_engine_iris):
    with mysql_pymysql_engine_iris.connect() as conn:
        yield conn


@pytest.fixture
def mysql_pymysql_conn_types(mysql_pymysql_engine_types):
    with mysql_pymysql_engine_types.connect() as conn:
        yield conn


@pytest.fixture
def postgresql_psycopg2_engine():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg2")
    engine = sqlalchemy.create_engine(
        "postgresql+psycopg2://postgres:postgres@localhost:5432/pandas",
        poolclass=sqlalchemy.pool.NullPool,
    )
    yield engine
    for view in get_all_views(engine):
        drop_view(view, engine)
    for tbl in get_all_tables(engine):
        drop_table(tbl, engine)
    engine.dispose()


@pytest.fixture
def postgresql_psycopg2_engine_iris(postgresql_psycopg2_engine, iris_path):
    create_and_load_iris(postgresql_psycopg2_engine, iris_path)
    create_and_load_iris_view(postgresql_psycopg2_engine)
    yield postgresql_psycopg2_engine


@pytest.fixture
def postgresql_psycopg2_engine_types(postgresql_psycopg2_engine, types_data):
    create_and_load_types(postgresql_psycopg2_engine, types_data, "postgres")
    yield postgresql_psycopg2_engine


@pytest.fixture
def postgresql_psycopg2_conn(postgresql_psycopg2_engine):
    with postgresql_psycopg2_engine.connect() as conn:
        yield conn


@pytest.fixture
def postgresql_adbc_conn():
    pytest.importorskip("pyarrow")
    pytest.importorskip("adbc_driver_postgresql")
    from adbc_driver_postgresql import dbapi

    uri = "postgresql://postgres:postgres@localhost:5432/pandas"
    with dbapi.connect(uri) as conn:
        yield conn
        for view in get_all_views(conn):
            drop_view(view, conn)
        for tbl in get_all_tables(conn):
            drop_table(tbl, conn)
        conn.commit()


@pytest.fixture
def postgresql_adbc_iris(postgresql_adbc_conn, iris_path):
    import adbc_driver_manager as mgr

    conn = postgresql_adbc_conn

    try:
        conn.adbc_get_table_schema("iris")
    except mgr.ProgrammingError:
        conn.rollback()
        create_and_load_iris_postgresql(conn, iris_path)
    try:
        conn.adbc_get_table_schema("iris_view")
    except mgr.ProgrammingError:  # note arrow-adbc issue 1022
        conn.rollback()
        create_and_load_iris_view(conn)
    yield conn


@pytest.fixture
def postgresql_adbc_types(postgresql_adbc_conn, types_data):
    import adbc_driver_manager as mgr

    conn = postgresql_adbc_conn

    try:
        conn.adbc_get_table_schema("types")
    except mgr.ProgrammingError:
        conn.rollback()
        new_data = [tuple(entry.values()) for entry in types_data]

        create_and_load_types_postgresql(conn, new_data)

    yield conn


@pytest.fixture
def postgresql_psycopg2_conn_iris(postgresql_psycopg2_engine_iris):
    with postgresql_psycopg2_engine_iris.connect() as conn:
        yield conn


@pytest.fixture
def postgresql_psycopg2_conn_types(postgresql_psycopg2_engine_types):
    with postgresql_psycopg2_engine_types.connect() as conn:
        yield conn


@pytest.fixture
def sqlite_str():
    pytest.importorskip("sqlalchemy")
    with tm.ensure_clean() as name:
        yield f"sqlite:///{name}"


@pytest.fixture
def sqlite_engine(sqlite_str):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    engine = sqlalchemy.create_engine(sqlite_str, poolclass=sqlalchemy.pool.NullPool)
    yield engine
    for view in get_all_views(engine):
        drop_view(view, engine)
    for tbl in get_all_tables(engine):
        drop_table(tbl, engine)
    engine.dispose()


@pytest.fixture
def sqlite_conn(sqlite_engine):
    with sqlite_engine.connect() as conn:
        yield conn


@pytest.fixture
def sqlite_str_iris(sqlite_str, iris_path):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    engine = sqlalchemy.create_engine(sqlite_str)
    create_and_load_iris(engine, iris_path)
    create_and_load_iris_view(engine)
    engine.dispose()
    return sqlite_str


@pytest.fixture
def sqlite_engine_iris(sqlite_engine, iris_path):
    create_and_load_iris(sqlite_engine, iris_path)
    create_and_load_iris_view(sqlite_engine)
    yield sqlite_engine


@pytest.fixture
def sqlite_conn_iris(sqlite_engine_iris):
    with sqlite_engine_iris.connect() as conn:
        yield conn


@pytest.fixture
def sqlite_str_types(sqlite_str, types_data):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    engine = sqlalchemy.create_engine(sqlite_str)
    create_and_load_types(engine, types_data, "sqlite")
    engine.dispose()
    return sqlite_str


@pytest.fixture
def sqlite_engine_types(sqlite_engine, types_data):
    create_and_load_types(sqlite_engine, types_data, "sqlite")
    yield sqlite_engine


@pytest.fixture
def sqlite_conn_types(sqlite_engine_types):
    with sqlite_engine_types.connect() as conn:
        yield conn


@pytest.fixture
def sqlite_adbc_conn():
    pytest.importorskip("pyarrow")
    pytest.importorskip("adbc_driver_sqlite")
    from adbc_driver_sqlite import dbapi

    with tm.ensure_clean() as name:
        uri = f"file:{name}"
        with dbapi.connect(uri) as conn:
            yield conn
            for view in get_all_views(conn):
                drop_view(view, conn)
            for tbl in get_all_tables(conn):
                drop_table(tbl, conn)
            conn.commit()


@pytest.fixture
def sqlite_adbc_iris(sqlite_adbc_conn, iris_path):
    import adbc_driver_manager as mgr

    conn = sqlite_adbc_conn
    try:
        conn.adbc_get_table_schema("iris")
    except mgr.ProgrammingError:
        conn.rollback()
        create_and_load_iris_sqlite3(conn, iris_path)
    try:
        conn.adbc_get_table_schema("iris_view")
    except mgr.ProgrammingError:
        conn.rollback()
        create_and_load_iris_view(conn)
    yield conn


@pytest.fixture
def sqlite_adbc_types(sqlite_adbc_conn, types_data):
    import adbc_driver_manager as mgr

    conn = sqlite_adbc_conn
    try:
        conn.adbc_get_table_schema("types")
    except mgr.ProgrammingError:
        conn.rollback()
        new_data = []
        for entry in types_data:
            entry["BoolCol"] = int(entry["BoolCol"])
            if entry["BoolColWithNull"] is not None:
                entry["BoolColWithNull"] = int(entry["BoolColWithNull"])
            new_data.append(tuple(entry.values()))

        create_and_load_types_sqlite3(conn, new_data)
        conn.commit()

    yield conn


@pytest.fixture
def sqlite_buildin():
    with contextlib.closing(sqlite3.connect(":memory:")) as closing_conn:
        with closing_conn as conn:
            yield conn


@pytest.fixture
def sqlite_buildin_iris(sqlite_buildin, iris_path):
    create_and_load_iris_sqlite3(sqlite_buildin, iris_path)
    create_and_load_iris_view(sqlite_buildin)
    yield sqlite_buildin


@pytest.fixture
def sqlite_buildin_types(sqlite_buildin, types_data):
    types_data = [tuple(entry.values()) for entry in types_data]
    create_and_load_types_sqlite3(sqlite_buildin, types_data)
    yield sqlite_buildin


mysql_connectable = [
    pytest.param("mysql_pymysql_engine", marks=pytest.mark.db),
    pytest.param("mysql_pymysql_conn", marks=pytest.mark.db),
]

mysql_connectable_iris = [
    pytest.param("mysql_pymysql_engine_iris", marks=pytest.mark.db),
    pytest.param("mysql_pymysql_conn_iris", marks=pytest.mark.db),
]

mysql_connectable_types = [
    pytest.param("mysql_pymysql_engine_types", marks=pytest.mark.db),
    pytest.param("mysql_pymysql_conn_types", marks=pytest.mark.db),
]

postgresql_connectable = [
    pytest.param("postgresql_psycopg2_engine", marks=pytest.mark.db),
    pytest.param("postgresql_psycopg2_conn", marks=pytest.mark.db),
]

postgresql_connectable_iris = [
    pytest.param("postgresql_psycopg2_engine_iris", marks=pytest.mark.db),
    pytest.param("postgresql_psycopg2_conn_iris", marks=pytest.mark.db),
]

postgresql_connectable_types = [
    pytest.param("postgresql_psycopg2_engine_types", marks=pytest.mark.db),
    pytest.param("postgresql_psycopg2_conn_types", marks=pytest.mark.db),
]

sqlite_connectable = [
    "sqlite_engine",
    "sqlite_conn",
    "sqlite_str",
]

sqlite_connectable_iris = [
    "sqlite_engine_iris",
    "sqlite_conn_iris",
    "sqlite_str_iris",
]

sqlite_connectable_types = [
    "sqlite_engine_types",
    "sqlite_conn_types",
    "sqlite_str_types",
]

sqlalchemy_connectable = mysql_connectable + postgresql_connectable + sqlite_connectable

sqlalchemy_connectable_iris = (
    mysql_connectable_iris + postgresql_connectable_iris + sqlite_connectable_iris
)

sqlalchemy_connectable_types = (
    mysql_connectable_types + postgresql_connectable_types + sqlite_connectable_types
)

adbc_connectable = [
    "sqlite_adbc_conn",
    pytest.param("postgresql_adbc_conn", marks=pytest.mark.db),
]

adbc_connectable_iris = [
    pytest.param("postgresql_adbc_iris", marks=pytest.mark.db),
    "sqlite_adbc_iris",
]

adbc_connectable_types = [
    pytest.param("postgresql_adbc_types", marks=pytest.mark.db),
    "sqlite_adbc_types",
]


all_connectable = sqlalchemy_connectable + ["sqlite_buildin"] + adbc_connectable

all_connectable_iris = (
    sqlalchemy_connectable_iris + ["sqlite_buildin_iris"] + adbc_connectable_iris
)

all_connectable_types = (
    sqlalchemy_connectable_types + ["sqlite_buildin_types"] + adbc_connectable_types
)


@pytest.mark.parametrize("conn", all_connectable)
def test_dataframe_to_sql(conn, test_frame1, request):
    # GH 51086 if conn is sqlite_engine
    conn = request.getfixturevalue(conn)
    test_frame1.to_sql(name="test", con=conn, if_exists="append", index=False)


@pytest.mark.parametrize("conn", all_connectable)
def test_dataframe_to_sql_empty(conn, test_frame1, request):
    if conn == "postgresql_adbc_conn" and not using_string_dtype():
        request.node.add_marker(
            pytest.mark.xfail(
                reason="postgres ADBC driver < 1.2 cannot insert index with null type",
            )
        )

    # GH 51086 if conn is sqlite_engine
    conn = request.getfixturevalue(conn)
    empty_df = test_frame1.iloc[:0]
    empty_df.to_sql(name="test", con=conn, if_exists="append", index=False)


@pytest.mark.parametrize("conn", all_connectable)
def test_dataframe_to_sql_arrow_dtypes(conn, request):
    # GH 52046
    pytest.importorskip("pyarrow")
    df = DataFrame(
        {
            "int": pd.array([1], dtype="int8[pyarrow]"),
            "datetime": pd.array(
                [datetime(2023, 1, 1)], dtype="timestamp[ns][pyarrow]"
            ),
            "date": pd.array([date(2023, 1, 1)], dtype="date32[day][pyarrow]"),
            "timedelta": pd.array([timedelta(1)], dtype="duration[ns][pyarrow]"),
            "string": pd.array(["a"], dtype="string[pyarrow]"),
        }
    )

    if "adbc" in conn:
        if conn == "sqlite_adbc_conn":
            df = df.drop(columns=["timedelta"])
        if pa_version_under14p1:
            exp_warning = DeprecationWarning
            msg = "is_sparse is deprecated"
        else:
            exp_warning = None
            msg = ""
    else:
        exp_warning = UserWarning
        msg = "the 'timedelta'"

    conn = request.getfixturevalue(conn)
    with tm.assert_produces_warning(exp_warning, match=msg, check_stacklevel=False):
        df.to_sql(name="test_arrow", con=conn, if_exists="replace", index=False)


@pytest.mark.parametrize("conn", all_connectable)
def test_dataframe_to_sql_arrow_dtypes_missing(conn, request, nulls_fixture):
    # GH 52046
    pytest.importorskip("pyarrow")
    df = DataFrame(
        {
            "datetime": pd.array(
                [datetime(2023, 1, 1), nulls_fixture], dtype="timestamp[ns][pyarrow]"
            ),
        }
    )
    conn = request.getfixturevalue(conn)
    df.to_sql(name="test_arrow", con=conn, if_exists="replace", index=False)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("method", [None, "multi"])
def test_to_sql(conn, method, test_frame1, request):
    if method == "multi" and "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'method' not implemented for ADBC drivers", strict=True
            )
        )

    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn, need_transaction=True) as pandasSQL:
        pandasSQL.to_sql(test_frame1, "test_frame", method=method)
        assert pandasSQL.has_table("test_frame")
    assert count_rows(conn, "test_frame") == len(test_frame1)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("mode, num_row_coef", [("replace", 1), ("append", 2)])
def test_to_sql_exist(conn, mode, num_row_coef, test_frame1, request):
    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn, need_transaction=True) as pandasSQL:
        pandasSQL.to_sql(test_frame1, "test_frame", if_exists="fail")
        pandasSQL.to_sql(test_frame1, "test_frame", if_exists=mode)
        assert pandasSQL.has_table("test_frame")
    assert count_rows(conn, "test_frame") == num_row_coef * len(test_frame1)


@pytest.mark.parametrize("conn", all_connectable)
def test_to_sql_exist_fail(conn, test_frame1, request):
    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn, need_transaction=True) as pandasSQL:
        pandasSQL.to_sql(test_frame1, "test_frame", if_exists="fail")
        assert pandasSQL.has_table("test_frame")

        msg = "Table 'test_frame' already exists"
        with pytest.raises(ValueError, match=msg):
            pandasSQL.to_sql(test_frame1, "test_frame", if_exists="fail")


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_iris_query(conn, request):
    conn = request.getfixturevalue(conn)
    iris_frame = read_sql_query("SELECT * FROM iris", conn)
    check_iris_frame(iris_frame)
    iris_frame = pd.read_sql("SELECT * FROM iris", conn)
    check_iris_frame(iris_frame)
    iris_frame = pd.read_sql("SELECT * FROM iris where 0=1", conn)
    assert iris_frame.shape == (0, 5)
    assert "SepalWidth" in iris_frame.columns


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_iris_query_chunksize(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'chunksize' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn = request.getfixturevalue(conn)
    iris_frame = concat(read_sql_query("SELECT * FROM iris", conn, chunksize=7))
    check_iris_frame(iris_frame)
    iris_frame = concat(pd.read_sql("SELECT * FROM iris", conn, chunksize=7))
    check_iris_frame(iris_frame)
    iris_frame = concat(pd.read_sql("SELECT * FROM iris where 0=1", conn, chunksize=7))
    assert iris_frame.shape == (0, 5)
    assert "SepalWidth" in iris_frame.columns


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_read_iris_query_expression_with_parameter(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'chunksize' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn = request.getfixturevalue(conn)
    from sqlalchemy import (
        MetaData,
        Table,
        create_engine,
        select,
    )

    metadata = MetaData()
    autoload_con = create_engine(conn) if isinstance(conn, str) else conn
    iris = Table("iris", metadata, autoload_with=autoload_con)
    iris_frame = read_sql_query(
        select(iris), conn, params={"name": "Iris-setosa", "length": 5.1}
    )
    check_iris_frame(iris_frame)
    if isinstance(conn, str):
        autoload_con.dispose()


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_iris_query_string_with_parameter(conn, request, sql_strings):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'chunksize' not implemented for ADBC drivers",
                strict=True,
            )
        )

    for db, query in sql_strings["read_parameters"].items():
        if db in conn:
            break
    else:
        raise KeyError(f"No part of {conn} found in sql_strings['read_parameters']")
    conn = request.getfixturevalue(conn)
    iris_frame = read_sql_query(query, conn, params=("Iris-setosa", 5.1))
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_read_iris_table(conn, request):
    # GH 51015 if conn = sqlite_iris_str
    conn = request.getfixturevalue(conn)
    iris_frame = read_sql_table("iris", conn)
    check_iris_frame(iris_frame)
    iris_frame = pd.read_sql("iris", conn)
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_read_iris_table_chunksize(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="chunksize argument NotImplemented with ADBC")
        )
    conn = request.getfixturevalue(conn)
    iris_frame = concat(read_sql_table("iris", conn, chunksize=7))
    check_iris_frame(iris_frame)
    iris_frame = concat(pd.read_sql("iris", conn, chunksize=7))
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_to_sql_callable(conn, test_frame1, request):
    conn = request.getfixturevalue(conn)

    check = []  # used to double check function below is really being used

    def sample(pd_table, conn, keys, data_iter):
        check.append(1)
        data = [dict(zip(keys, row)) for row in data_iter]
        conn.execute(pd_table.table.insert(), data)

    with pandasSQL_builder(conn, need_transaction=True) as pandasSQL:
        pandasSQL.to_sql(test_frame1, "test_frame", method=sample)
        assert pandasSQL.has_table("test_frame")
    assert check == [1]
    assert count_rows(conn, "test_frame") == len(test_frame1)


@pytest.mark.parametrize("conn", all_connectable_types)
def test_default_type_conversion(conn, request):
    conn_name = conn
    if conn_name == "sqlite_buildin_types":
        request.applymarker(
            pytest.mark.xfail(
                reason="sqlite_buildin connection does not implement read_sql_table"
            )
        )

    conn = request.getfixturevalue(conn)
    df = sql.read_sql_table("types", conn)

    assert issubclass(df.FloatCol.dtype.type, np.floating)
    assert issubclass(df.IntCol.dtype.type, np.integer)

    # MySQL/sqlite has no real BOOL type
    if "postgresql" in conn_name:
        assert issubclass(df.BoolCol.dtype.type, np.bool_)
    else:
        assert issubclass(df.BoolCol.dtype.type, np.integer)

    # Int column with NA values stays as float
    assert issubclass(df.IntColWithNull.dtype.type, np.floating)

    # Bool column with NA = int column with NA values => becomes float
    if "postgresql" in conn_name:
        assert issubclass(df.BoolColWithNull.dtype.type, object)
    else:
        assert issubclass(df.BoolColWithNull.dtype.type, np.floating)


@pytest.mark.parametrize("conn", mysql_connectable)
def test_read_procedure(conn, request):
    conn = request.getfixturevalue(conn)

    # GH 7324
    # Although it is more an api test, it is added to the
    # mysql tests as sqlite does not have stored procedures
    from sqlalchemy import text
    from sqlalchemy.engine import Engine

    df = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})
    df.to_sql(name="test_frame", con=conn, index=False)

    proc = """DROP PROCEDURE IF EXISTS get_testdb;

    CREATE PROCEDURE get_testdb ()

    BEGIN
        SELECT * FROM test_frame;
    END"""
    proc = text(proc)
    if isinstance(conn, Engine):
        with conn.connect() as engine_conn:
            with engine_conn.begin():
                engine_conn.execute(proc)
    else:
        with conn.begin():
            conn.execute(proc)

    res1 = sql.read_sql_query("CALL get_testdb();", conn)
    tm.assert_frame_equal(df, res1)

    # test delegation to read_sql_query
    res2 = sql.read_sql("CALL get_testdb();", conn)
    tm.assert_frame_equal(df, res2)


@pytest.mark.parametrize("conn", postgresql_connectable)
@pytest.mark.parametrize("expected_count", [2, "Success!"])
def test_copy_from_callable_insertion_method(conn, expected_count, request):
    # GH 8953
    # Example in io.rst found under _io.sql.method
    # not available in sqlite, mysql
    def psql_insert_copy(table, conn, keys, data_iter):
        # gets a DBAPI connection that can provide a cursor
        dbapi_conn = conn.connection
        with dbapi_conn.cursor() as cur:
            s_buf = StringIO()
            writer = csv.writer(s_buf)
            writer.writerows(data_iter)
            s_buf.seek(0)

            columns = ", ".join([f'"{k}"' for k in keys])
            if table.schema:
                table_name = f"{table.schema}.{table.name}"
            else:
                table_name = table.name

            sql_query = f"COPY {table_name} ({columns}) FROM STDIN WITH CSV"
            cur.copy_expert(sql=sql_query, file=s_buf)
        return expected_count

    conn = request.getfixturevalue(conn)
    expected = DataFrame({"col1": [1, 2], "col2": [0.1, 0.2], "col3": ["a", "n"]})
    result_count = expected.to_sql(
        name="test_frame", con=conn, index=False, method=psql_insert_copy
    )
    # GH 46891
    if expected_count is None:
        assert result_count is None
    else:
        assert result_count == expected_count
    result = sql.read_sql_table("test_frame", conn)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", postgresql_connectable)
def test_insertion_method_on_conflict_do_nothing(conn, request):
    # GH 15988: Example in to_sql docstring
    conn = request.getfixturevalue(conn)

    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql import text

    def insert_on_conflict(table, conn, keys, data_iter):
        data = [dict(zip(keys, row)) for row in data_iter]
        stmt = (
            insert(table.table)
            .values(data)
            .on_conflict_do_nothing(index_elements=["a"])
        )
        result = conn.execute(stmt)
        return result.rowcount

    create_sql = text(
        """
    CREATE TABLE test_insert_conflict (
        a  integer PRIMARY KEY,
        b  numeric,
        c  text
    );
    """
    )
    if isinstance(conn, Engine):
        with conn.connect() as con:
            with con.begin():
                con.execute(create_sql)
    else:
        with conn.begin():
            conn.execute(create_sql)

    expected = DataFrame([[1, 2.1, "a"]], columns=list("abc"))
    expected.to_sql(
        name="test_insert_conflict", con=conn, if_exists="append", index=False
    )

    df_insert = DataFrame([[1, 3.2, "b"]], columns=list("abc"))
    inserted = df_insert.to_sql(
        name="test_insert_conflict",
        con=conn,
        index=False,
        if_exists="append",
        method=insert_on_conflict,
    )
    result = sql.read_sql_table("test_insert_conflict", conn)
    tm.assert_frame_equal(result, expected)
    assert inserted == 0

    # Cleanup
    with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
        pandasSQL.drop_table("test_insert_conflict")


@pytest.mark.parametrize("conn", all_connectable)
def test_to_sql_on_public_schema(conn, request):
    if "sqlite" in conn or "mysql" in conn:
        request.applymarker(
            pytest.mark.xfail(
                reason="test for public schema only specific to postgresql"
            )
        )

    conn = request.getfixturevalue(conn)

    test_data = DataFrame([[1, 2.1, "a"], [2, 3.1, "b"]], columns=list("abc"))
    test_data.to_sql(
        name="test_public_schema",
        con=conn,
        if_exists="append",
        index=False,
        schema="public",
    )

    df_out = sql.read_sql_table("test_public_schema", conn, schema="public")
    tm.assert_frame_equal(test_data, df_out)


@pytest.mark.parametrize("conn", mysql_connectable)
def test_insertion_method_on_conflict_update(conn, request):
    # GH 14553: Example in to_sql docstring
    conn = request.getfixturevalue(conn)

    from sqlalchemy.dialects.mysql import insert
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql import text

    def insert_on_conflict(table, conn, keys, data_iter):
        data = [dict(zip(keys, row)) for row in data_iter]
        stmt = insert(table.table).values(data)
        stmt = stmt.on_duplicate_key_update(b=stmt.inserted.b, c=stmt.inserted.c)
        result = conn.execute(stmt)
        return result.rowcount

    create_sql = text(
        """
    CREATE TABLE test_insert_conflict (
        a INT PRIMARY KEY,
        b FLOAT,
        c VARCHAR(10)
    );
    """
    )
    if isinstance(conn, Engine):
        with conn.connect() as con:
            with con.begin():
                con.execute(create_sql)
    else:
        with conn.begin():
            conn.execute(create_sql)

    df = DataFrame([[1, 2.1, "a"]], columns=list("abc"))
    df.to_sql(name="test_insert_conflict", con=conn, if_exists="append", index=False)

    expected = DataFrame([[1, 3.2, "b"]], columns=list("abc"))
    inserted = expected.to_sql(
        name="test_insert_conflict",
        con=conn,
        index=False,
        if_exists="append",
        method=insert_on_conflict,
    )
    result = sql.read_sql_table("test_insert_conflict", conn)
    tm.assert_frame_equal(result, expected)
    assert inserted == 2

    # Cleanup
    with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
        pandasSQL.drop_table("test_insert_conflict")


@pytest.mark.parametrize("conn", postgresql_connectable)
def test_read_view_postgres(conn, request):
    # GH 52969
    conn = request.getfixturevalue(conn)

    from sqlalchemy.engine import Engine
    from sqlalchemy.sql import text

    table_name = f"group_{uuid.uuid4().hex}"
    view_name = f"group_view_{uuid.uuid4().hex}"

    sql_stmt = text(
        f"""
    CREATE TABLE {table_name} (
        group_id INTEGER,
        name TEXT
    );
    INSERT INTO {table_name} VALUES
        (1, 'name');
    CREATE VIEW {view_name}
    AS
    SELECT * FROM {table_name};
    """
    )
    if isinstance(conn, Engine):
        with conn.connect() as con:
            with con.begin():
                con.execute(sql_stmt)
    else:
        with conn.begin():
            conn.execute(sql_stmt)
    result = read_sql_table(view_name, conn)
    expected = DataFrame({"group_id": [1], "name": "name"})
    tm.assert_frame_equal(result, expected)


def test_read_view_sqlite(sqlite_buildin):
    # GH 52969
    create_table = """
CREATE TABLE groups (
   group_id INTEGER,
   name TEXT
);
"""
    insert_into = """
INSERT INTO groups VALUES
    (1, 'name');
"""
    create_view = """
CREATE VIEW group_view
AS
SELECT * FROM groups;
"""
    sqlite_buildin.execute(create_table)
    sqlite_buildin.execute(insert_into)
    sqlite_buildin.execute(create_view)
    result = pd.read_sql("SELECT * FROM group_view", sqlite_buildin)
    expected = DataFrame({"group_id": [1], "name": "name"})
    tm.assert_frame_equal(result, expected)


def test_execute_typeerror(sqlite_engine_iris):
    with pytest.raises(TypeError, match="pandas.io.sql.execute requires a connection"):
        with tm.assert_produces_warning(
            FutureWarning,
            match="`pandas.io.sql.execute` is deprecated and "
            "will be removed in the future version.",
        ):
            sql.execute("select * from iris", sqlite_engine_iris)


def test_execute_deprecated(sqlite_conn_iris):
    # GH50185
    with tm.assert_produces_warning(
        FutureWarning,
        match="`pandas.io.sql.execute` is deprecated and "
        "will be removed in the future version.",
    ):
        sql.execute("select * from iris", sqlite_conn_iris)


def flavor(conn_name):
    if "postgresql" in conn_name:
        return "postgresql"
    elif "sqlite" in conn_name:
        return "sqlite"
    elif "mysql" in conn_name:
        return "mysql"

    raise ValueError(f"unsupported connection: {conn_name}")


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_sql_iris_parameter(conn, request, sql_strings):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'params' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn_name = conn
    conn = request.getfixturevalue(conn)
    query = sql_strings["read_parameters"][flavor(conn_name)]
    params = ("Iris-setosa", 5.1)
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            iris_frame = pandasSQL.read_query(query, params=params)
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_sql_iris_named_parameter(conn, request, sql_strings):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'params' not implemented for ADBC drivers",
                strict=True,
            )
        )

    conn_name = conn
    conn = request.getfixturevalue(conn)
    query = sql_strings["read_named_parameters"][flavor(conn_name)]
    params = {"name": "Iris-setosa", "length": 5.1}
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            iris_frame = pandasSQL.read_query(query, params=params)
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_sql_iris_no_parameter_with_percent(conn, request, sql_strings):
    if "mysql" in conn or ("postgresql" in conn and "adbc" not in conn):
        request.applymarker(pytest.mark.xfail(reason="broken test"))

    conn_name = conn
    conn = request.getfixturevalue(conn)

    query = sql_strings["read_no_parameters_with_percent"][flavor(conn_name)]
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            iris_frame = pandasSQL.read_query(query, params=None)
    check_iris_frame(iris_frame)


# -----------------------------------------------------------------------------
# -- Testing the public API


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_api_read_sql_view(conn, request):
    conn = request.getfixturevalue(conn)
    iris_frame = sql.read_sql_query("SELECT * FROM iris_view", conn)
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_api_read_sql_with_chunksize_no_result(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="chunksize argument NotImplemented with ADBC")
        )
    conn = request.getfixturevalue(conn)
    query = 'SELECT * FROM iris_view WHERE "SepalLength" < 0.0'
    with_batch = sql.read_sql_query(query, conn, chunksize=5)
    without_batch = sql.read_sql_query(query, conn)
    tm.assert_frame_equal(concat(with_batch), without_batch)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql(conn, request, test_frame1):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame1", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame1")

    sql.to_sql(test_frame1, "test_frame1", conn)
    assert sql.has_table("test_frame1", conn)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_fail(conn, request, test_frame1):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame2", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame2")

    sql.to_sql(test_frame1, "test_frame2", conn, if_exists="fail")
    assert sql.has_table("test_frame2", conn)

    msg = "Table 'test_frame2' already exists"
    with pytest.raises(ValueError, match=msg):
        sql.to_sql(test_frame1, "test_frame2", conn, if_exists="fail")


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_replace(conn, request, test_frame1):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame3", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame3")

    sql.to_sql(test_frame1, "test_frame3", conn, if_exists="fail")
    # Add to table again
    sql.to_sql(test_frame1, "test_frame3", conn, if_exists="replace")
    assert sql.has_table("test_frame3", conn)

    num_entries = len(test_frame1)
    num_rows = count_rows(conn, "test_frame3")

    assert num_rows == num_entries


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_append(conn, request, test_frame1):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame4", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame4")

    assert sql.to_sql(test_frame1, "test_frame4", conn, if_exists="fail") == 4

    # Add to table again
    assert sql.to_sql(test_frame1, "test_frame4", conn, if_exists="append") == 4
    assert sql.has_table("test_frame4", conn)

    num_entries = 2 * len(test_frame1)
    num_rows = count_rows(conn, "test_frame4")

    assert num_rows == num_entries


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_type_mapping(conn, request, test_frame3):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame5", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame5")

    sql.to_sql(test_frame3, "test_frame5", conn, index=False)
    result = sql.read_sql("SELECT * FROM test_frame5", conn)

    tm.assert_frame_equal(test_frame3, result)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_series(conn, request):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_series", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_series")

    s = Series(np.arange(5, dtype="int64"), name="series")
    sql.to_sql(s, "test_series", conn, index=False)
    s2 = sql.read_sql_query("SELECT * FROM test_series", conn)
    tm.assert_frame_equal(s.to_frame(), s2)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_roundtrip(conn, request, test_frame1):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame_roundtrip", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame_roundtrip")

    sql.to_sql(test_frame1, "test_frame_roundtrip", con=conn)
    result = sql.read_sql_query("SELECT * FROM test_frame_roundtrip", con=conn)

    # HACK!
    if "adbc" in conn_name:
        result = result.rename(columns={"__index_level_0__": "level_0"})
    result.index = test_frame1.index
    result.set_index("level_0", inplace=True)
    result.index.astype(int)
    result.index.name = None
    tm.assert_frame_equal(result, test_frame1)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_roundtrip_chunksize(conn, request, test_frame1):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="chunksize argument NotImplemented with ADBC")
        )
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_frame_roundtrip", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_frame_roundtrip")

    sql.to_sql(
        test_frame1,
        "test_frame_roundtrip",
        con=conn,
        index=False,
        chunksize=2,
    )
    result = sql.read_sql_query("SELECT * FROM test_frame_roundtrip", con=conn)
    tm.assert_frame_equal(result, test_frame1)


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_api_execute_sql(conn, request):
    # drop_sql = "DROP TABLE IF EXISTS test"  # should already be done
    conn = request.getfixturevalue(conn)
    with sql.pandasSQL_builder(conn) as pandas_sql:
        iris_results = pandas_sql.execute("SELECT * FROM iris")
        row = iris_results.fetchone()
        iris_results.close()
    assert list(row) == [5.1, 3.5, 1.4, 0.2, "Iris-setosa"]


@pytest.mark.parametrize("conn", all_connectable_types)
def test_api_date_parsing(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    # Test date parsing in read_sql
    # No Parsing
    df = sql.read_sql_query("SELECT * FROM types", conn)
    if not ("mysql" in conn_name or "postgres" in conn_name):
        assert not issubclass(df.DateCol.dtype.type, np.datetime64)

    df = sql.read_sql_query("SELECT * FROM types", conn, parse_dates=["DateCol"])
    assert issubclass(df.DateCol.dtype.type, np.datetime64)
    assert df.DateCol.tolist() == [
        Timestamp(2000, 1, 3, 0, 0, 0),
        Timestamp(2000, 1, 4, 0, 0, 0),
    ]

    df = sql.read_sql_query(
        "SELECT * FROM types",
        conn,
        parse_dates={"DateCol": "%Y-%m-%d %H:%M:%S"},
    )
    assert issubclass(df.DateCol.dtype.type, np.datetime64)
    assert df.DateCol.tolist() == [
        Timestamp(2000, 1, 3, 0, 0, 0),
        Timestamp(2000, 1, 4, 0, 0, 0),
    ]

    df = sql.read_sql_query("SELECT * FROM types", conn, parse_dates=["IntDateCol"])
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)
    assert df.IntDateCol.tolist() == [
        Timestamp(1986, 12, 25, 0, 0, 0),
        Timestamp(2013, 1, 1, 0, 0, 0),
    ]

    df = sql.read_sql_query(
        "SELECT * FROM types", conn, parse_dates={"IntDateCol": "s"}
    )
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)
    assert df.IntDateCol.tolist() == [
        Timestamp(1986, 12, 25, 0, 0, 0),
        Timestamp(2013, 1, 1, 0, 0, 0),
    ]

    df = sql.read_sql_query(
        "SELECT * FROM types",
        conn,
        parse_dates={"IntDateOnlyCol": "%Y%m%d"},
    )
    assert issubclass(df.IntDateOnlyCol.dtype.type, np.datetime64)
    assert df.IntDateOnlyCol.tolist() == [
        Timestamp("2010-10-10"),
        Timestamp("2010-12-12"),
    ]


@pytest.mark.parametrize("conn", all_connectable_types)
@pytest.mark.parametrize("error", ["ignore", "raise", "coerce"])
@pytest.mark.parametrize(
    "read_sql, text, mode",
    [
        (sql.read_sql, "SELECT * FROM types", ("sqlalchemy", "fallback")),
        (sql.read_sql, "types", ("sqlalchemy")),
        (
            sql.read_sql_query,
            "SELECT * FROM types",
            ("sqlalchemy", "fallback"),
        ),
        (sql.read_sql_table, "types", ("sqlalchemy")),
    ],
)
def test_api_custom_dateparsing_error(
    conn, request, read_sql, text, mode, error, types_data_frame
):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if text == "types" and conn_name == "sqlite_buildin_types":
        request.applymarker(
            pytest.mark.xfail(reason="failing combination of arguments")
        )

    expected = types_data_frame.astype({"DateCol": "datetime64[ns]"})

    result = read_sql(
        text,
        con=conn,
        parse_dates={
            "DateCol": {"errors": error},
        },
    )
    if "postgres" in conn_name:
        # TODO: clean up types_data_frame fixture
        result["BoolCol"] = result["BoolCol"].astype(int)
        result["BoolColWithNull"] = result["BoolColWithNull"].astype(float)

    if conn_name == "postgresql_adbc_types":
        expected = expected.astype(
            {
                "IntDateCol": "int32",
                "IntDateOnlyCol": "int32",
                "IntCol": "int32",
            }
        )

        if not pa_version_under13p0:
            # TODO: is this astype safe?
            expected["DateCol"] = expected["DateCol"].astype("datetime64[us]")

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable_types)
def test_api_date_and_index(conn, request):
    # Test case where same column appears in parse_date and index_col
    conn = request.getfixturevalue(conn)
    df = sql.read_sql_query(
        "SELECT * FROM types",
        conn,
        index_col="DateCol",
        parse_dates=["DateCol", "IntDateCol"],
    )

    assert issubclass(df.index.dtype.type, np.datetime64)
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_timedelta(conn, request):
    # see #6921
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_timedelta", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_timedelta")

    df = to_timedelta(Series(["00:00:01", "00:00:03"], name="foo")).to_frame()

    if conn_name == "sqlite_adbc_conn":
        request.node.add_marker(
            pytest.mark.xfail(
                reason="sqlite ADBC driver doesn't implement timedelta",
            )
        )

    if "adbc" in conn_name:
        if pa_version_under14p1:
            exp_warning = DeprecationWarning
        else:
            exp_warning = None
    else:
        exp_warning = UserWarning

    with tm.assert_produces_warning(exp_warning, check_stacklevel=False):
        result_count = df.to_sql(name="test_timedelta", con=conn)
    assert result_count == 2
    result = sql.read_sql_query("SELECT * FROM test_timedelta", conn)

    if conn_name == "postgresql_adbc_conn":
        # TODO: Postgres stores an INTERVAL, which ADBC reads as a Month-Day-Nano
        # Interval; the default pandas type mapper maps this to a DateOffset
        # but maybe we should try and restore the timedelta here?
        expected = Series(
            [
                pd.DateOffset(months=0, days=0, microseconds=1000000, nanoseconds=0),
                pd.DateOffset(months=0, days=0, microseconds=3000000, nanoseconds=0),
            ],
            name="foo",
        )
    else:
        expected = df["foo"].astype("int64")
    tm.assert_series_equal(result["foo"], expected)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_complex_raises(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = DataFrame({"a": [1 + 1j, 2j]})

    if "adbc" in conn_name:
        msg = "datatypes not supported"
    else:
        msg = "Complex datatypes not supported"
    with pytest.raises(ValueError, match=msg):
        assert df.to_sql("test_complex", con=conn) is None


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize(
    "index_name,index_label,expected",
    [
        # no index name, defaults to 'index'
        (None, None, "index"),
        # specifying index_label
        (None, "other_label", "other_label"),
        # using the index name
        ("index_name", None, "index_name"),
        # has index name, but specifying index_label
        ("index_name", "other_label", "other_label"),
        # index name is integer
        (0, None, "0"),
        # index name is None but index label is integer
        (None, 0, "0"),
    ],
)
def test_api_to_sql_index_label(conn, request, index_name, index_label, expected):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="index_label argument NotImplemented with ADBC")
        )
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_index_label", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_index_label")

    temp_frame = DataFrame({"col1": range(4)})
    temp_frame.index.name = index_name
    query = "SELECT * FROM test_index_label"
    sql.to_sql(temp_frame, "test_index_label", conn, index_label=index_label)
    frame = sql.read_sql_query(query, conn)
    assert frame.columns[0] == expected


@pytest.mark.parametrize("conn", all_connectable)
def test_api_to_sql_index_label_multiindex(conn, request):
    conn_name = conn
    if "mysql" in conn_name:
        request.applymarker(
            pytest.mark.xfail(
                reason="MySQL can fail using TEXT without length as key", strict=False
            )
        )
    elif "adbc" in conn_name:
        request.node.add_marker(
            pytest.mark.xfail(reason="index_label argument NotImplemented with ADBC")
        )

    conn = request.getfixturevalue(conn)
    if sql.has_table("test_index_label", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_index_label")

    expected_row_count = 4
    temp_frame = DataFrame(
        {"col1": range(4)},
        index=MultiIndex.from_product([("A0", "A1"), ("B0", "B1")]),
    )

    # no index name, defaults to 'level_0' and 'level_1'
    result = sql.to_sql(temp_frame, "test_index_label", conn)
    assert result == expected_row_count
    frame = sql.read_sql_query("SELECT * FROM test_index_label", conn)
    assert frame.columns[0] == "level_0"
    assert frame.columns[1] == "level_1"

    # specifying index_label
    result = sql.to_sql(
        temp_frame,
        "test_index_label",
        conn,
        if_exists="replace",
        index_label=["A", "B"],
    )
    assert result == expected_row_count
    frame = sql.read_sql_query("SELECT * FROM test_index_label", conn)
    assert frame.columns[:2].tolist() == ["A", "B"]

    # using the index name
    temp_frame.index.names = ["A", "B"]
    result = sql.to_sql(temp_frame, "test_index_label", conn, if_exists="replace")
    assert result == expected_row_count
    frame = sql.read_sql_query("SELECT * FROM test_index_label", conn)
    assert frame.columns[:2].tolist() == ["A", "B"]

    # has index name, but specifying index_label
    result = sql.to_sql(
        temp_frame,
        "test_index_label",
        conn,
        if_exists="replace",
        index_label=["C", "D"],
    )
    assert result == expected_row_count
    frame = sql.read_sql_query("SELECT * FROM test_index_label", conn)
    assert frame.columns[:2].tolist() == ["C", "D"]

    msg = "Length of 'index_label' should match number of levels, which is 2"
    with pytest.raises(ValueError, match=msg):
        sql.to_sql(
            temp_frame,
            "test_index_label",
            conn,
            if_exists="replace",
            index_label="C",
        )


@pytest.mark.parametrize("conn", all_connectable)
def test_api_multiindex_roundtrip(conn, request):
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_multiindex_roundtrip", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_multiindex_roundtrip")

    df = DataFrame.from_records(
        [(1, 2.1, "line1"), (2, 1.5, "line2")],
        columns=["A", "B", "C"],
        index=["A", "B"],
    )

    df.to_sql(name="test_multiindex_roundtrip", con=conn)
    result = sql.read_sql_query(
        "SELECT * FROM test_multiindex_roundtrip", conn, index_col=["A", "B"]
    )
    tm.assert_frame_equal(df, result, check_index_type=True)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize(
    "dtype",
    [
        None,
        int,
        float,
        {"A": int, "B": float},
    ],
)
def test_api_dtype_argument(conn, request, dtype):
    # GH10285 Add dtype argument to read_sql_query
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_dtype_argument", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_dtype_argument")

    df = DataFrame([[1.2, 3.4], [5.6, 7.8]], columns=["A", "B"])
    assert df.to_sql(name="test_dtype_argument", con=conn) == 2

    expected = df.astype(dtype)

    if "postgres" in conn_name:
        query = 'SELECT "A", "B" FROM test_dtype_argument'
    else:
        query = "SELECT A, B FROM test_dtype_argument"
    result = sql.read_sql_query(query, con=conn, dtype=dtype)

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_integer_col_names(conn, request):
    conn = request.getfixturevalue(conn)
    df = DataFrame([[1, 2], [3, 4]], columns=[0, 1])
    sql.to_sql(df, "test_frame_integer_col_names", conn, if_exists="replace")


@pytest.mark.parametrize("conn", all_connectable)
def test_api_get_schema(conn, request, test_frame1):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'get_schema' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn = request.getfixturevalue(conn)
    create_sql = sql.get_schema(test_frame1, "test", con=conn)
    assert "CREATE" in create_sql


@pytest.mark.parametrize("conn", all_connectable)
def test_api_get_schema_with_schema(conn, request, test_frame1):
    # GH28486
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'get_schema' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn = request.getfixturevalue(conn)
    create_sql = sql.get_schema(test_frame1, "test", con=conn, schema="pypi")
    assert "CREATE TABLE pypi." in create_sql


@pytest.mark.parametrize("conn", all_connectable)
def test_api_get_schema_dtypes(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'get_schema' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn_name = conn
    conn = request.getfixturevalue(conn)
    float_frame = DataFrame({"a": [1.1, 1.2], "b": [2.1, 2.2]})

    if conn_name == "sqlite_buildin":
        dtype = "INTEGER"
    else:
        from sqlalchemy import Integer

        dtype = Integer
    create_sql = sql.get_schema(float_frame, "test", con=conn, dtype={"b": dtype})
    assert "CREATE" in create_sql
    assert "INTEGER" in create_sql


@pytest.mark.parametrize("conn", all_connectable)
def test_api_get_schema_keys(conn, request, test_frame1):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="'get_schema' not implemented for ADBC drivers",
                strict=True,
            )
        )
    conn_name = conn
    conn = request.getfixturevalue(conn)
    frame = DataFrame({"Col1": [1.1, 1.2], "Col2": [2.1, 2.2]})
    create_sql = sql.get_schema(frame, "test", con=conn, keys="Col1")

    if "mysql" in conn_name:
        constraint_sentence = "CONSTRAINT test_pk PRIMARY KEY (`Col1`)"
    else:
        constraint_sentence = 'CONSTRAINT test_pk PRIMARY KEY ("Col1")'
    assert constraint_sentence in create_sql

    # multiple columns as key (GH10385)
    create_sql = sql.get_schema(test_frame1, "test", con=conn, keys=["A", "B"])
    if "mysql" in conn_name:
        constraint_sentence = "CONSTRAINT test_pk PRIMARY KEY (`A`, `B`)"
    else:
        constraint_sentence = 'CONSTRAINT test_pk PRIMARY KEY ("A", "B")'
    assert constraint_sentence in create_sql


@pytest.mark.parametrize("conn", all_connectable)
def test_api_chunksize_read(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="chunksize argument NotImplemented with ADBC")
        )
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_chunksize", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_chunksize")

    df = DataFrame(
        np.random.default_rng(2).standard_normal((22, 5)), columns=list("abcde")
    )
    df.to_sql(name="test_chunksize", con=conn, index=False)

    # reading the query in one time
    res1 = sql.read_sql_query("select * from test_chunksize", conn)

    # reading the query in chunks with read_sql_query
    res2 = DataFrame()
    i = 0
    sizes = [5, 5, 5, 5, 2]

    for chunk in sql.read_sql_query("select * from test_chunksize", conn, chunksize=5):
        res2 = concat([res2, chunk], ignore_index=True)
        assert len(chunk) == sizes[i]
        i += 1

    tm.assert_frame_equal(res1, res2)

    # reading the query in chunks with read_sql_query
    if conn_name == "sqlite_buildin":
        with pytest.raises(NotImplementedError, match=""):
            sql.read_sql_table("test_chunksize", conn, chunksize=5)
    else:
        res3 = DataFrame()
        i = 0
        sizes = [5, 5, 5, 5, 2]

        for chunk in sql.read_sql_table("test_chunksize", conn, chunksize=5):
            res3 = concat([res3, chunk], ignore_index=True)
            assert len(chunk) == sizes[i]
            i += 1

        tm.assert_frame_equal(res1, res3)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_categorical(conn, request):
    if conn == "postgresql_adbc_conn":
        adbc = import_optional_dependency("adbc_driver_postgresql", errors="ignore")
        if adbc is not None and Version(adbc.__version__) < Version("0.9.0"):
            request.node.add_marker(
                pytest.mark.xfail(
                    reason="categorical dtype not implemented for ADBC postgres driver",
                    strict=True,
                )
            )
    # GH8624
    # test that categorical gets written correctly as dense column
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_categorical", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_categorical")

    df = DataFrame(
        {
            "person_id": [1, 2, 3],
            "person_name": ["John P. Doe", "Jane Dove", "John P. Doe"],
        }
    )
    df2 = df.copy()
    df2["person_name"] = df2["person_name"].astype("category")

    df2.to_sql(name="test_categorical", con=conn, index=False)
    res = sql.read_sql_query("SELECT * FROM test_categorical", conn)

    tm.assert_frame_equal(res, df)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_unicode_column_name(conn, request):
    # GH 11431
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_unicode", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_unicode")

    df = DataFrame([[1, 2], [3, 4]], columns=["\xe9", "b"])
    df.to_sql(name="test_unicode", con=conn, index=False)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_escaped_table_name(conn, request):
    # GH 13206
    conn_name = conn
    conn = request.getfixturevalue(conn)
    if sql.has_table("d1187b08-4943-4c8d-a7f6", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("d1187b08-4943-4c8d-a7f6")

    df = DataFrame({"A": [0, 1, 2], "B": [0.2, np.nan, 5.6]})
    df.to_sql(name="d1187b08-4943-4c8d-a7f6", con=conn, index=False)

    if "postgres" in conn_name:
        query = 'SELECT * FROM "d1187b08-4943-4c8d-a7f6"'
    else:
        query = "SELECT * FROM `d1187b08-4943-4c8d-a7f6`"
    res = sql.read_sql_query(query, conn)

    tm.assert_frame_equal(res, df)


@pytest.mark.parametrize("conn", all_connectable)
def test_api_read_sql_duplicate_columns(conn, request):
    # GH#53117
    if "adbc" in conn:
        pa = pytest.importorskip("pyarrow")
        if not (
            Version(pa.__version__) >= Version("16.0")
            and conn in ["sqlite_adbc_conn", "postgresql_adbc_conn"]
        ):
            request.node.add_marker(
                pytest.mark.xfail(
                    reason="pyarrow->pandas throws ValueError", strict=True
                )
            )
    conn = request.getfixturevalue(conn)
    if sql.has_table("test_table", conn):
        with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
            pandasSQL.drop_table("test_table")

    df = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3], "c": 1})
    df.to_sql(name="test_table", con=conn, index=False)

    result = pd.read_sql("SELECT a, b, a +1 as a, c FROM test_table", conn)
    expected = DataFrame(
        [[1, 0.1, 2, 1], [2, 0.2, 3, 1], [3, 0.3, 4, 1]],
        columns=["a", "b", "a", "c"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable)
def test_read_table_columns(conn, request, test_frame1):
    # test columns argument in read_table
    conn_name = conn
    if conn_name == "sqlite_buildin":
        request.applymarker(pytest.mark.xfail(reason="Not Implemented"))

    conn = request.getfixturevalue(conn)
    sql.to_sql(test_frame1, "test_frame", conn)

    cols = ["A", "B"]

    result = sql.read_sql_table("test_frame", conn, columns=cols)
    assert result.columns.tolist() == cols


@pytest.mark.parametrize("conn", all_connectable)
def test_read_table_index_col(conn, request, test_frame1):
    # test columns argument in read_table
    conn_name = conn
    if conn_name == "sqlite_buildin":
        request.applymarker(pytest.mark.xfail(reason="Not Implemented"))

    conn = request.getfixturevalue(conn)
    sql.to_sql(test_frame1, "test_frame", conn)

    result = sql.read_sql_table("test_frame", conn, index_col="index")
    assert result.index.names == ["index"]

    result = sql.read_sql_table("test_frame", conn, index_col=["A", "B"])
    assert result.index.names == ["A", "B"]

    result = sql.read_sql_table(
        "test_frame", conn, index_col=["A", "B"], columns=["C", "D"]
    )
    assert result.index.names == ["A", "B"]
    assert result.columns.tolist() == ["C", "D"]


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_read_sql_delegate(conn, request):
    if conn == "sqlite_buildin_iris":
        request.applymarker(
            pytest.mark.xfail(
                reason="sqlite_buildin connection does not implement read_sql_table"
            )
        )

    conn = request.getfixturevalue(conn)
    iris_frame1 = sql.read_sql_query("SELECT * FROM iris", conn)
    iris_frame2 = sql.read_sql("SELECT * FROM iris", conn)
    tm.assert_frame_equal(iris_frame1, iris_frame2)

    iris_frame1 = sql.read_sql_table("iris", conn)
    iris_frame2 = sql.read_sql("iris", conn)
    tm.assert_frame_equal(iris_frame1, iris_frame2)


def test_not_reflect_all_tables(sqlite_conn):
    conn = sqlite_conn
    from sqlalchemy import text
    from sqlalchemy.engine import Engine

    # create invalid table
    query_list = [
        text("CREATE TABLE invalid (x INTEGER, y UNKNOWN);"),
        text("CREATE TABLE other_table (x INTEGER, y INTEGER);"),
    ]

    for query in query_list:
        if isinstance(conn, Engine):
            with conn.connect() as conn:
                with conn.begin():
                    conn.execute(query)
        else:
            with conn.begin():
                conn.execute(query)

    with tm.assert_produces_warning(None):
        sql.read_sql_table("other_table", conn)
        sql.read_sql_query("SELECT * FROM other_table", conn)


@pytest.mark.parametrize("conn", all_connectable)
def test_warning_case_insensitive_table_name(conn, request, test_frame1):
    conn_name = conn
    if conn_name == "sqlite_buildin" or "adbc" in conn_name:
        request.applymarker(pytest.mark.xfail(reason="Does not raise warning"))

    conn = request.getfixturevalue(conn)
    # see gh-7815
    with tm.assert_produces_warning(
        UserWarning,
        match=(
            r"The provided table name 'TABLE1' is not found exactly as such in "
            r"the database after writing the table, possibly due to case "
            r"sensitivity issues. Consider using lower case table names."
        ),
    ):
        with sql.SQLDatabase(conn) as db:
            db.check_case_sensitive("TABLE1", "")

    # Test that the warning is certainly NOT triggered in a normal case.
    with tm.assert_produces_warning(None):
        test_frame1.to_sql(name="CaseSensitive", con=conn)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_sqlalchemy_type_mapping(conn, request):
    conn = request.getfixturevalue(conn)
    from sqlalchemy import TIMESTAMP

    # Test Timestamp objects (no datetime64 because of timezone) (GH9085)
    df = DataFrame(
        {"time": to_datetime(["2014-12-12 01:54", "2014-12-11 02:54"], utc=True)}
    )
    with sql.SQLDatabase(conn) as db:
        table = sql.SQLTable("test_type", db, frame=df)
        # GH 9086: TIMESTAMP is the suggested type for datetimes with timezones
        assert isinstance(table.table.c["time"].type, TIMESTAMP)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
@pytest.mark.parametrize(
    "integer, expected",
    [
        ("int8", "SMALLINT"),
        ("Int8", "SMALLINT"),
        ("uint8", "SMALLINT"),
        ("UInt8", "SMALLINT"),
        ("int16", "SMALLINT"),
        ("Int16", "SMALLINT"),
        ("uint16", "INTEGER"),
        ("UInt16", "INTEGER"),
        ("int32", "INTEGER"),
        ("Int32", "INTEGER"),
        ("uint32", "BIGINT"),
        ("UInt32", "BIGINT"),
        ("int64", "BIGINT"),
        ("Int64", "BIGINT"),
        (int, "BIGINT" if np.dtype(int).name == "int64" else "INTEGER"),
    ],
)
def test_sqlalchemy_integer_mapping(conn, request, integer, expected):
    # GH35076 Map pandas integer to optimal SQLAlchemy integer type
    conn = request.getfixturevalue(conn)
    df = DataFrame([0, 1], columns=["a"], dtype=integer)
    with sql.SQLDatabase(conn) as db:
        table = sql.SQLTable("test_type", db, frame=df)

        result = str(table.table.c.a.type)
    assert result == expected


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
@pytest.mark.parametrize("integer", ["uint64", "UInt64"])
def test_sqlalchemy_integer_overload_mapping(conn, request, integer):
    conn = request.getfixturevalue(conn)
    # GH35076 Map pandas integer to optimal SQLAlchemy integer type
    df = DataFrame([0, 1], columns=["a"], dtype=integer)
    with sql.SQLDatabase(conn) as db:
        with pytest.raises(
            ValueError, match="Unsigned 64 bit integer datatype is not supported"
        ):
            sql.SQLTable("test_type", db, frame=df)


@pytest.mark.parametrize("conn", all_connectable)
def test_database_uri_string(conn, request, test_frame1):
    pytest.importorskip("sqlalchemy")
    conn = request.getfixturevalue(conn)
    # Test read_sql and .to_sql method with a database URI (GH10654)
    # db_uri = 'sqlite:///:memory:' # raises
    # sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) near
    # "iris": syntax error [SQL: 'iris']
    with tm.ensure_clean() as name:
        db_uri = "sqlite:///" + name
        table = "iris"
        test_frame1.to_sql(name=table, con=db_uri, if_exists="replace", index=False)
        test_frame2 = sql.read_sql(table, db_uri)
        test_frame3 = sql.read_sql_table(table, db_uri)
        query = "SELECT * FROM iris"
        test_frame4 = sql.read_sql_query(query, db_uri)
    tm.assert_frame_equal(test_frame1, test_frame2)
    tm.assert_frame_equal(test_frame1, test_frame3)
    tm.assert_frame_equal(test_frame1, test_frame4)


@td.skip_if_installed("pg8000")
@pytest.mark.parametrize("conn", all_connectable)
def test_pg8000_sqlalchemy_passthrough_error(conn, request):
    pytest.importorskip("sqlalchemy")
    conn = request.getfixturevalue(conn)
    # using driver that will not be installed on CI to trigger error
    # in sqlalchemy.create_engine -> test passing of this error to user
    db_uri = "postgresql+pg8000://user:pass@host/dbname"
    with pytest.raises(ImportError, match="pg8000"):
        sql.read_sql("select * from table", db_uri)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_query_by_text_obj(conn, request):
    # WIP : GH10846
    conn_name = conn
    conn = request.getfixturevalue(conn)
    from sqlalchemy import text

    if "postgres" in conn_name:
        name_text = text('select * from iris where "Name"=:name')
    else:
        name_text = text("select * from iris where name=:name")
    iris_df = sql.read_sql(name_text, conn, params={"name": "Iris-versicolor"})
    all_names = set(iris_df["Name"])
    assert all_names == {"Iris-versicolor"}


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_query_by_select_obj(conn, request):
    conn = request.getfixturevalue(conn)
    # WIP : GH10846
    from sqlalchemy import (
        bindparam,
        select,
    )

    iris = iris_table_metadata()
    name_select = select(iris).where(iris.c.Name == bindparam("name"))
    iris_df = sql.read_sql(name_select, conn, params={"name": "Iris-setosa"})
    all_names = set(iris_df["Name"])
    assert all_names == {"Iris-setosa"}


@pytest.mark.parametrize("conn", all_connectable)
def test_column_with_percentage(conn, request):
    # GH 37157
    conn_name = conn
    if conn_name == "sqlite_buildin":
        request.applymarker(pytest.mark.xfail(reason="Not Implemented"))

    conn = request.getfixturevalue(conn)
    df = DataFrame({"A": [0, 1, 2], "%_variation": [3, 4, 5]})
    df.to_sql(name="test_column_percentage", con=conn, index=False)

    res = sql.read_sql_table("test_column_percentage", conn)

    tm.assert_frame_equal(res, df)


def test_sql_open_close(test_frame3):
    # Test if the IO in the database still work if the connection closed
    # between the writing and reading (as in many real situations).

    with tm.ensure_clean() as name:
        with closing(sqlite3.connect(name)) as conn:
            assert sql.to_sql(test_frame3, "test_frame3_legacy", conn, index=False) == 4

        with closing(sqlite3.connect(name)) as conn:
            result = sql.read_sql_query("SELECT * FROM test_frame3_legacy;", conn)

    tm.assert_frame_equal(test_frame3, result)


@td.skip_if_installed("sqlalchemy")
def test_con_string_import_error():
    conn = "mysql://root@localhost/pandas"
    msg = "Using URI string without sqlalchemy installed"
    with pytest.raises(ImportError, match=msg):
        sql.read_sql("SELECT * FROM iris", conn)


@td.skip_if_installed("sqlalchemy")
def test_con_unknown_dbapi2_class_does_not_error_without_sql_alchemy_installed():
    class MockSqliteConnection:
        def __init__(self, *args, **kwargs) -> None:
            self.conn = sqlite3.Connection(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def close(self):
            self.conn.close()

    with contextlib.closing(MockSqliteConnection(":memory:")) as conn:
        with tm.assert_produces_warning(UserWarning):
            sql.read_sql("SELECT 1", conn)


def test_sqlite_read_sql_delegate(sqlite_buildin_iris):
    conn = sqlite_buildin_iris
    iris_frame1 = sql.read_sql_query("SELECT * FROM iris", conn)
    iris_frame2 = sql.read_sql("SELECT * FROM iris", conn)
    tm.assert_frame_equal(iris_frame1, iris_frame2)

    msg = "Execution failed on sql 'iris': near \"iris\": syntax error"
    with pytest.raises(sql.DatabaseError, match=msg):
        sql.read_sql("iris", conn)


def test_get_schema2(test_frame1):
    # without providing a connection object (available for backwards comp)
    create_sql = sql.get_schema(test_frame1, "test")
    assert "CREATE" in create_sql


def test_sqlite_type_mapping(sqlite_buildin):
    # Test Timestamp objects (no datetime64 because of timezone) (GH9085)
    conn = sqlite_buildin
    df = DataFrame(
        {"time": to_datetime(["2014-12-12 01:54", "2014-12-11 02:54"], utc=True)}
    )
    db = sql.SQLiteDatabase(conn)
    table = sql.SQLiteTable("test_type", db, frame=df)
    schema = table.sql_schema()
    for col in schema.split("\n"):
        if col.split()[0].strip('"') == "time":
            assert col.split()[1] == "TIMESTAMP"


# -----------------------------------------------------------------------------
# -- Database flavor specific tests


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_create_table(conn, request):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn = request.getfixturevalue(conn)

    from sqlalchemy import inspect

    temp_frame = DataFrame({"one": [1.0, 2.0, 3.0, 4.0], "two": [4.0, 3.0, 2.0, 1.0]})
    with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
        assert pandasSQL.to_sql(temp_frame, "temp_frame") == 4

    insp = inspect(conn)
    assert insp.has_table("temp_frame")

    # Cleanup
    with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
        pandasSQL.drop_table("temp_frame")


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_drop_table(conn, request):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn = request.getfixturevalue(conn)

    from sqlalchemy import inspect

    temp_frame = DataFrame({"one": [1.0, 2.0, 3.0, 4.0], "two": [4.0, 3.0, 2.0, 1.0]})
    with sql.SQLDatabase(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            assert pandasSQL.to_sql(temp_frame, "temp_frame") == 4

        insp = inspect(conn)
        assert insp.has_table("temp_frame")

        with pandasSQL.run_transaction():
            pandasSQL.drop_table("temp_frame")
        try:
            insp.clear_cache()  # needed with SQLAlchemy 2.0, unavailable prior
        except AttributeError:
            pass
        assert not insp.has_table("temp_frame")


@pytest.mark.parametrize("conn", all_connectable)
def test_roundtrip(conn, request, test_frame1):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn_name = conn
    conn = request.getfixturevalue(conn)
    pandasSQL = pandasSQL_builder(conn)
    with pandasSQL.run_transaction():
        assert pandasSQL.to_sql(test_frame1, "test_frame_roundtrip") == 4
        result = pandasSQL.read_query("SELECT * FROM test_frame_roundtrip")

    if "adbc" in conn_name:
        result = result.rename(columns={"__index_level_0__": "level_0"})
    result.set_index("level_0", inplace=True)
    # result.index.astype(int)

    result.index.name = None

    tm.assert_frame_equal(result, test_frame1)


@pytest.mark.parametrize("conn", all_connectable_iris)
def test_execute_sql(conn, request):
    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            iris_results = pandasSQL.execute("SELECT * FROM iris")
            row = iris_results.fetchone()
            iris_results.close()
    assert list(row) == [5.1, 3.5, 1.4, 0.2, "Iris-setosa"]


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_sqlalchemy_read_table(conn, request):
    conn = request.getfixturevalue(conn)
    iris_frame = sql.read_sql_table("iris", con=conn)
    check_iris_frame(iris_frame)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_sqlalchemy_read_table_columns(conn, request):
    conn = request.getfixturevalue(conn)
    iris_frame = sql.read_sql_table(
        "iris", con=conn, columns=["SepalLength", "SepalLength"]
    )
    tm.assert_index_equal(iris_frame.columns, Index(["SepalLength", "SepalLength__1"]))


@pytest.mark.parametrize("conn", sqlalchemy_connectable_iris)
def test_read_table_absent_raises(conn, request):
    conn = request.getfixturevalue(conn)
    msg = "Table this_doesnt_exist not found"
    with pytest.raises(ValueError, match=msg):
        sql.read_sql_table("this_doesnt_exist", con=conn)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_types)
def test_sqlalchemy_default_type_conversion(conn, request):
    conn_name = conn
    if conn_name == "sqlite_str":
        pytest.skip("types tables not created in sqlite_str fixture")
    elif "mysql" in conn_name or "sqlite" in conn_name:
        request.applymarker(
            pytest.mark.xfail(reason="boolean dtype not inferred properly")
        )

    conn = request.getfixturevalue(conn)
    df = sql.read_sql_table("types", conn)

    assert issubclass(df.FloatCol.dtype.type, np.floating)
    assert issubclass(df.IntCol.dtype.type, np.integer)
    assert issubclass(df.BoolCol.dtype.type, np.bool_)

    # Int column with NA values stays as float
    assert issubclass(df.IntColWithNull.dtype.type, np.floating)
    # Bool column with NA values becomes object
    assert issubclass(df.BoolColWithNull.dtype.type, object)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_bigint(conn, request):
    # int64 should be converted to BigInteger, GH7433
    conn = request.getfixturevalue(conn)
    df = DataFrame(data={"i64": [2**62]})
    assert df.to_sql(name="test_bigint", con=conn, index=False) == 1
    result = sql.read_sql_table("test_bigint", conn)

    tm.assert_frame_equal(df, result)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_types)
def test_default_date_load(conn, request):
    conn_name = conn
    if conn_name == "sqlite_str":
        pytest.skip("types tables not created in sqlite_str fixture")
    elif "sqlite" in conn_name:
        request.applymarker(
            pytest.mark.xfail(reason="sqlite does not read date properly")
        )

    conn = request.getfixturevalue(conn)
    df = sql.read_sql_table("types", conn)

    assert issubclass(df.DateCol.dtype.type, np.datetime64)


@pytest.mark.parametrize("conn", postgresql_connectable)
@pytest.mark.parametrize("parse_dates", [None, ["DateColWithTz"]])
def test_datetime_with_timezone_query(conn, request, parse_dates):
    # edge case that converts postgresql datetime with time zone types
    # to datetime64[ns,psycopg2.tz.FixedOffsetTimezone..], which is ok
    # but should be more natural, so coerce to datetime64[ns] for now
    conn = request.getfixturevalue(conn)
    expected = create_and_load_postgres_datetz(conn)

    # GH11216
    df = read_sql_query("select * from datetz", conn, parse_dates=parse_dates)
    col = df.DateColWithTz
    tm.assert_series_equal(col, expected)


@pytest.mark.parametrize("conn", postgresql_connectable)
def test_datetime_with_timezone_query_chunksize(conn, request):
    conn = request.getfixturevalue(conn)
    expected = create_and_load_postgres_datetz(conn)

    df = concat(
        list(read_sql_query("select * from datetz", conn, chunksize=1)),
        ignore_index=True,
    )
    col = df.DateColWithTz
    tm.assert_series_equal(col, expected)


@pytest.mark.parametrize("conn", postgresql_connectable)
def test_datetime_with_timezone_table(conn, request):
    conn = request.getfixturevalue(conn)
    expected = create_and_load_postgres_datetz(conn)
    result = sql.read_sql_table("datetz", conn)
    tm.assert_frame_equal(result, expected.to_frame())


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_datetime_with_timezone_roundtrip(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    # GH 9086
    # Write datetimetz data to a db and read it back
    # For dbs that support timestamps with timezones, should get back UTC
    # otherwise naive data should be returned
    expected = DataFrame(
        {"A": date_range("2013-01-01 09:00:00", periods=3, tz="US/Pacific")}
    )
    assert expected.to_sql(name="test_datetime_tz", con=conn, index=False) == 3

    if "postgresql" in conn_name:
        # SQLAlchemy "timezones" (i.e. offsets) are coerced to UTC
        expected["A"] = expected["A"].dt.tz_convert("UTC")
    else:
        # Otherwise, timestamps are returned as local, naive
        expected["A"] = expected["A"].dt.tz_localize(None)

    result = sql.read_sql_table("test_datetime_tz", conn)
    tm.assert_frame_equal(result, expected)

    result = sql.read_sql_query("SELECT * FROM test_datetime_tz", conn)
    if "sqlite" in conn_name:
        # read_sql_query does not return datetime type like read_sql_table
        assert isinstance(result.loc[0, "A"], str)
        result["A"] = to_datetime(result["A"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_out_of_bounds_datetime(conn, request):
    # GH 26761
    conn = request.getfixturevalue(conn)
    data = DataFrame({"date": datetime(9999, 1, 1)}, index=[0])
    assert data.to_sql(name="test_datetime_obb", con=conn, index=False) == 1
    result = sql.read_sql_table("test_datetime_obb", conn)
    expected = DataFrame([pd.NaT], columns=["date"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_naive_datetimeindex_roundtrip(conn, request):
    # GH 23510
    # Ensure that a naive DatetimeIndex isn't converted to UTC
    conn = request.getfixturevalue(conn)
    dates = date_range("2018-01-01", periods=5, freq="6h")._with_freq(None)
    expected = DataFrame({"nums": range(5)}, index=dates)
    assert expected.to_sql(name="foo_table", con=conn, index_label="info_date") == 5
    result = sql.read_sql_table("foo_table", conn, index_col="info_date")
    # result index with gain a name from a set_index operation; expected
    tm.assert_frame_equal(result, expected, check_names=False)


@pytest.mark.parametrize("conn", sqlalchemy_connectable_types)
def test_date_parsing(conn, request):
    # No Parsing
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = sql.read_sql_table("types", conn)
    expected_type = object if "sqlite" in conn_name else np.datetime64
    assert issubclass(df.DateCol.dtype.type, expected_type)

    df = sql.read_sql_table("types", conn, parse_dates=["DateCol"])
    assert issubclass(df.DateCol.dtype.type, np.datetime64)

    df = sql.read_sql_table("types", conn, parse_dates={"DateCol": "%Y-%m-%d %H:%M:%S"})
    assert issubclass(df.DateCol.dtype.type, np.datetime64)

    df = sql.read_sql_table(
        "types",
        conn,
        parse_dates={"DateCol": {"format": "%Y-%m-%d %H:%M:%S"}},
    )
    assert issubclass(df.DateCol.dtype.type, np.datetime64)

    df = sql.read_sql_table("types", conn, parse_dates=["IntDateCol"])
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)

    df = sql.read_sql_table("types", conn, parse_dates={"IntDateCol": "s"})
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)

    df = sql.read_sql_table("types", conn, parse_dates={"IntDateCol": {"unit": "s"}})
    assert issubclass(df.IntDateCol.dtype.type, np.datetime64)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_datetime(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = DataFrame(
        {"A": date_range("2013-01-01 09:00:00", periods=3), "B": np.arange(3.0)}
    )
    assert df.to_sql(name="test_datetime", con=conn) == 3

    # with read_table -> type information from schema used
    result = sql.read_sql_table("test_datetime", conn)
    result = result.drop("index", axis=1)
    tm.assert_frame_equal(result, df)

    # with read_sql -> no type information -> sqlite has no native
    result = sql.read_sql_query("SELECT * FROM test_datetime", conn)
    result = result.drop("index", axis=1)
    if "sqlite" in conn_name:
        assert isinstance(result.loc[0, "A"], str)
        result["A"] = to_datetime(result["A"])
        tm.assert_frame_equal(result, df)
    else:
        tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_datetime_NaT(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = DataFrame(
        {"A": date_range("2013-01-01 09:00:00", periods=3), "B": np.arange(3.0)}
    )
    df.loc[1, "A"] = np.nan
    assert df.to_sql(name="test_datetime", con=conn, index=False) == 3

    # with read_table -> type information from schema used
    result = sql.read_sql_table("test_datetime", conn)
    tm.assert_frame_equal(result, df)

    # with read_sql -> no type information -> sqlite has no native
    result = sql.read_sql_query("SELECT * FROM test_datetime", conn)
    if "sqlite" in conn_name:
        assert isinstance(result.loc[0, "A"], str)
        result["A"] = to_datetime(result["A"], errors="coerce")
        tm.assert_frame_equal(result, df)
    else:
        tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_datetime_date(conn, request):
    # test support for datetime.date
    conn = request.getfixturevalue(conn)
    df = DataFrame([date(2014, 1, 1), date(2014, 1, 2)], columns=["a"])
    assert df.to_sql(name="test_date", con=conn, index=False) == 2
    res = read_sql_table("test_date", conn)
    result = res["a"]
    expected = to_datetime(df["a"])
    # comes back as datetime64
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_datetime_time(conn, request, sqlite_buildin):
    # test support for datetime.time
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = DataFrame([time(9, 0, 0), time(9, 1, 30)], columns=["a"])
    assert df.to_sql(name="test_time", con=conn, index=False) == 2
    res = read_sql_table("test_time", conn)
    tm.assert_frame_equal(res, df)

    # GH8341
    # first, use the fallback to have the sqlite adapter put in place
    sqlite_conn = sqlite_buildin
    assert sql.to_sql(df, "test_time2", sqlite_conn, index=False) == 2
    res = sql.read_sql_query("SELECT * FROM test_time2", sqlite_conn)
    ref = df.map(lambda _: _.strftime("%H:%M:%S.%f"))
    tm.assert_frame_equal(ref, res)  # check if adapter is in place
    # then test if sqlalchemy is unaffected by the sqlite adapter
    assert sql.to_sql(df, "test_time3", conn, index=False) == 2
    if "sqlite" in conn_name:
        res = sql.read_sql_query("SELECT * FROM test_time3", conn)
        ref = df.map(lambda _: _.strftime("%H:%M:%S.%f"))
        tm.assert_frame_equal(ref, res)
    res = sql.read_sql_table("test_time3", conn)
    tm.assert_frame_equal(df, res)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_mixed_dtype_insert(conn, request):
    # see GH6509
    conn = request.getfixturevalue(conn)
    s1 = Series(2**25 + 1, dtype=np.int32)
    s2 = Series(0.0, dtype=np.float32)
    df = DataFrame({"s1": s1, "s2": s2})

    # write and read again
    assert df.to_sql(name="test_read_write", con=conn, index=False) == 1
    df2 = sql.read_sql_table("test_read_write", conn)

    tm.assert_frame_equal(df, df2, check_dtype=False, check_exact=True)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_nan_numeric(conn, request):
    # NaNs in numeric float column
    conn = request.getfixturevalue(conn)
    df = DataFrame({"A": [0, 1, 2], "B": [0.2, np.nan, 5.6]})
    assert df.to_sql(name="test_nan", con=conn, index=False) == 3

    # with read_table
    result = sql.read_sql_table("test_nan", conn)
    tm.assert_frame_equal(result, df)

    # with read_sql
    result = sql.read_sql_query("SELECT * FROM test_nan", conn)
    tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_nan_fullcolumn(conn, request):
    # full NaN column (numeric float column)
    conn = request.getfixturevalue(conn)
    df = DataFrame({"A": [0, 1, 2], "B": [np.nan, np.nan, np.nan]})
    assert df.to_sql(name="test_nan", con=conn, index=False) == 3

    # with read_table
    result = sql.read_sql_table("test_nan", conn)
    tm.assert_frame_equal(result, df)

    # with read_sql -> not type info from table -> stays None
    df["B"] = df["B"].astype("object")
    df["B"] = None
    result = sql.read_sql_query("SELECT * FROM test_nan", conn)
    tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_nan_string(conn, request):
    # NaNs in string column
    conn = request.getfixturevalue(conn)
    df = DataFrame({"A": [0, 1, 2], "B": ["a", "b", np.nan]})
    assert df.to_sql(name="test_nan", con=conn, index=False) == 3

    # NaNs are coming back as None
    df.loc[2, "B"] = None

    # with read_table
    result = sql.read_sql_table("test_nan", conn)
    tm.assert_frame_equal(result, df)

    # with read_sql
    result = sql.read_sql_query("SELECT * FROM test_nan", conn)
    tm.assert_frame_equal(result, df)


@pytest.mark.parametrize("conn", all_connectable)
def test_to_sql_save_index(conn, request):
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(
                reason="ADBC implementation does not create index", strict=True
            )
        )
    conn_name = conn
    conn = request.getfixturevalue(conn)
    df = DataFrame.from_records(
        [(1, 2.1, "line1"), (2, 1.5, "line2")], columns=["A", "B", "C"], index=["A"]
    )

    tbl_name = "test_to_sql_saves_index"
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            assert pandasSQL.to_sql(df, tbl_name) == 2

    if conn_name in {"sqlite_buildin", "sqlite_str"}:
        ixs = sql.read_sql_query(
            "SELECT * FROM sqlite_master WHERE type = 'index' "
            f"AND tbl_name = '{tbl_name}'",
            conn,
        )
        ix_cols = []
        for ix_name in ixs.name:
            ix_info = sql.read_sql_query(f"PRAGMA index_info({ix_name})", conn)
            ix_cols.append(ix_info.name.tolist())
    else:
        from sqlalchemy import inspect

        insp = inspect(conn)

        ixs = insp.get_indexes(tbl_name)
        ix_cols = [i["column_names"] for i in ixs]

    assert ix_cols == [["A"]]


@pytest.mark.parametrize("conn", all_connectable)
def test_transactions(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)

    stmt = "CREATE TABLE test_trans (A INT, B TEXT)"
    if conn_name != "sqlite_buildin" and "adbc" not in conn_name:
        from sqlalchemy import text

        stmt = text(stmt)

    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction() as trans:
            trans.execute(stmt)


@pytest.mark.parametrize("conn", all_connectable)
def test_transaction_rollback(conn, request):
    conn_name = conn
    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction() as trans:
            stmt = "CREATE TABLE test_trans (A INT, B TEXT)"
            if "adbc" in conn_name or isinstance(pandasSQL, SQLiteDatabase):
                trans.execute(stmt)
            else:
                from sqlalchemy import text

                stmt = text(stmt)
                trans.execute(stmt)

        class DummyException(Exception):
            pass

        # Make sure when transaction is rolled back, no rows get inserted
        ins_sql = "INSERT INTO test_trans (A,B) VALUES (1, 'blah')"
        if isinstance(pandasSQL, SQLDatabase):
            from sqlalchemy import text

            ins_sql = text(ins_sql)
        try:
            with pandasSQL.run_transaction() as trans:
                trans.execute(ins_sql)
                raise DummyException("error")
        except DummyException:
            # ignore raised exception
            pass
        with pandasSQL.run_transaction():
            res = pandasSQL.read_query("SELECT * FROM test_trans")
        assert len(res) == 0

        # Make sure when transaction is committed, rows do get inserted
        with pandasSQL.run_transaction() as trans:
            trans.execute(ins_sql)
            res2 = pandasSQL.read_query("SELECT * FROM test_trans")
        assert len(res2) == 1


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_get_schema_create_table(conn, request, test_frame3):
    # Use a dataframe without a bool column, since MySQL converts bool to
    # TINYINT (which read_sql_table returns as an int and causes a dtype
    # mismatch)
    if conn == "sqlite_str":
        request.applymarker(
            pytest.mark.xfail(reason="test does not support sqlite_str fixture")
        )

    conn = request.getfixturevalue(conn)

    from sqlalchemy import text
    from sqlalchemy.engine import Engine

    tbl = "test_get_schema_create_table"
    create_sql = sql.get_schema(test_frame3, tbl, con=conn)
    blank_test_df = test_frame3.iloc[:0]

    create_sql = text(create_sql)
    if isinstance(conn, Engine):
        with conn.connect() as newcon:
            with newcon.begin():
                newcon.execute(create_sql)
    else:
        conn.execute(create_sql)
    returned_df = sql.read_sql_table(tbl, conn)
    tm.assert_frame_equal(returned_df, blank_test_df, check_index_type=False)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_dtype(conn, request):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn = request.getfixturevalue(conn)

    from sqlalchemy import (
        TEXT,
        String,
    )
    from sqlalchemy.schema import MetaData

    cols = ["A", "B"]
    data = [(0.8, True), (0.9, None)]
    df = DataFrame(data, columns=cols)
    assert df.to_sql(name="dtype_test", con=conn) == 2
    assert df.to_sql(name="dtype_test2", con=conn, dtype={"B": TEXT}) == 2
    meta = MetaData()
    meta.reflect(bind=conn)
    sqltype = meta.tables["dtype_test2"].columns["B"].type
    assert isinstance(sqltype, TEXT)
    msg = "The type of B is not a SQLAlchemy type"
    with pytest.raises(ValueError, match=msg):
        df.to_sql(name="error", con=conn, dtype={"B": str})

    # GH9083
    assert df.to_sql(name="dtype_test3", con=conn, dtype={"B": String(10)}) == 2
    meta.reflect(bind=conn)
    sqltype = meta.tables["dtype_test3"].columns["B"].type
    assert isinstance(sqltype, String)
    assert sqltype.length == 10

    # single dtype
    assert df.to_sql(name="single_dtype_test", con=conn, dtype=TEXT) == 2
    meta.reflect(bind=conn)
    sqltypea = meta.tables["single_dtype_test"].columns["A"].type
    sqltypeb = meta.tables["single_dtype_test"].columns["B"].type
    assert isinstance(sqltypea, TEXT)
    assert isinstance(sqltypeb, TEXT)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_notna_dtype(conn, request):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn_name = conn
    conn = request.getfixturevalue(conn)

    from sqlalchemy import (
        Boolean,
        DateTime,
        Float,
        Integer,
    )
    from sqlalchemy.schema import MetaData

    cols = {
        "Bool": Series([True, None]),
        "Date": Series([datetime(2012, 5, 1), None]),
        "Int": Series([1, None], dtype="object"),
        "Float": Series([1.1, None]),
    }
    df = DataFrame(cols)

    tbl = "notna_dtype_test"
    assert df.to_sql(name=tbl, con=conn) == 2
    _ = sql.read_sql_table(tbl, conn)
    meta = MetaData()
    meta.reflect(bind=conn)
    my_type = Integer if "mysql" in conn_name else Boolean
    col_dict = meta.tables[tbl].columns
    assert isinstance(col_dict["Bool"].type, my_type)
    assert isinstance(col_dict["Date"].type, DateTime)
    assert isinstance(col_dict["Int"].type, Integer)
    assert isinstance(col_dict["Float"].type, Float)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_double_precision(conn, request):
    if conn == "sqlite_str":
        pytest.skip("sqlite_str has no inspection system")

    conn = request.getfixturevalue(conn)

    from sqlalchemy import (
        BigInteger,
        Float,
        Integer,
    )
    from sqlalchemy.schema import MetaData

    V = 1.23456789101112131415

    df = DataFrame(
        {
            "f32": Series([V], dtype="float32"),
            "f64": Series([V], dtype="float64"),
            "f64_as_f32": Series([V], dtype="float64"),
            "i32": Series([5], dtype="int32"),
            "i64": Series([5], dtype="int64"),
        }
    )

    assert (
        df.to_sql(
            name="test_dtypes",
            con=conn,
            index=False,
            if_exists="replace",
            dtype={"f64_as_f32": Float(precision=23)},
        )
        == 1
    )
    res = sql.read_sql_table("test_dtypes", conn)

    # check precision of float64
    assert np.round(df["f64"].iloc[0], 14) == np.round(res["f64"].iloc[0], 14)

    # check sql types
    meta = MetaData()
    meta.reflect(bind=conn)
    col_dict = meta.tables["test_dtypes"].columns
    assert str(col_dict["f32"].type) == str(col_dict["f64_as_f32"].type)
    assert isinstance(col_dict["f32"].type, Float)
    assert isinstance(col_dict["f64"].type, Float)
    assert isinstance(col_dict["i32"].type, Integer)
    assert isinstance(col_dict["i64"].type, BigInteger)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_connectable_issue_example(conn, request):
    conn = request.getfixturevalue(conn)

    # This tests the example raised in issue
    # https://github.com/pandas-dev/pandas/issues/10104
    from sqlalchemy.engine import Engine

    def test_select(connection):
        query = "SELECT test_foo_data FROM test_foo_data"
        return sql.read_sql_query(query, con=connection)

    def test_append(connection, data):
        data.to_sql(name="test_foo_data", con=connection, if_exists="append")

    def test_connectable(conn):
        # https://github.com/sqlalchemy/sqlalchemy/commit/
        # 00b5c10846e800304caa86549ab9da373b42fa5d#r48323973
        foo_data = test_select(conn)
        test_append(conn, foo_data)

    def main(connectable):
        if isinstance(connectable, Engine):
            with connectable.connect() as conn:
                with conn.begin():
                    test_connectable(conn)
        else:
            test_connectable(connectable)

    assert (
        DataFrame({"test_foo_data": [0, 1, 2]}).to_sql(name="test_foo_data", con=conn)
        == 3
    )
    main(conn)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
@pytest.mark.parametrize(
    "input",
    [{"foo": [np.inf]}, {"foo": [-np.inf]}, {"foo": [-np.inf], "infe0": ["bar"]}],
)
def test_to_sql_with_negative_npinf(conn, request, input):
    # GH 34431

    df = DataFrame(input)
    conn_name = conn
    conn = request.getfixturevalue(conn)

    if "mysql" in conn_name:
        # GH 36465
        # The input {"foo": [-np.inf], "infe0": ["bar"]} does not raise any error
        # for pymysql version >= 0.10
        # TODO(GH#36465): remove this version check after GH 36465 is fixed
        pymysql = pytest.importorskip("pymysql")

        if Version(pymysql.__version__) < Version("1.0.3") and "infe0" in df.columns:
            mark = pytest.mark.xfail(reason="GH 36465")
            request.applymarker(mark)

        msg = "inf cannot be used with MySQL"
        with pytest.raises(ValueError, match=msg):
            df.to_sql(name="foobar", con=conn, index=False)
    else:
        assert df.to_sql(name="foobar", con=conn, index=False) == 1
        res = sql.read_sql_table("foobar", conn)
        tm.assert_equal(df, res)


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_temporary_table(conn, request):
    if conn == "sqlite_str":
        pytest.skip("test does not work with str connection")

    conn = request.getfixturevalue(conn)

    from sqlalchemy import (
        Column,
        Integer,
        Unicode,
        select,
    )
    from sqlalchemy.orm import (
        Session,
        declarative_base,
    )

    test_data = "Hello, World!"
    expected = DataFrame({"spam": [test_data]})
    Base = declarative_base()

    class Temporary(Base):
        __tablename__ = "temp_test"
        __table_args__ = {"prefixes": ["TEMPORARY"]}
        id = Column(Integer, primary_key=True)
        spam = Column(Unicode(30), nullable=False)

    with Session(conn) as session:
        with session.begin():
            conn = session.connection()
            Temporary.__table__.create(conn)
            session.add(Temporary(spam=test_data))
            session.flush()
            df = sql.read_sql_query(sql=select(Temporary.spam), con=conn)
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("conn", all_connectable)
def test_invalid_engine(conn, request, test_frame1):
    if conn == "sqlite_buildin" or "adbc" in conn:
        request.applymarker(
            pytest.mark.xfail(
                reason="SQLiteDatabase/ADBCDatabase does not raise for bad engine"
            )
        )

    conn = request.getfixturevalue(conn)
    msg = "engine must be one of 'auto', 'sqlalchemy'"
    with pandasSQL_builder(conn) as pandasSQL:
        with pytest.raises(ValueError, match=msg):
            pandasSQL.to_sql(test_frame1, "test_frame1", engine="bad_engine")


@pytest.mark.parametrize("conn", all_connectable)
def test_to_sql_with_sql_engine(conn, request, test_frame1):
    """`to_sql` with the `engine` param"""
    # mostly copied from this class's `_to_sql()` method
    conn = request.getfixturevalue(conn)
    with pandasSQL_builder(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            assert pandasSQL.to_sql(test_frame1, "test_frame1", engine="auto") == 4
            assert pandasSQL.has_table("test_frame1")

    num_entries = len(test_frame1)
    num_rows = count_rows(conn, "test_frame1")
    assert num_rows == num_entries


@pytest.mark.parametrize("conn", sqlalchemy_connectable)
def test_options_sqlalchemy(conn, request, test_frame1):
    # use the set option
    conn = request.getfixturevalue(conn)
    with pd.option_context("io.sql.engine", "sqlalchemy"):
        with pandasSQL_builder(conn) as pandasSQL:
            with pandasSQL.run_transaction():
                assert pandasSQL.to_sql(test_frame1, "test_frame1") == 4
                assert pandasSQL.has_table("test_frame1")

        num_entries = len(test_frame1)
        num_rows = count_rows(conn, "test_frame1")
        assert num_rows == num_entries


@pytest.mark.parametrize("conn", all_connectable)
def test_options_auto(conn, request, test_frame1):
    # use the set option
    conn = request.getfixturevalue(conn)
    with pd.option_context("io.sql.engine", "auto"):
        with pandasSQL_builder(conn) as pandasSQL:
            with pandasSQL.run_transaction():
                assert pandasSQL.to_sql(test_frame1, "test_frame1") == 4
                assert pandasSQL.has_table("test_frame1")

        num_entries = len(test_frame1)
        num_rows = count_rows(conn, "test_frame1")
        assert num_rows == num_entries


def test_options_get_engine():
    pytest.importorskip("sqlalchemy")
    assert isinstance(get_engine("sqlalchemy"), SQLAlchemyEngine)

    with pd.option_context("io.sql.engine", "sqlalchemy"):
        assert isinstance(get_engine("auto"), SQLAlchemyEngine)
        assert isinstance(get_engine("sqlalchemy"), SQLAlchemyEngine)

    with pd.option_context("io.sql.engine", "auto"):
        assert isinstance(get_engine("auto"), SQLAlchemyEngine)
        assert isinstance(get_engine("sqlalchemy"), SQLAlchemyEngine)


def test_get_engine_auto_error_message():
    # Expect different error messages from get_engine(engine="auto")
    # if engines aren't installed vs. are installed but bad version
    pass
    # TODO(GH#36893) fill this in when we add more engines


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("func", ["read_sql", "read_sql_query"])
def test_read_sql_dtype_backend(
    conn,
    request,
    string_storage,
    func,
    dtype_backend,
    dtype_backend_data,
    dtype_backend_expected,
):
    # GH#50048
    conn_name = conn
    conn = request.getfixturevalue(conn)
    table = "test"
    df = dtype_backend_data
    df.to_sql(name=table, con=conn, index=False, if_exists="replace")

    with pd.option_context("mode.string_storage", string_storage):
        result = getattr(pd, func)(
            f"Select * from {table}", conn, dtype_backend=dtype_backend
        )
        expected = dtype_backend_expected(string_storage, dtype_backend, conn_name)

    tm.assert_frame_equal(result, expected)

    if "adbc" in conn_name:
        # adbc does not support chunksize argument
        request.applymarker(
            pytest.mark.xfail(reason="adbc does not support chunksize argument")
        )

    with pd.option_context("mode.string_storage", string_storage):
        iterator = getattr(pd, func)(
            f"Select * from {table}",
            con=conn,
            dtype_backend=dtype_backend,
            chunksize=3,
        )
        expected = dtype_backend_expected(string_storage, dtype_backend, conn_name)
        for result in iterator:
            tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("func", ["read_sql", "read_sql_table"])
def test_read_sql_dtype_backend_table(
    conn,
    request,
    string_storage,
    func,
    dtype_backend,
    dtype_backend_data,
    dtype_backend_expected,
):
    if "sqlite" in conn and "adbc" not in conn:
        request.applymarker(
            pytest.mark.xfail(
                reason=(
                    "SQLite actually returns proper boolean values via "
                    "read_sql_table, but before pytest refactor was skipped"
                )
            )
        )
    # GH#50048
    conn_name = conn
    conn = request.getfixturevalue(conn)
    table = "test"
    df = dtype_backend_data
    df.to_sql(name=table, con=conn, index=False, if_exists="replace")

    with pd.option_context("mode.string_storage", string_storage):
        result = getattr(pd, func)(table, conn, dtype_backend=dtype_backend)
        expected = dtype_backend_expected(string_storage, dtype_backend, conn_name)
    tm.assert_frame_equal(result, expected)

    if "adbc" in conn_name:
        # adbc does not support chunksize argument
        return

    with pd.option_context("mode.string_storage", string_storage):
        iterator = getattr(pd, func)(
            table,
            conn,
            dtype_backend=dtype_backend,
            chunksize=3,
        )
        expected = dtype_backend_expected(string_storage, dtype_backend, conn_name)
        for result in iterator:
            tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("func", ["read_sql", "read_sql_table", "read_sql_query"])
def test_read_sql_invalid_dtype_backend_table(conn, request, func, dtype_backend_data):
    conn = request.getfixturevalue(conn)
    table = "test"
    df = dtype_backend_data
    df.to_sql(name=table, con=conn, index=False, if_exists="replace")

    msg = (
        "dtype_backend numpy is invalid, only 'numpy_nullable' and "
        "'pyarrow' are allowed."
    )
    with pytest.raises(ValueError, match=msg):
        getattr(pd, func)(table, conn, dtype_backend="numpy")


@pytest.fixture
def dtype_backend_data() -> DataFrame:
    return DataFrame(
        {
            "a": Series([1, np.nan, 3], dtype="Int64"),
            "b": Series([1, 2, 3], dtype="Int64"),
            "c": Series([1.5, np.nan, 2.5], dtype="Float64"),
            "d": Series([1.5, 2.0, 2.5], dtype="Float64"),
            "e": [True, False, None],
            "f": [True, False, True],
            "g": ["a", "b", "c"],
            "h": ["a", "b", None],
        }
    )


@pytest.fixture
def dtype_backend_expected():
    def func(string_storage, dtype_backend, conn_name) -> DataFrame:
        string_dtype: pd.StringDtype | pd.ArrowDtype
        if dtype_backend == "pyarrow":
            pa = pytest.importorskip("pyarrow")
            string_dtype = pd.ArrowDtype(pa.string())
        else:
            string_dtype = pd.StringDtype(string_storage)

        df = DataFrame(
            {
                "a": Series([1, np.nan, 3], dtype="Int64"),
                "b": Series([1, 2, 3], dtype="Int64"),
                "c": Series([1.5, np.nan, 2.5], dtype="Float64"),
                "d": Series([1.5, 2.0, 2.5], dtype="Float64"),
                "e": Series([True, False, pd.NA], dtype="boolean"),
                "f": Series([True, False, True], dtype="boolean"),
                "g": Series(["a", "b", "c"], dtype=string_dtype),
                "h": Series(["a", "b", None], dtype=string_dtype),
            }
        )
        if dtype_backend == "pyarrow":
            pa = pytest.importorskip("pyarrow")

            from pandas.arrays import ArrowExtensionArray

            df = DataFrame(
                {
                    col: ArrowExtensionArray(pa.array(df[col], from_pandas=True))
                    for col in df.columns
                }
            )

        if "mysql" in conn_name or "sqlite" in conn_name:
            if dtype_backend == "numpy_nullable":
                df = df.astype({"e": "Int64", "f": "Int64"})
            else:
                df = df.astype({"e": "int64[pyarrow]", "f": "int64[pyarrow]"})

        return df

    return func


@pytest.mark.parametrize("conn", all_connectable)
def test_chunksize_empty_dtypes(conn, request):
    # GH#50245
    if "adbc" in conn:
        request.node.add_marker(
            pytest.mark.xfail(reason="chunksize argument NotImplemented with ADBC")
        )
    conn = request.getfixturevalue(conn)
    dtypes = {"a": "int64", "b": "object"}
    df = DataFrame(columns=["a", "b"]).astype(dtypes)
    expected = df.copy()
    df.to_sql(name="test", con=conn, index=False, if_exists="replace")

    for result in read_sql_query(
        "SELECT * FROM test",
        conn,
        dtype=dtypes,
        chunksize=1,
    ):
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conn", all_connectable)
@pytest.mark.parametrize("dtype_backend", [lib.no_default, "numpy_nullable"])
@pytest.mark.parametrize("func", ["read_sql", "read_sql_query"])
def test_read_sql_dtype(conn, request, func, dtype_backend):
    # GH#50797
    conn = request.getfixturevalue(conn)
    table = "test"
    df = DataFrame({"a": [1, 2, 3], "b": 5})
    df.to_sql(name=table, con=conn, index=False, if_exists="replace")

    result = getattr(pd, func)(
        f"Select * from {table}",
        conn,
        dtype={"a": np.float64},
        dtype_backend=dtype_backend,
    )
    expected = DataFrame(
        {
            "a": Series([1, 2, 3], dtype=np.float64),
            "b": Series(
                [5, 5, 5],
                dtype="int64" if not dtype_backend == "numpy_nullable" else "Int64",
            ),
        }
    )
    tm.assert_frame_equal(result, expected)


def test_keyword_deprecation(sqlite_engine):
    conn = sqlite_engine
    # GH 54397
    msg = (
        "Starting with pandas version 3.0 all arguments of to_sql except for the "
        "arguments 'name' and 'con' will be keyword-only."
    )
    df = DataFrame([{"A": 1, "B": 2, "C": 3}, {"A": 1, "B": 2, "C": 3}])
    df.to_sql("example", conn)

    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.to_sql("example", conn, None, if_exists="replace")


def test_bigint_warning(sqlite_engine):
    conn = sqlite_engine
    # test no warning for BIGINT (to support int64) is raised (GH7433)
    df = DataFrame({"a": [1, 2]}, dtype="int64")
    assert df.to_sql(name="test_bigintwarning", con=conn, index=False) == 2

    with tm.assert_produces_warning(None):
        sql.read_sql_table("test_bigintwarning", conn)


def test_valueerror_exception(sqlite_engine):
    conn = sqlite_engine
    df = DataFrame({"col1": [1, 2], "col2": [3, 4]})
    with pytest.raises(ValueError, match="Empty table name specified"):
        df.to_sql(name="", con=conn, if_exists="replace", index=False)


def test_row_object_is_named_tuple(sqlite_engine):
    conn = sqlite_engine
    # GH 40682
    # Test for the is_named_tuple() function
    # Placed here due to its usage of sqlalchemy

    from sqlalchemy import (
        Column,
        Integer,
        String,
    )
    from sqlalchemy.orm import (
        declarative_base,
        sessionmaker,
    )

    BaseModel = declarative_base()

    class Test(BaseModel):
        __tablename__ = "test_frame"
        id = Column(Integer, primary_key=True)
        string_column = Column(String(50))

    with conn.begin():
        BaseModel.metadata.create_all(conn)
    Session = sessionmaker(bind=conn)
    with Session() as session:
        df = DataFrame({"id": [0, 1], "string_column": ["hello", "world"]})
        assert (
            df.to_sql(name="test_frame", con=conn, index=False, if_exists="replace")
            == 2
        )
        session.commit()
        test_query = session.query(Test.id, Test.string_column)
        df = DataFrame(test_query)

    assert list(df.columns) == ["id", "string_column"]


def test_read_sql_string_inference(sqlite_engine):
    conn = sqlite_engine
    # GH#54430
    table = "test"
    df = DataFrame({"a": ["x", "y"]})
    df.to_sql(table, con=conn, index=False, if_exists="replace")

    with pd.option_context("future.infer_string", True):
        result = read_sql_table(table, conn)

    dtype = pd.StringDtype(na_value=np.nan)
    expected = DataFrame(
        {"a": ["x", "y"]}, dtype=dtype, columns=Index(["a"], dtype=dtype)
    )

    tm.assert_frame_equal(result, expected)


def test_roundtripping_datetimes(sqlite_engine):
    conn = sqlite_engine
    # GH#54877
    df = DataFrame({"t": [datetime(2020, 12, 31, 12)]}, dtype="datetime64[ns]")
    df.to_sql("test", conn, if_exists="replace", index=False)
    result = pd.read_sql("select * from test", conn).iloc[0, 0]
    assert result == "2020-12-31 12:00:00.000000"


@pytest.fixture
def sqlite_builtin_detect_types():
    with contextlib.closing(
        sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    ) as closing_conn:
        with closing_conn as conn:
            yield conn


def test_roundtripping_datetimes_detect_types(sqlite_builtin_detect_types):
    # https://github.com/pandas-dev/pandas/issues/55554
    conn = sqlite_builtin_detect_types
    df = DataFrame({"t": [datetime(2020, 12, 31, 12)]}, dtype="datetime64[ns]")
    df.to_sql("test", conn, if_exists="replace", index=False)
    result = pd.read_sql("select * from test", conn).iloc[0, 0]
    assert result == Timestamp("2020-12-31 12:00:00.000000")


@pytest.mark.db
def test_psycopg2_schema_support(postgresql_psycopg2_engine):
    conn = postgresql_psycopg2_engine

    # only test this for postgresql (schema's not supported in
    # mysql/sqlite)
    df = DataFrame({"col1": [1, 2], "col2": [0.1, 0.2], "col3": ["a", "n"]})

    # create a schema
    with conn.connect() as con:
        with con.begin():
            con.exec_driver_sql("DROP SCHEMA IF EXISTS other CASCADE;")
            con.exec_driver_sql("CREATE SCHEMA other;")

    # write dataframe to different schema's
    assert df.to_sql(name="test_schema_public", con=conn, index=False) == 2
    assert (
        df.to_sql(
            name="test_schema_public_explicit",
            con=conn,
            index=False,
            schema="public",
        )
        == 2
    )
    assert (
        df.to_sql(name="test_schema_other", con=conn, index=False, schema="other") == 2
    )

    # read dataframes back in
    res1 = sql.read_sql_table("test_schema_public", conn)
    tm.assert_frame_equal(df, res1)
    res2 = sql.read_sql_table("test_schema_public_explicit", conn)
    tm.assert_frame_equal(df, res2)
    res3 = sql.read_sql_table("test_schema_public_explicit", conn, schema="public")
    tm.assert_frame_equal(df, res3)
    res4 = sql.read_sql_table("test_schema_other", conn, schema="other")
    tm.assert_frame_equal(df, res4)
    msg = "Table test_schema_other not found"
    with pytest.raises(ValueError, match=msg):
        sql.read_sql_table("test_schema_other", conn, schema="public")

    # different if_exists options

    # create a schema
    with conn.connect() as con:
        with con.begin():
            con.exec_driver_sql("DROP SCHEMA IF EXISTS other CASCADE;")
            con.exec_driver_sql("CREATE SCHEMA other;")

    # write dataframe with different if_exists options
    assert (
        df.to_sql(name="test_schema_other", con=conn, schema="other", index=False) == 2
    )
    df.to_sql(
        name="test_schema_other",
        con=conn,
        schema="other",
        index=False,
        if_exists="replace",
    )
    assert (
        df.to_sql(
            name="test_schema_other",
            con=conn,
            schema="other",
            index=False,
            if_exists="append",
        )
        == 2
    )
    res = sql.read_sql_table("test_schema_other", conn, schema="other")
    tm.assert_frame_equal(concat([df, df], ignore_index=True), res)


@pytest.mark.db
def test_self_join_date_columns(postgresql_psycopg2_engine):
    # GH 44421
    conn = postgresql_psycopg2_engine
    from sqlalchemy.sql import text

    create_table = text(
        """
    CREATE TABLE person
    (
        id serial constraint person_pkey primary key,
        created_dt timestamp with time zone
    );

    INSERT INTO person
        VALUES (1, '2021-01-01T00:00:00Z');
    """
    )
    with conn.connect() as con:
        with con.begin():
            con.execute(create_table)

    sql_query = (
        'SELECT * FROM "person" AS p1 INNER JOIN "person" AS p2 ON p1.id = p2.id;'
    )
    result = pd.read_sql(sql_query, conn)
    expected = DataFrame(
        [[1, Timestamp("2021", tz="UTC")] * 2], columns=["id", "created_dt"] * 2
    )
    tm.assert_frame_equal(result, expected)

    # Cleanup
    with sql.SQLDatabase(conn, need_transaction=True) as pandasSQL:
        pandasSQL.drop_table("person")


def test_create_and_drop_table(sqlite_engine):
    conn = sqlite_engine
    temp_frame = DataFrame({"one": [1.0, 2.0, 3.0, 4.0], "two": [4.0, 3.0, 2.0, 1.0]})
    with sql.SQLDatabase(conn) as pandasSQL:
        with pandasSQL.run_transaction():
            assert pandasSQL.to_sql(temp_frame, "drop_test_frame") == 4

        assert pandasSQL.has_table("drop_test_frame")

        with pandasSQL.run_transaction():
            pandasSQL.drop_table("drop_test_frame")

        assert not pandasSQL.has_table("drop_test_frame")


def test_sqlite_datetime_date(sqlite_buildin):
    conn = sqlite_buildin
    df = DataFrame([date(2014, 1, 1), date(2014, 1, 2)], columns=["a"])
    assert df.to_sql(name="test_date", con=conn, index=False) == 2
    res = read_sql_query("SELECT * FROM test_date", conn)
    # comes back as strings
    tm.assert_frame_equal(res, df.astype(str))


@pytest.mark.parametrize("tz_aware", [False, True])
def test_sqlite_datetime_time(tz_aware, sqlite_buildin):
    conn = sqlite_buildin
    # test support for datetime.time, GH #8341
    if not tz_aware:
        tz_times = [time(9, 0, 0), time(9, 1, 30)]
    else:
        tz_dt = date_range("2013-01-01 09:00:00", periods=2, tz="US/Pacific")
        tz_times = Series(tz_dt.to_pydatetime()).map(lambda dt: dt.timetz())

    df = DataFrame(tz_times, columns=["a"])

    assert df.to_sql(name="test_time", con=conn, index=False) == 2
    res = read_sql_query("SELECT * FROM test_time", conn)
    # comes back as strings
    expected = df.map(lambda _: _.strftime("%H:%M:%S.%f"))
    tm.assert_frame_equal(res, expected)


def get_sqlite_column_type(conn, table, column):
    recs = conn.execute(f"PRAGMA table_info({table})")
    for cid, name, ctype, not_null, default, pk in recs:
        if name == column:
            return ctype
    raise ValueError(f"Table {table}, column {column} not found")


def test_sqlite_test_dtype(sqlite_buildin):
    conn = sqlite_buildin
    cols = ["A", "B"]
    data = [(0.8, True), (0.9, None)]
    df = DataFrame(data, columns=cols)
    assert df.to_sql(name="dtype_test", con=conn) == 2
    assert df.to_sql(name="dtype_test2", con=conn, dtype={"B": "STRING"}) == 2

    # sqlite stores Boolean values as INTEGER
    assert get_sqlite_column_type(conn, "dtype_test", "B") == "INTEGER"

    assert get_sqlite_column_type(conn, "dtype_test2", "B") == "STRING"
    msg = r"B \(<class 'bool'>\) not a string"
    with pytest.raises(ValueError, match=msg):
        df.to_sql(name="error", con=conn, dtype={"B": bool})

    # single dtype
    assert df.to_sql(name="single_dtype_test", con=conn, dtype="STRING") == 2
    assert get_sqlite_column_type(conn, "single_dtype_test", "A") == "STRING"
    assert get_sqlite_column_type(conn, "single_dtype_test", "B") == "STRING"


def test_sqlite_notna_dtype(sqlite_buildin):
    conn = sqlite_buildin
    cols = {
        "Bool": Series([True, None]),
        "Date": Series([datetime(2012, 5, 1), None]),
        "Int": Series([1, None], dtype="object"),
        "Float": Series([1.1, None]),
    }
    df = DataFrame(cols)

    tbl = "notna_dtype_test"
    assert df.to_sql(name=tbl, con=conn) == 2

    assert get_sqlite_column_type(conn, tbl, "Bool") == "INTEGER"
    assert get_sqlite_column_type(conn, tbl, "Date") == "TIMESTAMP"
    assert get_sqlite_column_type(conn, tbl, "Int") == "INTEGER"
    assert get_sqlite_column_type(conn, tbl, "Float") == "REAL"


def test_sqlite_illegal_names(sqlite_buildin):
    # For sqlite, these should work fine
    conn = sqlite_buildin
    df = DataFrame([[1, 2], [3, 4]], columns=["a", "b"])

    msg = "Empty table or column name specified"
    with pytest.raises(ValueError, match=msg):
        df.to_sql(name="", con=conn)

    for ndx, weird_name in enumerate(
        [
            "test_weird_name]",
            "test_weird_name[",
            "test_weird_name`",
            'test_weird_name"',
            "test_weird_name'",
            "_b.test_weird_name_01-30",
            '"_b.test_weird_name_01-30"',
            "99beginswithnumber",
            "12345",
            "\xe9",
        ]
    ):
        assert df.to_sql(name=weird_name, con=conn) == 2
        sql.table_exists(weird_name, conn)

        df2 = DataFrame([[1, 2], [3, 4]], columns=["a", weird_name])
        c_tbl = f"test_weird_col_name{ndx:d}"
        assert df2.to_sql(name=c_tbl, con=conn) == 2
        sql.table_exists(c_tbl, conn)


def format_query(sql, *args):
    _formatters = {
        datetime: "'{}'".format,
        str: "'{}'".format,
        np.str_: "'{}'".format,
        bytes: "'{}'".format,
        float: "{:.8f}".format,
        int: "{:d}".format,
        type(None): lambda x: "NULL",
        np.float64: "{:.10f}".format,
        bool: "'{!s}'".format,
    }
    processed_args = []
    for arg in args:
        if isinstance(arg, float) and isna(arg):
            arg = None

        formatter = _formatters[type(arg)]
        processed_args.append(formatter(arg))

    return sql % tuple(processed_args)


def tquery(query, con=None):
    """Replace removed sql.tquery function"""
    with sql.pandasSQL_builder(con) as pandas_sql:
        res = pandas_sql.execute(query).fetchall()
    return None if res is None else list(res)


def test_xsqlite_basic(sqlite_buildin):
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    assert sql.to_sql(frame, name="test_table", con=sqlite_buildin, index=False) == 10
    result = sql.read_sql("select * from test_table", sqlite_buildin)

    # HACK! Change this once indexes are handled properly.
    result.index = frame.index

    expected = frame
    tm.assert_frame_equal(result, frame)

    frame["txt"] = ["a"] * len(frame)
    frame2 = frame.copy()
    new_idx = Index(np.arange(len(frame2)), dtype=np.int64) + 10
    frame2["Idx"] = new_idx.copy()
    assert sql.to_sql(frame2, name="test_table2", con=sqlite_buildin, index=False) == 10
    result = sql.read_sql("select * from test_table2", sqlite_buildin, index_col="Idx")
    expected = frame.copy()
    expected.index = new_idx
    expected.index.name = "Idx"
    tm.assert_frame_equal(expected, result)


def test_xsqlite_write_row_by_row(sqlite_buildin):
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    frame.iloc[0, 0] = np.nan
    create_sql = sql.get_schema(frame, "test")
    cur = sqlite_buildin.cursor()
    cur.execute(create_sql)

    ins = "INSERT INTO test VALUES (%s, %s, %s, %s)"
    for _, row in frame.iterrows():
        fmt_sql = format_query(ins, *row)
        tquery(fmt_sql, con=sqlite_buildin)

    sqlite_buildin.commit()

    result = sql.read_sql("select * from test", con=sqlite_buildin)
    result.index = frame.index
    tm.assert_frame_equal(result, frame, rtol=1e-3)


def test_xsqlite_execute(sqlite_buildin):
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    create_sql = sql.get_schema(frame, "test")
    cur = sqlite_buildin.cursor()
    cur.execute(create_sql)
    ins = "INSERT INTO test VALUES (?, ?, ?, ?)"

    row = frame.iloc[0]
    with sql.pandasSQL_builder(sqlite_buildin) as pandas_sql:
        pandas_sql.execute(ins, tuple(row))
    sqlite_buildin.commit()

    result = sql.read_sql("select * from test", sqlite_buildin)
    result.index = frame.index[:1]
    tm.assert_frame_equal(result, frame[:1])


def test_xsqlite_schema(sqlite_buildin):
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((10, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=10, freq="B"),
    )
    create_sql = sql.get_schema(frame, "test")
    lines = create_sql.splitlines()
    for line in lines:
        tokens = line.split(" ")
        if len(tokens) == 2 and tokens[0] == "A":
            assert tokens[1] == "DATETIME"

    create_sql = sql.get_schema(frame, "test", keys=["A", "B"])
    lines = create_sql.splitlines()
    assert 'PRIMARY KEY ("A", "B")' in create_sql
    cur = sqlite_buildin.cursor()
    cur.execute(create_sql)


def test_xsqlite_execute_fail(sqlite_buildin):
    create_sql = """
    CREATE TABLE test
    (
    a TEXT,
    b TEXT,
    c REAL,
    PRIMARY KEY (a, b)
    );
    """
    cur = sqlite_buildin.cursor()
    cur.execute(create_sql)

    with sql.pandasSQL_builder(sqlite_buildin) as pandas_sql:
        pandas_sql.execute("INSERT INTO test VALUES('foo', 'bar', 1.234)")
        pandas_sql.execute("INSERT INTO test VALUES('foo', 'baz', 2.567)")

        with pytest.raises(sql.DatabaseError, match="Execution failed on sql"):
            pandas_sql.execute("INSERT INTO test VALUES('foo', 'bar', 7)")


def test_xsqlite_execute_closed_connection():
    create_sql = """
    CREATE TABLE test
    (
    a TEXT,
    b TEXT,
    c REAL,
    PRIMARY KEY (a, b)
    );
    """
    with contextlib.closing(sqlite3.connect(":memory:")) as conn:
        cur = conn.cursor()
        cur.execute(create_sql)

        with sql.pandasSQL_builder(conn) as pandas_sql:
            pandas_sql.execute("INSERT INTO test VALUES('foo', 'bar', 1.234)")

    msg = "Cannot operate on a closed database."
    with pytest.raises(sqlite3.ProgrammingError, match=msg):
        tquery("select * from test", con=conn)


def test_xsqlite_keyword_as_column_names(sqlite_buildin):
    df = DataFrame({"From": np.ones(5)})
    assert sql.to_sql(df, con=sqlite_buildin, name="testkeywords", index=False) == 5


def test_xsqlite_onecolumn_of_integer(sqlite_buildin):
    # GH 3628
    # a column_of_integers dataframe should transfer well to sql

    mono_df = DataFrame([1, 2], columns=["c0"])
    assert sql.to_sql(mono_df, con=sqlite_buildin, name="mono_df", index=False) == 2
    # computing the sum via sql
    con_x = sqlite_buildin
    the_sum = sum(my_c0[0] for my_c0 in con_x.execute("select * from mono_df"))
    # it should not fail, and gives 3 ( Issue #3628 )
    assert the_sum == 3

    result = sql.read_sql("select * from mono_df", con_x)
    tm.assert_frame_equal(result, mono_df)


def test_xsqlite_if_exists(sqlite_buildin):
    df_if_exists_1 = DataFrame({"col1": [1, 2], "col2": ["A", "B"]})
    df_if_exists_2 = DataFrame({"col1": [3, 4, 5], "col2": ["C", "D", "E"]})
    table_name = "table_if_exists"
    sql_select = f"SELECT * FROM {table_name}"

    msg = "'notvalidvalue' is not valid for if_exists"
    with pytest.raises(ValueError, match=msg):
        sql.to_sql(
            frame=df_if_exists_1,
            con=sqlite_buildin,
            name=table_name,
            if_exists="notvalidvalue",
        )
    drop_table(table_name, sqlite_buildin)

    # test if_exists='fail'
    sql.to_sql(
        frame=df_if_exists_1, con=sqlite_buildin, name=table_name, if_exists="fail"
    )
    msg = "Table 'table_if_exists' already exists"
    with pytest.raises(ValueError, match=msg):
        sql.to_sql(
            frame=df_if_exists_1,
            con=sqlite_buildin,
            name=table_name,
            if_exists="fail",
        )
    # test if_exists='replace'
    sql.to_sql(
        frame=df_if_exists_1,
        con=sqlite_buildin,
        name=table_name,
        if_exists="replace",
        index=False,
    )
    assert tquery(sql_select, con=sqlite_buildin) == [(1, "A"), (2, "B")]
    assert (
        sql.to_sql(
            frame=df_if_exists_2,
            con=sqlite_buildin,
            name=table_name,
            if_exists="replace",
            index=False,
        )
        == 3
    )
    assert tquery(sql_select, con=sqlite_buildin) == [(3, "C"), (4, "D"), (5, "E")]
    drop_table(table_name, sqlite_buildin)

    # test if_exists='append'
    assert (
        sql.to_sql(
            frame=df_if_exists_1,
            con=sqlite_buildin,
            name=table_name,
            if_exists="fail",
            index=False,
        )
        == 2
    )
    assert tquery(sql_select, con=sqlite_buildin) == [(1, "A"), (2, "B")]
    assert (
        sql.to_sql(
            frame=df_if_exists_2,
            con=sqlite_buildin,
            name=table_name,
            if_exists="append",
            index=False,
        )
        == 3
    )
    assert tquery(sql_select, con=sqlite_buildin) == [
        (1, "A"),
        (2, "B"),
        (3, "C"),
        (4, "D"),
        (5, "E"),
    ]
    drop_table(table_name, sqlite_buildin)
