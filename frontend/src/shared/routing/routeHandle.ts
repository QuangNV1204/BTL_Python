import type { Params } from 'react-router'

export interface TabItem {
  to: string
  label: string
}

export interface RouteHandle {
  title?: string
  search?: boolean
  tabs?: (params: Params) => TabItem[]
}
