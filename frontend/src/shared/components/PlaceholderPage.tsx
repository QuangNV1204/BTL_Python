import { Card, Result, Typography } from 'antd'
import { useParams } from 'react-router'
import type { Screen } from '../routing/screens'

export function PlaceholderPage({ screen }: { screen: Screen }) {
  const params = useParams()
  const paramText = Object.entries(params)
    .map(([key, value]) => `${key} = ${value}`)
    .join(', ')

  return (
    <Card>
      <Result
        status="info"
        title={screen.title}
        subTitle={
          <>
            Màn hình chưa làm — phụ trách: <b>người {screen.owner}</b>
            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
              Prototype: <code>#{screen.prototype}</code>
              {paramText && <> · Tham số route: {paramText}</>}
            </Typography.Paragraph>
          </>
        }
      />
    </Card>
  )
}
