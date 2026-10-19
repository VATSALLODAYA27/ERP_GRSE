import {
  AppstoreOutlined,
  AuditOutlined,
  BookOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  FileAddOutlined,
  FileDoneOutlined,
  FileProtectOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  InboxOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  RadarChartOutlined,
  ReconciliationOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  StopOutlined,
  SwapOutlined,
  TableOutlined,
  TeamOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Avatar, Button, Flex, Layout, Menu, Tooltip, Typography } from 'antd'
import { useState, type ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { can, postJson, type User } from '../api'
import Helper from './Helper'
import ModeSwitch from './ModeSwitch'
import { ROLE_LABEL } from './Tags'

type NavItem = { key: string; label: string; hint: string; icon: ReactNode; show?: (user: User) => boolean }

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Control tower',
    items: [
      { key: '/', label: 'Control Tower', hint: 'Deliveries at risk, anomalies and what to reorder, today', icon: <RadarChartOutlined /> },
      { key: '/release', label: 'Release Dashboard', hint: 'Drawing checks and work orders that need attention', icon: <DashboardOutlined /> },
    ],
  },
  {
    group: 'Procurement',
    items: [
      { key: '/requisitions', label: 'Requisitions', hint: 'Requests for material, waiting for approval or ordering', icon: <FileAddOutlined /> },
      { key: '/purchase-orders', label: 'Purchase Orders', hint: 'Orders with vendors, their deliveries and delivery risk', icon: <ShoppingCartOutlined /> },
      { key: '/receipts', label: 'Goods Receipts', hint: 'What arrived at the stores, accepted and rejected', icon: <InboxOutlined /> },
      { key: '/invoices', label: 'Vendor Invoices', hint: 'Invoices matched against the order and the receipt', icon: <FileTextOutlined /> },
      { key: '/vendors', label: 'Vendors', hint: 'Vendor scorecards: delivery, quality and spend (mock data)', icon: <ShopOutlined /> },
    ],
  },
  {
    group: 'Inventory',
    items: [
      { key: '/items', label: 'Items & Stock', hint: 'Every item, its stock in each store and its status', icon: <AppstoreOutlined /> },
      { key: '/stock', label: 'Stock Ledger', hint: 'Every receipt, issue, transfer and adjustment', icon: <SwapOutlined /> },
    ],
  },
  {
    group: 'Finance',
    items: [
      { key: '/ledger', label: 'General Ledger', hint: 'Journal, trial balance and chart of accounts', icon: <ReconciliationOutlined /> },
      { key: '/payables', label: 'Payables', hint: 'What is owed to vendors, aged by due date', icon: <WalletOutlined /> },
    ],
  },
  {
    group: 'Engineering release',
    items: [
      { key: '/register', label: 'Drawing Register', hint: 'Every drawing, its current revision and status', icon: <TableOutlined /> },
      { key: '/checks/new', label: 'New Check', hint: 'Upload a drawing and check it against the rules', icon: <FileSearchOutlined /> },
      { key: '/checks', label: 'Checks', hint: 'Every check that has been run', icon: <FileDoneOutlined /> },
      { key: '/gate', label: 'Release Gate', hint: 'Which work orders may be released', icon: <StopOutlined /> },
      { key: '/class-approvals', label: 'Class Approvals', hint: 'Drawings waiting on class or customer approval', icon: <FileProtectOutlined /> },
      { key: '/rules', label: 'Rule Library', hint: 'The rules every check runs against', icon: <BookOutlined /> },
    ],
  },
  {
    group: 'Administration',
    items: [
      { key: '/audit', label: 'Audit Log', hint: 'Who did what, and when', icon: <AuditOutlined />, show: can.readAudit },
      { key: '/users', label: 'Users', hint: 'Accounts and their roles', icon: <TeamOutlined />, show: can.manageUsers },
    ],
  },
]

const menuItem = ({ key, label, icon }: NavItem) => ({ key, icon, label: <Link to={key}>{label}</Link> })

export default function AppLayout({ me }: { me: User }) {
  const { pathname } = useLocation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((item) => !item.show || item.show(me)) })).filter((g) => g.items.length)
  const nav = groups.flatMap((g) => g.items)
  // The longest matching path wins, so /checks/new selects "New Check" and /checks/7 selects "Checks".
  // A whole path segment must match, so a page is never selected by a name that merely starts the same way.
  const current =
    [...nav].sort((a, b) => b.key.length - a.key.length).find((item) => pathname === item.key || pathname.startsWith(item.key === '/' ? '/' : `${item.key}/`)) ?? nav[0]
  // A goods receipt opens in a drawer over the list, so opening one does not restart the page.
  const pageKey = pathname.startsWith('/receipts') ? '/receipts' : pathname

  const signOut = async () => {
    await postJson('/auth/logout').catch(() => undefined)
    // Set, not clear(): clearing the cache would leave the mounted "me" query showing the old user.
    queryClient.setQueryData(['me'], null)
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
    navigate('/')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider theme="light" width={256} collapsed={collapsed} trigger={null} className="app-sider">
        <div className="app-sider-inner">
          <div className="brand">
            <DeploymentUnitOutlined />
            {!collapsed && (
              <span>
                SENTINEL
                <small>Shipyard ERP intelligence</small>
              </span>
            )}
          </div>
          <Menu
            mode="inline"
            style={{ flex: 1, border: 0, overflowY: 'auto' }}
            selectedKeys={[current.key]}
            // Group headings do not fit the collapsed rail.
            items={collapsed ? nav.map(menuItem) : groups.map((g) => ({ type: 'group' as const, key: g.group, label: g.group.toUpperCase(), children: g.items.map(menuItem) }))}
          />
          <Flex className="user-card" align="center" justify="center" gap={10}>
            {!collapsed && (
              <>
                <Avatar style={{ background: 'var(--accent-grad)', flex: 'none' }}>{me.name.slice(0, 1).toUpperCase()}</Avatar>
                <div style={{ flex: 1, minWidth: 0, lineHeight: 1.25 }}>
                  <Typography.Text strong ellipsis style={{ display: 'block' }}>
                    {me.name}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {ROLE_LABEL[me.role]}
                  </Typography.Text>
                </div>
              </>
            )}
            <Tooltip title="Sign out" placement="right">
              <Button type="text" icon={<LogoutOutlined />} aria-label="Sign out" onClick={signOut} />
            </Tooltip>
          </Flex>
        </div>
      </Layout.Sider>
      <Layout>
        <Layout.Header className="app-header">
          <Flex align="center" gap={12} style={{ height: '100%' }}>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              aria-label={collapsed ? 'Expand the menu' : 'Collapse the menu'}
              onClick={() => setCollapsed(!collapsed)}
            />
            <div style={{ flex: 1, minWidth: 0, lineHeight: 1.3 }}>
              <Typography.Title level={4} ellipsis style={{ margin: 0 }}>
                {current.label}
              </Typography.Title>
              <Typography.Text type="secondary" ellipsis style={{ display: 'block' }}>
                {current.hint}
              </Typography.Text>
            </div>
            <ModeSwitch />
            {current.key !== '/checks/new' && (
              <Link to="/checks/new">
                <Button type="primary" icon={<PlusOutlined />}>
                  New check
                </Button>
              </Link>
            )}
          </Flex>
        </Layout.Header>
        <Layout.Content style={{ padding: '8px 24px 32px' }}>
          {/* The key restarts the fade-in each time the page changes. */}
          <div key={pageKey} className="page">
            <Outlet />
          </div>
        </Layout.Content>
      </Layout>
      <Helper me={me} page={current.label} />
    </Layout>
  )
}
