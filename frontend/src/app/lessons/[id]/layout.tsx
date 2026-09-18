export function generateStaticParams() {
  return [{ id: 'placeholder' }]
}

export default function LessonDetailLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
