import { Result, Spin } from 'antd'
import { Route, Routes } from 'react-router-dom'

import { useMe } from './api'
import AppLayout from './components/AppLayout'
import AuditLog from './pages/AuditLog'
import CheckReport from './pages/CheckReport'
import ClassApprovals from './pages/ClassApprovals'
import Checks from './pages/Checks'
import ControlTower from './pages/ControlTower'
import Dashboard from './pages/Dashboard'
import DrawingDetail from './pages/DrawingDetail'
import DrawingRegister from './pages/DrawingRegister'
import GeneralLedger from './pages/GeneralLedger'
import InvoiceDetail from './pages/InvoiceDetail'
import Invoices from './pages/Invoices'
import ItemDetail from './pages/ItemDetail'
import Items from './pages/Items'
import Login from './pages/Login'
import NewCheck from './pages/NewCheck'
import Payables from './pages/Payables'
import PurchaseOrderDetail from './pages/PurchaseOrderDetail'
import PurchaseOrders from './pages/PurchaseOrders'
import Receipts from './pages/Receipts'
import ReleaseGate from './pages/ReleaseGate'
import RequisitionDetail from './pages/RequisitionDetail'
import Requisitions from './pages/Requisitions'
import RuleLibrary from './pages/RuleLibrary'
import StockLedger from './pages/StockLedger'
import Users from './pages/Users'
import VendorDetail from './pages/VendorDetail'
import Vendors from './pages/Vendors'

export default function App() {
  const me = useMe()
  if (me.isPending) return <Spin fullscreen />
  if (me.isError) return <Result status="error" title="The server cannot be reached" subTitle={me.error.message} />
  if (!me.data) return <Login />
  return (
    <Routes>
      <Route element={<AppLayout me={me.data} />}>
        {/* PRAVAH: control tower, procurement, inventory and finance. */}
        <Route index element={<ControlTower me={me.data} />} />
        <Route path="requisitions" element={<Requisitions me={me.data} />} />
        <Route path="requisitions/:prNo" element={<RequisitionDetail me={me.data} />} />
        <Route path="purchase-orders" element={<PurchaseOrders me={me.data} />} />
        <Route path="purchase-orders/:poNo" element={<PurchaseOrderDetail me={me.data} />} />
        {/* A goods receipt opens in a drawer over the list, so both addresses show the list. */}
        <Route path="receipts" element={<Receipts />} />
        <Route path="receipts/:grnNo" element={<Receipts />} />
        <Route path="invoices" element={<Invoices me={me.data} />} />
        <Route path="invoices/:invNo" element={<InvoiceDetail me={me.data} />} />
        <Route path="vendors" element={<Vendors />} />
        <Route path="vendors/:vendorId" element={<VendorDetail me={me.data} />} />
        <Route path="items" element={<Items me={me.data} />} />
        <Route path="items/:itemCode" element={<ItemDetail me={me.data} />} />
        <Route path="stock" element={<StockLedger me={me.data} />} />
        <Route path="ledger" element={<GeneralLedger />} />
        <Route path="payables" element={<Payables />} />
        {/* Sentinel, the engineering release module. */}
        <Route path="release" element={<Dashboard me={me.data} />} />
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
