'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { getUniversityHealth, type MatrixHealthState } from '@/shared/lib/dashboard-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton } from '@/shared/ui/skeleton';
import styles from './university-health.module.css';

const stateLabel: Record<MatrixHealthState, string> = {
  HEALTHY: 'Стабильно', ATTENTION: 'Требует внимания', CRITICAL: 'Критично',
  NOT_STARTED: 'Не запущено', COMPLETED: 'Завершён', NOT_LINKED: 'Не используется',
};
const stateMark: Record<MatrixHealthState, string> = {
  HEALTHY: '●', ATTENTION: '!', CRITICAL: '!', NOT_STARTED: '○', COMPLETED: '✓', NOT_LINKED: '—',
};
const levelLabel = { stable: 'Стабильно', attention: 'Требует внимания', critical: 'Критично', no_data: 'Недостаточно данных' } as const;

export function UniversityHealth({ universityId }: { universityId: string }) {
  const query = useQuery({ queryKey: queryKeys.universities.health(universityId), queryFn: () => getUniversityHealth(universityId), staleTime: 30_000 });
  if (query.isPending) return <Skeleton height={360} />;
  if (query.isError) return <RouteErrorState onRetry={() => void query.refetch()} />;
  const health = query.data;
  if (!health) return <p className={styles.empty}>Health Score доступен при подключении к CRM.</p>;
  const attention = health.programs.filter((item) => item.state === 'ATTENTION').length;
  const critical = health.programs.filter((item) => item.state === 'CRITICAL').length;
  return <div className={styles.page}>
    <section className={styles.summary} aria-labelledby="health-title">
      <div className={styles.summaryMain}>
        <div><p className={styles.eyebrow}>Текущее состояние взаимодействия</p><h2 id="health-title">Health Score</h2><p className={styles.score} data-level={health.level}>{health.score === null ? '—' : <>{health.score}<span> / 100</span></>}</p><strong className={styles.level} data-level={health.level}>{levelLabel[health.level]}</strong></div>
        <p className={styles.intro}>Оценка показывает текущее состояние взаимодействия с ВУЗом: активные Workflow, сроки, задачи и связанные лицензии. Она не оценивает качество или рейтинг ВУЗа.</p>
      </div>
      <dl className={styles.summaryStats}><div><dt>Программы с Workflow</dt><dd>{health.started_programs} из {health.total_programs}</dd></div><div><dt>Требуют внимания</dt><dd>{attention}</dd></div><div><dt>Критично</dt><dd>{critical}</dd></div></dl>
    </section>
    <section className={styles.surface} aria-labelledby="health-why"><h3 id="health-why">Почему такая оценка</h3>{health.factors.length ? <ul className={styles.factors}>{health.factors.map((factor) => <li key={factor.label}><span aria-hidden="true">!</span>{factor.label}</li>)}</ul> : <p className={styles.empty}>Критичных факторов не обнаружено.</p>}</section>
    <section className={styles.surface} aria-labelledby="health-coverage"><h3 id="health-coverage">Охват программ</h3><p className={styles.coverage}>{health.started_programs} из {health.total_programs} Workflow запущено. Незапущенные программы не снижают Health Score.</p></section>
    <section className={styles.surface} aria-labelledby="health-programs"><h3 id="health-programs">По программам</h3>{health.programs.length ? <div className={styles.programs}>{health.programs.map((program) => {
      const href = program.workflow_instance_id ? `/workflows/${program.workflow_instance_id}` : `/universities/${universityId}?tab=workflow&program=${program.program_id}`;
      return <Link className={styles.program} href={href} key={program.program_id} aria-label={`${program.program_name}: ${stateLabel[program.state]}${program.score !== null && program.state !== 'COMPLETED' ? `, Health ${program.score}` : ''}`}><span className={styles.programName}>{program.program_name}</span><span className={styles.programState} data-state={program.state}><span aria-hidden="true">{stateMark[program.state]}</span>{stateLabel[program.state]}</span><strong>{program.state === 'COMPLETED' || program.state === 'NOT_STARTED' ? '—' : program.score ?? '—'}</strong></Link>;
    })}</div> : <p className={styles.empty}>У ВУЗа пока нет связанных программ.</p>}</section>
    <section className={styles.surface} aria-labelledby="health-attention"><h3 id="health-attention">Требует внимания</h3>{health.programs.some((program) => program.factors.length) ? <ul className={styles.factors}>{health.programs.filter((program) => program.factors.length).map((program) => <li key={program.program_id}><span aria-hidden="true">!</span><Link href={program.workflow_instance_id ? `/workflows/${program.workflow_instance_id}` : `/universities/${universityId}?tab=workflow&program=${program.program_id}`}>{program.program_name}</Link>: {program.factors.join('; ')}</li>)}</ul> : <p className={styles.empty}>Критичных факторов не обнаружено.</p>}</section>
  </div>;
}
