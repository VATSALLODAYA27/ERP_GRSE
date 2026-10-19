import type { ThemeConfig } from 'antd'
import { theme as antTheme } from 'antd'
import { createContext } from 'react'

/** Accent for buttons, links and the selected menu item. */
export const BRAND = '#3B5998'

// Status colours. Used for tags, the verdict banner and the markers on the drawing sheet.
export const TONE = {
  good: '#1E8E3E',
  warn: '#B86E00',
  bad: '#C62828',
  info: '#1D5FBF',
  neutral: '#6B7280',
} as const

/** Light or dark mode, and the function that flips it. Provided in main.tsx. */
export const ModeContext = createContext({ dark: false, toggle: () => {} })

const SHAPE = { borderRadius: 10, borderRadiusLG: 16, controlHeight: 36, fontSize: 14 }
const MENU = { itemBg: 'transparent', itemHeight: 40, itemBorderRadius: 10, itemMarginInline: 12, activeBarBorderWidth: 0, groupTitleFontSize: 11 }

const LIGHT: ThemeConfig = {
  algorithm: antTheme.defaultAlgorithm,
  token: {
    ...SHAPE,
    colorPrimary: BRAND,
    colorLink: BRAND,
    colorSuccess: TONE.good,
    colorWarning: TONE.warn,
    colorError: TONE.bad,
    colorInfo: TONE.info,
    colorTextBase: '#0F172A',
    colorBgLayout: '#F4F5F9',
    colorBorderSecondary: '#ECEEF3',
  },
  components: {
    Layout: { lightSiderBg: '#FFFFFF', headerBg: 'rgba(244,245,249,0.85)', headerHeight: 72, headerPadding: '0 24px' },
    Menu: { ...MENU, itemColor: '#475569', itemSelectedBg: '#EDF0F7', itemSelectedColor: BRAND },
    Table: { headerBg: 'transparent', headerColor: TONE.neutral, headerSplitColor: 'transparent', rowHoverBg: '#F5F6FA' },
    Tag: { borderRadiusSM: 999 },
  },
}

// Dark mode is black and grey with no blue: near-black page, charcoal cards, light-grey buttons.
const DARK: ThemeConfig = {
  algorithm: antTheme.darkAlgorithm,
  token: {
    ...SHAPE,
    // Mid grey: white text and ticks stay readable on it (checkboxes, radios, the switch).
    colorPrimary: '#71717A',
    colorLink: '#B4BED6',
    // The status colours are brightened so tags stay readable on a dark background.
    colorSuccess: '#4CC97F',
    colorWarning: '#F0B340',
    colorError: '#FF7B72',
    colorInfo: '#8AB4F8',
    colorTextBase: '#EDEDEF',
    colorTextDescription: 'rgba(237,237,239,0.65)',
    colorBgBase: '#0A0A0B',
    colorBgLayout: '#0A0A0B',
    colorBgContainer: '#151517',
    colorBgElevated: '#1C1C1F',
    colorBorder: '#34343A',
    colorBorderSecondary: '#26262A',
  },
  components: {
    Layout: { lightSiderBg: '#0F0F10', headerBg: 'rgba(10,10,11,0.8)', headerHeight: 72, headerPadding: '0 24px' },
    Menu: { ...MENU, itemColor: '#A1A1AA', itemSelectedBg: 'rgba(255,255,255,0.08)', itemSelectedColor: '#FAFAFA' },
    Table: { headerBg: 'transparent', headerColor: '#A1A1AA', headerSplitColor: 'transparent', rowHoverBg: '#1C1C1F' },
    Tag: { borderRadiusSM: 999 },
    // The main button is light grey with dark text, the usual look on a black interface.
    Button: { colorPrimary: '#E4E4E7', colorPrimaryHover: '#FFFFFF', colorPrimaryActive: '#D4D4D8', primaryColor: '#18181B', primaryShadow: 'none' },
    Tabs: { itemSelectedColor: '#FAFAFA', itemHoverColor: '#FAFAFA', itemActiveColor: '#FAFAFA', inkBarColor: '#FAFAFA' },
  },
}

/** Ant Design's colours and shapes for one mode. The plain-CSS parts follow through the variables in index.css. */
export const themeFor = (dark: boolean): ThemeConfig => (dark ? DARK : LIGHT)
