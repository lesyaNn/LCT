import Mail from '@atomaro/icons/24/communication/Mail';
import Phone from '@atomaro/icons/24/technology/Phone';
import Trash from '@atomaro/icons/24/action/Trash';
import type { UniversityResponsibleContact } from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { CopyButton } from '@/shared/ui/rtk/copy-button';
import { contactText } from '@/shared/lib/university-local-time';
import styles from './university-responsibles-section.module.css';

export function ResponsibleCard({ person, onRemove }: { person: UniversityResponsibleContact; onRemove?: () => void }) {
  return <article className={styles.card}>
    <div className={styles.cardHeader}>
      <Avatar initials={person.initials} size="m" />
      <div className={styles.identity}>
        <h3>{person.name}</h3>
        <p>{person.role}</p>
      </div>
      <CopyButton className={styles.copyButton} value={contactText(person)} label={`Копировать контакт: ${person.name}`} />
      {onRemove ? <IconButton className={styles.removeButton} intent="danger" icon={<Trash size={18} fill="currentColor" />} label={`Снять назначение: ${person.name}`} onClick={onRemove} /> : null}
    </div>
    {person.isPrimary ? <div className={styles.badgeRow}><StatusBadge intent="brand">Основной</StatusBadge></div> : null}
    <div className={styles.contacts}>
      {person.email ? <div className={styles.contactRow}><a href={`mailto:${person.email}`}><Mail size={16} fill="currentColor" />{person.email}</a><CopyButton className={styles.copyButton} value={person.email} label={`Копировать email: ${person.name}`} /></div> : null}
      {person.phone && person.phone !== '—' ? <div className={styles.contactRow}><a href={`tel:${person.phone.replace(/[^+\d]/g, '')}`}><Phone size={16} fill="currentColor" />{person.phone}</a><CopyButton className={styles.copyButton} value={person.phone} label={`Копировать телефон: ${person.name}`} /></div> : null}
    </div>
  </article>;
}
