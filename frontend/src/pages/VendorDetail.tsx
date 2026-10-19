import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Col, Descriptions, Flex, Row, Skeleton, Statistic, Table, Tabs, Tag, Typography } from 'antd'
import { useParams, useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { money, moneyShort, pct, useVendor } from '../erpApi'
import { LoadError, MsmeTag, StateTag, useDialog } from '../components/erp/Bits'
import OrderForm from '../components/erp/OrderForm'
import { VendorLedgerTable } from './Payables'
import { PO_COLUMNS } from './PurchaseOrders'

/** One vendor: the scorecard from its delivery record, its orders and what is owed to it. */
export default function VendorDetail({ me }: { me: User }) {
  const { vendorId = '' } = useParams()
  const query = useVendor(vendorId)
  const [params, setParams] = useSearchParams()
  const ordering = useDialog()

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) return <LoadError error={query.error} what="Vendor" back="/vendors" backLabel="Back to vendors" />
  const v = query.data
  const card = v.scorecard ?? v

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start" gap={16} wrap>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {v.name} <StateTag kind="grade" value={card.grade} /> {v.msme && <MsmeTag />} {v.active === false && <Tag color="error">Inactive</Tag>}
            </Typography.Title>
            <Typography.Text type="secondary">
              {v.vendor_id} · {v.city} · {v.category}
            </Typography.Text>
          </div>
          {can.request(me) && (
            <Button icon={<PlusOutlined />} onClick={() => ordering.show()}>
              New purchase order
            </Button>
          )}
        </Flex>
        <Descriptions column={{ xs: 1, md: 4 }} size="small" style={{ marginTop: 16 }}>
          <Descriptions.Item label="GSTIN">{v.gstin || '—'}</Descriptions.Item>
          <Descriptions.Item label="Payment terms">{v.payment_terms_days} days</Descriptions.Item>
          <Descriptions.Item label="Usual lead time">{v.lead_time_days} days</Descriptions.Item>
          <Descriptions.Item label="MSME">{v.msme ? 'Yes' : 'No'}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          { title: 'On time', value: pct(card.on_time_pct) },
          { title: 'Average delay', value: card.avg_delay_days === null || card.avg_delay_days === undefined ? '—' : `${Math.round(card.avg_delay_days * 10) / 10} days` },
          { title: 'Rejected at receipt', value: pct(card.rejection_pct) },
          { title: 'Orders closed', value: 'orders_closed' in card ? card.orders_closed : '—' },
          { title: 'Spend this year', value: moneyShort(card.spend_ytd) },
          { title: 'Open orders', value: moneyShort(card.open_po_value) },
        ].map((s) => (
          <Col key={s.title} xs={12} md={8} xl={4}>
            <Card size="small" style={{ height: '100%' }}>
              <Statistic title={s.title} value={s.value} />
            </Card>
          </Col>
        ))}
      </Row>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'orders'}
          onChange={(tab) => setParams({ tab }, { replace: true })}
          items={[
            {
              key: 'orders',
              label: `Purchase orders (${v.orders?.length ?? 0})`,
              children: <Table size="small" rowKey="po_no" columns={PO_COLUMNS} dataSource={v.orders} pagination={{ pageSize: 15, hideOnSinglePage: true }} locale={{ emptyText: 'No orders with this vendor.' }} />,
            },
            {
              key: 'payables',
              label: 'Payables',
              children: (
                <>
                  <Typography.Paragraph>
                    Owed now: <strong>{money(v.payables?.balance)}</strong>
                  </Typography.Paragraph>
                  <VendorLedgerTable rows={v.payables?.entries} loading={false} />
                </>
              ),
            },
          ]}
        />
      </Card>
      {ordering.key > 0 && <OrderForm key={ordering.key} open={ordering.open} onClose={ordering.hide} vendorId={v.vendor_id} />}
    </>
  )
}
