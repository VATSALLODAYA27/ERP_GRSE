import { Result, Spin } from 'antd'
import { Route, Routes } from 'react-router-dom'

import { useMe } from './api'
import AppLayout from './components/AppLayout'
import AuditLog from './pages/AuditLog'
import CheckReport from './pages/CheckReport'
import ClassApprovals from './pages/ClassApprovals'
import Checks from './pages/Checks'
import Dashboard from './pages/Dashboard'
import DrawingDetail from './pages/DrawingDetail'
import DrawingRegister from './pages/DrawingRegister'
import Login from './pages/Login'
import NewCheck from './pages/NewCheck'
import ReleaseGate from './pages/ReleaseGate'
import RuleLibrary from './pages/RuleLibrary'
import Users from './pages/Users'

export default function App() {
  const me = useMe()
  if (me.isPending) return <Spin fullscreen />
  if (me.isError) return <Result status="error" title="The server cannot be reached" subTitle={me.error.message} />
  if (!me.data) return <Login />
  return (
    <Routes>
      <Route element={<AppLayout me={me.data} />}>
        <Route index element={<Dashboard me={me.data} />} />
        <Route path="register" element={<DrawingRegister me={me.data} />} />
        <Route path="register/:drawingNo" element={<DrawingDetail me={me.data} />} />
        <Route path="gate" element={<ReleaseGate />} />
        <Route path="class-approvals" element={<ClassApprovals me={me.data} />} />
        <Route path="checks" element={<Checks />} />
        <Route path="checks/new" element={<NewCheck />} />
        <Route path="checks/:id" element={<CheckReport me={me.data} />} />
        <Route path="rules" element={<RuleLibrary me={me.data} />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="users" element={<Users me={me.data} />} />
        <Route path="*" element={<Result status="404" title="Page not found" />} />
      </Route>
    </Routes>
  )
}
