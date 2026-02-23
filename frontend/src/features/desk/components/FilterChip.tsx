import { filterChipClass } from '../utils'

type Props = {
  selected: boolean
  label: string
  onClick: () => void
}

export function FilterChip({ selected, label, onClick }: Props) {
  return (
    <button onClick={onClick} className={filterChipClass(selected)}>
      {label}
    </button>
  )
}
