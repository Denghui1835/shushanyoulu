import React from 'react'

interface PageHeaderProps {
  icon?: React.ReactNode
  title: React.ReactNode
  subtitle?: React.ReactNode
  extra?: React.ReactNode
}

/** 全站统一的页面头：图标 + 标题 + 副标题 + 右侧操作区 */
export default function PageHeader({ icon, title, subtitle, extra }: PageHeaderProps) {
  return (
    <div className="yq-page-header">
      {icon && <div className="yq-page-header-icon">{icon}</div>}
      <div style={{ minWidth: 0 }}>
        <h1>{title}</h1>
        {subtitle && <div className="yq-page-header-sub">{subtitle}</div>}
      </div>
      {extra && <div className="yq-page-header-extra">{extra}</div>}
    </div>
  )
}
