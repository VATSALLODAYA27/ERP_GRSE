import { FileAddOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Flex, Skeleton, Space, Table, Tabs, Typography } from 'antd'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { fmtDate, money, qty, useItem } from '../erpApi'
import { CriticalTag, LoadError, PoLink, StateTag, VendorLink, useDialog } from '../components/erp/Bits'
import RequisitionForm from '../components/erp/RequisitionForm'
import StockForm, { type StockMode } from '../components/erp/StockForm'
import { MovesTable, StockActions } from './StockLedger'

/** One item: stock in each store, every movement, open orders and the drawings that use it. */
export default function ItemDetail({ me }: { me: User }) {
  const { itemCode = '' } = useParams()
  const query = useItem(itemCode)
  const [params, setParams] = useSearchParams()
  const stock = useDialog<StockMode>()
  const requesting = useDialog()

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) return <LoadError error={query.error} what="Item" back="/items" backLabel="Back to items" />
  const item = query.data

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start" gap={16} wrap>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {item.item_code} <StateTag kind="stock" value={item.status} /> {item.critical && <CriticalTag />}
            </Typography.Title>
            <Typography.Text type="secondary">
              {item.description} · {item.category}
            </Typography.Text>
          </div>
          <Space wrap>
            <StockActions me={me} onAction={(mode) => stock.show(mode)} />
            {can.request(me) && (
              <Button icon={<FileAddOutlined />} onClick={() => requesting.show()}>
                Request more
              </Button>
            )}
          </Space>
        </Flex>
        <Descriptions column={{ xs: 1, md: 4 }} size="small" style={{ marginTop: 16 }}>
          <Descriptions.Item label="On hand">
            <Typography.Text strong type={item.on_hand <= 0 ? 'danger' : undefined}>
              {qty(item.on_hand)} {item.uom}
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="On order">
            {qty(item.on_order)} {item.uom}
          </Descriptions.Item>
          <Descriptions.Item label="Reorder level">
            {qty(item.reorder_level)} {item.uom}
            {item.reorder_qty ? ` (orders of ${qty(item.reorder_qty)})` : ''}
          </Descriptions.Item>
          <Descriptions.Item label="Stock value">{money(item.stock_value)}</Descriptions.Item>
          <Descriptions.Item label="Grade">{item.grade || '—'}</Descriptions.Item>
          <Descriptions.Item label="Standard price">{money(item.std_price, true)}</Descriptions.Item>
          <Descriptions.Item label="Moving-average cost">{money(item.avg_cost, true)}</Descriptions.Item>
          <Descriptions.Item label="Lead time">{item.lead_time_days ? `${item.lead_time_days} days` : '—'}</Descriptions.Item>
          {item.preferred_vendor_id && (
            <Descriptions.Item label="Preferred vendor">
              <VendorLink id={item.preferred_vendor_id} name={item.preferred_vendor_name} />
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'stores'}
          onChange={(tab) => setParams({ tab }, { replace: true })}
          items={[
            {
              key: 'stores',
              label: `By store (${item.by_store.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="store_code"
                  pagination={false}
                  dataSource={item.by_store}
                  locale={{ emptyText: 'Not held in any store.' }}
                  columns={[
                    {
                      title: 'Store',
                      dataIndex: 'store_code',
                      render: (code, s) => (
                        <Link to={`/stock?store=${encodeURIComponent(code)}&item=${encodeURIComponent(item.item_code)}`}>
                          {code} · {s.store_name}
                        </Link>
                      ),
                    },
                    { title: 'Quantity', dataIndex: 'qty', align: 'right', render: (v) => `${qty(v)} ${item.uom}` },
                    { title: 'Value', dataIndex: 'value', align: 'right', render: (v) => money(v) },
                  ]}
                />
              ),
            },
            {
              key: 'moves',
              label: `Movements (${item.moves.length})`,
              children: <MovesTable moves={item.moves} loading={false} withItem={false} pageSize={15} />,
            },
            {
              key: 'orders',
              label: `Open orders (${item.open_orders.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="key"
                  pagination={false}
                  dataSource={item.open_orders.map((o, i) => ({ ...o, key: i }))}
                  locale={{ emptyText: 'No open purchase orders for this item.' }}
                  columns={[
                    { title: 'Purchase order', dataIndex: 'po_no', render: (no) => <PoLink no={no} /> },
                    { title: 'Vendor', dataIndex: 'vendor_name' },
                    { title: 'Ordered', dataIndex: 'qty', align: 'right', render: qty },
                    { title: 'Received', dataIndex: 'received_qty', align: 'right', render: qty },
                    { title: 'Promised', dataIndex: 'promised_date', render: fmtDate },
                    { title: 'Delivery risk', dataIndex: 'risk_level', render: (l) => <StateTag kind="risk" value={l} /> },
                  ]}
                />
              ),
            },
            {
              key: 'used',
              label: `Where used (${item.where_used.length})`,
              children: (
                <>
                  <Typography.Paragraph type="secondary">
                    Drawings whose bill of materials lists this item, from the drawing register. Open a drawing to see its revisions, work orders and release status.
                  </Typography.Paragraph>
                  <Table
                    size="small"
                    rowKey={(w) => `${w.drawing_no}-${w.rev}-${w.part_no}`}
                    pagination={false}
                    dataSource={item.where_used}
                    locale={{ emptyText: 'No drawing lists this item.' }}
                    columns={[
                      { title: 'Drawing', dataIndex: 'drawing_no', render: (no) => <Link to={`/register/${encodeURIComponent(no)}`}>{no}</Link> },
                      { title: 'Rev', dataIndex: 'rev', width: 80 },
                      { title: 'Part no.', dataIndex: 'part_no' },
                      { title: 'Qty per drawing', dataIndex: 'qty', align: 'right', render: qty },
                    ]}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>
      {stock.key > 0 && stock.data && <StockForm key={`stock-${stock.key}`} mode={stock.data} open={stock.open} onClose={stock.hide} item={item.item_code} />}
      {requesting.key > 0 && <RequisitionForm key={`request-${requesting.key}`} open={requesting.open} onClose={requesting.hide} items={[item.item_code]} />}
    </>
  )
}
