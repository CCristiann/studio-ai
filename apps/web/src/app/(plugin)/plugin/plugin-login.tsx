'use client'

import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useInitiateDeviceFlow } from '@/hooks/mutations/use-device-auth-mutations'
import { authQueries } from '@/lib/query/queries/auth'

export function PluginLogin({ onToken }: { onToken: (token: string) => void }) {
  const [sessionId, setSessionId] = useState('')
  const [deviceCode, setDeviceCode] = useState('')
  const [userCode, setUserCode] = useState('')
  const [expiresAt, setExpiresAt] = useState(0)
  const [error, setError] = useState('')

  const initiate = useInitiateDeviceFlow()

  // Poll for token once device flow is initiated
  const { data: pollData } = useQuery({
    ...authQueries.deviceToken(sessionId, deviceCode, expiresAt),
  })

  // When polling returns a complete token, pass it up
  useEffect(() => {
    if (pollData?.status === 'complete' && pollData.token) {
      onToken(pollData.token)
    } else if (pollData?.status === 'expired') {
      setError('Session expired. Please try again.')
      setSessionId('')
      setDeviceCode('')
      setUserCode('')
    }
  }, [pollData, onToken])

  // Handle expiry based on deadline
  useEffect(() => {
    if (!expiresAt) return
    const timeout = setTimeout(() => {
      if (Date.now() >= expiresAt && deviceCode) {
        setError('Authorization expired. Please try again.')
        setSessionId('')
        setDeviceCode('')
        setUserCode('')
      }
    }, expiresAt - Date.now())
    return () => clearTimeout(timeout)
  }, [expiresAt, deviceCode])

  const startAuth = async () => {
    setError('')
    setUserCode('')

    initiate.mutate(undefined, {
      onSuccess: (data) => {
        setSessionId(data.session_id)
        setDeviceCode(data.device_code)
        setUserCode(data.user_code)
        setExpiresAt(Date.now() + data.expires_in * 1000)

        // Open system browser to /link
        const linkUrl = `${window.location.origin}/link`
        if (typeof window.sendToPlugin === 'function') {
          window.sendToPlugin({ type: 'open_browser', url: linkUrl })
        } else {
          window.open(linkUrl, '_blank')
        }
      },
      onError: () => {
        setError('Failed to start authentication.')
      },
    })
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-background">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <h1 className="text-xl font-semibold">Studio AI</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to connect your DAW
          </p>
        </div>

        {!userCode ? (
          <Button
            onClick={startAuth}
            className="w-full"
            disabled={initiate.isPending}
          >
            {initiate.isPending ? 'Starting...' : 'Sign in with Browser'}
          </Button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground text-center">
              Enter this code in your browser:
            </p>
            <div className="text-3xl font-mono font-bold text-center tracking-widest py-3">
              {userCode}
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Waiting for authorization...
            </p>
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive text-center">{error}</p>
        )}
      </Card>
    </div>
  )
}
