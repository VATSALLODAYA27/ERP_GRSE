import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons'
import { Card, Flex, Input, Select, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fmtDate, money, useAccounts, useJournal, useTrialBalance, type JournalEntry, type JournalLine, type LedgerAccount } from '../erpApi'
import { ItemLink, RefLink, StateTag, VendorLink, stateOptions } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'

const SOURCES = ['OPENING', 'GRN', 'INVOICE', 'PAYMENT', 'ISSUE', 'ADJUST']

/** A debit or credit cell: blank when zero, so the side that carries the amount stands out. */
const side = (v: number | null | undefined) => (v ? money(v, true) : '')

function JournalLines({ lines }: { lines: JournalLine[] }) {
  return (
    <Table<JournalLine & { key: number }>
      size="small"
      rowKey="key"
      pagination={false}
      dataSource={lines.map((l, i) => ({ ...l, key: i }))}
      columns={[
        { title: 'Account', render: (_, l) => `${l.account_code} ${l.account_name}` },
        { title: 'Debit', dataIndex: 'debit', align: 'right', render: side },
        { title: 'Credit', dataIndex: 'credit', align: 'right', render: side },
        { title: 'Vendor', dataIndex: 'vendor_id', render: (id) => (id ? <VendorLink id={id} /> : '') },
        { title: 'Item', dataIndex: 'item_code', render: (code) => (code ? <ItemLink code={code} /> : '') },
      ]}
    />
  )
}

/** Journal entries, newest first; each opens to its debit and credit lines. */
export function JournalTable({ entries, loading, pageSize }: { entries?: JournalEntry[]; loading: boolean; pageSize?: number }) {
  const columns: ColumnsType<JournalEntry> = [
    { title: 'Entry', dataIndex: 'je_no', render: (no) => <strong style={{ whiteSpace: 'nowrap' }}>{no}</strong> },
    { title: 'Date', dataIndex: 'on_date', render: (d) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(d)}</span> },
    { title: 'Source', dataIndex: 'source_type', render: (s) => <Tag>{s}</Tag> },
    { title: 'Document', dataIndex: 'source_no', render: (no, je) => <RefLink type={je.source_type} no={no} /> },
    { title: 'Narration', dataIndex: 'narration' },
    { title: 'By', dataIndex: 'created_by' },
    { title: 'Amount', dataIndex: 'total', align: 'right', render: (v) => money(v, true) },
  ]
  return (
    <Table
      size="small"
      rowKey="je_no"
      columns={columns}
      dataSource={entries}
      loading={loading}
      pagination={pageSize ? { pageSize, hideOnSinglePage: true } : false}
      expandable={{ rowExpandable: (je) => !!je.lines?.length, expandedRowRender: (je) => <JournalLines lines={je.lines ?? []} /> }}
      locale={{ emptyText: 'No ledger postings.' }}
    />
  )
}

function Journal({ account, setAccount }: { account?: string; setAccount: (code?: string) => void }) {
  const journal = useJournal()
  const accounts = useAccounts()
  const [source, setSource] = useState<string>()
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()
  const rows = (journal.data ?? []).filter(
    (je) =>
      (!source || je.source_type === source) &&
      (!account || je.lines?.some((l) => l.account_code === account)) &&
      `${je.je_no} ${je.source_no} ${je.narration}`.toLowerCase().includes(needle),
  )
  return (
    <>
      <ErrorAlert error={journal.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="Entry, document or narration" aria-label="Search the journal" onChange={(e) => setSearch(e.target.value)} style={{ width: 300 }} />
        <Select allowClear placeholder="Source" aria-label="Filter by source" value={source} onChange={setSource} options={SOURCES.map((value) => ({ value }))} style={{ width: 160 }} />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Account"
          aria-label="Filter by account"
          value={account}
          onChange={setAccount}
          options={(accounts.data ?? []).map((a) => ({ value: a.code, label: `${a.code} ${a.name}` }))}
          style={{ width: 300 }}
        />
      </Flex>
      <JournalTable entries={rows} loading={journal.isPending} pageSize={20} />
    </>
  )
}

function TrialBalanceView() {
  const tb = useTrialBalance()
  const data = tb.data
  return (
    <>
      <ErrorAlert error={tb.error} />
      {data && (
        <Flex align="center" gap={12} style={{ marginBottom: 12 }}>
          {data.balanced ? (
            <Tag color="success" icon={<CheckCircleFilled />} style={{ fontSize: 14, padding: '4px 12px' }}>
              Balanced
            </Tag>
          ) : (
            <Tag color="error" icon={<CloseCircleFilled />} style={{ fontSize: 14, padding: '4px 12px' }}>
              Not balanced
            </Tag>
          )}
          <Typography.Text type="secondary">Total debits equal total credits across every account; each posting is checked to balance before it is saved.</Typography.Text>
        </Flex>
      )}
      <Table
        size="small"
        rowKey="code"
        loading={tb.isPending}
        pagination={false}
        dataSource={data?.rows}
        columns={[
          { title: 'Code', dataIndex: 'code', width: 90 },
          { title: 'Account', dataIndex: 'name' },
          { title: 'Type', dataIndex: 'type', render: (t) => <StateTag kind="account" value={t} /> },
          { title: 'Debit', dataIndex: 'debit', align: 'right', render: side },
          { title: 'Credit', dataIndex: 'credit', align: 'right', render: side },
        ]}
        summary={() =>
          data ? (
            <Table.Summary.Row className="summary-row">
              <Table.Summary.Cell index={0} colSpan={3}>
                <strong>Total</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={3} align="right">
                <strong>{money(data.total_debit, true)}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">
                <strong>{money(data.total_credit, true)}</strong>
              </Table.Summary.Cell>
            </Table.Summary.Row>
          ) : null
        }
      />
    </>
  )
}

function Accounts({ open }: { open: (code: string) => void }) {
  const accounts = useAccounts()
  const columns: ColumnsType<LedgerAccount> = [
    { title: 'Code', dataIndex: 'code', width: 90, render: (code) => <a onClick={() => open(code)}>{code}</a> },
    { title: 'Account', dataIndex: 'name' },
    {
      title: 'Type',
      dataIndex: 'type',
      filters: stateOptions('account'),
      onFilter: (value, a) => a.type === value,
      render: (t) => <StateTag kind="account" value={t} />,
    },
    { title: 'Debits', dataIndex: 'debit', align: 'right', render: (v) => money(v, true) },
    { title: 'Credits', dataIndex: 'credit', align: 'right', render: (v) => money(v, true) },
    { title: 'Balance', dataIndex: 'balance', align: 'right', render: (v) => <strong>{money(v, true)}</strong> },
    { title: '', key: 'open', render: (_, a) => <a onClick={() => open(a.code)}>Postings</a> },
  ]
  return (
    <>
      <ErrorAlert error={accounts.error} />
      <Table size="small" rowKey="code" columns={columns} dataSource={accounts.data} loading={accounts.isPending} pagination={false} />
    </>
  )
}

/** The general ledger: every posting, the trial balance and the chart of accounts. */
export default function GeneralLedger() {
  // The open tab and account filter are part of the address, so a link can open the postings of one account.
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'journal'
  const account = params.get('account') ?? undefined
  const set = (next: Record<string, string | undefined>) => {
    const merged = { tab, account, ...next }
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v)) as Record<string, string>, { replace: true })
  }

  return (
    <Card>
      <Typography.Paragraph type="secondary">
        Every goods receipt, approved invoice, payment, stock issue and adjustment posts a balanced double entry here. Mock data for the prototype.
      </Typography.Paragraph>
      <Tabs
        activeKey={tab}
        onChange={(key) => set({ tab: key })}
        items={[
          { key: 'journal', label: 'Journal', children: <Journal account={account} setAccount={(code) => set({ account: code })} /> },
          { key: 'trial', label: 'Trial balance', children: <TrialBalanceView /> },
          { key: 'accounts', label: 'Accounts', children: <Accounts open={(code) => set({ tab: 'journal', account: code })} /> },
        ]}
      />
    </Card>
  )
}
