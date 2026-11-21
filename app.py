from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import func, select, text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from extensions import db
import models  # noqa: F401
from models import (
    Account,
    Expense,
    ExpenseCategory,
    Income,
    IncomeCategory,
    Transfer,
)

ALLOWED_ACCOUNT_KINDS = {"cash", "bank", "credit_card", "broker"}
ACCOUNT_NULLABLE_FIELDS = {"statement_day", "payment_day"}
TRANSFER_NULLABLE_FIELDS = {"note"}
INCOME_NULLABLE_FIELDS = {"note"}
EXPENSE_NULLABLE_FIELDS = {"note"}

DEFAULT_INCOME_CATEGORIES = ["薪資", "獎金", "投資收益", "發票中獎", "兼職副業", "其他收入"]
DEFAULT_EXPENSE_CATEGORIES = ["餐飲美食", "交通運輸", "日常用品", "居家水電", "娛樂消遣", "醫療保健", "其他支出"]


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
        "from_account_name": transfer.from_account.name if transfer.from_account else None,
        "to_account_id": int(transfer.to_account_id),
        "to_account_name": transfer.to_account.name if transfer.to_account else None,
        "note": transfer.note,
        "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
        "updated_at": transfer.updated_at.isoformat() if transfer.updated_at else None,
    }


def _serialize_category(cat: IncomeCategory | ExpenseCategory) -> dict[str, Any]:
    return {
        "id": int(cat.id),
        "name": cat.name,
        "description": cat.description,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
        "updated_at": cat.updated_at.isoformat() if cat.updated_at else None,
    }


def _serialize_income(income: Income) -> dict[str, Any]:
    return {
        "id": int(income.id),
        "account_id": int(income.account_id),
        "account_name": income.account.name if income.account else None,
        "category_id": int(income.category_id),
        "category_name": income.category.name if income.category else None,
        "received_on": income.received_on.isoformat() if income.received_on else None,
        "amount": _serialize_decimal(income.amount),
        "currency": income.currency,
        "fx_rate_to_twd": _serialize_decimal(income.fx_rate_to_twd),
        "description": income.description,
        "note": income.note,
        "created_at": income.created_at.isoformat() if income.created_at else None,
        "updated_at": income.updated_at.isoformat() if income.updated_at else None,
    }


def _serialize_expense(expense: Expense) -> dict[str, Any]:
    return {
        "id": int(expense.id),
        "account_id": int(expense.account_id),
        "account_name": expense.account.name if expense.account else None,
        "category_id": int(expense.category_id),
        "category_name": expense.category.name if expense.category else None,
        "spent_on": expense.spent_on.isoformat() if expense.spent_on else None,
        "amount": _serialize_decimal(expense.amount),
        "currency": expense.currency,
        "fx_rate_to_twd": _serialize_decimal(expense.fx_rate_to_twd),
        "description": expense.description,
        "note": expense.note,
        "created_at": expense.created_at.isoformat() if expense.created_at else None,
        "updated_at": expense.updated_at.isoformat() if expense.updated_at else None,
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

    cors_origins = os.environ.get("CORS_ORIGINS", "*").strip()
    if cors_origins != "*":
        cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    CORS(app, resources={r"/*": {"origins": cors_origins}})

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

            # 總收入
            income_amount, income_twd = db.session.execute(
                select(
                    func.coalesce(func.sum(Income.amount), Decimal("0")),
                    func.coalesce(
                        func.sum(Income.amount * Income.fx_rate_to_twd),
                        Decimal("0"),
                    ),
                ).where(Income.account_id == account_id)
            ).one()

            # 總支出
            expense_amount, expense_twd = db.session.execute(
                select(
                    func.coalesce(func.sum(Expense.amount), Decimal("0")),
                    func.coalesce(
                        func.sum(Expense.amount * Expense.fx_rate_to_twd),
                        Decimal("0"),
                    ),
                ).where(Expense.account_id == account_id)
            ).one()

            # 總轉入
            incoming_amount, incoming_twd = db.session.execute(
                select(
                    func.coalesce(func.sum(Transfer.amount), Decimal("0")),
                    func.coalesce(
                        func.sum(Transfer.amount * Transfer.fx_rate_to_twd),
                        Decimal("0"),
                    ),
                ).where(Transfer.to_account_id == account_id)
            ).one()

            # 總轉出
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
            # 餘額 = 初始餘額 + 總收入 - 總支出 + 總轉入 - 總轉出
            balance = (
                opening + income_amount - expense_amount + incoming_amount - outgoing_amount
            )
            balance_twd = (
                opening + income_twd - expense_twd + incoming_twd - outgoing_twd
            )

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
                    "total_income": _serialize_decimal(income_amount),
                    "total_expense": _serialize_decimal(expense_amount),
                    "total_transfer_in": _serialize_decimal(incoming_amount),
                    "total_transfer_out": _serialize_decimal(outgoing_amount),
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

    @app.route("/api/transfers/<int:transfer_id>", methods=["PATCH"])
    def update_transfer(transfer_id: int):
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        if (
            "id" in raw_payload
            and raw_payload["id"] is not None
            and raw_payload["id"] != transfer_id
        ):
            return _api_response(400, "不可修改移轉的主鍵編號", None)

        disallowed_fields = set(raw_payload.keys()) - {
            "id",
            "created_at",
            "updated_at",
            "amount",
            "transferred_on",
            "date",
            "currency",
            "fx_rate_to_twd",
            "from_account_id",
            "to_account_id",
            "note",
        }
        if disallowed_fields:
            return _api_response(400, "包含不允許修改的欄位", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in TRANSFER_NULLABLE_FIELDS and v is None)
        }

        try:
            transfer = db.session.get(Transfer, transfer_id)
            if transfer is None:
                return _api_response(404, "找不到這筆移轉紀錄", None)

            if "amount" in payload:
                new_amount = _parse_decimal(payload["amount"])
                if new_amount is None or new_amount <= Decimal("0"):
                    return _api_response(400, "移轉金額必須是大於 0 的數字", None)
                transfer.amount = new_amount

            raw_date = payload.get("transferred_on") or payload.get("date")
            if raw_date is not None:
                if not isinstance(raw_date, str) or not raw_date.strip():
                    return _api_response(400, "移轉日期不可為空白", None)
                try:
                    transfer.transferred_on = date.fromisoformat(raw_date.strip())
                except ValueError:
                    return _api_response(400, "移轉日期格式不正確，請使用 YYYY-MM-DD 格式", None)

            if "currency" in payload:
                curr, err = _validate_currency(payload["currency"])
                if err:
                    return _api_response(400, err, None)
                transfer.currency = curr

            if "fx_rate_to_twd" in payload:
                rate = _parse_decimal(payload["fx_rate_to_twd"])
                if rate is None or rate <= Decimal("0"):
                    return _api_response(400, "匯率必須是大於 0 的數字", None)
                transfer.fx_rate_to_twd = rate

            from_acc_id = transfer.from_account_id
            to_acc_id = transfer.to_account_id

            if "from_account_id" in payload:
                f_id = _parse_int(payload["from_account_id"])
                if f_id is None:
                    return _api_response(400, "請指定有效的轉出帳戶", None)
                if db.session.get(Account, f_id) is None:
                    return _api_response(400, "指定的轉出帳戶不存在", None)
                from_acc_id = f_id

            if "to_account_id" in payload:
                t_id = _parse_int(payload["to_account_id"])
                if t_id is None:
                    return _api_response(400, "請指定有效的轉入帳戶", None)
                if db.session.get(Account, t_id) is None:
                    return _api_response(400, "指定的轉入帳戶不存在", None)
                to_acc_id = t_id

            if from_acc_id == to_acc_id:
                return _api_response(400, "轉出帳戶與轉入帳戶不能相同", None)

            transfer.from_account_id = from_acc_id
            transfer.to_account_id = to_acc_id

            if "note" in payload:
                if payload["note"] is not None and not isinstance(payload["note"], str):
                    return _api_response(400, "備註必須是文字格式", None)
                transfer.note = payload["note"]

            transfer.updated_at = func.now()
            db.session.commit()
            db.session.refresh(transfer)
            return _api_response(200, "成功更新移轉紀錄", _serialize_transfer(transfer))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "移轉資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("更新移轉失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/transfers/<int:transfer_id>", methods=["DELETE"])
    def delete_transfer(transfer_id: int):
        try:
            transfer = db.session.get(Transfer, transfer_id)
            if transfer is None:
                return _api_response(404, "找不到這筆移轉紀錄", None)

            db.session.delete(transfer)
            db.session.commit()
            return _api_response(200, "成功刪除移轉紀錄", {"id": transfer_id})
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("刪除移轉失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    # ==========================
    # 分類 (Categories) API
    # ==========================

    def _ensure_default_categories():
        try:
            inc_count = (
                db.session.execute(select(func.count(IncomeCategory.id))).scalar() or 0
            )
            if inc_count == 0:
                for name in DEFAULT_INCOME_CATEGORIES:
                    db.session.add(IncomeCategory(name=name))
                db.session.commit()

            exp_count = (
                db.session.execute(select(func.count(ExpenseCategory.id))).scalar() or 0
            )
            if exp_count == 0:
                for name in DEFAULT_EXPENSE_CATEGORIES:
                    db.session.add(ExpenseCategory(name=name))
                db.session.commit()
        except Exception:
            db.session.rollback()

    @app.route("/api/categories", methods=["GET"])
    def get_all_categories():
        _ensure_default_categories()
        try:
            income_cats = (
                db.session.execute(
                    select(IncomeCategory).order_by(IncomeCategory.id.asc())
                )
                .scalars()
                .all()
            )
            expense_cats = (
                db.session.execute(
                    select(ExpenseCategory).order_by(ExpenseCategory.id.asc())
                )
                .scalars()
                .all()
            )
            return _api_response(
                200,
                "成功取得分類清單",
                {
                    "income": [_serialize_category(c) for c in income_cats],
                    "expense": [_serialize_category(c) for c in expense_cats],
                },
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢分類失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/income-categories", methods=["GET"])
    def list_income_categories():
        _ensure_default_categories()
        try:
            cats = (
                db.session.execute(
                    select(IncomeCategory).order_by(IncomeCategory.id.asc())
                )
                .scalars()
                .all()
            )
            return _api_response(
                200,
                "成功取得收入分類清單",
                [_serialize_category(c) for c in cats],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢收入分類失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/income-categories", methods=["POST"])
    def create_income_category():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        raw_name = raw_payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return _api_response(400, "請填寫分類名稱", None)
        name = raw_name.strip()

        desc = raw_payload.get("description")
        if desc is not None and not isinstance(desc, str):
            return _api_response(400, "分類描述必須為文字格式", None)

        try:
            cat = IncomeCategory(name=name, description=desc)
            db.session.add(cat)
            db.session.commit()
            db.session.refresh(cat)
            return _api_response(201, "成功新增收入分類", _serialize_category(cat))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "分類名稱已存在或格式不正確", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增收入分類失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expense-categories", methods=["GET"])
    def list_expense_categories():
        _ensure_default_categories()
        try:
            cats = (
                db.session.execute(
                    select(ExpenseCategory).order_by(ExpenseCategory.id.asc())
                )
                .scalars()
                .all()
            )
            return _api_response(
                200,
                "成功取得支出分類清單",
                [_serialize_category(c) for c in cats],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢支出分類失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expense-categories", methods=["POST"])
    def create_expense_category():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        raw_name = raw_payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return _api_response(400, "請填寫分類名稱", None)
        name = raw_name.strip()

        desc = raw_payload.get("description")
        if desc is not None and not isinstance(desc, str):
            return _api_response(400, "分類描述必須為文字格式", None)

        try:
            cat = ExpenseCategory(name=name, description=desc)
            db.session.add(cat)
            db.session.commit()
            db.session.refresh(cat)
            return _api_response(201, "成功新增支出分類", _serialize_category(cat))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "分類名稱已存在或格式不正確", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增支出分類失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    # ==========================
    # 收入 (Incomes) API
    # ==========================

    @app.route("/api/incomes", methods=["GET"])
    def list_incomes():
        try:
            query = select(Income).order_by(Income.received_on.desc(), Income.id.desc())

            acc_id = request.args.get("account_id")
            if acc_id and acc_id.isdigit():
                query = query.where(Income.account_id == int(acc_id))

            cat_id = request.args.get("category_id")
            if cat_id and cat_id.isdigit():
                query = query.where(Income.category_id == int(cat_id))

            start_date = request.args.get("start_date")
            if start_date:
                try:
                    query = query.where(Income.received_on >= date.fromisoformat(start_date))
                except ValueError:
                    pass

            end_date = request.args.get("end_date")
            if end_date:
                try:
                    query = query.where(Income.received_on <= date.fromisoformat(end_date))
                except ValueError:
                    pass

            incomes = db.session.execute(query).scalars().all()
            return _api_response(
                200,
                "成功取得收入清單",
                [_serialize_income(inc) for inc in incomes],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢收入清單失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/incomes", methods=["POST"])
    def create_income():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in INCOME_NULLABLE_FIELDS and v is None)
        }

        account_id = _parse_int(payload.get("account_id"))
        if account_id is None:
            return _api_response(400, "請指定有效的帳戶", None)

        category_id = _parse_int(payload.get("category_id"))
        if category_id is None:
            return _api_response(400, "請指定有效的收入分類", None)

        amount = _parse_decimal(payload.get("amount"))
        if amount is None or amount <= Decimal("0"):
            return _api_response(400, "收入金額必須是大於 0 的數字", None)

        raw_date = payload.get("received_on") or payload.get("date") or payload.get("received_at")
        if not isinstance(raw_date, str) or not raw_date.strip():
            return _api_response(400, "請填寫收入日期", None)
        try:
            # 支援 YYYY-MM-DD 或 ISO 日期字串
            received_on = date.fromisoformat(raw_date.strip()[:10])
        except ValueError:
            return _api_response(400, "收入日期格式不正確，請使用 YYYY-MM-DD 格式", None)

        raw_desc = payload.get("description")
        if not isinstance(raw_desc, str) or not raw_desc.strip():
            return _api_response(400, "請填寫收入摘要/說明", None)
        description = raw_desc.strip()
        if len(description) > 200:
            return _api_response(400, "收入摘要長度不可超過 200 個字元", None)

        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return _api_response(400, "指定的帳戶不存在", None)

            category = db.session.get(IncomeCategory, category_id)
            if category is None:
                return _api_response(400, "指定的收入分類不存在", None)

            currency = payload.get("currency")
            if currency is None:
                currency = account.currency or "TWD"
            else:
                currency, err = _validate_currency(currency)
                if err:
                    return _api_response(400, err, None)

            fx_rate = _parse_decimal(payload.get("fx_rate_to_twd"))
            if fx_rate is None or fx_rate <= Decimal("0"):
                fx_rate = Decimal("1") if currency == "TWD" else Decimal("1")

            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                return _api_response(400, "備註必須是文字格式", None)

            income = Income(
                account_id=account_id,
                category_id=category_id,
                received_on=received_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate,
                description=description,
                note=note,
            )
            db.session.add(income)
            db.session.commit()
            db.session.refresh(income)
            return _api_response(201, "成功新增收入紀錄", _serialize_income(income))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "收入資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增收入失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/incomes/<int:income_id>", methods=["GET"])
    def get_income(income_id: int):
        try:
            income = db.session.get(Income, income_id)
            if income is None:
                return _api_response(404, "找不到這筆收入紀錄", None)
            return _api_response(200, "成功取得收入紀錄", _serialize_income(income))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢單筆收入失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/incomes/<int:income_id>", methods=["PATCH"])
    def update_income(income_id: int):
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        if (
            "id" in raw_payload
            and raw_payload["id"] is not None
            and raw_payload["id"] != income_id
        ):
            return _api_response(400, "不可修改收入的主鍵編號", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in INCOME_NULLABLE_FIELDS and v is None)
        }

        try:
            income = db.session.get(Income, income_id)
            if income is None:
                return _api_response(404, "找不到這筆收入紀錄", None)

            if "account_id" in payload:
                acc_id = _parse_int(payload["account_id"])
                if acc_id is None or db.session.get(Account, acc_id) is None:
                    return _api_response(400, "指定的帳戶不存在", None)
                income.account_id = acc_id

            if "category_id" in payload:
                cat_id = _parse_int(payload["category_id"])
                if cat_id is None or db.session.get(IncomeCategory, cat_id) is None:
                    return _api_response(400, "指定的收入分類不存在", None)
                income.category_id = cat_id

            if "amount" in payload:
                amt = _parse_decimal(payload["amount"])
                if amt is None or amt <= Decimal("0"):
                    return _api_response(400, "收入金額必須是大於 0 的數字", None)
                income.amount = amt

            raw_date = payload.get("received_on") or payload.get("date") or payload.get("received_at")
            if raw_date is not None:
                if not isinstance(raw_date, str) or not raw_date.strip():
                    return _api_response(400, "收入日期不可為空白", None)
                try:
                    income.received_on = date.fromisoformat(raw_date.strip()[:10])
                except ValueError:
                    return _api_response(400, "收入日期格式不正確，請使用 YYYY-MM-DD 格式", None)

            if "description" in payload:
                raw_desc = payload["description"]
                if not isinstance(raw_desc, str) or not raw_desc.strip():
                    return _api_response(400, "收入摘要不可為空白", None)
                income.description = raw_desc.strip()

            if "currency" in payload:
                curr, err = _validate_currency(payload["currency"])
                if err:
                    return _api_response(400, err, None)
                income.currency = curr

            if "fx_rate_to_twd" in payload:
                rate = _parse_decimal(payload["fx_rate_to_twd"])
                if rate is None or rate <= Decimal("0"):
                    return _api_response(400, "匯率必須是大於 0 的數字", None)
                income.fx_rate_to_twd = rate

            if "note" in payload:
                if payload["note"] is not None and not isinstance(payload["note"], str):
                    return _api_response(400, "備註必須是文字格式", None)
                income.note = payload["note"]

            income.updated_at = func.now()
            db.session.commit()
            db.session.refresh(income)
            return _api_response(200, "成功更新收入紀錄", _serialize_income(income))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "收入資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("更新收入失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/incomes/<int:income_id>", methods=["DELETE"])
    def delete_income(income_id: int):
        try:
            income = db.session.get(Income, income_id)
            if income is None:
                return _api_response(404, "找不到這筆收入紀錄", None)

            db.session.delete(income)
            db.session.commit()
            return _api_response(200, "成功刪除收入紀錄", {"id": income_id})
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("刪除收入失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    # ==========================
    # 支出 (Expenses) API
    # ==========================

    @app.route("/api/expenses", methods=["GET"])
    def list_expenses():
        try:
            query = select(Expense).order_by(Expense.spent_on.desc(), Expense.id.desc())

            acc_id = request.args.get("account_id")
            if acc_id and acc_id.isdigit():
                query = query.where(Expense.account_id == int(acc_id))

            cat_id = request.args.get("category_id")
            if cat_id and cat_id.isdigit():
                query = query.where(Expense.category_id == int(cat_id))

            start_date = request.args.get("start_date")
            if start_date:
                try:
                    query = query.where(Expense.spent_on >= date.fromisoformat(start_date))
                except ValueError:
                    pass

            end_date = request.args.get("end_date")
            if end_date:
                try:
                    query = query.where(Expense.spent_on <= date.fromisoformat(end_date))
                except ValueError:
                    pass

            expenses = db.session.execute(query).scalars().all()
            return _api_response(
                200,
                "成功取得支出清單",
                [_serialize_expense(exp) for exp in expenses],
            )
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢支出清單失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expenses", methods=["POST"])
    def create_expense():
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in EXPENSE_NULLABLE_FIELDS and v is None)
        }

        account_id = _parse_int(payload.get("account_id"))
        if account_id is None:
            return _api_response(400, "請指定有效的帳戶", None)

        category_id = _parse_int(payload.get("category_id"))
        if category_id is None:
            return _api_response(400, "請指定有效的支出分類", None)

        amount = _parse_decimal(payload.get("amount"))
        if amount is None or amount <= Decimal("0"):
            return _api_response(400, "支出金額必須是大於 0 的數字", None)

        raw_date = payload.get("spent_on") or payload.get("date") or payload.get("spent_at")
        if not isinstance(raw_date, str) or not raw_date.strip():
            return _api_response(400, "請填寫支出日期", None)
        try:
            spent_on = date.fromisoformat(raw_date.strip()[:10])
        except ValueError:
            return _api_response(400, "支出日期格式不正確，請使用 YYYY-MM-DD 格式", None)

        raw_desc = payload.get("description")
        if not isinstance(raw_desc, str) or not raw_desc.strip():
            return _api_response(400, "請填寫支出摘要/說明", None)
        description = raw_desc.strip()
        if len(description) > 200:
            return _api_response(400, "支出摘要長度不可超過 200 個字元", None)

        try:
            account = db.session.get(Account, account_id)
            if account is None:
                return _api_response(400, "指定的帳戶不存在", None)

            category = db.session.get(ExpenseCategory, category_id)
            if category is None:
                return _api_response(400, "指定的支出分類不存在", None)

            currency = payload.get("currency")
            if currency is None:
                currency = account.currency or "TWD"
            else:
                currency, err = _validate_currency(currency)
                if err:
                    return _api_response(400, err, None)

            fx_rate = _parse_decimal(payload.get("fx_rate_to_twd"))
            if fx_rate is None or fx_rate <= Decimal("0"):
                fx_rate = Decimal("1") if currency == "TWD" else Decimal("1")

            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                return _api_response(400, "備註必須是文字格式", None)

            expense = Expense(
                account_id=account_id,
                category_id=category_id,
                spent_on=spent_on,
                amount=amount,
                currency=currency,
                fx_rate_to_twd=fx_rate,
                description=description,
                note=note,
            )
            db.session.add(expense)
            db.session.commit()
            db.session.refresh(expense)
            return _api_response(201, "成功新增支出紀錄", _serialize_expense(expense))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "支出資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("新增支出失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expenses/<int:expense_id>", methods=["GET"])
    def get_expense(expense_id: int):
        try:
            expense = db.session.get(Expense, expense_id)
            if expense is None:
                return _api_response(404, "找不到這筆支出紀錄", None)
            return _api_response(200, "成功取得支出紀錄", _serialize_expense(expense))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("查詢單筆支出失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expenses/<int:expense_id>", methods=["PATCH"])
    def update_expense(expense_id: int):
        raw_payload = request.get_json(silent=True)
        if not isinstance(raw_payload, dict):
            return _api_response(400, "請提供有效的 JSON 物件資料", None)

        if (
            "id" in raw_payload
            and raw_payload["id"] is not None
            and raw_payload["id"] != expense_id
        ):
            return _api_response(400, "不可修改支出的主鍵編號", None)

        payload = {
            k: v
            for k, v in raw_payload.items()
            if k not in {"id", "created_at", "updated_at"}
            and not (k in EXPENSE_NULLABLE_FIELDS and v is None)
        }

        try:
            expense = db.session.get(Expense, expense_id)
            if expense is None:
                return _api_response(404, "找不到這筆支出紀錄", None)

            if "account_id" in payload:
                acc_id = _parse_int(payload["account_id"])
                if acc_id is None or db.session.get(Account, acc_id) is None:
                    return _api_response(400, "指定的帳戶不存在", None)
                expense.account_id = acc_id

            if "category_id" in payload:
                cat_id = _parse_int(payload["category_id"])
                if cat_id is None or db.session.get(ExpenseCategory, cat_id) is None:
                    return _api_response(400, "指定的支出分類不存在", None)
                expense.category_id = cat_id

            if "amount" in payload:
                amt = _parse_decimal(payload["amount"])
                if amt is None or amt <= Decimal("0"):
                    return _api_response(400, "支出金額必須是大於 0 的數字", None)
                expense.amount = amt

            raw_date = payload.get("spent_on") or payload.get("date") or payload.get("spent_at")
            if raw_date is not None:
                if not isinstance(raw_date, str) or not raw_date.strip():
                    return _api_response(400, "支出日期不可為空白", None)
                try:
                    expense.spent_on = date.fromisoformat(raw_date.strip()[:10])
                except ValueError:
                    return _api_response(400, "支出日期格式不正確，請使用 YYYY-MM-DD 格式", None)

            if "description" in payload:
                raw_desc = payload["description"]
                if not isinstance(raw_desc, str) or not raw_desc.strip():
                    return _api_response(400, "支出摘要不可為空白", None)
                expense.description = raw_desc.strip()

            if "currency" in payload:
                curr, err = _validate_currency(payload["currency"])
                if err:
                    return _api_response(400, err, None)
                expense.currency = curr

            if "fx_rate_to_twd" in payload:
                rate = _parse_decimal(payload["fx_rate_to_twd"])
                if rate is None or rate <= Decimal("0"):
                    return _api_response(400, "匯率必須是大於 0 的數字", None)
                expense.fx_rate_to_twd = rate

            if "note" in payload:
                if payload["note"] is not None and not isinstance(payload["note"], str):
                    return _api_response(400, "備註必須是文字格式", None)
                expense.note = payload["note"]

            expense.updated_at = func.now()
            db.session.commit()
            db.session.refresh(expense)
            return _api_response(200, "成功更新支出紀錄", _serialize_expense(expense))
        except (IntegrityError, DataError):
            db.session.rollback()
            return _api_response(400, "支出資料不符合規範，請檢查輸入內容", None)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("更新支出失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
    def delete_expense(expense_id: int):
        try:
            expense = db.session.get(Expense, expense_id)
            if expense is None:
                return _api_response(404, "找不到這筆支出紀錄", None)

            db.session.delete(expense)
            db.session.commit()
            return _api_response(200, "成功刪除支出紀錄", {"id": expense_id})
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("刪除支出失敗")
            return _api_response(500, "資料庫暫時連不上", None)

    @app.errorhandler(404)
    def not_found(error):
        return _api_response(404, "找不到這一筆", None)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

