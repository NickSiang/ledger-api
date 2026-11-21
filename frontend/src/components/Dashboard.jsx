import React, { useState, useEffect } from 'react';
import {
  getAccounts,
  getCategories,
  addExpense,
  addIncome,
  addTransfer,
  getExpenses,
  getIncomes,
  createAccount,
  getApiBaseUrl,
  setApiBaseUrl,
  checkHealth,
} from '../api';

export default function Dashboard() {
  const [accounts, setAccounts] = useState([]);
  const [categories, setCategories] = useState({ income: [], expense: [] });
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
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

  // 彈窗控制：新增帳戶 Modal & API 伺服器設定 Modal
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [accountFormData, setAccountFormData] = useState({
    name: '',
    kind: 'bank',
    currency: 'TWD',
    opening_balance: 0,
    statement_day: '',
    payment_day: '',
  });

  const [showConfigModal, setShowConfigModal] = useState(false);
  const [customApiUrl, setCustomApiUrl] = useState(getApiBaseUrl());
  const [testResult, setTestResult] = useState('');

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
      setApiOnline(true);

      // 自動預選帳戶
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
      setApiOnline(false);

      const isHttps = window.location.protocol === 'https:';
      const currentUrl = getApiBaseUrl();

      if (isHttps && currentUrl.startsWith('http://')) {
        setMessage({
          type: 'error',
          text: `無法連線後端：您目前在 GitHub Pages (HTTPS)，瀏覽器會阻擋連線至非安全的 HTTP 網址 (${currentUrl})。請點擊右上角「API 設定」填入您的 Vercel 後端網址 (https://...)。`,
        });
      } else {
        setMessage({
          type: 'error',
          text: `無法連線到後端 API (${currentUrl})。若在本地端請確認已執行 python app.py；若在線上請點擊右上角設定雲端後端網址。`,
        });
      }
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

  const handleAccountInputChange = (e) => {
    const { name, value } = e.target;
    setAccountFormData((prev) => ({ ...prev, [name]: value }));
  };

  // 儲存新帳戶至 Supabase
  const handleCreateAccount = async (e) => {
    e.preventDefault();
    if (!accountFormData.name.trim()) {
      alert('請填寫帳戶名稱');
      return;
    }

    try {
      setSubmitting(true);
      const payload = {
        name: accountFormData.name.trim(),
        kind: accountFormData.kind,
        currency: accountFormData.currency.trim().toUpperCase() || 'TWD',
        opening_balance: Number(accountFormData.opening_balance) || 0,
      };

      if (accountFormData.statement_day) {
        payload.statement_day = Number(accountFormData.statement_day);
      }
      if (accountFormData.payment_day) {
        payload.payment_day = Number(accountFormData.payment_day);
      }

      const created = await createAccount(payload);
      setMessage({ type: 'success', text: `成功新增帳戶「${created.name}」並已儲存至 Supabase 資料庫！` });
      setShowAccountModal(false);

      // 清空表單
      setAccountFormData({
        name: '',
        kind: 'bank',
        currency: 'TWD',
        opening_balance: 0,
        statement_day: '',
        payment_day: '',
      });

      // 重新整理帳戶列表並自動選中剛建立的帳戶
      await fetchData();
      setFormData((prev) => ({ ...prev, accountId: created.id }));
    } catch (err) {
      console.error('建立帳戶失敗:', err);
      const errMsg = err.response?.data?.message || '建立帳戶失敗，請確認後端連線狀態或帳戶名稱是否重複';
      alert(errMsg);
    } finally {
      setSubmitting(false);
    }
  };

  // 測試 API 連線
  const handleTestApiUrl = async () => {
    try {
      setTestResult('測試連線中...');
      setApiBaseUrl(customApiUrl);
      const res = await checkHealth();
      setTestResult(`✅ 連線成功！伺服器回應: ${res.message || 'ok'}`);
    } catch (err) {
      setTestResult(`❌ 連線失敗: ${err.message}`);
    }
  };

  // 保存 API 設定並重新讀取
  const handleSaveApiUrl = () => {
    setApiBaseUrl(customApiUrl);
    setShowConfigModal(false);
    setMessage({ type: 'success', text: `已切換後端 API 網址為: ${getApiBaseUrl()}` });
    fetchData();
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
        setMessage({ type: 'success', text: '成功新增一筆支出並儲存至 Supabase！' });
      } else if (entryType === 'income') {
        await addIncome({
          account_id: Number(formData.accountId),
          category_id: Number(formData.categoryId),
          amount: Number(formData.amount),
          received_on: formData.date,
          description: formData.description.trim(),
          note: formData.note.trim() || null,
        });
        setMessage({ type: 'success', text: '成功新增一筆收入並儲存至 Supabase！' });
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
        setMessage({ type: 'success', text: '成功新增一筆轉帳並儲存至 Supabase！' });
      }

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
      {/* 頂部標題與連線狀態 */}
      <div className="dashboard-header">
        <div>
          <h1>個人記帳本</h1>
          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
            前後端串接儀表板 (PostgreSQL on Supabase)
          </span>
        </div>
        <button
          type="button"
          className={`api-badge ${apiOnline ? 'online' : 'offline'}`}
          onClick={() => {
            setCustomApiUrl(getApiBaseUrl());
            setTestResult('');
            setShowConfigModal(true);
          }}
          title="點擊設定或切換後端 API 伺服器網址"
        >
          {apiOnline ? '🟢 API: 已連線' : '🔴 API: 未連線 (點擊設定)'}
        </button>
      </div>

      {/* 狀態訊息提示 */}
      {message.text && (
        <div className={`alert ${message.type === 'success' ? 'alert-success' : 'alert-error'}`}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{message.text}</span>
            {!apiOnline && (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                  onClick={() => setShowConfigModal(true)}
                >
                  ⚙️ 設定 API 網址
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                  onClick={fetchData}
                >
                  🔄 重試連線
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 1. 帳戶列表與餘額 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>帳戶資產總覽</div>
        <button
          type="button"
          className="btn-link-action"
          style={{ fontSize: '0.9rem' }}
          onClick={() => setShowAccountModal(true)}
        >
          ＋ 新增帳戶
        </button>
      </div>

      {loading && accounts.length === 0 ? (
        <div className="empty-state">載入帳戶資訊中...</div>
      ) : accounts.length === 0 ? (
        <div className="empty-state">
          目前尚未建立任何帳戶，
          <button type="button" className="btn-link-action" onClick={() => setShowAccountModal(true)}>
            點此立即新增帳戶
          </button>
        </div>
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
            {/* 帳戶選擇（附帶＋新增帳戶快捷按鈕） */}
            <div className="form-group">
              <div className="label-with-action">
                <label>{entryType === 'transfer' ? '轉出帳戶' : '選擇帳戶'}</label>
                <button
                  type="button"
                  className="btn-link-action"
                  onClick={() => setShowAccountModal(true)}
                >
                  ＋ 新增帳戶
                </button>
              </div>
              <select
                name="accountId"
                className="form-control"
                value={formData.accountId}
                onChange={handleInputChange}
                required
              >
                {accounts.length === 0 ? (
                  <option value="">(尚未建立帳戶)</option>
                ) : (
                  accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({acc.currency} / 餘額: ${acc.balance ?? acc.opening_balance ?? 0})
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* 若為轉帳：轉入帳戶 */}
            {entryType === 'transfer' ? (
              <div className="form-group">
                <div className="label-with-action">
                  <label>轉入帳戶</label>
                  <button
                    type="button"
                    className="btn-link-action"
                    onClick={() => setShowAccountModal(true)}
                  >
                    ＋ 新增帳戶
                  </button>
                </div>
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
                placeholder={entryType === 'expense' ? '例：午餐便當' : entryType === 'income' ? '例：本月薪資' : '例：提款備註'}
                value={formData.description}
                onChange={handleInputChange}
                required={entryType !== 'transfer'}
              />
            </div>

            {/* 備註 (選填) */}
            <div className="form-group">
              <label>詳細備註 (選填)</label>
              <input
                type="text"
                name="note"
                className="form-control"
                placeholder="補充備註..."
                value={formData.note}
                onChange={handleInputChange}
              />
            </div>
          </div>

          <button
            type="submit"
            className={`btn-submit ${entryType}`}
            disabled={submitting || accounts.length === 0}
          >
            {submitting ? '儲存中...' : accounts.length === 0 ? '請先建立帳戶' : entryType === 'expense' ? '確認送出支出' : entryType === 'income' ? '確認送出收入' : '確認送出轉帳'}
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

      {/* Modal 1: 新增帳戶彈窗 */}
      {showAccountModal && (
        <div className="modal-overlay" onClick={() => setShowAccountModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>＋ 新增帳戶（儲存至 Supabase）</h3>
              <button type="button" className="modal-close-btn" onClick={() => setShowAccountModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateAccount}>
              <div className="form-group" style={{ marginBottom: 14 }}>
                <label>帳戶名稱 *</label>
                <input
                  type="text"
                  name="name"
                  className="form-control"
                  placeholder="例：玉山主帳戶、台幣錢包、國泰信用卡"
                  value={accountFormData.name}
                  onChange={handleAccountInputChange}
                  required
                />
              </div>

              <div className="form-group" style={{ marginBottom: 14 }}>
                <label>帳戶種類 *</label>
                <select
                  name="kind"
                  className="form-control"
                  value={accountFormData.kind}
                  onChange={handleAccountInputChange}
                  required
                >
                  <option value="bank">銀行帳戶 (bank)</option>
                  <option value="cash">現金 (cash)</option>
                  <option value="credit_card">信用卡 (credit_card)</option>
                  <option value="broker">券商交割戶 (broker)</option>
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                <div className="form-group">
                  <label>幣別代碼 *</label>
                  <input
                    type="text"
                    name="currency"
                    className="form-control"
                    placeholder="TWD"
                    maxLength={3}
                    value={accountFormData.currency}
                    onChange={handleAccountInputChange}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>初始開帳餘額</label>
                  <input
                    type="number"
                    name="opening_balance"
                    className="form-control"
                    placeholder="0"
                    step="any"
                    value={accountFormData.opening_balance}
                    onChange={handleAccountInputChange}
                  />
                </div>
              </div>

              {accountFormData.kind === 'credit_card' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                  <div className="form-group">
                    <label>結帳日 (1~31，選填)</label>
                    <input
                      type="number"
                      name="statement_day"
                      className="form-control"
                      placeholder="例：15"
                      min="1"
                      max="31"
                      value={accountFormData.statement_day}
                      onChange={handleAccountInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label>繳款日 (1~31，選填)</label>
                    <input
                      type="number"
                      name="payment_day"
                      className="form-control"
                      placeholder="例：5"
                      min="1"
                      max="31"
                      value={accountFormData.payment_day}
                      onChange={handleAccountInputChange}
                    />
                  </div>
                </div>
              )}

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowAccountModal(false)}
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting}
                >
                  {submitting ? '儲存中...' : '儲存至 Supabase 資料庫'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 2: API 伺服器網址設定彈窗 */}
      {showConfigModal && (
        <div className="modal-overlay" onClick={() => setShowConfigModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>⚙️ 後端 API 伺服器網址設定</h3>
              <button type="button" className="modal-close-btn" onClick={() => setShowConfigModal(false)}>
                &times;
              </button>
            </div>

            <div style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: 14, lineHeight: 1.6 }}>
              {window.location.protocol === 'https:' ? (
                <div style={{ background: '#fffbeb', border: '1px solid #fef3c7', padding: '10px 12px', borderRadius: 8, color: '#92400e' }}>
                  <strong>⚠️ 提示（GitHub Pages 線上環境）：</strong><br />
                  GitHub Pages 為 HTTPS 協議，無法直接連線至本機的 <code>http://127.0.0.1:5000</code>（會被瀏覽器強制阻擋）。<br />
                  請填入您部署在 <strong>Vercel</strong> 上的後端網址（例如：<code>https://ledger-api-yourname.vercel.app</code>）。
                </div>
              ) : (
                <div>
                  本地開發環境預設連線為 <code>http://127.0.0.1:5000</code>，請確保本地端已執行 <code>python app.py</code>。
                </div>
              )}
            </div>

            <div className="form-group" style={{ marginBottom: 14 }}>
              <label>API 伺服器 Base URL</label>
              <input
                type="text"
                className="form-control"
                placeholder="http://127.0.0.1:5000 或 https://xxx.vercel.app"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
              />
            </div>

            {testResult && (
              <div style={{ fontSize: '0.85rem', marginBottom: 12, padding: '8px 10px', borderRadius: 6, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                {testResult}
              </div>
            )}

            <div className="modal-actions">
              <button type="button" className="btn-secondary" onClick={handleTestApiUrl}>
                測試連線
              </button>
              <button type="button" className="btn-primary" onClick={handleSaveApiUrl}>
                保存並載入
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
