import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Switch } from 'antd'
import { useContext } from 'react'

import { ModeContext } from '../theme'

/** Flips the whole site between light and dark. The choice is remembered in this browser. */
export default function ModeSwitch() {
  const { dark, toggle } = useContext(ModeContext)
  return <Switch checked={dark} onChange={toggle} checkedChildren={<MoonOutlined />} unCheckedChildren={<SunOutlined />} aria-label="Dark mode" />
}
