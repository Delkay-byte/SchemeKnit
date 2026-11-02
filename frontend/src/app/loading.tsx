import { AppShellSkeleton } from '@/components/ui/skeleton'

export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      <main className="container mx-auto px-4 py-8">
        <AppShellSkeleton />
      </main>
    </div>
  )
}
