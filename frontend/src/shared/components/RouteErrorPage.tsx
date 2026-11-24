import { isRouteErrorResponse, useRouteError } from 'react-router'
import { ErrorState, NotFoundState } from './PageState'

export function RouteErrorPage() {
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundState />
  }
  return <ErrorState error={error} onRetry={() => window.location.reload()} />
}
