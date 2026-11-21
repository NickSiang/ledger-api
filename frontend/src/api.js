import axios from 'axios';

// 預設為本地端 Flask 伺服器網址，亦可透過 .env 中的 VITE_API_BASE_URL 覆蓋（適用於未來 GitHub Pages 串接 Vercel 後端）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

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
        console.error(`獲取帳戶 ${acc.id} 餘額失敗:`, err);
        return {
          ...acc,
          balance: acc.opening_balance || 0,
        };
      }
    })
  );

  return accountsWithBalance;
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
