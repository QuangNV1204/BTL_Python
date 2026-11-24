import { ConfigProvider } from 'antd'
import viVN from 'antd/locale/vi_VN'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { antdThemeFor, type ThemeMode } from './antdTheme'
import { initialThemeMode, saveThemeMode, ThemeModeContext } from './themeMode'

export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialThemeMode)

  useEffect(() => {
    document.documentElement.dataset.theme = mode
    saveThemeMode(mode)
  }, [mode])

  const value = useMemo(
    () => ({ mode, toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')) }),
    [mode],
  )

  return (
    <ThemeModeContext value={value}>
      <ConfigProvider locale={viVN} theme={antdThemeFor(mode)}>
        {children}
      </ConfigProvider>
    </ThemeModeContext>
  )
}
