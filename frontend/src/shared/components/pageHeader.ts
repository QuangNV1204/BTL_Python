import { createContext, useContext, useEffect } from 'react'

export interface Crumb {
  label: string
  to?: string
}

export interface PageHeader {
  title?: string
  crumbs?: Crumb[]
}

export const PageHeaderContext = createContext<(header: PageHeader | null) => void>(() => {})

export function usePageHeader(header: PageHeader | null): void {
  const setHeader = useContext(PageHeaderContext)
  const key = JSON.stringify(header)
  useEffect(() => {
    setHeader(JSON.parse(key) as PageHeader | null)
    return () => setHeader(null)
  }, [setHeader, key])
}
