"""
Worker process — wake-on-enqueue queue consumer.

Run:
    uv run uvicorn worker.http:app --host 0.0.0.0 --port 8001
    python -m worker.main
"""
import uvicorn


def main() -> None:
    uvicorn.run(
        "worker.http:app",
        host="0.0.0.0",
        port=8001,
        log_level="info",
    )


if __name__ == "__main__":
    main()
