'use client'

import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useInitiateDeviceFlow } from '@/hooks/mutations/use-device-auth-mutations'
import { authQueries } from '@/lib/query/queries/auth'
import Dither from '@/components/Dither'

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

  // Single expiry path: poll response wins if it arrives, otherwise the client
  // deadline acts as a backstop (the query disables at expiresAt, so without it
  // a session that quietly times out would leave the UI stuck on "Waiting...").
  useEffect(() => {
    if (!deviceCode) return

    const reset = () => {
      setError('Session expired. Please try again.')
      setSessionId('')
      setDeviceCode('')
      setUserCode('')
    }

    if (pollData?.status === 'complete' && pollData.token) {
      onToken(pollData.token)
      return
    }
    if (pollData?.status === 'expired') {
      reset()
      return
    }

    if (!expiresAt) return
    const remaining = expiresAt - Date.now()
    if (remaining <= 0) {
      reset()
      return
    }
    const timeout = setTimeout(reset, remaining)
    return () => clearTimeout(timeout)
  }, [pollData, deviceCode, expiresAt, onToken])

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
      <div className="w-full h-screen fixed top-0 left-0">
        <Dither
          waveColor={[0.8823529411764706, 0.8823529411764706, 0.8823529411764706]}
          disableAnimation={false}
          enableMouseInteraction={false}
          mouseRadius={1}
          colorNum={7}
          pixelSize={2}
          waveAmplitude={0.25}
          waveFrequency={3.5}
          waveSpeed={0.04}
        />
      </div>
      <Card className="w-full max-w-sm fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-card/70 backdrop-blur-xl p-12 rounded-3xl">
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
            {!initiate.isPending && 'Sign in with Browser'}
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
