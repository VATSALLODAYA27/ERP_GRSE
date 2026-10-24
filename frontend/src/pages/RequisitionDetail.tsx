import { CheckOutlined, CloseOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Flex, Modal, Skeleton, Space, Table, Typography } from 'antd'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { can, type User } from '../api'
import { AFFECTS, erp, fmtDate, money, qty, useAction, useRequisition, type RequisitionLine } from '../erpApi'
import { AuditTable, ItemLink, LoadError, PoLink, ReasonModal, StateTag, WorkOrderTags } from '../components/erp/Bits'

/** One requisition: its lines, who decided it, and the purchase orders it became. */
export default function RequisitionDetail({ me }: { me: User }) {
  const { prNo = '' } = useParams()
  const query = useRequisition(prNo)
  const [dialog, setDialog] = useState<'reject' | 'convert' | null>(null)
  const approve = useAction(() => erp.approveRequisition(prNo), AFFECTS.requisition, `Requisition ${prNo} approved`)
  const reject = useAction((reason: string) => erp.rejectRequisition(prNo, reason), AFFECTS.requisition, `Requisition ${prNo} rejected`)
  const convert = useAction(() => erp.convertRequisition(prNo), AFFECTS.order, (r) =>
    r?.orders?.length ? `Draft purchase order${r.orders.length === 1 ? '' : 's'} created: ${r.orders.join(', ')}` : 'Converted to purchase orders',
  )

  if (query.isPending) return <Skeleton active paragraph={{ rows: 8 }} />
  if (query.isError) return <LoadError error={query.error} what="Requisition" back="/requisitions" backLabel="Back to requisitions" />
  const pr = query.data
  const decides = can.approve(me)
  const total = pr.value ?? pr.lines.reduce((sum, l) => sum + (l.est_value ?? 0), 0)

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start" gap={16} wrap>
          <Typography.Title level={3} style={{ marginTop: 0 }}>
            {pr.pr_no} <StateTag kind="pr" value={pr.status} />
          </Typography.Title>
          {decides && (
            <Space wrap>
              {pr.status === 'SUBMITTED' && (
                <>
                  <Button type="primary" icon={<CheckOutlined />} loading={approve.isPending} onClick={() => approve.mutate()}>
                    Approve
                  </Button>
                  <Button danger icon={<CloseOutlined />} onClick={() => setDialog('reject')}>
                    Reject
                  </Button>
                </>
              )}
              {pr.status === 'APPROVED' && (
                <Button type="primary" icon={<ShoppingCartOutlined />} onClick={() => setDialog('convert')}>
                  Convert to purchase orders
                </Button>
              )}
            </Space>
          )}
        </Flex>
        <Descriptions column={{ xs: 1, md: 3 }} size="small">
          <Descriptions.Item label="Raised on">{fmtDate(pr.created_on)}</Descriptions.Item>
          <Descriptions.Item label="Requested by">{pr.requested_by}</Descriptions.Item>
          <Descriptions.Item label="Work order">
            <WorkOrderTags orders={[pr.work_order]} />
          </Descriptions.Item>
          <Descriptions.Item label="Source">
            <StateTag kind="source" value={pr.source} />
          </Descriptions.Item>
          <Descriptions.Item label="Decided by">{pr.decided_by || '—'}</Descriptions.Item>
          <Descriptions.Item label="Estimated value">{money(total)}</Descriptions.Item>
          {pr.note && <Descriptions.Item label="Note">{pr.note}</Descriptions.Item>}
        </Descriptions>
        {!decides && pr.status === 'SUBMITTED' && (
          <Typography.Text type="secondary">A reviewer approves the requisition and converts it into purchase orders.</Typography.Text>
        )}
      </Card>
      <Card title={`Lines (${pr.lines.length})`}>
        <Table<RequisitionLine>
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={pr.lines}
          columns={[
            { title: 'Item', dataIndex: 'item_code', render: (code) => <ItemLink code={code} /> },
            { title: 'Description', dataIndex: 'description' },
            { title: 'Qty', dataIndex: 'qty', align: 'right', render: qty },
            { title: 'Need by', dataIndex: 'need_by', render: fmtDate },
            { title: 'Est. value', dataIndex: 'est_value', align: 'right', render: (v) => money(v) },
            { title: 'Purchase order', dataIndex: 'po_no', render: (no) => (no ? <PoLink no={no} /> : <Typography.Text type="secondary">Not yet ordered</Typography.Text>) },
          ]}
        />
      </Card>
      {pr.audit && pr.audit.length > 0 && (
        <Card title={`Audit trail (${pr.audit.length})`} style={{ marginTop: 16 }}>
          <AuditTable entries={pr.audit} />
        </Card>
      )}
      <ReasonModal
        open={dialog === 'reject'}
        title={`Reject ${pr.pr_no}`}
        okText="Reject"
        danger
        required
        description="The requester sees the reason. A rejected requisition cannot be converted."
        loading={reject.isPending}
        onClose={() => setDialog(null)}
        onSubmit={(reason) => reject.mutate(reason, { onSuccess: () => setDialog(null) })}
      />
      <Modal
        open={dialog === 'convert'}
        title={`Convert ${pr.pr_no} to purchase orders`}
        okText="Create draft orders"
        confirmLoading={convert.isPending}
        onOk={() => convert.mutate(undefined, { onSuccess: () => setDialog(null) })}
        onCancel={() => setDialog(null)}
      >
        <Typography.Paragraph>
          One draft purchase order is created for each preferred vendor on these lines, at the standard price, promised at today plus the vendor's lead time.
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary">Each order still needs approval before it is sent.</Typography.Paragraph>
      </Modal>
    </>
  )
}
