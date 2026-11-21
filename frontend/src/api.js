import axios from 'axios';

// 取得當前設定的 API Base URL（優先採用 localStorage 中使用者自訂的網址，次選環境變數，預設為本地端）
export const getApiBaseUrl = () => {
  const customUrl = localStorage.getItem('LEDGER_API_URL');
  if (customUrl && customUrl.trim()) {
    return customUrl.trim().replace(/\/+$/, '');
  }
  return (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/+$/, '');
};

const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 8000,
});

// 當每次發送請求時，動態確保 baseURL 為最新設定
apiClient.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  return config;
});

// 設定自訂 API Base URL（適用於 GitHub Pages 填寫 Vercel 後端網址）
export const setApiBaseUrl = (url) => {
  if (url && url.trim()) {
    localStorage.setItem('LEDGER_API_URL', url.trim().replace(/\/+$/, ''));
  } else {
    localStorage.removeItem('LEDGER_API_URL');
  }
  apiClient.defaults.baseURL = getApiBaseUrl();
};

// 檢查後端健康狀況
export const checkHealth = async () => {
  const response = await apiClient.get('/');
  return response.data;
};

// 帳戶相關 API
export const getAccounts = async () => {
  const response = await apiClient.get('/api/accounts');
  const accounts = response.data.data || [];

  // 同時抓取每個帳戶的最新計算餘額
  const accountsWithBalance = await Promise.all(
    accounts.map(async (acc) => {
      try {
        const balRes = await apiClient.get(`/api/accounts/${acc.id}/balance`);
        return {
          ...acc,
          ...balRes.data.data,
        };
      } catch (err) {
        return {
          ...acc,
          balance: acc.opening_balance || 0,
        };
      }
    })
  );

  return accountsWithBalance;
};

// 新增帳戶並儲存至 Supabase
export const createAccount = async (data) => {
  const response = await apiClient.post('/api/accounts', data);
  return response.data.data;
};

// 分類 API
export const getCategories = async () => {
  const response = await apiClient.get('/api/categories');
  return response.data.data || { income: [], expense: [] };
};

// 支出相關 API
export const addExpense = async (data) => {
  const response = await apiClient.post('/api/expenses', data);
  return response.data.data;
};

export const getExpenses = async (params = {}) => {
  const response = await apiClient.get('/api/expenses', { params });
  return response.data.data || [];
};

export const deleteExpense = async (id) => {
  const response = await apiClient.delete(`/api/expenses/${id}`);
  return response.data;
};

// 收入相關 API
export const addIncome = async (data) => {
  const response = await apiClient.post('/api/incomes', data);
  return response.data.data;
};

export const getIncomes = async (params = {}) => {
  const response = await apiClient.get('/api/incomes', { params });
  return response.data.data || [];
};

export const deleteIncome = async (id) => {
  const response = await apiClient.delete(`/api/incomes/${id}`);
  return response.data;
};

// 移轉相關 API
export const getTransfers = async () => {
  const response = await apiClient.get('/api/transfers');
  return response.data.data || [];
};

export const addTransfer = async (data) => {
  const response = await apiClient.post('/api/transfers', data);
  return response.data.data;
};

export const deleteTransfer = async (id) => {
  const response = await apiClient.delete(`/api/transfers/${id}`);
  return response.data;
};

export default apiClient;
