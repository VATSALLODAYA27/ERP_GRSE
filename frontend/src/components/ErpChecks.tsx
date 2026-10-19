import { Alert, Empty, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Link } from 'react-router-dom'

import type { BomRow, BomValues, Check, Impact } from '../api'

const BOM_RESULT: Record<BomRow['result'], { label: string; color: string }> = {
  match: { label: 'Match', color: 'success' },
  mismatch: { label: 'Mismatch', color: 'error' },
  not_in_erp: { label: 'Not in ERP', color: 'error' },
  not_on_drawing: { label: 'Not on drawing', color: 'error' },
}

const BOM_FIELDS: [keyof BomValues, string][] = [
  ['material', 'Material'],
  ['thickness_mm', 'Thk (mm)'],
  ['qty', 'Qty'],
]

/** One pair of columns per property: the value on the drawing, then the value in the ERP, highlighted when they differ. */
const bomColumns: ColumnsType<BomRow> = [
  { title: 'Part no.', dataIndex: 'part_no', render: (no) => <strong>{no}</strong> },
  { title: 'Description', dataIndex: 'description' },
  ...BOM_FIELDS.map(([field, title]) => ({
    title,
    children: (['drawing', 'erp'] as const).map((side) => ({
      title: side === 'drawing' ? 'Drawing' : 'ERP',
      key: `${field}-${side}`,
      render: (_: unknown, row: BomRow) => {
        const value = row[side]?.[field]
        if (value === undefined) return <Typography.Text type="secondary">—</Typography.Text>
        const differs = row.drawing && row.erp && row.drawing[field] !== row.erp[field]
        return differs ? <Typography.Text type="danger" strong>{value}</Typography.Text> : value
      },
    })),
  })),
  {
    title: 'Result',
    dataIndex: 'result',
    render: (result: BomRow['result']) => <Tag color={BOM_RESULT[result].color}>{BOM_RESULT[result].label}</Tag>,
  },
]

/** The drawing's parts list beside the ERP bill of materials for the same revision. */
export function BomCheck({ check }: { check: Check }) {
  if (!check.bom_check) {
    return <Empty description={`The ERP extract has no bill of materials for ${check.drawing_no || 'this drawing'} revision ${check.revision}.`} />
  }
  const problems = check.bom_check.filter((row) => row.result !== 'match').length
  return (
    <>
      <Alert
        showIcon
        type={problems ? 'error' : 'success'}
        style={{ marginBottom: 16 }}
        message={
          problems
            ? `${problems} of ${check.bom_check.length} parts do not agree with the ERP bill of materials. Material ordered from the ERP would not match this drawing.`
            : `All ${check.bom_check.length} parts agree with the ERP bill of materials.`
        }
      />
      <Table size="small" bordered rowKey="part_no" pagination={false} columns={bomColumns} dataSource={check.bom_check} />
    </>
  )
}

const workOrderColumns: ColumnsType<Impact['work_orders'][number]> = [
  { title: 'Work order', dataIndex: 'order_no', render: (no) => <strong>{no}</strong> },
  { title: 'Released against', dataIndex: 'rev', render: (rev) => `Rev ${rev}` },
  {
    title: 'State',
    dataIndex: 'state',
    render: (state) => (state === 'RELEASED' ? <Tag color="error">Already released to the shop floor</Tag> : <Tag>Created, not yet released</Tag>),
  },
]

const purchaseOrderColumns: ColumnsType<Impact['purchase_orders'][number]> = [
  { title: 'Purchase order', dataIndex: 'po_no', render: (no) => <strong>{no}</strong> },
  { title: 'Part no.', dataIndex: 'part_no' },
  { title: 'Ordered qty', dataIndex: 'qty' },
  { title: 'What changed on the drawing', dataIndex: 'change' },
]

/** Who is affected by the change from the previous revision to this one. */
export function ImpactView({ check }: { check: Check }) {
  const impact = check.impact
  if (!impact) {
    return (
      <Empty description="Impact is worked out from a revision change, and this check has no earlier revision to compare with. Upload the previous revision together with the drawing under New Check." />
    )
  }
  const orders = impact.work_orders.length
  const pos = impact.purchase_orders.length
  return (
    <>
      <Alert
        showIcon
        type={orders + pos ? 'warning' : 'success'}
        style={{ marginBottom: 16 }}
        message={
          orders + pos
            ? `The change from Rev ${impact.from_revision} to Rev ${check.revision} affects ${orders} work order${orders === 1 ? '' : 's'} and ${pos} open purchase order${pos === 1 ? '' : 's'}.`
            : `No work orders or open purchase orders are affected by the change from Rev ${impact.from_revision} to Rev ${check.revision}.`
        }
        description={
          <>
            Taken from the ERP extract when this check ran. See the <Link to="/gate">Release Gate</Link> for the current state of every work order.
          </>
        }
      />
      <Typography.Title level={5}>Work orders still on Rev {impact.from_revision}</Typography.Title>
      <Table
        size="small"
        rowKey="order_no"
        pagination={false}
        columns={workOrderColumns}
        dataSource={impact.work_orders}
        locale={{ emptyText: `No work orders use Rev ${impact.from_revision}.` }}
        style={{ marginBottom: 24 }}
      />
      <Typography.Title level={5}>Open purchase orders for parts that changed</Typography.Title>
      <Table
        size="small"
        rowKey="po_no"
        pagination={false}
        columns={purchaseOrderColumns}
        dataSource={impact.purchase_orders}
        locale={{ emptyText: 'No open purchase orders are for parts that changed.' }}
      />
    </>
  )
}
