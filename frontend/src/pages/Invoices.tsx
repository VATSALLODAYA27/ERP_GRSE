import { ExclamationCircleFilled, PlusOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Input, Select, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { fmtDate, money, today, useInvoices, type InvoiceSummary } from '../erpApi'
import { InvoiceLink, PoLink, StateTag, VendorLink, stateOptions, useDialog } from '../components/erp/Bits'
import InvoiceForm from '../components/erp/InvoiceForm'
import { ErrorAlert } from '../components/Tags'

const UNPAID = new Set(['MATCHED', 'EXCEPTION', 'APPROVED'])

export const flagCount = (flags: InvoiceSummary['flags']) => (typeof flags === 'number' ? flags : (flags?.length ?? 0))

/** The due date, in red once it has passed on an invoice not yet paid. */
export function DueDate({ date, status }: { date: string; status: string }) {
  const overdue = UNPAID.has(status) && date < today()
  return overdue ? (
    <Typography.Text type="danger" style={{ whiteSpace: 'nowrap' }}>
      {fmtDate(date)} (overdue)
    </Typography.Text>
  ) : (
    <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(date)}</span>
  )
}

const COLUMNS: ColumnsType<InvoiceSummary> = [
  { title: 'Invoice', dataIndex: 'inv_no', sorter: (a, b) => a.inv_no.localeCompare(b.inv_no), render: (no) => <InvoiceLink no={no} /> },
  { title: "Vendor's no.", dataIndex: 'vendor_invoice_no' },
  { title: 'Vendor', dataIndex: 'vendor_name', render: (name, inv) => <VendorLink id={inv.vendor_id} name={name} /> },
  { title: 'Purchase order', dataIndex: 'po_no', render: (no) => <PoLink no={no} /> },
  { title: 'Invoice date', dataIndex: 'invoice_date', sorter: (a, b) => a.invoice_date.localeCompare(b.invoice_date), defaultSortOrder: 'descend', render: fmtDate },
  { title: 'Due', dataIndex: 'due_date', sorter: (a, b) => a.due_date.localeCompare(b.due_date), render: (d, inv) => <DueDate date={d} status={inv.status} /> },
  { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="invoice" value={s} /> },
  { title: 'Total', dataIndex: 'total', align: 'right', sorter: (a, b) => a.total - b.total, render: (v) => money(v) },
  {
    title: 'Flags',
    dataIndex: 'flags',
    render: (flags) => {
      const n = flagCount(flags)
      return n ? (
        <Tag color="warning" icon={<ExclamationCircleFilled />}>
          {n}
        </Tag>
      ) : null
    },
  },
]

export default function Invoices({ me }: { me: User }) {
  const invoices = useInvoices()
  const [params] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<string | undefined>(params.get('status') ?? undefined)
  const dialog = useDialog()
  const needle = search.trim().toLowerCase()
  const rows = (invoices.data ?? []).filter(
    (inv) => (!status || inv.status === status) && `${inv.inv_no} ${inv.vendor_invoice_no} ${inv.vendor_name} ${inv.po_no}`.toLowerCase().includes(needle),
  )

  return (
    <Card>
      <ErrorAlert error={invoices.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="Invoice, vendor or order" aria-label="Search vendor invoices" onChange={(e) => setSearch(e.target.value)} style={{ width: 300 }} />
        <Select allowClear placeholder="Status" aria-label="Filter by status" value={status} onChange={setStatus} options={stateOptions('invoice')} style={{ width: 180 }} />
        {can.request(me) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => dialog.show()} style={{ marginLeft: 'auto' }}>
            Enter vendor invoice
          </Button>
        )}
      </Flex>
      <Table
        size="small"
        rowKey="inv_no"
        columns={COLUMNS}
        dataSource={rows}
        loading={invoices.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No invoices match.' }}
      />
      {dialog.key > 0 && <InvoiceForm key={dialog.key} open={dialog.open} onClose={dialog.hide} />}
    </Card>
  )
}
