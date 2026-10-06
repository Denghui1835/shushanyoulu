import { Card, Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getAuthToken } from '../api'
import { AuthForm } from '../components/AuthModal'

/** /login：独立登录页（个人中心等处的「去登录」指向这里，不再跳到没有入口的社区页）。 */
export default function LoginPage() {
  const navigate = useNavigate()
  const loggedIn = !!getAuthToken()

  if (loggedIn) {
    return (
      <Result
        status="success"
        title="你已经登录了"
        subTitle="可以直接去个人中心，或回到书架继续学习。"
        extra={[
          <Button type="primary" key="profile" onClick={() => navigate('/profile')}>去个人中心</Button>,
          <Button key="shelf" onClick={() => navigate('/bookshelf')}>回我的书架</Button>,
        ]}
      />
    )
  }

  return (
    <div className="yq-page" style={{ display: 'flex', justifyContent: 'center', paddingTop: 60 }}>
      <Card style={{ width: 400 }} styles={{ body: { padding: '8px 24px 24px' } }}>
        <div style={{ textAlign: 'center', margin: '8px 0 4px' }}>
          <div style={{ fontSize: 22, fontWeight: 600 }}>书山有路</div>
          <div style={{ color: '#999', fontSize: 13 }}>登录后你的书架、计划与元气值才会跟着你走</div>
        </div>
        <AuthForm onSuccess={() => navigate('/')} />
      </Card>
    </div>
  )
}