import React, { useState, useEffect } from 'react';
import {
  getAccounts,
  getCategories,
  addExpense,
  addIncome,
  addTransfer,
  getExpenses,
  getIncomes,
} from '../api';

export default function Dashboard() {
  const [accounts, setAccounts] = useState([]);
  const [categories, setCategories] = useState({ income: [], expense: [] });
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  // 表單切換狀態：'expense' | 'income' | 'transfer'
  const [entryType, setEntryType] = useState('expense');

  // 表單資料狀態
  const [formData, setFormData] = useState({
    accountId: '',
    toAccountId: '',
    categoryId: '',
    amount: '',
    date: new Date().toISOString().slice(0, 10),
    description: '',
    note: '',
  });

  // 載入基本資料
  const fetchData = async () => {
    try {
      setLoading(true);
      const [accs, cats, exps, incs] = await Promise.all([
        getAccounts(),
        getCategories(),
        getExpenses(),
        getIncomes(),
      ]);

      setAccounts(accs);
      setCategories(cats);

      // 自動預選第一個帳戶與第一個分類（若尚未選取）
      if (accs.length > 0 && !formData.accountId) {
        setFormData((prev) => ({
          ...prev,
          accountId: accs[0].id,
          toAccountId: accs.length > 1 ? accs[1].id : accs[0].id,
        }));
      }

      // 組合最近的收支明細
      const combined = [
        ...exps.map((e) => ({ ...e, type: 'expense', sortDate: e.spent_on || e.created_at })),
        ...incs.map((i) => ({ ...i, type: 'income', sortDate: i.received_on || i.created_at })),
      ].sort((a, b) => new Date(b.sortDate) - new Date(a.sortDate)).slice(0, 8);

      setRecentRecords(combined);
    } catch (err) {
      console.error('載入資料失敗:', err);
      setMessage({ type: 'error', text: '無法連線到後端 API，請確認 Flask 伺服器是否已啟動 (port 5000)' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 當切換分類清單時，預選對應分類
  useEffect(() => {
    const currentCats = entryType === 'income' ? categories.income : categories.expense;
    if (currentCats && currentCats.length > 0) {
      setFormData((prev) => ({ ...prev, categoryId: currentCats[0].id }));
    }
  }, [entryType, categories]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.amount || Number(formData.amount) <= 0) {
      setMessage({ type: 'error', text: '請輸入有效的金額 (大於 0)' });
      return;
    }
    if (!formData.description.trim() && entryType !== 'transfer') {
      setMessage({ type: 'error', text: '請填寫摘要說明' });
      return;
    }

    try {
      setSubmitting(true);
      setMessage({ type: '', text: '' });

      if (entryType === 'expense') {
        await addExpense({
          account_id: Number(formData.accountId),
          category_id: Number(formData.categoryId),
          amount: Number(formData.amount),
          spent_on: formData.date,
          description: formData.description.trim(),
          note: formData.note.trim() || null,
        });
        setMessage({ type: 'success', text: '成功新增一筆支出！' });
      } else if (entryType === 'income') {
        await addIncome({
          account_id: Number(formData.accountId),
          category_id: Number(formData.categoryId),
          amount: Number(formData.amount),
          received_on: formData.date,
          description: formData.description.trim(),
          note: formData.note.trim() || null,
        });
        setMessage({ type: 'success', text: '成功新增一筆收入！' });
      } else if (entryType === 'transfer') {
        if (formData.accountId === formData.toAccountId) {
          setMessage({ type: 'error', text: '轉出與轉入帳戶不可相同' });
          setSubmitting(false);
          return;
        }
        await addTransfer({
          from_account_id: Number(formData.accountId),
          to_account_id: Number(formData.toAccountId),
          amount: Number(formData.amount),
          transferred_on: formData.date,
          currency: 'TWD',
          fx_rate_to_twd: 1,
          note: formData.note.trim() || formData.description.trim() || null,
        });
        setMessage({ type: 'success', text: '成功新增一筆轉帳！' });
      }

      // 重設金額與描述，重新抓取帳戶餘額與最新明細
      setFormData((prev) => ({ ...prev, amount: '', description: '', note: '' }));
      await fetchData();
    } catch (err) {
      console.error('送出失敗:', err);
      const errMsg = err.response?.data?.message || '新增失敗，請檢查輸入內容或後端狀態';
      setMessage({ type: 'error', text: errMsg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="dashboard-container">
      {/* 頂部標題 */}
      <div className="dashboard-header">
        <div>
          <h1>個人記帳本</h1>
          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
            前後端串接儀表板 (Vite + React)
          </span>
        </div>
        <span className="api-badge">API: 連線中</span>
      </div>

      {/* 狀態訊息提示 */}
      {message.text && (
        <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
          {message.text}
        </div>
      )}

      {/* 1. 帳戶列表與餘額 */}
      <div className="section-title">帳戶資產總覽</div>
      {loading && accounts.length === 0 ? (
        <div className="empty-state">載入帳戶資訊中...</div>
      ) : accounts.length === 0 ? (
        <div className="empty-state">目前尚未建立任何帳戶</div>
      ) : (
        <div className="accounts-grid">
          {accounts.map((acc) => {
            const bal = acc.balance ?? acc.opening_balance ?? 0;
            return (
              <div key={acc.id} className="account-card">
                <div className="account-card-header">
                  <span className="account-name">{acc.name}</span>
                  <span className="account-kind">{acc.kind}</span>
                </div>
                <div className={`account-balance ${bal < 0 ? 'negative' : ''}`}>
                  ${Number(bal).toLocaleString()} <span style={{ fontSize: '0.9rem' }}>{acc.currency}</span>
                </div>
                <div className="account-sub-info">
                  <span>收: +${Number(acc.total_income || 0).toLocaleString()}</span>
                  <span>支: -${Number(acc.total_expense || 0).toLocaleString()}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 2. 記帳表單 (新增支出 / 收入 / 轉帳) */}
      <div className="form-card">
        <div className="tab-group">
          <button
            type="button"
            className={`tab-btn expense ${entryType === 'expense' ? 'active' : ''}`}
            onClick={() => setEntryType('expense')}
          >
            - 新增支出
          </button>
          <button
            type="button"
            className={`tab-btn income ${entryType === 'income' ? 'active' : ''}`}
            onClick={() => setEntryType('income')}
          >
            + 新增收入
          </button>
          <button
            type="button"
            className={`tab-btn transfer ${entryType === 'transfer' ? 'active' : ''}`}
            onClick={() => setEntryType('transfer')}
          >
            ⇄ 帳戶轉帳
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            {/* 帳戶選擇 */}
            <div className="form-group">
              <label>{entryType === 'transfer' ? '轉出帳戶' : '選擇帳戶'}</label>
              <select
                name="accountId"
                className="form-control"
                value={formData.accountId}
                onChange={handleInputChange}
                required
              >
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name} ({acc.currency})
                  </option>
                ))}
              </select>
            </div>

            {/* 若為轉帳：轉入帳戶 */}
            {entryType === 'transfer' ? (
              <div className="form-group">
                <label>轉入帳戶</label>
                <select
                  name="toAccountId"
                  className="form-control"
                  value={formData.toAccountId}
                  onChange={handleInputChange}
                  required
                >
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({acc.currency})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              /* 若為收支：分類選擇 */
              <div className="form-group">
                <label>分類</label>
                <select
                  name="categoryId"
                  className="form-control"
                  value={formData.categoryId}
                  onChange={handleInputChange}
                  required
                >
                  {(entryType === 'income' ? categories.income : categories.expense).map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* 金額 */}
            <div className="form-group">
              <label>金額</label>
              <input
                type="number"
                name="amount"
                className="form-control"
                placeholder="0"
                min="0.01"
                step="any"
                value={formData.amount}
                onChange={handleInputChange}
                required
              />
            </div>

            {/* 日期 */}
            <div className="form-group">
              <label>日期</label>
              <input
                type="date"
                name="date"
                className="form-control"
                value={formData.date}
                onChange={handleInputChange}
                required
              />
            </div>

            {/* 摘要說明 */}
            <div className="form-group">
              <label>摘要說明</label>
              <input
                type="text"
                name="description"
                className="form-control"
                placeholder={entryType === 'expense' ? '例：午餐便當' : entryType === 'income' ? '例：本月薪資' : '例：提款'}
                value={formData.description}
                onChange={handleInputChange}
                required={entryType !== 'transfer'}
              />
            </div>

            {/* 備註 (選填) */}
            <div className="form-group">
              <label>備註 (選填)</label>
              <input
                type="text"
                name="note"
                className="form-control"
                placeholder="補充細節..."
                value={formData.note}
                onChange={handleInputChange}
              />
            </div>
          </div>

          <button
            type="submit"
            className={`btn-submit ${entryType}`}
            disabled={submitting}
          >
            {submitting ? '處理中...' : entryType === 'expense' ? '確認送出支出' : entryType === 'income' ? '確認送出收入' : '確認送出轉帳'}
          </button>
        </form>
      </div>

      {/* 3. 最近收支紀錄明細 */}
      <div className="records-card">
        <div className="section-title" style={{ marginBottom: 16 }}>最近動態紀錄</div>
        {recentRecords.length === 0 ? (
          <div className="empty-state">尚無近期收支明細</div>
        ) : (
          recentRecords.map((item) => (
            <div key={`${item.type}-${item.id}`} className="record-item">
              <div className="record-left">
                <span className="record-title">{item.description || '無摘要'}</span>
                <span className="record-meta">
                  {item.sortDate} · {item.account_name || '帳戶'} · {item.category_name || '一般'}
                </span>
              </div>
              <div className={`record-amount ${item.type}`}>
                {item.type === 'income' ? '+' : '-'}${Number(item.amount).toLocaleString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
