'use client'

import { signIn, getProviders, getCsrfToken } from "next-auth/react"
import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function SignIn() {
  const [providers, setProviders] = useState<any>(null)
  const [csrfToken, setCsrfToken] = useState<string>('')

  useEffect(() => {
    const fetchData = async () => {
      const providers = await getProviders()
      const csrfToken = await getCsrfToken()
      setProviders(providers)
      setCsrfToken(csrfToken || '')
    }
    fetchData()
  }, [])

  if (!providers) {
    return <div>Loading...</div>
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in to OpenMemory</CardTitle>
          <CardDescription>
            Please sign in to access your memories and applications.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {Object.values(providers).map((provider: any) => (
            <div key={provider.name}>
              <Button
                onClick={() => signIn(provider.id)}
                className="w-full"
                size="lg"
              >
                Sign in with {provider.name}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}