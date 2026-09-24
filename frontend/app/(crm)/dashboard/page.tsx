'use client';

import { useQuery } from '@tanstack/react-query';
import Education from '@atomaro/icons/24/culture/Education';
import Book from '@atomaro/icons/24/culture/Book';
import Group from '@atomaro/icons/24/business/Group';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import Attention from '@atomaro/icons/24/action/Attention';
import Time from '@atomaro/icons/24/alert/TimeStroke';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Checklist from '@atomaro/icons/24/action/Checklist';
import { dashboardQueryKey, getDashboardOverview, type DashboardOverview } from '@/shared/lib/dashboard-repository';
import { PageIntro } from '@/shared/ui/page-intro';
import { PageSkeleton } from '@/shared/ui/page-skeleton';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { KpiCard, type KpiTone } from '@/widgets/dashboard/kpi-card';
import { DashboardAnalytics } from '@/widgets/dashboard/dashboard-charts';
import styles from '@/widgets/dashboard/dashboard.module.css';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { formatDateTimeRu } from '@/shared/lib/formatters';

const numberFormatter = new Intl.NumberFormat('ru-RU');
const scoreFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function formatCount(value: number | null) {
  return value === null ? '—' : numberFormatter.format(value);
}

function formatScore(value: number | null) {
  return value === null ? '—' : `${scoreFormatter.format(value)}%`;
}

interface KpiDefinition {
  title: string;
  caption: string;
  tone: KpiTone;
  icon: typeof Education;
  href?: string;
  ariaLabel?: string;
  value: (overview: DashboardOverview) => string;
  tooltip?: (overview: DashboardOverview) => string;
}

const kpiDefinitions: KpiDefinition[] = [
  { title: 'Вузы', caption: 'в реестре', tone: 'brand', icon: Education, value: (overview) => formatCount(overview.universitiesTotal) },
  { title: 'Средний Health Score', caption: 'среднее по вузам', tone: 'brand', icon: StatisticsBoard, value: (overview) => formatScore(overview.averageHealthScore) },
  { title: 'Красные вузы', caption: 'нуждаются во внимании', tone: 'danger', icon: Attention, href: '/universities?health_status=red', ariaLabel: 'Перейти к красным вузам', value: (overview) => formatCount(overview.redUniversities) },
  { title: 'Просроченные этапы', caption: 'требуют контроля', tone: 'danger', icon: Time, href: '/workflows?overdue=true', ariaLabel: 'Перейти к просроченным этапам workflow', value: (overview) => formatCount(overview.overdueStages) },
  { title: 'Истекающие лицензии', caption: 'до истечения 30 дней', tone: 'warning', icon: DocumentText, value: (overview) => formatCount(overview.expiringLicenses) },
  { title: 'Активные программы', caption: 'запущены', tone: 'orange', icon: Book, value: (overview) => formatCount(overview.activePrograms) },
  { title: 'Преподаватели к повышению', caption: 'требуют внимания', tone: 'warning', icon: Group, value: (overview) => formatCount(overview.teachersNeedUpgrade) },
  {
    title: 'Заявки с сайта за 7 дней',
    caption: 'новые заявки',
    tone: 'orange',
    icon: Checklist,
    href: '/universities',
    ariaLabel: 'Открыть список ВУЗов с заявками с сайта',
    value: (overview) => formatCount(overview.websiteApplications7d),
    tooltip: (overview) => `Источник: сайт\nСинхронизировано: ${overview.websiteSyncedAt ? formatDateTimeRu(overview.websiteSyncedAt) : 'недоступно'}`,
  },
  {
    title: 'Обучающиеся в LMS',
    caption: 'активные записи',
    tone: 'brand',
    icon: Group,
    href: '/universities',
    ariaLabel: 'Открыть список ВУЗов с данными LMS',
    value: (overview) => formatCount(overview.lmsStudents),
    tooltip: (overview) => `Источник: LMS\nСинхронизировано: ${overview.lmsSyncedAt ? formatDateTimeRu(overview.lmsSyncedAt) : 'недоступно'}`,
  },
];

export default function DashboardPage() {
  const overviewQuery = useQuery({
    queryKey: dashboardQueryKey,
    queryFn: getDashboardOverview,
    staleTime: 30_000,
  });

  if (overviewQuery.isPending) {
    return <PageSkeleton cardCount={9} variant="dashboard" />;
  }

  if (overviewQuery.isError || !overviewQuery.data) {
    return <RouteErrorState onRetry={() => void overviewQuery.refetch()} />;
  }

  return (
    <div className={styles.page}>
      <PageIntro title="Обзор" description="Ключевые показатели состояния образовательной сети и операционных задач команды." eyebrow="Исполнительный обзор" />
      <section className={styles.section} aria-labelledby="dashboard-kpi-title" data-testid="dashboard-kpi">
        <h2 className={styles.sectionTitle} id="dashboard-kpi-title">Ключевые показатели</h2>
        <div className={styles.grid}>
          {kpiDefinitions.map((definition) => {
            const card = <KpiCard
                ariaLabel={definition.ariaLabel}
                caption={definition.caption}
                href={definition.href}
                icon={definition.icon}
                key={definition.title}
                title={definition.title}
                tone={definition.tone}
                value={definition.value(overviewQuery.data)}
              />;
            return definition.tooltip
              ? <div className={styles.kpiTooltip} key={definition.title}><Tooltip content={<span style={{ whiteSpace: 'pre-line' }}>{definition.tooltip(overviewQuery.data)}</span>}>{card}</Tooltip></div>
              : card;
          })}
        </div>
      </section>
      <DashboardAnalytics />
    </div>
  );
}
