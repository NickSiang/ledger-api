from decimal import Decimal

from sqlalchemy import CheckConstraint, UniqueConstraint, func, text

from extensions import db


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        default="TWD",
        server_default=text("'TWD'"),
    )
    opening_balance = db.Column(
        db.Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    statement_day = db.Column(db.Integer, nullable=True)
    payment_day = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    outgoing_transfers = db.relationship(
        "Transfer",
        foreign_keys="Transfer.from_account_id",
        back_populates="from_account",
        passive_deletes=True,
    )
    incoming_transfers = db.relationship(
        "Transfer",
        foreign_keys="Transfer.to_account_id",
        back_populates="to_account",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_accounts_name"),
        CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="ck_accounts_kind",
        ),
        CheckConstraint(
            "char_length(btrim(currency)) = 3",
            name="ck_accounts_currency_length",
        ),
        CheckConstraint(
            "statement_day IS NULL OR (statement_day >= 1 AND statement_day <= 31)",
            name="ck_accounts_statement_day_range",
        ),
        CheckConstraint(
            "payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)",
            name="ck_accounts_payment_day_range",
        ),
    )


class Transfer(db.Model):
    __tablename__ = "transfers"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    transferred_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(18, 4), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        default="TWD",
        server_default=text("'TWD'"),
    )
    fx_rate_to_twd = db.Column(
        db.Numeric(18, 6),
        nullable=False,
        default=Decimal("1"),
        server_default=text("1"),
    )
    from_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    from_account = db.relationship(
        "Account",
        foreign_keys=[from_account_id],
        back_populates="outgoing_transfers",
    )
    to_account = db.relationship(
        "Account",
        foreign_keys=[to_account_id],
        back_populates="incoming_transfers",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        CheckConstraint(
            "char_length(btrim(currency)) = 3",
            name="ck_transfers_currency_length",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_transfers_fx_rate_to_twd_positive",
        ),
        CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_different_accounts",
        ),
    )
