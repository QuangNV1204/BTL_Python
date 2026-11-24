import { ICON_PATHS, type IconName } from './iconPaths'

export function Icon({ name, size, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `ic ${className}` : 'ic'}
      style={size ? { width: size, height: size } : undefined}
      viewBox="0 0 24 24"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] }}
    />
  )
}
