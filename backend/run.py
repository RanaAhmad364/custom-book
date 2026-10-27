from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

load_dotenv(Path(__file__).with_name(".env"))


def create_application() -> Flask:
    from memorybook import create_app

    return create_app()


app = create_application()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=app.config.get("DEBUG", False), use_reloader=False)
