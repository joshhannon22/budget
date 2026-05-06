from pathlib import Path
import typer

app = typer.Typer(help="Personal finance data pipeline.")

KNOWN_SOURCES = ["pnc", "fidelity", "amex", "discover", "capital_one"]


@app.command("init-db")
def init_db():
    """Create the SQLite database and run schema migrations."""
    from budgeting.db.connection import get_connection, DB_PATH

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "db" / "schema.sql"
    schema_sql = schema_path.read_text()

    with get_connection() as conn:
        conn.executescript(schema_sql)

    typer.echo(f"Database initialized at {DB_PATH}")


@app.command("ingest")
def ingest(
    csv_path: Path = typer.Argument(..., help="Path to the CSV file to ingest"),
    source: str = typer.Option(..., help=f"Source name: {', '.join(KNOWN_SOURCES)}"),
):
    """Ingest a CSV export into the pipeline."""
    from budgeting.ingest import run_ingest

    if source not in KNOWN_SOURCES:
        typer.echo(f"Error: unknown source {source!r}. Choose from: {', '.join(KNOWN_SOURCES)}", err=True)
        raise typer.Exit(1)

    try:
        result = run_ingest(csv_path, source)
        typer.echo(
            f"{result['source'].upper()}: read {result['rows_read']} rows, "
            f"inserted {result['rows_inserted']}, skipped {result['rows_skipped']}"
        )
    except NotImplementedError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)


@app.command("list-sources")
def list_sources():
    """List the known account sources."""
    for source in KNOWN_SOURCES:
        typer.echo(source)


if __name__ == "__main__":
    app()
