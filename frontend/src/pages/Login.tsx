import { CheckCircleFilled, DeploymentUnitOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Flex, Form, Input, Radio, Tabs, Typography } from 'antd'
import { useState } from 'react'

import { postJson, type User } from '../api'
import ModeSwitch from '../components/ModeSwitch'
import { ErrorAlert } from '../components/Tags'

const FEATURES = [
  'Procurement from requisition to payment, with late deliveries flagged early',
  'Stock in every store, posted to a ledger that always balances',
  'Sentinel release gate: no drawing reaches the shop floor unchecked',
]

function SignIn() {
  const queryClient = useQueryClient()
  const login = useMutation({
    mutationFn: (values: { username: string; password: string }) => postJson<User>('/auth/login', values),
    onSuccess: (user) => queryClient.setQueryData(['me'], user),
  })
  return (
    <>
      <ErrorAlert error={login.error} />
      <Form name="signin" layout="vertical" requiredMark={false} onFinish={login.mutate}>
        <Form.Item name="username" label="Username" rules={[{ required: true, message: 'Enter your username' }]}>
          <Input autoFocus autoComplete="username" />
        </Form.Item>
        <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Enter your password' }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={login.isPending}>
          Sign in
        </Button>
      </Form>
    </>
  )
}

function Register() {
  const [form] = Form.useForm()
  const [created, setCreated] = useState<string>()
  const register = useMutation({
    mutationFn: (values: { role: string; name: string; username: string; password: string }) => postJson<User>('/auth/register', values),
    onSuccess: (user) => {
      setCreated(user.username)
      form.resetFields()
    },
  })
  return (
    <>
      {created && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Account "${created}" created`}
          description="An admin must approve it before you can sign in."
        />
      )}
      <ErrorAlert error={register.error} />
      <Form name="register" form={form} layout="vertical" requiredMark={false} onFinish={({ confirm: _, ...values }) => register.mutate(values)}>
        <Form.Item name="role" label="Account type" initialValue="reviewer" extra="An engineer uploads drawings for checking. A reviewer approves or rejects them.">
          <Radio.Group
            options={[
              { value: 'engineer', label: 'Engineer' },
              { value: 'reviewer', label: 'Reviewer' },
            ]}
          />
        </Form.Item>
        <Form.Item name="name" label="Full name" rules={[{ required: true, whitespace: true, message: 'Enter your name' }]}>
          <Input autoComplete="name" maxLength={80} />
        </Form.Item>
        <Form.Item
          name="username"
          label="Username"
          extra="3 to 32 letters, digits, dot, dash or underscore"
          rules={[{ required: true, pattern: /^[A-Za-z0-9_.-]{3,32}$/, message: 'Use 3 to 32 letters, digits, dot, dash or underscore' }]}
        >
          <Input autoComplete="username" />
        </Form.Item>
        <Form.Item name="password" label="Password" extra="At least 8 characters" rules={[{ required: true, min: 8, message: 'Use at least 8 characters' }]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="Repeat password"
          dependencies={['password']}
          rules={[
            { required: true, message: 'Repeat the password' },
            ({ getFieldValue }) => ({
              validator: (_, value) => (!value || value === getFieldValue('password') ? Promise.resolve() : Promise.reject(new Error('The two passwords do not match'))),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={register.isPending}>
          Request account
        </Button>
      </Form>
    </>
  )
}

export default function Login() {
  return (
    <div className="login">
      <div className="login-art">
        <div className="brand">
          <DeploymentUnitOutlined />
          <span>PRAVAH</span>
        </div>
        <div>
          <h1>Material moves on time. Every rupee is accounted for.</h1>
          <ul>
            {FEATURES.map((feature) => (
              <li key={feature}>
                <CheckCircleFilled /> {feature}
              </li>
            ))}
          </ul>
        </div>
        <span>Shipyard ERP intelligence</span>
      </div>
      <Flex vertical justify="center" align="center" style={{ padding: 24 }}>
        <div style={{ width: '100%', maxWidth: 400 }}>
          <Flex justify="end" style={{ marginBottom: 24 }}>
            <ModeSwitch />
          </Flex>
          <Typography.Title level={2} style={{ marginTop: 0, marginBottom: 4 }}>
            Welcome
          </Typography.Title>
          <Typography.Text type="secondary">Sign in to PRAVAH, shipyard ERP intelligence.</Typography.Text>
          <Tabs
            style={{ marginTop: 16 }}
            items={[
              { key: 'signin', label: 'Sign in', children: <SignIn /> },
              { key: 'register', label: 'Register', children: <Register /> },
            ]}
          />
        </div>
      </Flex>
    </div>
  )
}
