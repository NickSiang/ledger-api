from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from sqlalchemy import text

from extensions import db


def _get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        project_root = Path(__file__).resolve().parent
        load_dotenv(project_root / ".env")
        database_url = os.environ.get("DATABASE_URL", "").strip()

    if not database_url:
        raise RuntimeError(
            "缺少環境變數 DATABASE_URL，請設定環境變數或在專案目錄 .env 中配置 PostgreSQL 連線字串。"
        )
    return database_url


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    app.config["SQLALCHEMY_DATABASE_URI"] = _get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.route("/", methods=["GET"])
    def health_check():
        return (
            jsonify(
                {
                    "code": 200,
                    "message": "伺服器運作正常，測試正常可以進行其他任務。",
                    "data": {
                        "status": "ok",
                        "time": datetime.now(timezone.utc).isoformat(),
                    },
                }
            ),
            200,
        )

    @app.route("/api/health/db", methods=["GET"])
    def db_health_check():
        try:
            db.session.execute(text("SELECT 1"))
            return (
                jsonify(
                    {
                        "code": 200,
                        "message": "資料庫連線正常",
                        "data": {"status": "ok"},
                    }
                ),
                200,
            )
        except Exception:
            app.logger.exception("資料庫連線檢查失敗")
            return (
                jsonify(
                    {
                        "code": 500,
                        "message": "資料庫暫時連不上",
                        "data": None,
                    }
                ),
                500,
            )

    @app.errorhandler(404)
    def not_found(error):
        return (
            jsonify(
                {
                    "code": 404,
                    "message": "找不到這一筆",
                    "data": None,
                }
            ),
            404,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

