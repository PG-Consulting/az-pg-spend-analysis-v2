import { useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'

export default function Home() {
  const router = useRouter()
  useEffect(() => { router.replace('/taxonomy') }, [router])
  return (
    <Head>
      <title>Spend.AI | PG Consultoria</title>
    </Head>
  )
}
