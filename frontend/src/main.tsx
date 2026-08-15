import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#7c5cfc',
          colorInfo: '#7c5cfc',
          colorLink: '#7c5cfc',
          colorBgLayout: '#f5f7fa',
          colorText: '#1f2430',
          colorTextSecondary: '#5f6672',
          colorBorder: '#e6e9f0',
          borderRadius: 10,
          borderRadiusLG: 16,
          controlHeight: 36,
          fontSize: 14,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
        },
        components: {
          Button: { primaryShadow: '0 4px 12px rgba(124,92,252,0.28)' },
          Card: { borderRadiusLG: 16 },
          Menu: { itemBorderRadius: 10 },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)
