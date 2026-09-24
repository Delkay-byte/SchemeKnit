export function generateStaticParams() {
  return [{ id: 'placeholder' }]
}

export default function GenerateLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
