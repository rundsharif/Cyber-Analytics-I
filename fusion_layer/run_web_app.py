"""Convenience entry point for launching the localhost S3 test web app."""

if __name__ == "__main__":
    try:
        from src.web_app import app
    except ModuleNotFoundError as exc:
        if str(exc) == "No module named 'flask'":
            raise SystemExit(
                "Flask is not installed in this Python environment. "
                "Run: python3 -m pip install -r requirements.txt"
            )
        raise

    app.run(host="127.0.0.1", port=5050, debug=True)