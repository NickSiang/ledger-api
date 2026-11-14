from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from sqlalchemy import func, select, text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from extensions import db
import models  # noqa: F401
from models import Account, Transfer

ALLOWED_ACCOUNT_KINDS = {"cash", "bank", "credit_card", "broker"}
ACCOUNT_NULLABLE_FIELDS = {"statement_day", "payment_day"}
TRANSFER_NULLABLE_FIELDS = {"note"}


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


def _api_response(code: int, message: str, data: Any = None):
    return (
        jsonify(
            {
                "code": code,
                "message": message,
                "data": data,
            }
        ),
        code,
    )


def _serialize_decimal(val: Decimal | None) -> int | float | None:
    if val is None:
        return None
    normalized = val.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    return float(normalized)


def _serialize_account(account: Account) -> dict[str, Any]:
    return {
        "id": int(account.id),
        "name": account.name,
        "kind": account.kind,
        "currency": account.currency,
        "opening_balance": _serialize_decimal(account.opening_balance),
        "statement_day": account.statement_day,
        "payment_day": account.payment_day,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


def _serialize_transfer(transfer: Transfer) -> dict[str, Any]:
    return {
        "id": int(transfer.id),
        "transferred_on": (
            transfer.transferred_on.isoformat() if transfer.transferred_on else None
        ),
        "amount": _serialize_decimal(transfer.amount),
        "currency": transfer.currency,
        "fx_rate_to_twd": _serialize_decimal(transfer.fx_rate_to_twd),
        "from_account_id": int(transfer.from_account_id),
        "to_account_id": int(transfer.to_account_id),
        "note": transfer.note,
        "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
        "updated_at": transfer.updated_at.isoformat() if transfer.updated_at else None,
    }


def _parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, str, Decimal)):
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None
        if not parsed.is_finite():
            return None
        return parsed
    return None


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _validate_day_of_month(value: Any, label: str) -> tuple[int | None, str | None]:
    day = _parse_int(value)
    if day is None or day < 1 or day > 31:
        return None, f"{label}必須是 1 到 31 之間的整數"
    return day, None


def _validate_currency(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "幣別格式不正確，請提供三碼英文字母"
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isascii() or not cleaned.isalpha():
        return None, "幣別請填寫三碼英文字母，例如 TWD 或 USD"
    return cleaned, None


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    app.config["SQLALCHEMY_DATABASE_URI"] = _get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.route("/", methods=["GET"])
    def health_check():
        return _api_response(
            200,
            "伺服器運作正常，測試正常可以進行其他任務。",
            {
                "status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.route("/api/health/db", methods=["GET"])
    def db_health_check():
        try:
            db.session.execute(text("SELECT 1"))
            return _api_response(200, "資料庫連線正常", {"status": "ok"})
        except Exception:
            app.logger.exception("資料庫連線檢查失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/accounts", methods=["GET"])
    def list_accounts():
        try:
            accounts = (
                db.session.execute(select(Account).order_by(Account.id.asc()))
                .scalars()
                .all()
            )
            return _api_response(
                200,
                "成功取得帳戶清單",
                [_serialize_account(acc) for acc in accounts],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢帳戶清單失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/accounts", methods=["POST"])
    def create_account():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in ACCOUNT_NULLABLE_FIELDS and v is None)
        }

        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return _api_response(400, "請填寫帳戶名稱", None)
        name = raw_name.strip()
        if len(name) > 100:
            return _api_response(400, "帳戶名稱長度不可超過 100 個字元", None)

        raw_kind = payload.get("kind")
        if not isinstance(raw_kind, str) or raw_kind not in ALLOWED_ACCOUNT_KINDS:
            return _api_response(
                400,
                "帳戶種類不正確，僅允許現金、銀行、信用卡或券商帳戶",
                None,
            )

        if payload.get("currency") is None:
            currency = "TWD"
        else:
            currency, err = _validate_currency(payload.get("currency"))
            if err:
                return _api_response(400, err, None)

        if payload.get("opening_balance") is None:
            opening_balance = Decimal("0")
        else:
            opening_balance = _parse_decimal(payload.get("opening_balance"))
            if opening_balance is None:
                return _api_response(400, "初始餘額必須是有效的數字", None)

        statement_day = None
        if "statement_day" in payload:
            statement_day, err = _validate_day_of_month(
                payload["statement_day"], "結帳日"
            )
            if err:
                return _api_response(400, err, None)

        payment_day = None
        if "payment_day" in payload:
            payment_day, err = _validate_day_of_month(
                payload["payment_day"], "繳款日"
            )
            if err:
                return _api_response(400, err, None)

        try:
            existing = db.session.execute(
                select(Account.id).where(Account.name == name)
            ).scalar_one_or_none()
            if existing is not None:
                return _api_response(400, "這個帳戶名稱已經有人用了，請換一個名稱", None)

            account = Account(
                name=name,
                kind=raw_kind,
                currency=currency,
                opening_balance=opening_balance,
                statement_day=statement_day,
                payment_day=payment_day,
            )
            db.session.add(account)
            db.session.commit()
            db.session.refresh(account)
            return _api_response(201, "成功新增帳戶", _serialize_account(account))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "帳戶資料不符合規範或名稱重複，請檢查後重試", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增帳戶失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/accounts/<int:account_id>", methods=["GET"])
    def get_account(account_id: int):
        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return _api_response(404, "找不到這個帳戶", None)
            return _api_response(200, "成功取得帳戶資料", _serialize_account(account))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢單筆帳戶失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/accounts/<int:account_id>", methods=["PATCH"])
    def update_account(account_id: int):
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        updatable_keys = {"name", "statement_day", "payment_day"}
        if (
            "id" in raw_payload
            and raw_payload["id"] is not None
            and raw_payload["id"] != account_id
            and not (set(raw_payload.keys()) & updatable_keys)
        ):
            return _api_response(400, "不可修改帳戶的主鍵編號", None)

        disallowed_fields = set(raw_payload.keys()) - {
            "id",
            "created_at",
            "updated_at",
            "name",
            "statement_day",
            "payment_day",
        }
        if disallowed_fields:
            return _api_response(400, "僅允許修改帳戶名稱、結帳日與繳款日", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in ACCOUNT_NULLABLE_FIELDS and v is None)
        }

        new_name = None
        if "name" in payload:
            raw_name = payload["name"]
            if not isinstance(raw_name, str) or not raw_name.strip():
                return _api_response(400, "帳戶名稱不可為空白", None)
            new_name = raw_name.strip()
            if len(new_name) > 100:
                return _api_response(400, "帳戶名稱長度不可超過 100 個字元", None)

        new_statement_day = None
        has_statement_day = "statement_day" in payload
        if has_statement_day:
            new_statement_day, err = _validate_day_of_month(
                payload["statement_day"], "結帳日"
            )
            if err:
                return _api_response(400, err, None)

        new_payment_day = None
        has_payment_day = "payment_day" in payload
        if has_payment_day:
            new_payment_day, err = _validate_day_of_month(
                payload["payment_day"], "繳款日"
            )
            if err:
                return _api_response(400, err, None)

        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return _api_response(404, "找不到這個帳戶", None)

            if new_name is not None and new_name != account.name:
                duplicate = db.session.execute(
                    select(Account.id).where(
                        Account.name == new_name,
                        Account.id != account_id,
                    )
                ).scalar_one_or_none()
                if duplicate is not None:
                    return _api_response(
                        400, "這個帳戶名稱已經有人用了，請換一個名稱", None
                    )
                account.name = new_name

            if has_statement_day:
                account.statement_day = new_statement_day

            if has_payment_day:
                account.payment_day = new_payment_day

            account.updated_at = func.now()
            db.session.commit()
            db.session.refresh(account)
            return _api_response(200, "成功更新帳戶資料", _serialize_account(account))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "帳戶更新資料不符合規範或名稱重複", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("更新帳戶失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/accounts/<int:account_id>/balance", methods=["GET"])
    def get_account_balance(account_id: int):
        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return _api_response(404, "找不到這個帳戶", None)

            incoming_amount, incoming_twd = db.session.execute(
                select(
                    func.coalesce(func.sum(Transfer.amount), Decimal("0")),
                    func.coalesce(
                        func.sum(Transfer.amount * Transfer.fx_rate_to_twd),
                        Decimal("0"),
                    ),
                ).where(Transfer.to_account_id == account_id)
            ).one()

            outgoing_amount, outgoing_twd = db.session.execute(
                select(
                    func.coalesce(func.sum(Transfer.amount), Decimal("0")),
                    func.coalesce(
                        func.sum(Transfer.amount * Transfer.fx_rate_to_twd),
                        Decimal("0"),
                    ),
                ).where(Transfer.from_account_id == account_id)
            ).one()

            opening = account.opening_balance or Decimal("0")
            balance = opening + incoming_amount - outgoing_amount
            balance_twd = opening + incoming_twd - outgoing_twd

            serialized_balance = _serialize_decimal(balance)
            serialized_balance_twd = _serialize_decimal(balance_twd)

            return _api_response(
                200,
                "成功取得帳戶餘額",
                {
                    "account_id": int(account.id),
                    "id": int(account.id),
                    "name": account.name,
                    "currency": account.currency,
                    "opening_balance": _serialize_decimal(opening),
                    "balance": serialized_balance,
                    "original_balance": serialized_balance,
                    "balance_twd": serialized_balance_twd,
                    "twd_balance": serialized_balance_twd,
                },
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢帳戶餘額失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/transfers", methods=["GET"])
    def list_transfers():
        try:
            transfers = (
                db.session.execute(select(Transfer).order_by(Transfer.id.asc()))
                .scalars()
                .all()
            )
            return _api_response(
                200,
                "成功取得移轉清單",
                [_serialize_transfer(t) for t in transfers],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢移轉清單失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/transfers/<int:transfer_id>", methods=["GET"])
    def get_transfer(transfer_id: int):
        try:
            transfer = db.session.get(Transfer, transfer_id)
            if transfer is None:
                return _api_response(404, "找不到這筆移轉紀錄", None)
            return _api_response(200, "成功取得移轉紀錄", _serialize_transfer(transfer))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢單筆移轉失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/transfers", methods=["POST"])
    def create_transfer():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in TRANSFER_NULLABLE_FIELDS and v is None)
        }

        raw_date = payload.get("transferred_on")
        if not isinstance(raw_date, str) or not raw_date.strip():
            return _api_response(400, "請填寫移轉日期", None)
        try:
            transferred_on = date.fromisoformat(raw_date.strip())
        except ValueError:
            return _api_response(400, "移轉日期格式不正確，請使用 YYYY-MM-DD 格式", None)

        amount = _parse_decimal(payload.get("amount"))
        if amount is None or amount <= Decimal("0"):
            return _api_response(400, "移轉金額必須是大於 0 的數字", None)

        if payload.get("currency") is None:
            return _api_response(400, "請填寫移轉幣別", None)
        currency, err = _validate_currency(payload.get("currency"))
        if err:
            return _api_response(400, err, None)

        fx_rate_to_twd = _parse_decimal(payload.get("fx_rate_to_twd"))
        if fx_rate_to_twd is None or fx_rate_to_twd <= Decimal("0"):
            return _api_response(400, "匯率必須是大於 0 的數字", None)

        from_account_id = _parse_int(payload.get("from_account_id"))
        to_account_id = _parse_int(payload.get("to_account_id"))
        if from_account_id is None or to_account_id is None:
            return _api_response(400, "請指定有效的轉出帳戶與轉入帳戶", None)

        if from_account_id == to_account_id:
            return _api_response(400, "轉出帳戶與轉入帳戶不能相同", None)

        note = None
        if "note" in payload:
            if not isinstance(payload["note"], str):
                return _api_response(400, "備註必須是文字格式", None)
            note = payload["note"]

        try:
            from_account = db.session.get(Account, from_account_id)
            to_account = db.session.get(Account, to_account_id)
            if from_account is None or to_account is None:
                return _api_response(400, "指定的轉出帳戶或轉入帳戶不存在", None)

            transfer = Transfer(
                transferred_on=transferred_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate_to_twd,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                note=note,
            )
            db.session.add(transfer)
            db.session.commit()
            db.session.refresh(transfer)
            return _api_response(201, "成功新增移轉紀錄", _serialize_transfer(transfer))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "移轉資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增移轉失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.errorhandler(404)
    def not_found(error):
        return _api_response(404, "找不到這一筆", None)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

