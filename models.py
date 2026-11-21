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
    incomes = db.relationship(
        "Income",
        foreign_keys="Income.account_id",
        back_populates="account",
        passive_deletes=True,
    )
    expenses = db.relationship(
        "Expense",
        foreign_keys="Expense.account_id",
        back_populates="account",
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


class IncomeCategory(db.Model):
    __tablename__ = "income_categories"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
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

    incomes = db.relationship(
        "Income",
        foreign_keys="Income.category_id",
        back_populates="category",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_income_categories_name"),
        CheckConstraint(
            "btrim(name) <> ''",
            name="ck_income_categories_name_not_empty",
        ),
    )


class ExpenseCategory(db.Model):
    __tablename__ = "expense_categories"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
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

    expenses = db.relationship(
        "Expense",
        foreign_keys="Expense.category_id",
        back_populates="category",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_expense_categories_name"),
        CheckConstraint(
            "btrim(name) <> ''",
            name="ck_expense_categories_name_not_empty",
        ),
    )


class Income(db.Model):
    __tablename__ = "incomes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id = db.Column(
        db.BigInteger,
        db.ForeignKey("income_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    received_on = db.Column(db.Date, nullable=False)
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
    description = db.Column(db.String(200), nullable=False)
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

    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        back_populates="incomes",
    )
    category = db.relationship(
        "IncomeCategory",
        foreign_keys=[category_id],
        back_populates="incomes",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_incomes_amount_positive"),
        CheckConstraint(
            "char_length(btrim(currency)) = 3",
            name="ck_incomes_currency_length",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_incomes_fx_rate_to_twd_positive",
        ),
        CheckConstraint(
            "btrim(description) <> ''",
            name="ck_incomes_description_not_empty",
        ),
    )


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id = db.Column(
        db.BigInteger,
        db.ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    spent_on = db.Column(db.Date, nullable=False)
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
    description = db.Column(db.String(200), nullable=False)
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

    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        back_populates="expenses",
    )
    category = db.relationship(
        "ExpenseCategory",
        foreign_keys=[category_id],
        back_populates="expenses",
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        CheckConstraint(
            "char_length(btrim(currency)) = 3",
            name="ck_expenses_currency_length",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="ck_expenses_fx_rate_to_twd_positive",
        ),
        CheckConstraint(
            "btrim(description) <> ''",
            name="ck_expenses_description_not_empty",
        ),
    )

