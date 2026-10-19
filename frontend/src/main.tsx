import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import React, { useEffect, useMemo, useState } from 'react'
import { flushSync } from 'react-dom'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { ApiError } from './api'
import App from './App'
import './index.css'
import { ModeContext, themeFor } from './theme'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  queryCache: new QueryCache({
    // A session that has expired shows the sign-in page instead of a page full of errors.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(['me'], null)
    },
  }),
})

const MODE_KEY = 'grse-theme'

function Root() {
  const [dark, setDark] = useState(() => localStorage.getItem(MODE_KEY) === 'dark')
  const [printing, setPrinting] = useState(false)
  // Paper is white: a report printed from dark mode is printed in light mode.
  const shown = dark && !printing

  useEffect(() => {
    localStorage.setItem(MODE_KEY, dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    // The plain-CSS parts of the site (index.css) read this attribute.
    document.documentElement.dataset.theme = shown ? 'dark' : 'light'
  }, [shown])

  useEffect(() => {
    // flushSync: the page must be redrawn before the browser takes its print snapshot.
    const before = () => flushSync(() => setPrinting(true))
    const after = () => setPrinting(false)
    window.addEventListener('beforeprint', before)
    window.addEventListener('afterprint', after)
    return () => {
      window.removeEventListener('beforeprint', before)
      window.removeEventListener('afterprint', after)
    }
  }, [])

  const mode = useMemo(() => ({ dark, toggle: () => setDark((was) => !was) }), [dark])

  return (
    <ModeContext.Provider value={mode}>
      <ConfigProvider theme={themeFor(shown)}>
        <AntApp>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </ModeContext.Provider>
  )
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </React.StrictMode>,
)
