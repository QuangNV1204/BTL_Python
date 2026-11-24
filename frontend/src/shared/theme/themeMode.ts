import { createContext, useContext } from 'react'
import type { ThemeMode } from './antdTheme'

export interface ThemeModeValue {
  mode: ThemeMode
  toggle: () => void
}

export const ThemeModeContext = createContext<ThemeModeValue>({ mode: 'light', toggle: () => {} })

export function useThemeMode(): ThemeModeValue {
  return useContext(ThemeModeContext)
}

const STORAGE_KEY = 'las.theme'

export function initialThemeMode(): ThemeMode {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') {
      return saved
    }
  } catch {
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function saveThemeMode(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, mode)
  } catch {
  }
}
