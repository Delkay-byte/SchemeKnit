import { type HTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Shared skeleton system.
 *
 * Skeletons mirror the structure of the content that is loading so the page
 * does not jump when real data arrives. All blocks are decorative; the
 * `SkeletonRegion` wrapper carries the accessible loading announcement.
 */

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'animate-pulse rounded-md bg-slate-200/80 motion-reduce:animate-none',
        className,
      )}
      {...props}
    />
  )
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number
  className?: string
}) {
  return (
    <div aria-hidden="true" className={cn('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          className={cn('h-3', index === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  )
}

export function SkeletonHeading({ className }: { className?: string }) {
  return <Skeleton className={cn('h-7 w-52', className)} />
}

export function SkeletonButton({ className }: { className?: string }) {
  return <Skeleton className={cn('h-9 w-32 rounded-md', className)} />
}

export function SkeletonAvatar({ className }: { className?: string }) {
  return <Skeleton className={cn('h-10 w-10 rounded-full', className)} />
}

export function SkeletonField({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn('space-y-2', className)}>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-10 w-full rounded-md" />
    </div>
  )
}

export function SkeletonStat({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'rounded-2xl border border-[#102A43]/8 bg-white px-4 py-4 shadow-[0_10px_30px_rgba(16,42,67,0.08)]',
        className,
      )}
    >
      <Skeleton className="h-2.5 w-24" />
      <Skeleton className="mt-3 h-7 w-16" />
    </div>
  )
}

export function SkeletonCard({
  lines = 3,
  className,
}: {
  lines?: number
  className?: string
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'rounded-2xl border border-[#102A43]/8 bg-white p-5 shadow-[0_10px_30px_rgba(16,42,67,0.08)]',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <SkeletonAvatar />
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <div className="mt-4">
        <SkeletonText lines={lines} />
      </div>
    </div>
  )
}

export function SkeletonTable({
  rows = 5,
  columns = 5,
  className,
}: {
  rows?: number
  columns?: number
  className?: string
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'overflow-hidden rounded-2xl border border-[#102A43]/8 bg-white shadow-[0_10px_30px_rgba(16,42,67,0.08)]',
        className,
      )}
    >
      <div className="flex gap-4 border-b border-slate-100 bg-slate-50/80 px-4 py-3">
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, row) => (
        <div
          key={row}
          className="flex items-center gap-4 border-b border-slate-100 px-4 py-4 last:border-b-0"
        >
          {Array.from({ length: columns }).map((_, column) => (
            <Skeleton
              key={column}
              className={cn('h-3 flex-1', column === columns - 1 && 'max-w-16')}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonListItem({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'flex items-center gap-3 rounded-xl border border-slate-100 bg-white px-4 py-3',
        className,
      )}
    >
      <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1 space-y-2">
        <Skeleton className="h-3.5 w-1/2" />
        <Skeleton className="h-3 w-3/4" />
      </div>
      <Skeleton className="h-8 w-20 rounded-md" />
    </div>
  )
}

export function SkeletonPageHeader({
  withActions = true,
  className,
}: {
  withActions?: boolean
  className?: string
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between',
        className,
      )}
    >
      <div className="space-y-2">
        <SkeletonHeading />
        <Skeleton className="h-3.5 w-72 max-w-full" />
      </div>
      {withActions && <SkeletonButton />}
    </div>
  )
}

/** Wrapper that announces loading once to assistive technology. */
export function SkeletonRegion({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={cn('space-y-6', className)}
    >
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}

/** Application shell used by the global route loading state. */
export function AppShellSkeleton() {
  return (
    <SkeletonRegion label="Loading SchemeKnit" className="container mx-auto px-4 py-8">
      <div aria-hidden="true" className="mb-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <Skeleton className="h-5 w-32" />
        </div>
        <SkeletonButton className="hidden sm:block" />
      </div>
      <SkeletonPageHeader />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonStat key={index} />
        ))}
      </div>
      <SkeletonCard lines={2} />
      <SkeletonTable rows={4} columns={5} />
    </SkeletonRegion>
  )
}

export function DashboardSkeleton() {
  return (
    <SkeletonRegion label="Loading your dashboard">
      <SkeletonPageHeader />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonStat key={index} />
        ))}
      </div>
      <SkeletonCard lines={2} />
      <div className="space-y-3">
        <Skeleton className="h-5 w-40" />
        <SkeletonTable rows={4} columns={5} />
      </div>
    </SkeletonRegion>
  )
}

export function ListPageSkeleton({
  label = 'Loading content',
  rows = 6,
  columns = 5,
}: {
  label?: string
  rows?: number
  columns?: number
}) {
  return (
    <SkeletonRegion label={label}>
      <SkeletonPageHeader />
      <Skeleton className="h-10 w-full max-w-xs rounded-md" />
      <SkeletonTable rows={rows} columns={columns} />
    </SkeletonRegion>
  )
}

export function DetailPageSkeleton({ label = 'Loading content' }: { label?: string }) {
  return (
    <SkeletonRegion label={label}>
      <SkeletonPageHeader />
      <SkeletonCard lines={3} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <SkeletonCard lines={6} />
          <SkeletonCard lines={4} />
        </div>
        <div className="space-y-4">
          <SkeletonCard lines={3} />
          <SkeletonCard lines={2} />
        </div>
      </div>
    </SkeletonRegion>
  )
}

export function FormPageSkeleton({ label = 'Loading form' }: { label?: string }) {
  return (
    <SkeletonRegion label={label}>
      <SkeletonPageHeader withActions={false} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-2xl border border-[#102A43]/8 bg-white p-5 shadow-[0_10px_30px_rgba(16,42,67,0.08)]">
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 6 }).map((_, index) => (
                <SkeletonField key={index} />
              ))}
            </div>
          </div>
        </div>
        <SkeletonCard lines={4} />
      </div>
    </SkeletonRegion>
  )
}
