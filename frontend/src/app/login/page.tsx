import { RoleLogin } from '@/components/role-login'
import { PlanComparisonCard } from '@/components/plan-comparison-card'

export default function LoginPage() {
  return (
    <div>
      <RoleLogin entry="teacher" />
      <PlanComparisonCard />
    </div>
  )
}
