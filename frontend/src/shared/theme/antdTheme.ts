import { theme as antdTheme, type ThemeConfig } from 'antd'


export const cssVar = {
  primary: 'var(--primary)',
  primarySoft: 'var(--primary-soft)',
  primaryText: 'var(--primary-text)',
  ai: 'var(--ai)',
  aiSoft: 'var(--ai-soft)',
  aiText: 'var(--ai-text)',
  aiLine: 'var(--ai-line)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
  text2: 'var(--text-2)',
  border: 'var(--border)',
} as const

export type ThemeMode = 'light' | 'dark'

const FONT = "'Be Vietnam Pro', system-ui, sans-serif"

const common: ThemeConfig = {
  token: {
    fontFamily: FONT,
    fontSize: 14,
    borderRadius: 8,
    borderRadiusLG: 16,
    controlHeight: 40,
    controlHeightSM: 32,
  },
  components: {
    Button: { fontWeight: 600, primaryShadow: 'none', defaultShadow: 'none', dangerShadow: 'none' },
    Card: { headerFontSize: 18 },
  },
}

const lightTokens: ThemeConfig['token'] = {
  colorPrimary: '#4F46E5',
  colorSuccess: '#16A34A',
  colorWarning: '#D97706',
  colorError: '#DC2626',
  colorInfo: '#0891B2',
  colorBgLayout: '#F5F6FA',
  colorBgContainer: '#FFFFFF',
  colorBgElevated: '#FFFFFF',
  colorBorder: '#D1D5DB',
  colorBorderSecondary: '#E5E7EB',
  colorText: '#111827',
  colorTextSecondary: '#4B5563',
  colorTextTertiary: '#6B7280',
}

const darkTokens: ThemeConfig['token'] = {
  colorPrimary: '#818CF8',
  colorSuccess: '#4ADE80',
  colorWarning: '#FBBF24',
  colorError: '#F87171',
  colorInfo: '#22D3EE',
  colorBgLayout: '#0B1120',
  colorBgContainer: '#111827',
  colorBgElevated: '#111827',
  colorBorder: '#374151',
  colorBorderSecondary: '#1F2937',
  colorText: '#F3F4F6',
  colorTextSecondary: '#9CA3AF',
  colorTextTertiary: '#8B95A7',
  colorTextLightSolid: '#0B1120',
}

export function antdThemeFor(mode: ThemeMode): ThemeConfig {
  return {
    ...common,
    algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: { ...common.token, ...(mode === 'dark' ? darkTokens : lightTokens) },
  }
}
