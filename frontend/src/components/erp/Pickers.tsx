import { AutoComplete, Flex, Select, Typography, type AutoCompleteProps, type SelectProps } from 'antd'

import { useGate } from '../../api'
import { qty, useItems, useStores, useVendors } from '../../erpApi'

type PickerProps = Omit<SelectProps<string>, 'options' | 'mode'>

const matches = (input: string, option?: { search?: string }) => (option?.search ?? '').toLowerCase().includes(input.trim().toLowerCase())

/** Pick an item by code or description; each option shows what is on hand, so nobody orders what is already in the store. */
export function ItemSelect(props: PickerProps) {
  const items = useItems()
  return (
    <Select
      showSearch
      placeholder="Item code or description"
      loading={items.isPending}
      filterOption={matches}
      popupMatchSelectWidth={false}
      notFoundContent={items.isError ? 'The items cannot be loaded' : undefined}
      options={(items.data ?? []).map((item) => ({
        value: item.item_code,
        search: `${item.item_code} ${item.description} ${item.category}`,
        label: (
          <Flex justify="space-between" gap={16}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              <strong>{item.item_code}</strong> {item.description}
            </span>
            <Typography.Text type={item.on_hand <= 0 ? 'danger' : item.status === 'REORDER' ? 'warning' : 'secondary'} style={{ whiteSpace: 'nowrap' }}>
              on hand {qty(item.on_hand)} {item.uom}
            </Typography.Text>
          </Flex>
        ),
      }))}
      {...props}
    />
  )
}

export function StoreSelect({ exclude, ...props }: PickerProps & { exclude?: string }) {
  const stores = useStores()
  return (
    <Select
      placeholder="Store"
      loading={stores.isPending}
      options={(stores.data ?? [])
        .filter((s) => s.store_code !== exclude)
        .map((s) => ({ value: s.store_code, label: `${s.store_code} · ${s.name}` }))}
      {...props}
    />
  )
}

export function VendorSelect(props: PickerProps) {
  const vendors = useVendors()
  return (
    <Select
      showSearch
      placeholder="Vendor"
      loading={vendors.isPending}
      filterOption={matches}
      options={(vendors.data ?? []).map((v) => ({
        value: v.vendor_id,
        search: `${v.vendor_id} ${v.name} ${v.city} ${v.category}`,
        label: (
          <Flex justify="space-between" gap={16}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.name}</span>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
              grade {v.grade} · {v.lead_time_days} days lead
            </Typography.Text>
          </Flex>
        ),
      }))}
      {...props}
    />
  )
}

/** A work order number: the ones in the ERP extract are offered, and any other can be typed. */
export function WorkOrderInput(props: Omit<AutoCompleteProps<string>, 'options'>) {
  const gate = useGate()
  return (
    <AutoComplete
      placeholder="WO-24019"
      allowClear
      filterOption={(input, option) => String(option?.value ?? '').toLowerCase().includes(input.trim().toLowerCase())}
      options={[...new Set((gate.data ?? []).map((row) => row.order_no))].map((value) => ({ value }))}
      {...props}
    />
  )
}
