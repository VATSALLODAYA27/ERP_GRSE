import { FilePdfOutlined, UploadOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Form, Input, Row, Spin, Tag, Typography, Upload } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, LOW_CONFIDENCE, TITLE_BLOCK_FIELDS, type Check, type ReadResult } from '../api'
import { ErrorAlert } from '../components/Tags'

const STEPS = [
  ['Reads the title block', 'Drawing number, revision, status, material and thickness, plus the parts list and notes. A scanned drawing is read by OCR, and you confirm the values first.'],
  ['Compares with the register', 'Is this the current revision, and is it approved?'],
  ['Compares with the previous revision', 'Lists what changed, overlays the two sheets, and lists the work orders and purchase orders affected.'],
  ['Compares with the ERP bill of materials', 'Do the parts, materials and quantities on the drawing match what would be ordered?'],
  ['Runs the fixed rules', 'Each finding cites the clause it comes from.'],
  ['Waits for a decision', 'The tool proposes a verdict; a reviewer or the admin approves or rejects the release.'],
]

function upload<T>(path: string, parts: Record<string, File | string | undefined>) {
  const body = new FormData()
  for (const [name, value] of Object.entries(parts)) if (value !== undefined) body.append(name, value)
  return api<T>(path, { method: 'POST', body })
}

/** What the tool read from the chosen file. For a scan the values are editable, because OCR can misread. */
function WhatWasRead({ read, values, onChange }: { read: ReadResult; values: Record<string, string>; onChange: (name: string, value: string) => void }) {
  if (read.source === 'vector') {
    return (
      <Descriptions size="small" column={2} bordered title="Read from the drawing" style={{ marginBottom: 16 }}>
        {TITLE_BLOCK_FIELDS.map(([name, label]) => (
          <Descriptions.Item key={name} label={label}>
            {read.fields[name].value || <Typography.Text type="danger">(not found)</Typography.Text>}
          </Descriptions.Item>
        ))}
        <Descriptions.Item label="Parts list">{read.parts} rows</Descriptions.Item>
      </Descriptions>
    )
  }
  return (
    <div style={{ marginBottom: 16 }}>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 12 }}
        message="This is a scanned drawing, read by OCR"
        description="OCR can misread a character. Compare each value with the drawing and correct any that are wrong. The check runs on the values shown here, and your corrections are recorded."
      />
      <Form layout="vertical">
        <Row gutter={12}>
          {TITLE_BLOCK_FIELDS.map(([name, label]) => {
            const { value, confidence } = read.fields[name]
            return (
              <Col key={name} xs={24} md={name === 'title' ? 24 : 12}>
                <Form.Item
                  style={{ marginBottom: 12 }}
                  label={
                    <>
                      {label}&nbsp;
                      {value === '' ? (
                        <Tag color="error">Not read: type it in</Tag>
                      ) : (
                        confidence !== null && confidence < LOW_CONFIDENCE && <Tag color="warning">Low confidence ({confidence}%)</Tag>
                      )}
                      {values[name] !== value && <Tag color="processing">Corrected</Tag>}
                    </>
                  }
                >
                  <Input aria-label={label} value={values[name]} maxLength={200} onChange={(e) => onChange(name, e.target.value)} />
                </Form.Item>
              </Col>
            )
          })}
        </Row>
      </Form>
      <Typography.Text type="secondary">
        The parts list ({read.parts} rows) and the notes are also read by OCR. They cannot be corrected here; the report marks them as read from a scan.
      </Typography.Text>
    </div>
  )
}

export default function NewCheck() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File>()
  const [previous, setPrevious] = useState<File>()
  const [values, setValues] = useState<Record<string, string>>({})

  const read = useMutation({
    mutationFn: (pdf: File) => upload<ReadResult>('/checks/read', { file: pdf }),
    onSuccess: (result) => setValues(Object.fromEntries(TITLE_BLOCK_FIELDS.map(([name]) => [name, result.fields[name].value]))),
  })
  const scanned = read.data?.source === 'scan'
  const run = useMutation({
    mutationFn: (pdf: File) => upload<Check>('/checks', { file: pdf, previous, confirmed: scanned ? JSON.stringify(values) : undefined }),
    onSuccess: (check) => {
      queryClient.invalidateQueries({ queryKey: ['checks'] })
      queryClient.invalidateQueries({ queryKey: ['gate'] })
      queryClient.invalidateQueries({ queryKey: ['register'] })
      navigate(`/checks/${check.id}`)
    },
  })

  // The chosen PDF shown in the browser's own viewer, so a scan can be compared with what OCR read.
  const preview = useMemo(() => (file && scanned ? URL.createObjectURL(file) : undefined), [file, scanned])
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview])

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={15}>
        <Card title="Drawing to check">
          <Upload.Dragger
            accept=".pdf,application/pdf"
            maxCount={1}
            // Keep the file in the browser until the check is run; for now it is only read.
            beforeUpload={(picked) => {
              setFile(picked)
              run.reset()
              read.mutate(picked)
              return false
            }}
            onRemove={() => {
              setFile(undefined)
              read.reset()
            }}
            fileList={file ? [{ uid: '1', name: file.name, status: 'done' }] : []}
          >
            <p className="ant-upload-drag-icon">
              <FilePdfOutlined />
            </p>
            <p className="ant-upload-text">Drag a drawing PDF here, or click to choose one</p>
            <p className="ant-upload-hint">One PDF, up to 25 MB. A scanned drawing is read by OCR, which takes about 10 seconds.</p>
          </Upload.Dragger>

          <div style={{ marginTop: 16 }}>
            {read.isPending && (
              <Spin tip="Reading the drawing. A scan takes about 10 seconds.">
                <div style={{ height: 80 }} />
              </Spin>
            )}
            <ErrorAlert error={read.error} />
            {file && read.data && <WhatWasRead read={read.data} values={values} onChange={(name, value) => setValues({ ...values, [name]: value })} />}
            {preview && (
              <object data={preview} type="application/pdf" aria-label="The scanned drawing" style={{ width: '100%', height: 420, marginBottom: 16, border: '1px solid #d9dee7' }} />
            )}
          </div>

          <div style={{ margin: '0 0 16px' }}>
            <Typography.Text strong>Previous revision (optional)</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
              Used to show what changed. If an earlier revision of this drawing has already been checked, it is picked up automatically and you can leave this empty.
            </Typography.Paragraph>
            <Upload
              accept=".pdf,application/pdf"
              maxCount={1}
              beforeUpload={(picked) => {
                setPrevious(picked)
                run.reset()
                return false
              }}
              onRemove={() => setPrevious(undefined)}
              fileList={previous ? [{ uid: '2', name: previous.name, status: 'done' }] : []}
            >
              <Button icon={<UploadOutlined />}>Choose previous revision PDF</Button>
            </Upload>
          </div>
          <ErrorAlert error={run.error} />
          <Button type="primary" size="large" block disabled={!file || !read.data} loading={run.isPending} onClick={() => file && run.mutate(file)}>
            {scanned ? 'Confirm these values and run the check' : 'Run compliance check'}
          </Button>
        </Card>
      </Col>
      <Col xs={24} xl={9}>
        <Card title="What the check does">
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            {STEPS.map(([title, description]) => (
              <li key={title} style={{ marginBottom: 12 }}>
                <Typography.Text strong>{title}</Typography.Text>
                <br />
                <Typography.Text type="secondary">{description}</Typography.Text>
              </li>
            ))}
          </ol>
        </Card>
      </Col>
    </Row>
  )
}
