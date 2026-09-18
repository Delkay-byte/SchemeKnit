export function generateStaticParams() {
  return [{ id: 'placeholder' }]
}

export default function ReviewLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
